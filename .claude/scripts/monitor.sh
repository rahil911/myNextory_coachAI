#!/usr/bin/env bash
# monitor.sh — Aggregated agent monitoring dashboard
#
# Usage:
#   monitor.sh              # One-shot display
#   monitor.sh --watch      # Auto-refresh every 5 seconds
#   monitor.sh --agent NAME # Detail view for one agent
set -euo pipefail

STATUS_DIR="/tmp/baap-agent-status"
HEARTBEAT_DIR="/tmp/baap-heartbeats"
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
NOW=$(date +%s)

show_dashboard() {
  clear 2>/dev/null || true
  echo "╔══════════════════════════════════════════════════════════════════════════╗"
  echo "║                    BAAP AGENT MONITOR — $(date '+%H:%M:%S')                       ║"
  echo "╠══════════════════════════════════════════════════════════════════════════╣"

  # Active agents from status files
  if [ -d "$STATUS_DIR" ] && ls "$STATUS_DIR"/*.json &>/dev/null; then
    printf "║ %-20s %-8s %-10s %-10s %-18s ║\n" "AGENT" "LEVEL" "STATUS" "HEARTBEAT" "BEAD"
    echo "║──────────────────────────────────────────────────────────────────────────║"

    for status_file in "$STATUS_DIR"/*.json; do
      AGENT=$(python3 -c "import json; print(json.load(open('$status_file')).get('agent','?'))" 2>/dev/null || echo "?")
      LEVEL=$(python3 -c "import json; print('L'+str(json.load(open('$status_file')).get('level','?')))" 2>/dev/null || echo "?")
      STATUS=$(python3 -c "import json; print(json.load(open('$status_file')).get('status','?'))" 2>/dev/null || echo "?")
      BEAD=$(python3 -c "import json; print(json.load(open('$status_file')).get('bead','—'))" 2>/dev/null || echo "—")

      # Heartbeat check
      HB_FILE="$HEARTBEAT_DIR/$AGENT"
      if [ -f "$HB_FILE" ]; then
        LAST_HB=$(cat "$HB_FILE")
        HB_AGE=$(( NOW - LAST_HB ))
        if [ "$HB_AGE" -lt 120 ]; then
          HB_STATUS="${HB_AGE}s ago"
        else
          HB_STATUS="STALE!"
        fi
      else
        HB_STATUS="none"
      fi

      printf "║ %-20s %-8s %-10s %-10s %-18s ║\n" "$AGENT" "$LEVEL" "$STATUS" "$HB_STATUS" "$BEAD"
    done
  else
    echo "║ No active agents.                                                        ║"
  fi

  echo "╠══════════════════════════════════════════════════════════════════════════╣"

  # Beads summary
  if command -v bd &>/dev/null; then
    OPEN=$(bd list --status=open 2>/dev/null | wc -l || echo 0)
    IN_PROG=$(bd list --status=in_progress 2>/dev/null | wc -l || echo 0)
    BLOCKED=$(bd blocked 2>/dev/null | wc -l || echo 0)
    echo "║ Beads: $IN_PROG in-progress | $OPEN open | $BLOCKED blocked                         ║"
  fi

  # Worktrees
  WT_COUNT=$(git worktree list 2>/dev/null | grep -c agents || echo 0)
  echo "║ Worktrees: $WT_COUNT active                                                      ║"

  echo "╚══════════════════════════════════════════════════════════════════════════╝"
}

show_agent_detail() {
  local AGENT="$1"
  echo "=== Agent: $AGENT ==="

  # Status
  STATUS_FILE="$STATUS_DIR/$AGENT.json"
  if [ -f "$STATUS_FILE" ]; then
    python3 -c "import json; [print(f'  {k}: {v}') for k,v in json.load(open('$STATUS_FILE')).items()]"
  fi

  echo ""
  echo "=== Last 20 log lines ==="
  LOG_FILE="$AGENT_DIR/$AGENT/agent.log"
  if [ -f "$LOG_FILE" ]; then
    tail -20 "$LOG_FILE"
  else
    echo "  No log file found."
  fi

  echo ""
  echo "=== Beads ==="
  if command -v bd &>/dev/null; then
    bd list --status=in_progress 2>/dev/null | grep -i "$AGENT" || echo "  No in-progress beads for $AGENT"
  fi
}

# Parse args
case "${1:-}" in
  --watch)
    while true; do
      show_dashboard
      sleep 5
    done
    ;;
  --agent)
    show_agent_detail "${2:?Usage: monitor.sh --agent NAME}"
    ;;
  *)
    show_dashboard
    ;;
esac
