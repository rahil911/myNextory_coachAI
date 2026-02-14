#!/usr/bin/env bash
# Run an MCP server using the project's venv Python, regardless of machine.
# Auto-creates venv and installs deps if missing. Works on macOS, Linux, WSL.
# Usage: run_mcp.sh <script_name>  e.g. run_mcp.sh ownership_graph.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"
DEPS_MARKER="$VENV_DIR/.mcp_deps_installed"
SERVER_SCRIPT="$1"

# ── Step 1: Ensure venv exists ──────────────────────────────────────────────
if [ ! -f "$VENV_PYTHON" ]; then
  echo "Creating Python venv at $VENV_DIR..." >&2
  python3 -m venv "$VENV_DIR" || {
    echo "Error: python3 not found or venv creation failed." >&2
    echo "Install Python 3: https://www.python.org/downloads/" >&2
    exit 1
  }
fi

# ── Step 2: Ensure MCP deps are installed ───────────────────────────────────
if [ ! -f "$DEPS_MARKER" ]; then
  echo "Installing MCP server dependencies (first time only)..." >&2

  # Core deps (all servers need these)
  "$VENV_PIP" install --quiet "mcp[cli]" httpx >&2 || {
    echo "Error: Failed to install core MCP deps (mcp, httpx)." >&2
    exit 1
  }

  # MySQL connector for db-tools MCP server
  "$VENV_PIP" install --quiet mysql-connector-python >&2 || {
    echo "Warning: mysql-connector-python failed. db-tools MCP will not work." >&2
    echo "The ownership-graph MCP server will work fine." >&2
  }

  echo "All MCP dependencies installed." >&2
  touch "$DEPS_MARKER"
fi

# ── Step 3: Run the server ──────────────────────────────────────────────────
exec "$VENV_PYTHON" "$SCRIPT_DIR/$SERVER_SCRIPT"
