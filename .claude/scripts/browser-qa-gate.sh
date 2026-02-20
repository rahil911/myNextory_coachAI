#!/usr/bin/env bash
# =============================================================================
# browser-qa-gate.sh -- Spawn bowser-qa-agent to validate UI after merge
#
# Usage:
#   browser-qa-gate.sh <agent-name> <worktree-path>
#
# Arguments:
#   agent-name     Name of the agent whose work is being validated
#   worktree-path  Path to the agent's git worktree
#
# Exit codes:
#   0  ALL_PASSED      -- all stories passed, merge proceeds
#   1  PARTIAL_FAILURE -- some stories failed, fix bead created
#   2  ALL_FAILED      -- all stories failed, fix bead created
#   3  ERROR           -- QA infrastructure failed (Playwright, dashboard)
#   4  SKIPPED         -- no UI files in diff, gate skipped
#
# Environment:
#   BAAP_ROOT          Project root (default: git rev-parse --show-toplevel)
#   QA_TIMEOUT         Max seconds for QA run (default: 180)
#   SKIP_BROWSER_QA    Set to "true" to skip entirely
#   QA_STORY_FILE      Override story file (default: ai_review/user_stories/tory-workspace.yaml)
#   DASHBOARD_URL      Dashboard URL (default: http://localhost:8002)
#   MAX_QA_RETRIES     Max retry rounds before escalation (default: 2)
# =============================================================================

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Arguments
# ─────────────────────────────────────────────────────────────────────────────
AGENT_NAME="${1:?Usage: browser-qa-gate.sh <agent-name> <worktree-path>}"
WORKTREE_PATH="${2:?Usage: browser-qa-gate.sh <agent-name> <worktree-path>}"

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
BAAP_ROOT="${BAAP_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
QA_TIMEOUT="${QA_TIMEOUT:-180}"
SKIP_BROWSER_QA="${SKIP_BROWSER_QA:-false}"
DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:8002}"
MAX_QA_RETRIES="${MAX_QA_RETRIES:-2}"
QA_STORY_FILE="${QA_STORY_FILE:-ai_review/user_stories/tory-workspace.yaml}"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
QA_SESSION_ID="qa-${AGENT_NAME}-${TIMESTAMP}"
SCREENSHOT_DIR="$BAAP_ROOT/screenshots/bowser-qa/${QA_SESSION_ID}"
RETRY_DIR="/tmp/baap-browser-qa"
QA_OUTPUT_DIR="$BAAP_ROOT/.claude/agents/bowser-qa-agent/reviews"

# ─────────────────────────────────────────────────────────────────────────────
# Skip check
# ─────────────────────────────────────────────────────────────────────────────
if [ "$SKIP_BROWSER_QA" = "true" ]; then
    echo "[browser-qa] Skipping browser QA (SKIP_BROWSER_QA=true)"
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# Validate inputs
# ─────────────────────────────────────────────────────────────────────────────
if [ ! -d "$WORKTREE_PATH" ]; then
    echo "[browser-qa] ERROR: Worktree not found: $WORKTREE_PATH" >&2
    exit 3
fi

# ─────────────────────────────────────────────────────────────────────────────
# Compute the diff — check for UI files
# ─────────────────────────────────────────────────────────────────────────────
echo "[browser-qa] Computing diff for agent '$AGENT_NAME' in $WORKTREE_PATH..."

MAIN_BRANCH="main"
cd "$WORKTREE_PATH"
MERGE_BASE="$(git merge-base HEAD "$MAIN_BRANCH" 2>/dev/null || git rev-parse "$MAIN_BRANCH")"
CHANGED_FILES="$(git diff --name-only "$MERGE_BASE"..HEAD)"

cd "$BAAP_ROOT"

if [ -z "$CHANGED_FILES" ]; then
    echo "[browser-qa] No changes detected. Skipping."
    exit 4
fi

# Check for UI-relevant files (.js, .css, .html)
UI_FILES="$(echo "$CHANGED_FILES" | grep -E '\.(js|css|html)$' || true)"

if [ -z "$UI_FILES" ]; then
    echo "[browser-qa] No UI files (.js/.css/.html) in diff. Skipping."
    exit 4
fi

UI_FILE_COUNT="$(echo "$UI_FILES" | wc -l | tr -d ' ')"
echo "[browser-qa] Found $UI_FILE_COUNT UI file(s) in diff:"
echo "$UI_FILES" | sed 's/^/  /'

# ─────────────────────────────────────────────────────────────────────────────
# Check story file exists
# ─────────────────────────────────────────────────────────────────────────────
STORY_PATH="$BAAP_ROOT/$QA_STORY_FILE"
if [ ! -f "$STORY_PATH" ]; then
    echo "[browser-qa] WARNING: Story file not found: $STORY_PATH"
    echo "[browser-qa] No stories to validate. Skipping."
    exit 4
fi

# ─────────────────────────────────────────────────────────────────────────────
# Ensure dashboard is running
# ─────────────────────────────────────────────────────────────────────────────
echo "[browser-qa] Checking dashboard at $DASHBOARD_URL..."

if ! curl -sf "$DASHBOARD_URL/" > /dev/null 2>&1; then
    echo "[browser-qa] Dashboard not responding. Attempting restart..."

    # Kill any stale uvicorn on port 8002
    STALE_PID="$(lsof -ti:8002 2>/dev/null || true)"
    if [ -n "$STALE_PID" ]; then
        echo "[browser-qa] Killing stale process on port 8002 (PID: $STALE_PID)"
        kill "$STALE_PID" 2>/dev/null || true
        sleep 1
    fi

    # Start dashboard using start-dashboard.sh in background
    DASHBOARD_SCRIPT="$BAAP_ROOT/.claude/scripts/start-dashboard.sh"
    if [ -x "$DASHBOARD_SCRIPT" ]; then
        echo "[browser-qa] Starting dashboard via start-dashboard.sh..."
        nohup bash "$DASHBOARD_SCRIPT" > /tmp/baap-dashboard-qa.log 2>&1 &
        DASHBOARD_PID=$!
        echo "[browser-qa] Dashboard PID: $DASHBOARD_PID"
    else
        # Fallback: start manually with .venv
        VENV="$BAAP_ROOT/.venv"
        if [ -f "$VENV/bin/activate" ]; then
            # shellcheck source=/dev/null
            source "$VENV/bin/activate"
        fi
        echo "[browser-qa] Starting dashboard manually..."
        nohup python3 -m uvicorn dashboard_api:app --host 0.0.0.0 --port 8002 --log-level warning \
            --app-dir "$BAAP_ROOT/.claude/scripts" > /tmp/baap-dashboard-qa.log 2>&1 &
        DASHBOARD_PID=$!
    fi

    # Wait for dashboard to come up (max 10 seconds)
    echo "[browser-qa] Waiting for dashboard to start..."
    for i in $(seq 1 10); do
        if curl -sf "$DASHBOARD_URL/" > /dev/null 2>&1; then
            echo "[browser-qa] Dashboard started (attempt $i)"
            break
        fi
        if [ "$i" -eq 10 ]; then
            echo "[browser-qa] ERROR: Dashboard failed to start after 10s" >&2
            echo "[browser-qa] Log: $(tail -5 /tmp/baap-dashboard-qa.log 2>/dev/null || echo 'no log')" >&2
            exit 3
        fi
        sleep 1
    done
else
    echo "[browser-qa] Dashboard is running."
fi

# ─────────────────────────────────────────────────────────────────────────────
# Check Playwright is available
# ─────────────────────────────────────────────────────────────────────────────
if ! command -v npx &>/dev/null; then
    echo "[browser-qa] ERROR: npx not found. Playwright requires Node.js." >&2
    exit 3
fi

# Quick check that playwright is installed
if ! npx playwright --version &>/dev/null 2>&1; then
    echo "[browser-qa] ERROR: Playwright not installed. Run: npx playwright install chromium" >&2
    exit 3
fi

# ─────────────────────────────────────────────────────────────────────────────
# Create output directories
# ─────────────────────────────────────────────────────────────────────────────
mkdir -p "$SCREENSHOT_DIR"
mkdir -p "$QA_OUTPUT_DIR"
mkdir -p "$RETRY_DIR"

# ─────────────────────────────────────────────────────────────────────────────
# Extract bead information (same pattern as review-agent.sh)
# ─────────────────────────────────────────────────────────────────────────────
BRANCH_NAME="$(cd "$WORKTREE_PATH" && git rev-parse --abbrev-ref HEAD)"
BEAD_ID=""

if [[ "$BRANCH_NAME" =~ /([A-Za-z0-9_-]+)$ ]]; then
    BEAD_ID="${BASH_REMATCH[1]}"
fi

BEAD_MARKER="$WORKTREE_PATH/.claude/agents/$AGENT_NAME/current_bead.json"
if [ -f "$BEAD_MARKER" ]; then
    BEAD_ID="$(jq -r '.id // empty' "$BEAD_MARKER" 2>/dev/null || echo "$BEAD_ID")"
fi

if [ -z "$BEAD_ID" ] && command -v bd &>/dev/null; then
    BEAD_ID="$(bd list --status open --label "agent:$AGENT_NAME" --limit 1 --format json 2>/dev/null | jq -r '.[0].id // empty' 2>/dev/null || echo "")"
fi

echo "[browser-qa] Bead: ${BEAD_ID:-unknown}"
echo "[browser-qa] Story file: $QA_STORY_FILE"

# ─────────────────────────────────────────────────────────────────────────────
# Spawn bowser-qa-agent via Claude Code
# ─────────────────────────────────────────────────────────────────────────────
echo "[browser-qa] Spawning bowser-qa-agent (sonnet)..."

QA_START="$(date +%s)"

AGENT_SPEC="$BAAP_ROOT/.claude/agents/bowser-qa-agent/agent.md"
SYSTEM_PROMPT=""
if [ -f "$AGENT_SPEC" ]; then
    SYSTEM_PROMPT="$(tail -n +17 "$AGENT_SPEC")"
fi

QA_PROMPT="Run all user stories from the file at $QA_STORY_FILE against $DASHBOARD_URL.

Session ID: $QA_SESSION_ID
Agent under test: $AGENT_NAME
Bead: ${BEAD_ID:-unknown}
Screenshot directory: $SCREENSHOT_DIR

UI files changed in this merge:
$UI_FILES

Instructions:
1. Read the YAML story file at $STORY_PATH
2. For each story, navigate to the URL, wait for conditions, take a screenshot, and check assertions
3. Save screenshots to $SCREENSHOT_DIR/
4. Output a single JSON verdict block (wrapped in \`\`\`json ... \`\`\`) with this structure:
{
  \"session_id\": \"$QA_SESSION_ID\",
  \"stories_total\": <N>,
  \"stories_passed\": <N>,
  \"stories_failed\": <N>,
  \"verdict\": \"ALL_PASSED\" | \"PARTIAL_FAILURE\" | \"ALL_FAILED\",
  \"results\": [ { \"story_id\": \"...\", \"title\": \"...\", \"status\": \"PASSED|FAILED\", \"screenshot\": \"...\", \"error\": \"...\" } ]
}

CRITICAL: Output the JSON verdict as your FINAL output, wrapped in a json code block."

QA_RAW_OUTPUT="$(timeout "${QA_TIMEOUT}s" claude \
    --model sonnet \
    --print \
    --no-input \
    --max-tokens 8000 \
    --system-prompt "$SYSTEM_PROMPT" \
    --prompt "$QA_PROMPT" \
    2>/dev/null)" || {
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq 124 ]; then
        echo "[browser-qa] ERROR: QA timed out after ${QA_TIMEOUT}s" >&2
        exit 3
    else
        echo "[browser-qa] ERROR: Claude Code failed with exit code $EXIT_CODE" >&2
        exit 3
    fi
}

QA_END="$(date +%s)"
QA_DURATION=$((QA_END - QA_START))
echo "[browser-qa] QA completed in ${QA_DURATION}s"

# Save raw output
echo "$QA_RAW_OUTPUT" > "$QA_OUTPUT_DIR/${QA_SESSION_ID}-raw.txt"

# ─────────────────────────────────────────────────────────────────────────────
# Extract JSON verdict from QA output
# ─────────────────────────────────────────────────────────────────────────────
QA_JSON="$(echo "$QA_RAW_OUTPUT" | python3 -c "
import sys, json, re

text = sys.stdin.read()

# Find json code blocks
json_blocks = re.findall(r'\`\`\`json\s*\n(.*?)\n\s*\`\`\`', text, re.DOTALL)

if json_blocks:
    candidate = json_blocks[-1]
else:
    # Try to find raw JSON with verdict field
    matches = re.findall(r'\{[^{}]*\"verdict\"[^{}]*\}', text, re.DOTALL)
    if not matches:
        matches = re.findall(r'\{[\s\S]*?\"verdict\"[\s\S]*?\}', text, re.DOTALL)
    candidate = matches[-1] if matches else ''

if candidate:
    try:
        parsed = json.loads(candidate)
        assert 'verdict' in parsed
        assert parsed['verdict'] in ('ALL_PASSED', 'PARTIAL_FAILURE', 'ALL_FAILED')
        print(json.dumps(parsed, indent=2))
    except (json.JSONDecodeError, AssertionError):
        print(json.dumps({
            'verdict': 'ALL_FAILED',
            'stories_total': 0,
            'stories_passed': 0,
            'stories_failed': 0,
            'results': [],
            'error': 'QA agent produced malformed JSON output. Check raw output.',
            'raw_output_path': '$QA_OUTPUT_DIR/${QA_SESSION_ID}-raw.txt'
        }, indent=2))
else:
    print(json.dumps({
        'verdict': 'ALL_FAILED',
        'stories_total': 0,
        'stories_passed': 0,
        'stories_failed': 0,
        'results': [],
        'error': 'No JSON verdict found in QA output. Check raw output.',
        'raw_output_path': '$QA_OUTPUT_DIR/${QA_SESSION_ID}-raw.txt'
    }, indent=2))
" 2>/dev/null)"

# Save structured verdict
echo "$QA_JSON" > "$QA_OUTPUT_DIR/${QA_SESSION_ID}.json"
echo "[browser-qa] Verdict saved to $QA_OUTPUT_DIR/${QA_SESSION_ID}.json"

# ─────────────────────────────────────────────────────────────────────────────
# Process verdict
# ─────────────────────────────────────────────────────────────────────────────
VERDICT="$(echo "$QA_JSON" | jq -r '.verdict')"
STORIES_TOTAL="$(echo "$QA_JSON" | jq -r '.stories_total // 0')"
STORIES_PASSED="$(echo "$QA_JSON" | jq -r '.stories_passed // 0')"
STORIES_FAILED="$(echo "$QA_JSON" | jq -r '.stories_failed // 0')"

echo ""
echo "============================================"
echo "  BROWSER QA VERDICT: $VERDICT"
echo "  Stories: $STORIES_PASSED/$STORIES_TOTAL passed"
echo "  Failed:  $STORIES_FAILED"
echo "  Session: $QA_SESSION_ID"
echo "============================================"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Handle failures — create fix beads, track retries
# ─────────────────────────────────────────────────────────────────────────────
if [ "$VERDICT" != "ALL_PASSED" ]; then
    echo "[browser-qa] Failures detected. Checking retry count..."

    # Determine the origin bead for retry tracking
    ORIGIN_BEAD="${BEAD_ID:-$AGENT_NAME}"
    RETRY_FILE="$RETRY_DIR/${ORIGIN_BEAD}.retries"
    RETRY_COUNT=0

    if [ -f "$RETRY_FILE" ]; then
        RETRY_COUNT="$(cat "$RETRY_FILE" 2>/dev/null || echo 0)"
    fi

    echo "[browser-qa] Retry count for $ORIGIN_BEAD: $RETRY_COUNT / $MAX_QA_RETRIES"

    # Build failure summary for bead description
    FAILURE_SUMMARY="$(echo "$QA_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
lines = ['## Browser QA Failures\n']
lines.append(f'Session: {data.get(\"session_id\", \"unknown\")}')
lines.append(f'Verdict: {data[\"verdict\"]}')
lines.append(f'Passed: {data.get(\"stories_passed\", 0)}/{data.get(\"stories_total\", 0)}\n')
for r in data.get('results', []):
    if r.get('status') == 'FAILED':
        lines.append(f'- FAILED: {r.get(\"title\", r.get(\"story_id\", \"unknown\"))}')
        if r.get('error'):
            lines.append(f'  Error: {r[\"error\"]}')
        if r.get('screenshot'):
            lines.append(f'  Screenshot: {r[\"screenshot\"]}')
if data.get('error'):
    lines.append(f'\nInfrastructure error: {data[\"error\"]}')
print('\n'.join(lines))
" 2>/dev/null || echo "QA verdict: $VERDICT")"

    if [ "$RETRY_COUNT" -ge "$MAX_QA_RETRIES" ]; then
        # Escalate to human
        echo "[browser-qa] Max retries ($MAX_QA_RETRIES) reached. Escalating to human."

        if command -v bd &>/dev/null; then
            ESCALATE_ID="$(bd create "[QA-ESCALATE] Browser QA failures for $AGENT_NAME (${RETRY_COUNT}x)" \
                -p 0 \
                --label "type:qa-escalate" \
                --label "agent:$AGENT_NAME" \
                --label "verdict:$VERDICT" \
                2>/dev/null | grep -oE '[A-Za-z0-9_-]+' | head -1 || echo "")"

            if [ -n "$ESCALATE_ID" ] && [ -n "$BEAD_ID" ]; then
                bd dep add "$ESCALATE_ID" "$BEAD_ID" 2>/dev/null || true
            fi

            echo "[browser-qa] Escalation bead: $ESCALATE_ID"
        fi

        echo ""
        echo "!!! BROWSER QA ESCALATED TO HUMAN !!!"
        echo "Max retries reached ($MAX_QA_RETRIES). Manual review required."
        echo "Verdict: $QA_OUTPUT_DIR/${QA_SESSION_ID}.json"
        echo "Raw output: $QA_OUTPUT_DIR/${QA_SESSION_ID}-raw.txt"
        echo "Screenshots: $SCREENSHOT_DIR/"
        echo ""
    else
        # Create fix bead and increment retry counter
        NEW_RETRY=$((RETRY_COUNT + 1))
        echo "$NEW_RETRY" > "$RETRY_FILE"
        echo "[browser-qa] Retry $NEW_RETRY/$MAX_QA_RETRIES — creating fix bead..."

        if command -v bd &>/dev/null; then
            FIX_BEAD_ID="$(bd create "[QA-FIX] $VERDICT: Browser QA failures for $AGENT_NAME (round $NEW_RETRY)" \
                -p 1 \
                --label "type:qa-fix" \
                --label "agent:$AGENT_NAME" \
                --label "verdict:$VERDICT" \
                --label "retry:$NEW_RETRY" \
                2>/dev/null | grep -oE '[A-Za-z0-9_-]+' | head -1 || echo "")"

            if [ -n "$FIX_BEAD_ID" ] && [ -n "$BEAD_ID" ]; then
                bd dep add "$FIX_BEAD_ID" "$BEAD_ID" 2>/dev/null || true
            fi

            echo "[browser-qa] Fix bead created: $FIX_BEAD_ID"
            echo "[browser-qa] Findings:"
            echo "$FAILURE_SUMMARY"
        fi
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Clean up retry tracking on success
# ─────────────────────────────────────────────────────────────────────────────
if [ "$VERDICT" = "ALL_PASSED" ]; then
    ORIGIN_BEAD="${BEAD_ID:-$AGENT_NAME}"
    RETRY_FILE="$RETRY_DIR/${ORIGIN_BEAD}.retries"
    rm -f "$RETRY_FILE" 2>/dev/null || true
    echo "[browser-qa] Retry counter cleared for $ORIGIN_BEAD"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Return exit code based on verdict
# ─────────────────────────────────────────────────────────────────────────────
case "$VERDICT" in
    ALL_PASSED)       exit 0 ;;
    PARTIAL_FAILURE)  exit 1 ;;
    ALL_FAILED)       exit 2 ;;
    *)                exit 3 ;;
esac
