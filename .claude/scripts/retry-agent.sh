#!/usr/bin/env bash
# retry-agent.sh — Retry a failed agent's work
#
# Usage: retry-agent.sh <agent_name> [max_retries]
#
# What it does:
# 1. Reads the agent's status to find its bead
# 2. Discards the failed worktree
# 3. Re-opens the bead (if it was auto-closed)
# 4. Spawns a fresh agent session with the same bead
# 5. Tracks retry count to prevent infinite loops
set -euo pipefail

AGENT_NAME="${1:?Usage: retry-agent.sh <agent_name> [max_retries]}"
MAX_RETRIES="${2:-3}"

STATUS_DIR="/tmp/baap-agent-status"
STATUS_FILE="$STATUS_DIR/$AGENT_NAME.json"
RETRY_FILE="$STATUS_DIR/$AGENT_NAME.retries"

# ── Check retry count ────────────────────────────────────────────────────────
RETRY_COUNT=0
if [ -f "$RETRY_FILE" ]; then
  RETRY_COUNT=$(cat "$RETRY_FILE")
fi

if [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
  echo "ERROR: Agent $AGENT_NAME has been retried $RETRY_COUNT times (max: $MAX_RETRIES)" >&2
  echo "Escalating to human. Bead remains open for manual intervention." >&2
  exit 1
fi

# ── Read failure info ────────────────────────────────────────────────────────
BEAD_ID=""
LEVEL="1"
if [ -f "$STATUS_FILE" ]; then
  BEAD_ID=$(python3 -c "import json; print(json.load(open('$STATUS_FILE')).get('bead',''))" 2>/dev/null || true)
  LEVEL=$(python3 -c "import json; print(json.load(open('$STATUS_FILE')).get('level',1))" 2>/dev/null || true)
  FAILURE=$(python3 -c "import json; print(json.load(open('$STATUS_FILE')).get('failure_reason','unknown'))" 2>/dev/null || true)
  echo "Retrying $AGENT_NAME (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)"
  echo "Last failure: $FAILURE"
  echo "Bead: $BEAD_ID"
fi

# ── Cleanup old worktree ────────────────────────────────────────────────────
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
if [ -d "$AGENT_DIR/$AGENT_NAME" ]; then
  bash "$(dirname "$0")/cleanup.sh" "$AGENT_NAME" discard
fi

# ── Re-open bead if it was auto-closed ──────────────────────────────────────
if [ -n "$BEAD_ID" ] && command -v bd &>/dev/null; then
  # Check if bead was auto-closed by cleanup.sh
  BEAD_STATUS=$(bd show "$BEAD_ID" --json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)
  if [ "$BEAD_STATUS" = "closed" ]; then
    bd update "$BEAD_ID" --status=open 2>/dev/null || true
    echo "Re-opened bead $BEAD_ID"
  fi
fi

# ── Increment retry count ───────────────────────────────────────────────────
echo "$((RETRY_COUNT + 1))" > "$RETRY_FILE"

# ── Build prompt with retry context ─────────────────────────────────────────
RETRY_PROMPT="bd show $BEAD_ID && work on it"
if [ "$RETRY_COUNT" -gt 0 ]; then
  RETRY_PROMPT="This is retry attempt $((RETRY_COUNT + 1)). Previous attempt failed ($FAILURE). Check the bead notes for context. $RETRY_PROMPT"
fi

# ── Re-spawn ────────────────────────────────────────────────────────────────
MAIN_REPO="$(cd "${AGENT_DIR%/agents}" && git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/Projects/baap")"
bash "$(dirname "$0")/spawn.sh" reactive "$RETRY_PROMPT" "$MAIN_REPO" "$AGENT_NAME" "$LEVEL"

echo "Agent $AGENT_NAME re-spawned (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)"
