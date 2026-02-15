#!/usr/bin/env bash
# generate-contract.sh -- Generate a draft contract between two agents
#
# Usage:
#   generate-contract.sh <producer_agent> <consumer_agent> [--boundary-type TYPE] [--output FILE]
#
# Examples:
#   generate-contract.sh db-agent api-agent --boundary-type db_schema
#   generate-contract.sh api-agent ui-agent --boundary-type api_response --output .claude/contracts/api-to-ui.contract.json
#
# The script:
# 1. Queries the Ownership KG for DEPENDS_ON edges between the two agents
# 2. Identifies boundary files (producer's outputs that consumer reads)
# 3. Attempts to extract schema from producer files
# 4. Generates a draft contract.json
set -euo pipefail

PRODUCER="${1:?Usage: generate-contract.sh <producer_agent> <consumer_agent> [--boundary-type TYPE]}"
CONSUMER="${2:?Missing consumer agent}"
shift 2

BOUNDARY_TYPE="api_response"
OUTPUT=""
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --boundary-type) BOUNDARY_TYPE="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [ -z "$OUTPUT" ]; then
  OUTPUT="$PROJECT_ROOT/.claude/contracts/${PRODUCER}-to-${CONSUMER}.contract.json"
fi

# Find Python
PYTHON=""
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null; then
  PYTHON="python"
else
  echo "Error: Python 3 required" >&2
  exit 1
fi

EXTRACT_SCRIPT="$PROJECT_ROOT/.claude/scripts/extract-schema.py"

echo "Generating contract: $PRODUCER -> $CONSUMER"
echo "Boundary type: $BOUNDARY_TYPE"
echo ""

# ── Step 1: Discover boundary files ──────────────────────────────────────────
# Attempt to find files owned by each agent.
# Strategy: Check if ownership KG MCP is available, else use heuristics.

discover_files() {
  local agent="$1"
  local role="$2"  # producer or consumer

  # Heuristic: look for conventional directory patterns
  local patterns=()
  case "$agent" in
    *db*|*data*)
      patterns=("dbt/models/**/*.sql" "migrations/**/*.sql" "db/**/*.sql")
      ;;
    *api*|*backend*)
      patterns=("backend/**/*.py" "src/api/**/*.py" "api/**/*.py" "src/**/*.py")
      ;;
    *ui*|*frontend*)
      patterns=("ui/src/**/*.ts" "ui/src/**/*.tsx" "frontend/src/**/*.ts" "frontend/src/**/*.tsx")
      ;;
    *)
      patterns=("src/**/*" "lib/**/*")
      ;;
  esac

  for pattern in "${patterns[@]}"; do
    # Use find with globbing
    local found
    found="$(cd "$PROJECT_ROOT" && find . -path "./$pattern" -type f 2>/dev/null | head -20 | sed 's|^\./||')" || true
    if [ -n "$found" ]; then
      echo "$found"
    fi
  done
}

echo "Discovering producer files ($PRODUCER)..."
PRODUCER_FILES="$(discover_files "$PRODUCER" producer)"
if [ -z "$PRODUCER_FILES" ]; then
  echo "  No files found for producer '$PRODUCER'. You will need to fill in files manually."
  PRODUCER_FILES=""
fi

echo "Discovering consumer files ($CONSUMER)..."
CONSUMER_FILES="$(discover_files "$CONSUMER" consumer)"
if [ -z "$CONSUMER_FILES" ]; then
  echo "  No files found for consumer '$CONSUMER'. You will need to fill in files manually."
  CONSUMER_FILES=""
fi

# ── Step 2: Detect extraction method ─────────────────────────────────────────

detect_extraction() {
  local first_file="$1"
  if [ -z "$first_file" ]; then
    echo "unknown unknown unknown"
    return
  fi

  case "$first_file" in
    *.py)
      # Look for Pydantic models
      if grep -q "BaseModel\|BaseSchema" "$PROJECT_ROOT/$first_file" 2>/dev/null; then
        # Find the first class name
        local class_name
        class_name="$(grep -m1 "class \w\+.*BaseModel\|class \w\+.*BaseSchema" "$PROJECT_ROOT/$first_file" 2>/dev/null | sed 's/class \(\w\+\).*/\1/')" || true
        echo "python pydantic_model ${class_name:-UnknownModel}"
      else
        # Look for function signatures
        local func_name
        func_name="$(grep -m1 "def \w\+" "$PROJECT_ROOT/$first_file" 2>/dev/null | sed 's/.*def \(\w\+\).*/\1/')" || true
        echo "python function_signature ${func_name:-unknown}"
      fi
      ;;
    *.ts|*.tsx)
      # Look for interface or type
      local iface_name
      iface_name="$(grep -m1 "interface \w\+\|type \w\+ =" "$PROJECT_ROOT/$first_file" 2>/dev/null | sed 's/.*\(interface\|type\) \(\w\+\).*/\2/')" || true
      echo "typescript typescript_interface ${iface_name:-UnknownInterface}"
      ;;
    *.sql)
      echo "sql sql_table UNKNOWN_TABLE"
      ;;
    *)
      echo "unknown unknown unknown"
      ;;
  esac
}

FIRST_PRODUCER_FILE="$(echo "$PRODUCER_FILES" | head -1)"
read -r LANG METHOD TARGET <<< "$(detect_extraction "$FIRST_PRODUCER_FILE")"

echo ""
echo "Detected extraction: language=$LANG, method=$METHOD, target=$TARGET"

# ── Step 3: Attempt schema extraction ────────────────────────────────────────

EXTRACTED_SCHEMA='{}'
if [ -n "$FIRST_PRODUCER_FILE" ] && [ "$LANG" != "unknown" ] && [ -f "$EXTRACT_SCRIPT" ]; then
  echo "Extracting schema from $FIRST_PRODUCER_FILE..."
  EXTRACTED_SCHEMA="$($PYTHON "$EXTRACT_SCRIPT" \
    --language "$LANG" \
    --method "$METHOD" \
    --target "$TARGET" \
    --file "$PROJECT_ROOT/$FIRST_PRODUCER_FILE" \
    --pretty 2>&1)" || {
    echo "  Warning: Extraction failed. Using empty schema."
    EXTRACTED_SCHEMA='{}'
  }
fi

# ── Step 4: Build contract JSON ──────────────────────────────────────────────

# Convert file lists to JSON arrays
producer_files_json="$($PYTHON -c "
import json
files = '''$PRODUCER_FILES'''.strip().split('\n')
files = [f for f in files if f]
print(json.dumps(files[:5]))  # Limit to first 5
")"

consumer_files_json="$($PYTHON -c "
import json
files = '''$CONSUMER_FILES'''.strip().split('\n')
files = [f for f in files if f]
print(json.dumps(files[:5]))  # Limit to first 5
")"

CONTRACT_ID="${PRODUCER}-to-${CONSUMER}"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$(dirname "$OUTPUT")"

$PYTHON << PYEOF > "$OUTPUT"
import json
from datetime import datetime

contract = {
    "contract_id": "$CONTRACT_ID",
    "version": "1.0.0",
    "producer": {
        "agent_id": "$PRODUCER",
        "files": json.loads('$producer_files_json'),
        "extraction": {
            "language": "$LANG",
            "method": "$METHOD",
            "target": "$TARGET"
        }
    },
    "consumers": [
        {
            "agent_id": "$CONSUMER",
            "files": json.loads('$consumer_files_json'),
            "usage": "TODO: Describe how $CONSUMER uses $PRODUCER's output"
        }
    ],
    "boundary_type": "$BOUNDARY_TYPE",
    "schema": json.loads('''$EXTRACTED_SCHEMA'''),
    "strict": True,
    "validation_mode": "block_merge",
    "metadata": {
        "created_at": "$TIMESTAMP",
        "created_by": "generate-contract.sh",
        "description": "Auto-generated contract for $PRODUCER -> $CONSUMER boundary. Review and edit before committing."
    }
}

# Clean up extraction if unknown
if contract["producer"]["extraction"]["language"] == "unknown":
    del contract["producer"]["extraction"]

print(json.dumps(contract, indent=2))
PYEOF

echo ""
echo "Contract written to: $OUTPUT"
echo ""
echo "IMPORTANT: Review the generated contract before committing."
echo "  - Verify the schema matches your expectations"
echo "  - Fill in any TODO fields"
echo "  - Adjust strict/validation_mode as needed"
echo "  - Add additional consumer files if needed"
