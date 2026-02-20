"""
config.py — Configuration for Command Center API.

All paths are configurable via environment variables. Defaults auto-detect
from the project root (found by walking up from this file to find .git).

Environment variables:
    BAAP_PROJECT_ROOT       — Override project root detection
    BAAP_STATUS_DIR         — Agent status JSON directory (default: /tmp/baap-agent-status)
    BAAP_HEARTBEAT_DIR      — Heartbeat file directory (default: /tmp/baap-heartbeats)
    BAAP_LOG_DIR            — Agent log directory (default: {project}/.claude/logs)
    BAAP_SCRIPTS_DIR        — Shell scripts directory (default: {project}/.claude/scripts)
    BAAP_KG_CACHE           — Knowledge graph cache (default: {project}/.claude/kg/agent_graph_cache.json)
    BAAP_ATTACHMENTS_DIR    — Upload storage (default: {project}/.claude/command-center/attachments)
    BAAP_CC_PORT            — API port (default: 8002)
    BAAP_HEARTBEAT_STALE_S  — Seconds before heartbeat is stale (default: 120)
"""

import os
from pathlib import Path


def _find_project_root() -> Path:
    """Walk up from this file to find a directory containing .git."""
    current = Path(__file__).resolve().parent
    for _ in range(10):  # max 10 levels up
        if (current / ".git").exists():
            return current
        if (current / ".claude").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    # Fallback: assume 4 levels up from backend/config.py
    # .claude/command-center/backend/config.py -> project root
    return Path(__file__).resolve().parent.parent.parent.parent


PROJECT_ROOT = Path(os.environ.get("BAAP_PROJECT_ROOT", str(_find_project_root())))

# Directories
STATUS_DIR = Path(os.environ.get("BAAP_STATUS_DIR", "/tmp/baap-agent-status"))
HEARTBEAT_DIR = Path(os.environ.get("BAAP_HEARTBEAT_DIR", "/tmp/baap-heartbeats"))
LOG_DIR = Path(os.environ.get("BAAP_LOG_DIR", str(PROJECT_ROOT / ".claude" / "logs")))
SCRIPTS_DIR = Path(os.environ.get("BAAP_SCRIPTS_DIR", str(PROJECT_ROOT / ".claude" / "scripts")))
KG_CACHE = Path(os.environ.get("BAAP_KG_CACHE", str(PROJECT_ROOT / ".claude" / "kg" / "agent_graph_cache.json")))
ATTACHMENTS_DIR = Path(os.environ.get(
    "BAAP_ATTACHMENTS_DIR",
    str(PROJECT_ROOT / ".claude" / "command-center" / "attachments")
))
SESSIONS_DIR = Path(os.environ.get(
    "BAAP_SESSIONS_DIR",
    str(PROJECT_ROOT / ".claude" / "command-center" / "sessions")
))

# Server
PORT = int(os.environ.get("BAAP_CC_PORT", "8002"))

# Thresholds
HEARTBEAT_STALE_SECONDS = int(os.environ.get("BAAP_HEARTBEAT_STALE_S", "120"))

# Timeline
MAX_TIMELINE_EVENTS = 500

# Ensure directories exist
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
STATUS_DIR.mkdir(parents=True, exist_ok=True)
HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# RAG Configuration — re-export so any RAG module that still does
# `from config import X` finds the names here (Python caches this module
# in sys.modules as 'config').  The canonical source is rag/rag_config.py.
# ---------------------------------------------------------------------------
_rag_config_path = Path(__file__).resolve().parent.parent.parent / "rag" / "rag_config.py"
if _rag_config_path.exists():
    _rag_ns = {"__file__": str(_rag_config_path)}
    exec(compile(_rag_config_path.read_text(), str(_rag_config_path), "exec"), _rag_ns)
    for _k, _v in _rag_ns.items():
        if not _k.startswith("_") and _k.isupper() and _k not in globals():
            globals()[_k] = _v
