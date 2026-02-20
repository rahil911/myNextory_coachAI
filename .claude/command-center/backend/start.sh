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

cd "$SCRIPT_DIR"

# ── SSL / TLS ────────────────────────────────────────────────────────────────
# Auto-detect certificates.  Priority:
#   1. Let's Encrypt (if available)
#   2. Self-signed in .claude/command-center/certs/
#   3. Generate self-signed on first run
CERTS_DIR="$SCRIPT_DIR/../certs"
LE_DIR="/etc/letsencrypt/live/rahil911.duckdns.org"
SSL_ARGS=""

if [ -f "$LE_DIR/fullchain.pem" ] && [ -f "$LE_DIR/privkey.pem" ]; then
  SSL_ARGS="--ssl-certfile $LE_DIR/fullchain.pem --ssl-keyfile $LE_DIR/privkey.pem"
  echo "Using Let's Encrypt certificates"
elif [ -f "$CERTS_DIR/cert.pem" ] && [ -f "$CERTS_DIR/key.pem" ]; then
  SSL_ARGS="--ssl-certfile $CERTS_DIR/cert.pem --ssl-keyfile $CERTS_DIR/key.pem"
  echo "Using self-signed certificates from $CERTS_DIR"
else
  echo "Generating self-signed SSL certificate..."
  mkdir -p "$CERTS_DIR"
  openssl req -x509 -newkey rsa:2048 \
    -keyout "$CERTS_DIR/key.pem" -out "$CERTS_DIR/cert.pem" \
    -days 365 -nodes -subj '/CN=rahil911.duckdns.org' 2>/dev/null
  SSL_ARGS="--ssl-certfile $CERTS_DIR/cert.pem --ssl-keyfile $CERTS_DIR/key.pem"
  echo "Generated self-signed certificate in $CERTS_DIR"
fi

PROTO="https"
WS_PROTO="wss"
if [ -z "$SSL_ARGS" ]; then
  PROTO="http"
  WS_PROTO="ws"
fi

echo "Starting Baap Command Center on $PROTO://0.0.0.0:$PORT"
echo "  API docs: $PROTO://0.0.0.0:$PORT/docs"
echo "  WebSocket: $WS_PROTO://0.0.0.0:$PORT/ws"

if [ "${1:-}" = "--bg" ]; then
  nohup uvicorn main:app --host 0.0.0.0 --port "$PORT" --log-level warning $SSL_ARGS > /tmp/baap-command-center.log 2>&1 &
  echo "PID: $!"
  echo "Log: /tmp/baap-command-center.log"
else
  exec uvicorn main:app --host 0.0.0.0 --port "$PORT" --log-level warning $SSL_ARGS
fi
