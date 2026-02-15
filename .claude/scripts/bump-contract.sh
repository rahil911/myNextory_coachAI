#!/usr/bin/env bash
# bump-contract.sh -- Bump contract version for a breaking change
#
# Usage:
#   bump-contract.sh <contract_file> <major|minor|patch> --reason "Added variant_sku column"
#
# Examples:
#   bump-contract.sh .claude/contracts/db-to-api-products.contract.json minor --reason "Added variant_sku"
#   bump-contract.sh .claude/contracts/api-to-ui-products.contract.json major --reason "Renamed id to product_id"
set -euo pipefail

CONTRACT_FILE="${1:?Usage: bump-contract.sh <contract_file> <major|minor|patch> --reason \"...\"}"
BUMP_TYPE="${2:?Missing bump type: major, minor, or patch}"
shift 2

REASON=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reason) REASON="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [ -z "$REASON" ]; then
  echo "Error: --reason is required for contract bumps" >&2
  exit 1
fi

if [ ! -f "$CONTRACT_FILE" ]; then
  echo "Error: Contract file not found: $CONTRACT_FILE" >&2
  exit 1
fi

PYTHON=""
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null; then
  PYTHON="python"
else
  echo "Error: Python 3 required" >&2
  exit 1
fi

# Bump version and archive old schema
$PYTHON << PYEOF > "${CONTRACT_FILE}.tmp"
import json
from datetime import datetime, timezone

with open("$CONTRACT_FILE") as f:
    contract = json.load(f)

old_version = contract["version"]
parts = old_version.split(".")
major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

bump_type = "$BUMP_TYPE"
if bump_type == "major":
    major += 1
    minor = 0
    patch = 0
elif bump_type == "minor":
    minor += 1
    patch = 0
elif bump_type == "patch":
    patch += 1
else:
    raise ValueError(f"Invalid bump type: {bump_type}")

new_version = f"{major}.{minor}.{patch}"

# Archive previous version
if "previous_versions" not in contract:
    contract["previous_versions"] = []

contract["previous_versions"].append({
    "version": old_version,
    "deprecated_at": datetime.now(timezone.utc).isoformat(),
    "migration_notes": "$REASON"
})

contract["version"] = new_version

# Update metadata
if "metadata" not in contract:
    contract["metadata"] = {}
contract["metadata"]["last_validated"] = datetime.now(timezone.utc).isoformat()

print(json.dumps(contract, indent=2))
PYEOF

mv "${CONTRACT_FILE}.tmp" "$CONTRACT_FILE"

echo "Contract bumped: $old_version -> $(python3 -c "import json; print(json.load(open('$CONTRACT_FILE'))['version'])")"

# Create notification beads for consumers
if command -v bd &>/dev/null; then
  CONTRACT_ID="$($PYTHON -c "import json; print(json.load(open('$CONTRACT_FILE'))['contract_id'])")"
  CONSUMERS="$($PYTHON -c "import json; [print(c['agent_id']) for c in json.load(open('$CONTRACT_FILE'))['consumers']]")"

  while IFS= read -r consumer; do
    if [ -n "$consumer" ]; then
      bd create "CONTRACT UPDATED: $CONTRACT_ID v$(python3 -c "import json; print(json.load(open('$CONTRACT_FILE'))['version'])") -- $consumer review required. Reason: $REASON" \
        --priority 1 2>/dev/null || true
      echo "Notification bead created for: $consumer"
    fi
  done <<< "$CONSUMERS"
fi

echo ""
echo "Next steps:"
echo "  1. Update the schema in $CONTRACT_FILE to reflect the new interface"
echo "  2. Re-extract: python3 scripts/extract-schema.py --language ... --method ... --target ... --file ..."
echo "  3. Run validation: bash scripts/validate-contracts.sh"
echo "  4. Commit the updated contract file"
