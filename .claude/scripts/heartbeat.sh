#!/usr/bin/env bash
# heartbeat.sh — Background heartbeat for agent liveness detection
# Usage: heartbeat.sh <agent_name> <interval_seconds>
set -euo pipefail

AGENT_NAME="${1:?Usage: heartbeat.sh <agent_name> <interval>}"
INTERVAL="${2:-60}"
TMUX_SESSION="${TMUX_SESSION_NAME:-agents}"
HEARTBEAT_DIR="/tmp/baap-heartbeats"

mkdir -p "$HEARTBEAT_DIR"
HEARTBEAT_FILE="$HEARTBEAT_DIR/$AGENT_NAME"

echo "Heartbeat started for $AGENT_NAME (every ${INTERVAL}s)"

while true; do
  # Check if agent's tmux window still exists
  if ! tmux list-windows -t "$TMUX_SESSION" 2>/dev/null | grep -q "$AGENT_NAME"; then
    echo "Agent $AGENT_NAME tmux window gone. Stopping heartbeat."
    rm -f "$HEARTBEAT_FILE"
    exit 0
  fi

  # Write heartbeat timestamp
  date +%s > "$HEARTBEAT_FILE"

  # Update status file with latest info
  AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
  STATUS_DIR="/tmp/baap-agent-status"
  STATUS_FILE="$STATUS_DIR/$AGENT_NAME.json"
  if [ -f "$STATUS_FILE" ]; then
    python3 -c "
import json, datetime
with open('$STATUS_FILE', 'r') as f:
    s = json.load(f)
s['last_update'] = datetime.datetime.now().isoformat()
s['status'] = 'working'
try:
    with open('$AGENT_DIR/$AGENT_NAME/agent.log', 'r') as log:
        lines = log.readlines()
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith('─'):
                s['current_action'] = line[:200]
                break
except: pass
with open('$STATUS_FILE', 'w') as f:
    json.dump(s, f, indent=2)
" 2>/dev/null || true
  fi

  sleep "$INTERVAL"
done
