#!/usr/bin/env bash
# =============================================================================
# check-ownership.sh -- Fast ownership boundary check (no LLM needed)
#
# Usage:
#   check-ownership.sh <agent-name> <worktree-path>
#
# Exit codes:
#   0  All changed files are owned by the agent (or unowned/shared)
#   1  Ownership violations found
# =============================================================================

set -euo pipefail

AGENT_NAME="${1:?Usage: check-ownership.sh <agent-name> <worktree-path>}"
WORKTREE_PATH="${2:?Usage: check-ownership.sh <agent-name> <worktree-path>}"
BAAP_ROOT="${BAAP_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
OWNERSHIP_KG="$BAAP_ROOT/.claude/kg/agent_graph_cache.json"

if [ ! -f "$OWNERSHIP_KG" ]; then
    echo "[ownership] WARNING: Ownership KG not found at $OWNERSHIP_KG" >&2
    echo "[ownership] Skipping ownership check."
    exit 0
fi

# Get changed files
cd "$WORKTREE_PATH"
MAIN_BRANCH="main"
MERGE_BASE="$(git merge-base HEAD "$MAIN_BRANCH" 2>/dev/null || git rev-parse "$MAIN_BRANCH")"
CHANGED_FILES="$(git diff "$MERGE_BASE"..HEAD --name-only)"
cd "$BAAP_ROOT"

if [ -z "$CHANGED_FILES" ]; then
    echo "[ownership] No changed files."
    exit 0
fi

# Check ownership for each file
VIOLATIONS=""
VIOLATION_COUNT=0

while IFS= read -r file; do
    [ -z "$file" ] && continue

    OWNER="$(python3 -c "
import json, sys, fnmatch

with open('$OWNERSHIP_KG') as f:
    kg = json.load(f)

file = '$file'
nodes = kg.get('nodes', [])

# Shared files that any agent can edit
shared_patterns = [
    'CLAUDE.md',
    '.claude/kg/*',
    'docs/*',
    '*.md',
    '.gitignore',
    'package.json',
    'package-lock.json',
    'requirements.txt',
]

# Check if file is shared
for pattern in shared_patterns:
    if fnmatch.fnmatch(file, pattern):
        print('SHARED')
        sys.exit(0)

# Find the owner
for node in nodes:
    if node.get('type') != 'agent':
        continue
    agent_id = node.get('id', '')
    owns = node.get('properties', {}).get('owns', [])
    for own_pattern in owns:
        if fnmatch.fnmatch(file, own_pattern) or file.startswith(own_pattern.rstrip('/*')):
            print(agent_id)
            sys.exit(0)

print('UNOWNED')
" 2>/dev/null || echo "UNOWNED")"

    if [ "$OWNER" != "$AGENT_NAME" ] && [ "$OWNER" != "SHARED" ] && [ "$OWNER" != "UNOWNED" ]; then
        VIOLATIONS="${VIOLATIONS}  - $file (owned by: $OWNER)\n"
        VIOLATION_COUNT=$((VIOLATION_COUNT + 1))
    fi
done <<< "$CHANGED_FILES"

if [ "$VIOLATION_COUNT" -gt 0 ]; then
    echo "[ownership] VIOLATIONS FOUND ($VIOLATION_COUNT):"
    echo -e "$VIOLATIONS"
    echo "[ownership] Agent '$AGENT_NAME' modified files owned by other agents."
    exit 1
else
    echo "[ownership] All changed files are owned by '$AGENT_NAME' or shared/unowned."
    exit 0
fi
