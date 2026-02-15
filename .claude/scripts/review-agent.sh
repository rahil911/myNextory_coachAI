#!/usr/bin/env bash
# =============================================================================
# review-agent.sh -- Spawn a review agent to evaluate a worktree diff
#
# Usage:
#   review-agent.sh <agent-name> <worktree-path> [--fast]
#
# Arguments:
#   agent-name     Name of the agent whose work is being reviewed
#   worktree-path  Path to the agent's git worktree
#   --fast         Force fast-path (Haiku) review regardless of diff size
#
# Exit codes:
#   0  APPROVED     -- merge can proceed
#   1  CHANGES_REQUESTED -- merge blocked, fix bead created
#   2  REJECTED     -- merge blocked, escalated to human
#   3  ERROR        -- review failed (infrastructure), merge blocked
#
# Environment:
#   BAAP_ROOT       Project root (default: git rev-parse --show-toplevel)
#   REVIEW_TIMEOUT  Max seconds for review (default: 120)
#   FAST_THRESHOLD_FILES  Max files for fast-path (default: 2)
#   FAST_THRESHOLD_LINES  Max lines for fast-path (default: 50)
#   SKIP_REVIEW     Set to "true" to skip review entirely (for orchestrator)
# =============================================================================

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Arguments
# ─────────────────────────────────────────────────────────────────────────────
AGENT_NAME="${1:?Usage: review-agent.sh <agent-name> <worktree-path> [--fast]}"
WORKTREE_PATH="${2:?Usage: review-agent.sh <agent-name> <worktree-path> [--fast]}"
FORCE_FAST="${3:-}"

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
BAAP_ROOT="${BAAP_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
REVIEW_TIMEOUT="${REVIEW_TIMEOUT:-120}"
FAST_THRESHOLD_FILES="${FAST_THRESHOLD_FILES:-2}"
FAST_THRESHOLD_LINES="${FAST_THRESHOLD_LINES:-50}"
SKIP_REVIEW="${SKIP_REVIEW:-false}"

REVIEW_PROMPT_TEMPLATE="$BAAP_ROOT/.claude/scripts/review-prompt.md"
REVIEW_VERDICT_SCRIPT="$BAAP_ROOT/.claude/scripts/review-verdict.sh"
REVIEW_OUTPUT_DIR="$BAAP_ROOT/.claude/agents/review-agent/reviews"
OWNERSHIP_KG="$BAAP_ROOT/.claude/kg/agent_graph_cache.json"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
REVIEW_ID="review-${AGENT_NAME}-${TIMESTAMP}"
REVIEW_OUTPUT_FILE="$REVIEW_OUTPUT_DIR/${REVIEW_ID}.json"

# Source project-specific config if it exists
REVIEW_CONFIG="$BAAP_ROOT/.claude/agents/review-agent/config.sh"
if [ -f "$REVIEW_CONFIG" ]; then
    # shellcheck source=/dev/null
    source "$REVIEW_CONFIG"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Skip review check
# ─────────────────────────────────────────────────────────────────────────────
if [ "$SKIP_REVIEW" = "true" ]; then
    echo "[review-agent] Skipping review (SKIP_REVIEW=true)"
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# Validate inputs
# ─────────────────────────────────────────────────────────────────────────────
if [ ! -d "$WORKTREE_PATH" ]; then
    echo "[review-agent] ERROR: Worktree not found: $WORKTREE_PATH" >&2
    exit 3
fi

if [ ! -f "$REVIEW_PROMPT_TEMPLATE" ]; then
    echo "[review-agent] ERROR: Review prompt template not found: $REVIEW_PROMPT_TEMPLATE" >&2
    exit 3
fi

mkdir -p "$REVIEW_OUTPUT_DIR"

# ─────────────────────────────────────────────────────────────────────────────
# Compute the diff
# ─────────────────────────────────────────────────────────────────────────────
echo "[review-agent] Computing diff for agent '$AGENT_NAME' in $WORKTREE_PATH..."

# Get the merge base (where the worktree branched from main)
MAIN_BRANCH="main"
cd "$WORKTREE_PATH"
MERGE_BASE="$(git merge-base HEAD "$MAIN_BRANCH" 2>/dev/null || git rev-parse "$MAIN_BRANCH")"
DIFF_CONTENT="$(git diff "$MERGE_BASE"..HEAD)"
DIFF_STAT="$(git diff "$MERGE_BASE"..HEAD --stat)"
DIFF_NUMSTAT="$(git diff "$MERGE_BASE"..HEAD --numstat)"

# Parse diff statistics
FILES_CHANGED="$(echo "$DIFF_NUMSTAT" | wc -l | tr -d ' ')"
LINES_ADDED="$(echo "$DIFF_NUMSTAT" | awk '{sum += $1} END {print sum+0}')"
LINES_REMOVED="$(echo "$DIFF_NUMSTAT" | awk '{sum += $2} END {print sum+0}')"
TOTAL_LINES=$((LINES_ADDED + LINES_REMOVED))

# List changed files for ownership check
CHANGED_FILES="$(git diff "$MERGE_BASE"..HEAD --name-only)"

cd "$BAAP_ROOT"

echo "[review-agent] Diff: $FILES_CHANGED files, +$LINES_ADDED -$LINES_REMOVED ($TOTAL_LINES total)"

# ─────────────────────────────────────────────────────────────────────────────
# Empty diff check
# ─────────────────────────────────────────────────────────────────────────────
if [ -z "$DIFF_CONTENT" ]; then
    echo "[review-agent] No changes detected. Nothing to review."
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# Check if all changed files should skip review
# ─────────────────────────────────────────────────────────────────────────────
if type should_skip_review &>/dev/null && should_skip_review "$CHANGED_FILES"; then
    echo "[review-agent] All changed files match skip patterns. Skipping review."
    exit 0
fi

# Check if this is an infrastructure-only change
if type is_infrastructure_change &>/dev/null && is_infrastructure_change "$CHANGED_FILES"; then
    echo "[review-agent] Infrastructure-only change detected."
    if [ "$SKIP_REVIEW" != "force" ]; then
        echo "[review-agent] Skipping review for infrastructure paths."
        exit 0
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Determine review tier (fast vs full)
# ─────────────────────────────────────────────────────────────────────────────
if [ "$FORCE_FAST" = "--fast" ] || \
   { [ "$FILES_CHANGED" -le "$FAST_THRESHOLD_FILES" ] && [ "$TOTAL_LINES" -le "$FAST_THRESHOLD_LINES" ]; }; then
    REVIEW_TIER="fast"
    REVIEW_MODEL="haiku"
    REVIEW_MAX_TOKENS="4096"
    echo "[review-agent] Fast-path review (Haiku): $FILES_CHANGED files, $TOTAL_LINES lines"
else
    REVIEW_TIER="full"
    REVIEW_MODEL="opus"
    REVIEW_MAX_TOKENS="16384"
    echo "[review-agent] Full review (Opus): $FILES_CHANGED files, $TOTAL_LINES lines"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Extract bead information
# ─────────────────────────────────────────────────────────────────────────────
# The agent's bead ID should be in the worktree's branch name or a marker file
BRANCH_NAME="$(cd "$WORKTREE_PATH" && git rev-parse --abbrev-ref HEAD)"
BEAD_ID=""
BEAD_TITLE=""
ACCEPTANCE_CRITERIA="Not specified in bead."

# Try to extract bead ID from branch name (convention: agent-name/bead-id)
if [[ "$BRANCH_NAME" =~ /([A-Za-z0-9_-]+)$ ]]; then
    BEAD_ID="${BASH_REMATCH[1]}"
fi

# Try to read bead info from the agent's work directory
BEAD_MARKER="$WORKTREE_PATH/.claude/agents/$AGENT_NAME/current_bead.json"
if [ -f "$BEAD_MARKER" ]; then
    BEAD_ID="$(jq -r '.id // empty' "$BEAD_MARKER" 2>/dev/null || echo "$BEAD_ID")"
    BEAD_TITLE="$(jq -r '.title // empty' "$BEAD_MARKER" 2>/dev/null || echo "")"
    ACCEPTANCE_CRITERIA="$(jq -r '.acceptance_criteria // "Not specified"' "$BEAD_MARKER" 2>/dev/null || echo "Not specified in bead.")"
fi

# Fallback: search beads for the agent's active work
if [ -z "$BEAD_ID" ] && command -v bd &>/dev/null; then
    BEAD_ID="$(bd list --status open --label "agent:$AGENT_NAME" --limit 1 --format json 2>/dev/null | jq -r '.[0].id // empty' 2>/dev/null || echo "")"
    if [ -n "$BEAD_ID" ]; then
        BEAD_TITLE="$(bd show "$BEAD_ID" --format json 2>/dev/null | jq -r '.title // empty' 2>/dev/null || echo "")"
    fi
fi

echo "[review-agent] Bead: ${BEAD_ID:-unknown} - ${BEAD_TITLE:-no title}"

# ─────────────────────────────────────────────────────────────────────────────
# Extract ownership information for changed files
# ─────────────────────────────────────────────────────────────────────────────
OWNERSHIP_ENTRIES="{}"
if [ -f "$OWNERSHIP_KG" ]; then
    # Build a JSON object mapping changed files to their owners
    OWNERSHIP_ENTRIES="$(python3 -c "
import json, sys

try:
    with open('$OWNERSHIP_KG') as f:
        kg = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    print('{}')
    sys.exit(0)

changed_files = '''$CHANGED_FILES'''.strip().split('\n')
ownership = {}

# Extract ownership mapping from KG
# KG structure: nodes[] with {id, type, properties: {owns: [files]}}
nodes = kg.get('nodes', [])
for node in nodes:
    if node.get('type') == 'agent':
        agent_id = node.get('id', '')
        owns = node.get('properties', {}).get('owns', [])
        for file_pattern in owns:
            for cf in changed_files:
                # Exact match or glob-style prefix match
                if cf == file_pattern or cf.startswith(file_pattern.rstrip('*').rstrip('/')):
                    ownership[cf] = agent_id

# Also check for files NOT in any ownership
for cf in changed_files:
    if cf and cf not in ownership:
        ownership[cf] = 'UNOWNED'

print(json.dumps(ownership, indent=2))
" 2>/dev/null || echo "{}")"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Generate repo file tree (top-level only, for context)
# ─────────────────────────────────────────────────────────────────────────────
REPO_FILE_TREE="$(cd "$BAAP_ROOT" && find . -maxdepth 2 -not -path './.git/*' -not -path './node_modules/*' -not -path './.venv/*' -not -path './ui/node_modules/*' -not -path './.next/*' | sort | head -100)"

# ─────────────────────────────────────────────────────────────────────────────
# Build the review prompt from template
# ─────────────────────────────────────────────────────────────────────────────
REVIEW_PROMPT="$(cat "$REVIEW_PROMPT_TEMPLATE")"

# Perform template substitutions
# Using Python for reliable multi-line string substitution
REVIEW_PROMPT="$(python3 -c "
import sys

template = sys.stdin.read()
replacements = {
    '{{BEAD_ID}}': '''${BEAD_ID:-unknown}''',
    '{{BEAD_TITLE}}': '''${BEAD_TITLE:-No title available}''',
    '{{ACCEPTANCE_CRITERIA}}': '''${ACCEPTANCE_CRITERIA}''',
    '{{AGENT_NAME}}': '''${AGENT_NAME}''',
    '{{WORKTREE_PATH}}': '''${WORKTREE_PATH}''',
    '{{BRANCH_NAME}}': '''${BRANCH_NAME}''',
    '{{FILES_CHANGED}}': '''${FILES_CHANGED}''',
    '{{LINES_ADDED}}': '''${LINES_ADDED}''',
    '{{LINES_REMOVED}}': '''${LINES_REMOVED}''',
    '{{REVIEW_TIER}}': '''${REVIEW_TIER}''',
    '{{REPO_FILE_TREE}}': '''${REPO_FILE_TREE}''',
}

for key, value in replacements.items():
    template = template.replace(key, value)

print(template)
" <<< "$REVIEW_PROMPT")"

# Diff and ownership are substituted separately to handle special characters
REVIEW_PROMPT_FILE="$REVIEW_OUTPUT_DIR/${REVIEW_ID}-prompt.md"
python3 -c "
import sys, json

prompt = open('$REVIEW_OUTPUT_DIR/${REVIEW_ID}-prompt-base.md' if False else '/dev/stdin').read()

# Read diff from file to avoid shell escaping issues
diff_content = '''$(echo "$DIFF_CONTENT" | head -5000)'''
ownership = '''$OWNERSHIP_ENTRIES'''

prompt = prompt.replace('{{DIFF_CONTENT}}', diff_content)
prompt = prompt.replace('{{OWNERSHIP_ENTRIES}}', ownership)

with open('$REVIEW_PROMPT_FILE', 'w') as f:
    f.write(prompt)
" <<< "$REVIEW_PROMPT"

echo "[review-agent] Review prompt written to $REVIEW_PROMPT_FILE"

# ─────────────────────────────────────────────────────────────────────────────
# Spawn the review agent via Claude Code
# ─────────────────────────────────────────────────────────────────────────────
echo "[review-agent] Spawning review agent ($REVIEW_MODEL)..."

REVIEW_START="$(date +%s)"

# Run Claude Code in headless/pipe mode with the review prompt
# The agent reads the prompt file and produces structured output
REVIEW_RAW_OUTPUT="$(timeout "${REVIEW_TIMEOUT}s" claude \
    --model "$REVIEW_MODEL" \
    --print \
    --no-input \
    --max-tokens "$REVIEW_MAX_TOKENS" \
    --system-prompt "$(cat "$BAAP_ROOT/.claude/agents/review-agent/agent.md" | tail -n +8)" \
    --prompt "$(cat "$REVIEW_PROMPT_FILE")" \
    2>/dev/null)" || {
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq 124 ]; then
        echo "[review-agent] ERROR: Review timed out after ${REVIEW_TIMEOUT}s" >&2
        # On timeout, block the merge -- safety first
        echo '{"verdict":"CHANGES_REQUESTED","scores":{"correctness":5,"code_quality":5,"safety":5,"ownership_compliance":5,"schema_compatibility":5},"weighted_total":5.0,"findings":[{"severity":"high","dimension":"correctness","file":"","line":0,"description":"Review timed out. Manual review required.","suggestion":"Review the diff manually or increase REVIEW_TIMEOUT."}],"summary":"Review timed out after '${REVIEW_TIMEOUT}' seconds. Merge blocked pending manual review.","acceptance_criteria_met":false,"time_spent_seconds":'${REVIEW_TIMEOUT}'}' > "$REVIEW_OUTPUT_FILE"
        exit 1
    else
        echo "[review-agent] ERROR: Claude Code failed with exit code $EXIT_CODE" >&2
        exit 3
    fi
}

REVIEW_END="$(date +%s)"
REVIEW_DURATION=$((REVIEW_END - REVIEW_START))
echo "[review-agent] Review completed in ${REVIEW_DURATION}s"

# ─────────────────────────────────────────────────────────────────────────────
# Extract JSON verdict from review output
# ─────────────────────────────────────────────────────────────────────────────
# The reviewer outputs a JSON block -- extract it
REVIEW_JSON="$(echo "$REVIEW_RAW_OUTPUT" | python3 -c "
import sys, json, re

text = sys.stdin.read()

# Find the last JSON block in the output (reviewer puts it at the end)
# Match \`\`\`json ... \`\`\` blocks first
json_blocks = re.findall(r'\`\`\`json\s*\n(.*?)\n\s*\`\`\`', text, re.DOTALL)

if json_blocks:
    candidate = json_blocks[-1]
else:
    # Try to find raw JSON object
    # Look for the verdict JSON pattern
    matches = re.findall(r'(\{[^{}]*\"verdict\"[^{}]*\{.*?\}[^{}]*\})', text, re.DOTALL)
    if matches:
        candidate = matches[-1]
    else:
        # Last resort: find any JSON-like block
        matches = re.findall(r'\{[\s\S]*?\}(?=\s*$)', text)
        candidate = matches[-1] if matches else ''

if candidate:
    try:
        parsed = json.loads(candidate)
        # Validate required fields
        assert 'verdict' in parsed
        assert parsed['verdict'] in ('APPROVED', 'CHANGES_REQUESTED', 'REJECTED')
        print(json.dumps(parsed, indent=2))
    except (json.JSONDecodeError, AssertionError):
        # Malformed JSON -- treat as review failure
        print(json.dumps({
            'verdict': 'CHANGES_REQUESTED',
            'scores': {'correctness': 5, 'code_quality': 5, 'safety': 5, 'ownership_compliance': 5, 'schema_compatibility': 5},
            'weighted_total': 5.0,
            'findings': [{'severity': 'high', 'dimension': 'correctness', 'file': '', 'line': 0,
                          'description': 'Review agent produced malformed output. Manual review required.',
                          'suggestion': 'Check review-agent output at $REVIEW_OUTPUT_DIR/${REVIEW_ID}-raw.txt'}],
            'summary': 'Review agent output could not be parsed. Merge blocked pending manual review.',
            'acceptance_criteria_met': False,
            'time_spent_seconds': $REVIEW_DURATION
        }, indent=2))
else:
    print(json.dumps({
        'verdict': 'CHANGES_REQUESTED',
        'scores': {'correctness': 5, 'code_quality': 5, 'safety': 5, 'ownership_compliance': 5, 'schema_compatibility': 5},
        'weighted_total': 5.0,
        'findings': [{'severity': 'high', 'dimension': 'correctness', 'file': '', 'line': 0,
                      'description': 'Review agent produced no structured output. Manual review required.',
                      'suggestion': 'Check review-agent output at $REVIEW_OUTPUT_DIR/${REVIEW_ID}-raw.txt'}],
        'summary': 'No verdict JSON found in review output. Merge blocked pending manual review.',
        'acceptance_criteria_met': False,
        'time_spent_seconds': $REVIEW_DURATION
    }, indent=2))
" 2>/dev/null)"

# Save raw output for debugging
echo "$REVIEW_RAW_OUTPUT" > "$REVIEW_OUTPUT_DIR/${REVIEW_ID}-raw.txt"

# Save structured verdict
echo "$REVIEW_JSON" > "$REVIEW_OUTPUT_FILE"
echo "[review-agent] Verdict saved to $REVIEW_OUTPUT_FILE"

# ─────────────────────────────────────────────────────────────────────────────
# Process verdict
# ─────────────────────────────────────────────────────────────────────────────
VERDICT="$(echo "$REVIEW_JSON" | jq -r '.verdict')"
WEIGHTED_TOTAL="$(echo "$REVIEW_JSON" | jq -r '.weighted_total')"
FINDINGS_COUNT="$(echo "$REVIEW_JSON" | jq '.findings | length')"
CRITICAL_COUNT="$(echo "$REVIEW_JSON" | jq '[.findings[] | select(.severity == "critical")] | length')"
SUMMARY="$(echo "$REVIEW_JSON" | jq -r '.summary')"

echo ""
echo "============================================"
echo "  REVIEW VERDICT: $VERDICT"
echo "  Weighted Score: $WEIGHTED_TOTAL / 10.0"
echo "  Findings: $FINDINGS_COUNT ($CRITICAL_COUNT critical)"
echo "  Summary: $SUMMARY"
echo "============================================"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Create review bead
# ─────────────────────────────────────────────────────────────────────────────
if command -v bd &>/dev/null; then
    REVIEW_BEAD_TITLE="Review: ${AGENT_NAME} - ${VERDICT}"
    case "$VERDICT" in
        APPROVED)
            REVIEW_PRIORITY=3
            REVIEW_STATUS="closed"
            ;;
        CHANGES_REQUESTED)
            REVIEW_PRIORITY=1
            REVIEW_STATUS="open"
            ;;
        REJECTED)
            REVIEW_PRIORITY=0
            REVIEW_STATUS="open"
            ;;
        *)
            REVIEW_PRIORITY=1
            REVIEW_STATUS="open"
            ;;
    esac

    REVIEW_BEAD_ID="$(bd create "$REVIEW_BEAD_TITLE" \
        -p "$REVIEW_PRIORITY" \
        --label "type:review" \
        --label "agent:$AGENT_NAME" \
        --label "verdict:$VERDICT" \
        --label "score:$WEIGHTED_TOTAL" \
        2>/dev/null | grep -oE '[A-Za-z0-9_-]+' | head -1 || echo "")"

    if [ -n "$REVIEW_BEAD_ID" ] && [ -n "$BEAD_ID" ]; then
        # Link review bead to the original work bead
        bd dep add "$REVIEW_BEAD_ID" "$BEAD_ID" 2>/dev/null || true
    fi

    # If approved, close the review bead immediately
    if [ "$VERDICT" = "APPROVED" ] && [ -n "$REVIEW_BEAD_ID" ]; then
        bd close "$REVIEW_BEAD_ID" --reason "Review passed. Score: $WEIGHTED_TOTAL/10" 2>/dev/null || true
    fi

    echo "[review-agent] Review bead created: $REVIEW_BEAD_ID"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Handle CHANGES_REQUESTED -- create fix bead for original agent
# ─────────────────────────────────────────────────────────────────────────────
if [ "$VERDICT" = "CHANGES_REQUESTED" ]; then
    echo "[review-agent] Creating fix bead for agent '$AGENT_NAME'..."

    # Build fix description from findings
    FIX_DESCRIPTION="$(echo "$REVIEW_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
lines = ['## Review Findings (fix required)\n']
lines.append(f'Review score: {data[\"weighted_total\"]}/10.0\n')
for f in data.get('findings', []):
    sev = f.get('severity', 'info').upper()
    dim = f.get('dimension', 'unknown')
    file = f.get('file', '')
    line = f.get('line', 0)
    desc = f.get('description', '')
    sug = f.get('suggestion', '')
    loc = f'{file}:{line}' if file else 'general'
    lines.append(f'- [{sev}] ({dim}) {loc}: {desc}')
    if sug:
        lines.append(f'  Fix: {sug}')
print('\n'.join(lines))
")"

    if command -v bd &>/dev/null; then
        FIX_BEAD_ID="$(bd create "Fix review findings: $AGENT_NAME" \
            -p 1 \
            --label "type:fix" \
            --label "agent:$AGENT_NAME" \
            --label "source:review" \
            2>/dev/null | grep -oE '[A-Za-z0-9_-]+' | head -1 || echo "")"

        if [ -n "$FIX_BEAD_ID" ] && [ -n "$REVIEW_BEAD_ID" ]; then
            bd dep add "$FIX_BEAD_ID" "$REVIEW_BEAD_ID" 2>/dev/null || true
        fi

        echo "[review-agent] Fix bead created: $FIX_BEAD_ID"
        echo "[review-agent] Findings:"
        echo "$FIX_DESCRIPTION"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Handle REJECTED -- escalate to human
# ─────────────────────────────────────────────────────────────────────────────
if [ "$VERDICT" = "REJECTED" ]; then
    echo "[review-agent] REJECTED -- escalating to human review"
    echo "[review-agent] Critical findings require human decision before this code can merge."

    # Log the rejection details prominently
    echo ""
    echo "!!! MERGE BLOCKED: HUMAN REVIEW REQUIRED !!!"
    echo ""
    echo "Review output: $REVIEW_OUTPUT_FILE"
    echo "Raw output:    $REVIEW_OUTPUT_DIR/${REVIEW_ID}-raw.txt"
    echo ""
    echo "$REVIEW_JSON" | jq '.findings[] | select(.severity == "critical" or .severity == "high")' 2>/dev/null || true
    echo ""
fi

# ─────────────────────────────────────────────────────────────────────────────
# Return exit code based on verdict
# ─────────────────────────────────────────────────────────────────────────────
case "$VERDICT" in
    APPROVED)           exit 0 ;;
    CHANGES_REQUESTED)  exit 1 ;;
    REJECTED)           exit 2 ;;
    *)                  exit 3 ;;
esac
