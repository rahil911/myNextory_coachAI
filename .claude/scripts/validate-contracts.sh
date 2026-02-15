#!/usr/bin/env bash
# validate-contracts.sh -- Validate agent outputs against cross-agent contracts
#
# Usage:
#   validate-contracts.sh [--agent AGENT_ID] [--contracts-dir DIR] [--project-root DIR]
#
# When --agent is specified, only contracts where that agent is the producer are checked.
# When omitted, ALL contracts are validated.
#
# Exit codes:
#   0 = all contracts valid
#   1 = one or more contracts broken
#   2 = error (missing files, bad config)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ID=""
CONTRACTS_DIR=""
PROJECT_ROOT=""
SKIP_NOTIFICATION=false

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent) AGENT_ID="$2"; shift 2 ;;
    --contracts-dir) CONTRACTS_DIR="$2"; shift 2 ;;
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    --skip-notification) SKIP_NOTIFICATION=true; shift ;;
    --help|-h)
      echo "Usage: validate-contracts.sh [--agent AGENT_ID] [--contracts-dir DIR] [--project-root DIR]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ── Defaults ──────────────────────────────────────────────────────────────────
if [ -z "$PROJECT_ROOT" ]; then
  PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

if [ -z "$CONTRACTS_DIR" ]; then
  CONTRACTS_DIR="$PROJECT_ROOT/.claude/contracts"
fi

EXTRACT_SCRIPT="$PROJECT_ROOT/.claude/scripts/extract-schema.py"

# Find Python
PYTHON=""
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null && python --version 2>&1 | grep -q "Python 3"; then
  PYTHON="python"
else
  echo "Error: Python 3 not found" >&2
  exit 2
fi

# ── Validation engine ─────────────────────────────────────────────────────────
FAILED=0
PASSED=0
SKIPPED=0
FAILURES=""

validate_contract() {
  local contract_file="$1"
  local contract_id
  contract_id="$($PYTHON -c "import json; print(json.load(open('$contract_file'))['contract_id'])")"

  # Check if we should skip this contract (agent filter)
  if [ -n "$AGENT_ID" ]; then
    local producer_agent
    producer_agent="$($PYTHON -c "import json; print(json.load(open('$contract_file'))['producer']['agent_id'])")"
    if [ "$producer_agent" != "$AGENT_ID" ]; then
      SKIPPED=$((SKIPPED + 1))
      return 0
    fi
  fi

  echo "  Validating: $contract_id"

  # Extract contract details
  local contract_json
  contract_json="$($PYTHON -c "
import json, sys
c = json.load(open('$contract_file'))
print(json.dumps({
    'contract_id': c['contract_id'],
    'version': c['version'],
    'language': c['producer'].get('extraction', {}).get('language', ''),
    'method': c['producer'].get('extraction', {}).get('method', ''),
    'target': c['producer'].get('extraction', {}).get('target', ''),
    'files': c['producer'].get('files', []),
    'schema': c['schema'],
    'strict': c.get('strict', True),
    'validation_mode': c.get('validation_mode', 'block_merge'),
    'consumers': [{'agent_id': cons['agent_id']} for cons in c.get('consumers', [])],
}))
")"

  local language method target strict validation_mode
  language="$($PYTHON -c "import json; print(json.loads('$contract_json'.replace(\"'\", \"\"))['language'])" 2>/dev/null || echo "")"

  # If no extraction config, skip (manually maintained contract)
  if [ -z "$language" ] || [ "$language" = "" ]; then
    echo "    Skipped (no extraction config -- manually maintained)"
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi

  # Use Python for reliable JSON parsing
  local details
  details="$($PYTHON << 'PYEOF'
import json, sys, os

contract_file = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CONTRACT_FILE", "")
c = json.load(open(contract_file))

extraction = c["producer"].get("extraction", {})
print(extraction.get("language", ""))
print(extraction.get("method", ""))
print(extraction.get("target", ""))
print(json.dumps(c["producer"].get("files", [])))
print(json.dumps(c["schema"]))
print(str(c.get("strict", True)))
print(c.get("validation_mode", "block_merge"))
print(json.dumps([cons["agent_id"] for cons in c.get("consumers", [])]))
PYEOF
  )" 2>/dev/null || true

  # Fallback: parse directly with Python
  local extracted_schema=""
  local found_source=false

  # Find the first existing source file
  local source_files
  source_files="$($PYTHON -c "import json; [print(f) for f in json.load(open('$contract_file'))['producer']['files']]")"

  local source_file=""
  while IFS= read -r f; do
    local full_path="$PROJECT_ROOT/$f"
    if [ -f "$full_path" ]; then
      source_file="$full_path"
      found_source=true
      break
    fi
  done <<< "$source_files"

  if [ "$found_source" = false ]; then
    echo "    WARNING: No producer source files found -- cannot re-extract schema"
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi

  # Re-extract schema from current source
  local lang meth tgt
  lang="$($PYTHON -c "import json; print(json.load(open('$contract_file'))['producer']['extraction']['language'])")"
  meth="$($PYTHON -c "import json; print(json.load(open('$contract_file'))['producer']['extraction']['method'])")"
  tgt="$($PYTHON -c "import json; print(json.load(open('$contract_file'))['producer']['extraction']['target'])")"

  extracted_schema="$($PYTHON "$EXTRACT_SCRIPT" --language "$lang" --method "$meth" --target "$tgt" --file "$source_file" 2>&1)" || {
    echo "    ERROR: Schema extraction failed: $extracted_schema"
    FAILED=$((FAILED + 1))
    FAILURES="$FAILURES\n  - $contract_id: extraction failed"
    return 1
  }

  # Validate: check that contracted schema is a subset of extracted schema
  # (every required field in the contract must exist in the extracted schema)
  local validation_result
  validation_result="$($PYTHON << PYEOF
import json, sys

contracted = json.loads('''$(echo "$($PYTHON -c "import json; print(json.dumps(json.load(open('$contract_file'))['schema']))")")''')
extracted = json.loads('''$extracted_schema''')
strict = $(echo "$($PYTHON -c "import json; print('True' if json.load(open('$contract_file')).get('strict', True) else 'False')")")

errors = []

# Check required fields exist in extracted
contracted_required = set(contracted.get("required", []))
extracted_props = set(extracted.get("properties", {}).keys())
contracted_props = set(contracted.get("properties", {}).keys())

missing_required = contracted_required - extracted_props
if missing_required:
    errors.append(f"Missing required fields in source: {sorted(missing_required)}")

# Check that contracted properties exist in extracted (if strict)
if strict:
    missing_props = contracted_props - extracted_props
    if missing_props:
        errors.append(f"Missing properties in source: {sorted(missing_props)}")

# Check type compatibility for fields present in both
for field in contracted_props & extracted_props:
    c_type = contracted["properties"][field].get("type")
    e_type = extracted["properties"][field].get("type")

    if c_type and e_type:
        # Normalize to sets for comparison
        c_types = set(c_type) if isinstance(c_type, list) else {c_type}
        e_types = set(e_type) if isinstance(e_type, list) else {e_type}

        # Extracted types should be a superset of (or equal to) contracted types
        if not c_types.issubset(e_types):
            errors.append(f"Type mismatch for '{field}': contract={c_type}, source={e_type}")

if errors:
    print("FAIL")
    for e in errors:
        print(f"  {e}")
else:
    print("PASS")
PYEOF
  )" || {
    echo "    ERROR: Validation script failed"
    FAILED=$((FAILED + 1))
    FAILURES="$FAILURES\n  - $contract_id: validation script error"
    return 1
  }

  local status
  status="$(echo "$validation_result" | head -1)"

  if [ "$status" = "PASS" ]; then
    echo "    PASS"
    PASSED=$((PASSED + 1))
  else
    echo "    FAIL"
    echo "$validation_result" | tail -n +2 | while IFS= read -r line; do
      echo "      $line"
    done

    local val_mode
    val_mode="$($PYTHON -c "import json; print(json.load(open('$contract_file')).get('validation_mode', 'block_merge'))")"

    FAILED=$((FAILED + 1))
    FAILURES="$FAILURES\n  - $contract_id: schema mismatch"

    # Create notification beads for consumers
    if [ "$SKIP_NOTIFICATION" = false ] && command -v bd &>/dev/null; then
      local consumers
      consumers="$($PYTHON -c "import json; [print(c['agent_id']) for c in json.load(open('$contract_file'))['consumers']]")"
      while IFS= read -r consumer; do
        if [ -n "$consumer" ]; then
          bd create "CONTRACT BROKEN: $contract_id -- $consumer must update" \
            --priority 1 2>/dev/null || true
          echo "    Bead created for consumer: $consumer"
        fi
      done <<< "$consumers"
    fi

    if [ "$val_mode" = "warn_only" ]; then
      echo "    (validation_mode=warn_only -- not blocking merge)"
      FAILED=$((FAILED - 1))  # Don't count as failure for exit code
      PASSED=$((PASSED + 1))
    fi
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
echo "Contract Validation"
echo "==================="
echo "Project: $PROJECT_ROOT"
echo "Contracts: $CONTRACTS_DIR"
[ -n "$AGENT_ID" ] && echo "Agent filter: $AGENT_ID"
echo ""

if [ ! -d "$CONTRACTS_DIR" ]; then
  echo "No contracts directory found at $CONTRACTS_DIR -- nothing to validate."
  exit 0
fi

contract_files=("$CONTRACTS_DIR"/*.contract.json)
if [ ! -f "${contract_files[0]}" ]; then
  echo "No contract files found in $CONTRACTS_DIR"
  exit 0
fi

for contract_file in "${contract_files[@]}"; do
  if [ -f "$contract_file" ]; then
    validate_contract "$contract_file" || true
  fi
done

echo ""
echo "Results: $PASSED passed, $FAILED failed, $SKIPPED skipped"

if [ $FAILED -gt 0 ]; then
  echo ""
  echo "FAILURES:"
  echo -e "$FAILURES"
  echo ""
  echo "To bypass: cleanup.sh <agent> merge --skip-contracts"
  exit 1
fi

exit 0
