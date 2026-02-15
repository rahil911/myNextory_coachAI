#!/usr/bin/env bash
# start-dashboard.sh — Launch the Baap monitoring dashboard
#
# Usage:
#   bash .claude/scripts/start-dashboard.sh
#
# Starts FastAPI on port 8002. Access from Mac via:
#   http://100.78.153.91:8002
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV="$PROJECT_ROOT/.venv"

# Activate venv if available
if [ -f "$VENV/bin/activate" ]; then
  source "$VENV/bin/activate"
fi

# Ensure dependencies
python3 -c "import fastapi, uvicorn" 2>/dev/null || {
  echo "Installing fastapi and uvicorn..."
  pip install fastapi uvicorn 2>/dev/null
}

echo "Starting Baap Dashboard on http://0.0.0.0:8002"
echo "Access from Mac: http://100.78.153.91:8002"

cd "$SCRIPT_DIR"
exec uvicorn dashboard_api:app --host 0.0.0.0 --port 8002 --log-level warning
