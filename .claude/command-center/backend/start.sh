#!/usr/bin/env bash
# start.sh — Launch the Baap Command Center API
#
# Usage:
#   bash .claude/command-center/backend/start.sh           # foreground
#   bash .claude/command-center/backend/start.sh --bg      # background
#
# Starts FastAPI on port 8002 (configurable via BAAP_CC_PORT).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VENV="$PROJECT_ROOT/.venv"

# Activate venv if available
if [ -f "$VENV/bin/activate" ]; then
  source "$VENV/bin/activate"
fi

# Ensure dependencies
python3 -c "import fastapi, uvicorn, websockets" 2>/dev/null || {
  echo "Installing dependencies..."
  pip install fastapi uvicorn websockets python-multipart 2>/dev/null
}

export BAAP_PROJECT_ROOT="$PROJECT_ROOT"
PORT="${BAAP_CC_PORT:-8002}"

echo "Starting Baap Command Center on http://0.0.0.0:$PORT"
echo "  API docs: http://0.0.0.0:$PORT/docs"
echo "  WebSocket: ws://0.0.0.0:$PORT/ws"

cd "$SCRIPT_DIR"

if [ "${1:-}" = "--bg" ]; then
  nohup uvicorn main:app --host 0.0.0.0 --port "$PORT" --log-level warning > /tmp/baap-command-center.log 2>&1 &
  echo "PID: $!"
  echo "Log: /tmp/baap-command-center.log"
else
  exec uvicorn main:app --host 0.0.0.0 --port "$PORT" --log-level warning
fi
