#!/usr/bin/env bash
# kill-agent.sh — Gracefully cancel a running agent
# Usage: kill-agent.sh <agent_name> [reason]
set -euo pipefail

AGENT_NAME="${1:?Usage: kill-agent.sh <agent_name> [reason]}"
REASON="${2:-Manually cancelled}"
TMUX_SESSION="${TMUX_SESSION_NAME:-agents}"

echo "Killing agent: $AGENT_NAME"
echo "Reason: $REASON"

# 1. Kill the claude process in tmux window
if tmux list-windows -t "$TMUX_SESSION" 2>/dev/null | grep -q "$AGENT_NAME"; then
  tmux send-keys -t "$TMUX_SESSION:$AGENT_NAME" C-c 2>/dev/null || true
  sleep 2

  PANE_PID=$(tmux list-panes -t "$TMUX_SESSION:$AGENT_NAME" -F '#{pane_pid}' 2>/dev/null || true)
  if [ -n "$PANE_PID" ]; then
    pkill -TERM -P "$PANE_PID" 2>/dev/null || true
    sleep 1
    pkill -KILL -P "$PANE_PID" 2>/dev/null || true
  fi

  tmux kill-window -t "$TMUX_SESSION:$AGENT_NAME" 2>/dev/null || true
  echo "Killed tmux window."
fi

# 2. Update status file to "stopped"
STATUS_FILE="/tmp/baap-agent-status/$AGENT_NAME.json"
if [ -f "$STATUS_FILE" ]; then
  python3 -c "
import json, datetime
with open('$STATUS_FILE', 'r') as f:
    s = json.load(f)
s['status'] = 'stopped'
s['last_update'] = datetime.datetime.now().isoformat()
s['stop_reason'] = '$REASON'
with open('$STATUS_FILE', 'w') as f:
    json.dump(s, f, indent=2)
" 2>/dev/null || true
fi

# 3. Mark in-progress beads as cancelled
if command -v bd &>/dev/null; then
  bd agent state "$AGENT_NAME" stopped 2>/dev/null || true
fi

# 4. Stop heartbeat
rm -f "/tmp/baap-heartbeats/$AGENT_NAME"

# 4. Discard worktree and branch
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
if [ -d "$AGENT_DIR/$AGENT_NAME" ]; then
  bash "$(dirname "$0")/cleanup.sh" "$AGENT_NAME" discard
  echo "Worktree discarded."
else
  echo "No worktree found (already cleaned up)."
fi

echo "Agent $AGENT_NAME killed and cleaned up."
