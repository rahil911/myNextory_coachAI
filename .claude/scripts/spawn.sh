#!/usr/bin/env bash
# spawn.sh — Spawn a Claude Code agent in an isolated git worktree
#
# Usage:
#   spawn.sh <mode> <prompt> <repo_path> [agent_name] [level]
#
# Arguments:
#   mode        - reactive|proactive|team
#   prompt      - The task prompt for the agent
#   repo_path   - Absolute path to the main repository
#   agent_name  - Agent identity (default: auto-generated from mode+timestamp)
#   level       - Agent level 0-3 for timeout enforcement (default: 1)
#
# Examples:
#   spawn.sh reactive "bd show baap-abc && work on it" ~/Projects/baap identity-agent 1
#   spawn.sh reactive "bd show baap-xyz" ~/Projects/baap platform-agent 1
set -euo pipefail

MODE="${1:?Usage: spawn.sh <mode> <prompt> <repo_path> [agent_name] [level]}"
PROMPT="${2:?Missing prompt}"
REPO="${3:?Missing repo path}"
NAME="${4:-${MODE}-$(date +%Y%m%d_%H%M%S)}"
LEVEL="${5:-1}"
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
WORKTREE="$AGENT_DIR/$NAME"
BRANCH="agent/$NAME"
TMUX_SESSION="${TMUX_SESSION_NAME:-agents}"

# ── Pre-flight ───────────────────────────────────────────────────────────────
for tool in claude bd git tmux; do
  command -v "$tool" &>/dev/null || { echo "ERROR: $tool not found in PATH" >&2; exit 1; }
done

# Resolve main repo root (handles both repo path and worktree path)
MAIN_REPO="$(cd "$REPO" && git rev-parse --show-toplevel)"

# ── Timeout ──────────────────────────────────────────────────────────────────
case "$LEVEL" in
  0) TIMEOUT_SECS=0 ;;
  1) TIMEOUT_SECS=7200 ;;
  2) TIMEOUT_SECS=3600 ;;
  3) TIMEOUT_SECS=1800 ;;
  *) TIMEOUT_SECS=3600 ;;
esac

# ── Create worktree ──────────────────────────────────────────────────────────
mkdir -p "$AGENT_DIR"
cd "$MAIN_REPO"
git worktree add "$WORKTREE" -b "$BRANCH" HEAD 2>/dev/null || {
  echo "Worktree or branch already exists. Cleaning up..."
  git worktree remove "$WORKTREE" --force 2>/dev/null || true
  git branch -D "$BRANCH" 2>/dev/null || true
  git worktree add "$WORKTREE" -b "$BRANCH" HEAD
}
echo "Created worktree: $WORKTREE (branch: $BRANCH)"

# ── Symlinks (shared state) ─────────────────────────────────────────────────
# .beads/ — CRITICAL: agents need shared beads for communication
if [ -d "$MAIN_REPO/.beads" ]; then
  ln -sfn "$MAIN_REPO/.beads" "$WORKTREE/.beads"
  echo "Symlinked .beads/ from main repo"
fi

# .venv/ — avoid cold start (minutes of pip install per worktree)
if [ -d "$MAIN_REPO/.venv" ]; then
  ln -sfn "$MAIN_REPO/.venv" "$WORKTREE/.venv"
  echo "Symlinked .venv/ from main repo"
fi

# .claude/integrations/ — shared credentials for 3rd party APIs
INTEGRATIONS="$MAIN_REPO/.claude/integrations"
if [ -d "$INTEGRATIONS" ]; then
  rm -rf "$WORKTREE/.claude/integrations" 2>/dev/null || true
  ln -sfn "$INTEGRATIONS" "$WORKTREE/.claude/integrations"
  echo "Symlinked .claude/integrations/ from main repo"
fi

# ── Bootstrap agent memory ───────────────────────────────────────────────────
MEMORY_DIR="$MAIN_REPO/.claude/agents/$NAME/memory"
if [ ! -d "$MEMORY_DIR" ]; then
  mkdir -p "$MEMORY_DIR"
  cat > "$MEMORY_DIR/MEMORY.md" << MEMEOF
# $NAME Memory

## Created
- $(date -Iseconds)
- First session, no prior knowledge

## My Ownership
- Check with: get_agent_files("$NAME")

## Key Decisions
- (none yet)

## Recent Changes
- (none yet)
MEMEOF
  echo "Created memory directory for $NAME"

  cd "$MAIN_REPO"
  git add ".claude/agents/$NAME/memory/" 2>/dev/null || true
  git commit -m "Bootstrap memory for $NAME" --no-verify 2>/dev/null || true
fi

# ── Build claude command ─────────────────────────────────────────────────────
MCP_CONFIG="$MAIN_REPO/.mcp.json"
FULL_PROMPT="You are agent '$NAME'. Your agent level is L${LEVEL}. ${PROMPT}"

CLAUDE_CMD="claude -p \"${FULL_PROMPT//\"/\\\"}\" --dangerously-skip-permissions"

# MCP config (absolute path so it works from worktree)
if [ -f "$MCP_CONFIG" ]; then
  CLAUDE_CMD="$CLAUDE_CMD --mcp-config $MCP_CONFIG"
fi

# Model tiering
case "$LEVEL" in
  0) CLAUDE_CMD="$CLAUDE_CMD --model claude-opus-4-6" ;;
  1) CLAUDE_CMD="$CLAUDE_CMD --model claude-sonnet-4-5-20250929" ;;
  *) CLAUDE_CMD="$CLAUDE_CMD --model claude-haiku-4-5-20251001" ;;
esac

# Timeout wrapper
if [ "$TIMEOUT_SECS" -gt 0 ]; then
  CLAUDE_CMD="timeout ${TIMEOUT_SECS}s $CLAUDE_CMD"
fi

# ── Log & status setup ───────────────────────────────────────────────────────
LOG_FILE="$WORKTREE/agent.log"
STATUS_DIR="/tmp/baap-agent-status"
mkdir -p "$STATUS_DIR"

cat > "$STATUS_DIR/$NAME.json" << STATUSEOF
{
  "agent": "$NAME",
  "level": $LEVEL,
  "status": "spawning",
  "started_at": "$(date -Iseconds)",
  "last_update": "$(date -Iseconds)",
  "worktree": "$WORKTREE",
  "log_file": "$WORKTREE/agent.log"
}
STATUSEOF

# ── Ensure tmux session ─────────────────────────────────────────────────────
tmux has-session -t "$TMUX_SESSION" 2>/dev/null || tmux new-session -d -s "$TMUX_SESSION"

# ── Launch in tmux window ───────────────────────────────────────────────────
# Agent output is tee'd to agent.log for persistence + post-mortem debugging.
# Exit code is captured and written to the status file.
tmux new-window -t "$TMUX_SESSION" -n "$NAME" \
  "cd $WORKTREE && export AGENT_NAME=$NAME && export AGENT_LEVEL=$LEVEL && \
   $CLAUDE_CMD 2>&1 | tee $LOG_FILE; \
   EXIT_CODE=\$?; \
   python3 -c \"
import json, datetime
sf = '$STATUS_DIR/$NAME.json'
try:
    with open(sf, 'r') as f: s = json.load(f)
except: s = {}
s['status'] = 'completed' if \$EXIT_CODE == 0 else 'failed'
s['exit_code'] = \$EXIT_CODE
s['finished_at'] = datetime.datetime.now().isoformat()
if \$EXIT_CODE == 124: s['failure_reason'] = 'timeout'
elif \$EXIT_CODE != 0: s['failure_reason'] = 'error'
with open(sf, 'w') as f: json.dump(s, f, indent=2)
\" 2>/dev/null; \
   echo 'Agent $NAME finished (exit \$EXIT_CODE). Press Enter to close.'; read"

# ── Launch heartbeat in background ───────────────────────────────────────────
mkdir -p /tmp/baap-heartbeats
nohup bash "$MAIN_REPO/.claude/scripts/heartbeat.sh" "$NAME" 60 \
  > "/tmp/baap-heartbeats/$NAME.log" 2>&1 &
echo "Heartbeat PID: $!"

echo "Spawned agent '$NAME' (L${LEVEL}) in worktree: $WORKTREE"
echo "Monitor: tmux attach -t $TMUX_SESSION"
echo "Log: tail -f $LOG_FILE"
if [ "$TIMEOUT_SECS" -gt 0 ]; then
  echo "Timeout: ${TIMEOUT_SECS}s ($(( TIMEOUT_SECS / 60 ))min)"
else
  echo "Timeout: none (L0 orchestrator)"
fi
