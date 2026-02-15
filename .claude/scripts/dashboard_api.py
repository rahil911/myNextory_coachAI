#!/usr/bin/env python3
"""
dashboard_api.py — Lightweight monitoring API for Baap agent swarm.

Reads from:
  - /tmp/baap-agent-status/*.json  (agent status, written by spawn.sh)
  - /tmp/baap-heartbeats/*         (heartbeat timestamps, written by heartbeat.sh)
  - bd list --json                 (bead data from beads CLI)
  - .claude/logs/*.log             (archived agent logs)

Serves on port 8002. Run with:
  uvicorn dashboard_api:app --host 0.0.0.0 --port 8002
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Baap Dashboard API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATUS_DIR = Path("/tmp/baap-agent-status")
HEARTBEAT_DIR = Path("/tmp/baap-heartbeats")
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # .claude/scripts -> project root
LOG_DIR = PROJECT_ROOT / ".claude" / "logs"

# ── Timeline event log (in-memory, last 200 events) ──────────────────────────
_timeline: list[dict] = []
_last_agent_snapshot: dict[str, str] = {}  # agent_name -> last known status
MAX_TIMELINE = 200


def _add_event(event_type: str, agent: str, detail: str) -> None:
    """Append an event to the in-memory timeline."""
    _timeline.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "agent": agent,
        "detail": detail,
    })
    if len(_timeline) > MAX_TIMELINE:
        _timeline.pop(0)


def _detect_transitions(agents: list[dict]) -> None:
    """Compare current agent statuses against last snapshot, emit events for changes."""
    global _last_agent_snapshot
    current: dict[str, str] = {}
    for a in agents:
        name = a["agent"]
        status = a["status"]
        current[name] = status
        prev = _last_agent_snapshot.get(name)
        if prev is None:
            _add_event("agent_spawned", name, f"Agent appeared with status: {status}")
        elif prev != status:
            _add_event("status_change", name, f"{prev} -> {status}")
    # Detect agents that disappeared
    for name, prev_status in _last_agent_snapshot.items():
        if name not in current:
            _add_event("agent_gone", name, f"Agent disappeared (was: {prev_status})")
    _last_agent_snapshot = current


def _read_status_files() -> list[dict]:
    """Read all agent status JSON files."""
    agents = []
    if not STATUS_DIR.exists():
        return agents
    now = time.time()
    for f in sorted(STATUS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        name = data.get("agent", f.stem)
        # Heartbeat check
        hb_file = HEARTBEAT_DIR / name
        hb_age = None
        hb_stale = False
        if hb_file.exists():
            try:
                last_hb = float(hb_file.read_text().strip())
                hb_age = int(now - last_hb)
                hb_stale = hb_age > 120
            except (ValueError, OSError):
                pass
        agents.append({
            "agent": name,
            "level": data.get("level", "?"),
            "status": data.get("status", "unknown"),
            "bead": data.get("bead", None),
            "current_action": data.get("current_action", None),
            "started_at": data.get("started_at", None),
            "last_update": data.get("last_update", None),
            "worktree": data.get("worktree", None),
            "errors": data.get("errors", 0),
            "heartbeat_age_s": hb_age,
            "heartbeat_stale": hb_stale,
        })
    return agents


def _get_beads() -> list[dict]:
    """Get bead data from bd CLI."""
    try:
        result = subprocess.run(
            ["bd", "list", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    return []


def _build_epics(beads: list[dict]) -> list[dict]:
    """Group beads by epic/parent and compute progress."""
    epics: dict[str, dict[str, Any]] = {}
    for b in beads:
        epic = b.get("epic") or b.get("parent") or b.get("project") or "ungrouped"
        if epic not in epics:
            epics[epic] = {"epic": epic, "total": 0, "completed": 0, "in_progress": 0,
                           "blocked": 0, "open": 0, "beads": []}
        epics[epic]["total"] += 1
        epics[epic]["beads"].append(b.get("id", "?"))
        status = (b.get("status") or "").lower()
        if status in ("closed", "done", "completed", "resolved"):
            epics[epic]["completed"] += 1
        elif status in ("in_progress", "in-progress", "active"):
            epics[epic]["in_progress"] += 1
        elif status in ("blocked",):
            epics[epic]["blocked"] += 1
        else:
            epics[epic]["open"] += 1
    result = []
    for e in epics.values():
        e["progress_pct"] = round(e["completed"] / e["total"] * 100, 1) if e["total"] > 0 else 0
        result.append(e)
    result.sort(key=lambda x: x["progress_pct"])
    return result


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/dashboard/agents")
def get_agents():
    """List all agents with status, heartbeat, current bead."""
    agents = _read_status_files()
    _detect_transitions(agents)
    return {"agents": agents, "count": len(agents), "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/api/dashboard/epics")
def get_epics():
    """List epics with progress (beads completed/total)."""
    beads = _get_beads()
    epics = _build_epics(beads)
    return {"epics": epics, "count": len(epics)}


@app.get("/api/dashboard/beads")
def get_beads():
    """All beads with status, assignee, dependencies."""
    beads = _get_beads()
    return {"beads": beads, "count": len(beads)}


@app.get("/api/dashboard/timeline")
def get_timeline():
    """Recent events (agent spawned, status changes, disappearances)."""
    # Trigger a status read to detect transitions
    agents = _read_status_files()
    _detect_transitions(agents)
    # Also scan for recently closed beads in log dir
    recent_logs: list[dict] = []
    if LOG_DIR.exists():
        for lf in sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
            recent_logs.append({
                "file": lf.name,
                "size_kb": round(lf.stat().st_size / 1024, 1),
                "modified": datetime.fromtimestamp(lf.stat().st_mtime, tz=timezone.utc).isoformat(),
            })
    return {
        "events": list(reversed(_timeline[-20:])),
        "recent_logs": recent_logs,
        "total_events": len(_timeline),
    }


@app.get("/api/dashboard/health")
def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# ── Serve the HTML dashboard ─────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    html_path = SCRIPT_DIR / "dashboard.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(), status_code=200)
    return HTMLResponse(content="<h1>dashboard.html not found</h1>", status_code=404)
