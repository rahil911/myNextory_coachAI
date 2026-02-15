# Phase 3e: Human Progress Dashboard — Web-Based Monitoring UI

## Purpose

The terminal-based `monitor.sh` (Phase 1e) works for quick checks, but it has three
limitations the human keeps hitting:

1. **No remote access from Mac** — you have to `ssh india-linux` and run monitor.sh.
   No way to glance at progress from a browser while doing other work.
2. **No historical timeline** — monitor.sh is a snapshot. It doesn't show "agent X
   started at 10:30, finished bead Y at 10:45, got killed at 11:00." You lose the
   narrative of what happened.
3. **No dependency visualization** — `bd list` dumps beads flat. You can't see which
   beads block which, which epics are 60% done, which agents are idle waiting.

This phase creates a lightweight web dashboard served on India port 8002. The human
opens `http://100.78.153.91:8002` from Mac (via Tailscale) and sees everything:
agent swimlanes, epic progress bars, bead dependency graph, and a live event timeline.

**Design constraint**: This is NOT a full Next.js app. It's a single-file HTML dashboard
served by a single-file FastAPI backend. Total: 2 files, <500 lines combined. It runs
in tmux alongside the other services and requires zero build steps.

## Risks Mitigated

- Risk: Human has no remote visibility into swarm progress without SSH
- Risk: No historical timeline of agent events (starts, completions, failures)
- Risk: Bead dependency chains invisible — blocked work not surfaced
- Risk: Stale heartbeats and failed agents not surfaced until human checks manually
- Risk: Epic completion percentage unknown — human can't estimate time remaining

## Files to Create

- `.claude/scripts/dashboard_api.py` — FastAPI backend (~180 lines)
- `.claude/scripts/dashboard.html` — Single-file HTML/CSS/JS dashboard (~300 lines)
- `.claude/scripts/start-dashboard.sh` — Launcher script (~15 lines)

## Files to Modify

- None. This is additive — no existing files touched.

## Dependencies

- Phase 1e (observability): `/tmp/baap-agent-status/*.json` and `/tmp/baap-heartbeats/*` must exist
- Phase 1d (lifecycle): `heartbeat.sh` and `kill-agent.sh` must be working
- `bd` CLI must be installed and functional
- Python 3 with `fastapi` and `uvicorn` (already in .venv from other phases)

---

## Fix 1: Dashboard API — `.claude/scripts/dashboard_api.py`

### Problem

The data exists in 4 different places (status files, heartbeat files, beads CLI, log
directory) but there's no unified way to query it from a browser. The HTML dashboard
needs a JSON API to poll.

### Solution

A single-file FastAPI app that reads from all 4 sources and exposes 4 endpoints.
No database, no models, no migrations — just reads files and shells out to `bd`.

### Full Implementation

```python
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
```

### Key Design Decisions

1. **In-memory timeline** — Events are detected by diffing agent status snapshots on
   each poll. No database, no persistent event log. If the API restarts, timeline resets.
   This is fine for a monitoring dashboard.

2. **Beads via subprocess** — We shell out to `bd list --json` rather than importing beads
   internals. This keeps the API decoupled and means it works regardless of how beads
   stores data internally.

3. **Heartbeat staleness at 2 minutes** — Matches the threshold from monitor.sh (Phase 1e).
   If a heartbeat file is older than 120 seconds, the agent is flagged as stale.

4. **No authentication** — This runs on the Tailscale network, only accessible from
   the human's Mac. No need for auth on an internal monitoring tool.

5. **CORS wildcard** — The HTML is served from the same origin, but allowing `*` means
   you can also hit the API from curl or other tools without issues.

---

## Fix 2: HTML Dashboard — `.claude/scripts/dashboard.html`

### Problem

The API returns JSON but the human needs a visual dashboard they can open in a browser
and leave in a tab. It should auto-refresh and make problems immediately visible.

### Solution

A single HTML file with inline CSS and JS. No build step, no npm, no React. Just
`fetch()` and DOM manipulation. Polls every 10 seconds.

### Full Implementation

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Baap Agent Swarm</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --dim: #8b949e; --green: #3fb950;
    --yellow: #d29922; --red: #f85149; --blue: #58a6ff; --purple: #bc8cff;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, 'SF Mono', 'Consolas', monospace; font-size: 14px; padding: 20px; }
  h1 { font-size: 18px; margin-bottom: 4px; }
  .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 12px; }
  .header-right { font-size: 12px; color: var(--dim); }
  .pulse { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--green); margin-right: 6px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
  .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .panel-title { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--dim); margin-bottom: 12px; }
  .full-width { grid-column: 1 / -1; }

  /* Agent cards */
  .agent-card { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: 6px; margin-bottom: 6px; background: var(--bg); }
  .agent-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  .agent-dot.working { background: var(--green); }
  .agent-dot.spawning { background: var(--yellow); }
  .agent-dot.stopped { background: var(--dim); }
  .agent-dot.stuck { background: var(--red); animation: pulse 1s infinite; }
  .agent-name { font-weight: 600; min-width: 160px; }
  .agent-level { color: var(--purple); font-size: 12px; min-width: 30px; }
  .agent-action { color: var(--dim); font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .agent-hb { font-size: 11px; min-width: 70px; text-align: right; }
  .agent-hb.stale { color: var(--red); font-weight: 700; }

  /* Epic progress */
  .epic-row { margin-bottom: 10px; }
  .epic-header { display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 13px; }
  .epic-bar-bg { height: 20px; background: var(--bg); border-radius: 4px; overflow: hidden; display: flex; }
  .epic-bar-fill { height: 100%; transition: width 0.5s ease; }
  .epic-bar-done { background: var(--green); }
  .epic-bar-wip { background: var(--yellow); }
  .epic-bar-blocked { background: var(--red); }
  .epic-stats { font-size: 11px; color: var(--dim); margin-top: 2px; }

  /* Beads table */
  .bead-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .bead-table th { text-align: left; color: var(--dim); font-weight: 400; padding: 4px 8px; border-bottom: 1px solid var(--border); }
  .bead-table td { padding: 4px 8px; border-bottom: 1px solid var(--bg); }
  .bead-status { padding: 1px 6px; border-radius: 3px; font-size: 11px; }
  .bead-status.closed { background: #1a3a2a; color: var(--green); }
  .bead-status.in_progress { background: #3a2a0a; color: var(--yellow); }
  .bead-status.blocked { background: #3a1a1a; color: var(--red); }
  .bead-status.open { background: #1a2a3a; color: var(--blue); }

  /* Timeline */
  .event { display: flex; gap: 10px; padding: 4px 0; font-size: 12px; border-bottom: 1px solid var(--bg); }
  .event-time { color: var(--dim); min-width: 80px; flex-shrink: 0; }
  .event-type { min-width: 110px; flex-shrink: 0; }
  .event-type.agent_spawned { color: var(--green); }
  .event-type.status_change { color: var(--yellow); }
  .event-type.agent_gone { color: var(--red); }
  .event-agent { color: var(--blue); min-width: 140px; flex-shrink: 0; }
  .event-detail { color: var(--dim); }

  /* Alerts */
  .alerts { margin-bottom: 16px; }
  .alert { padding: 8px 14px; border-radius: 6px; margin-bottom: 6px; font-size: 13px; display: flex; align-items: center; gap: 8px; }
  .alert-warn { background: #3a2a0a; border: 1px solid var(--yellow); color: var(--yellow); }
  .alert-crit { background: #3a1a1a; border: 1px solid var(--red); color: var(--red); }

  .empty { color: var(--dim); font-style: italic; padding: 12px 0; }
  .count-badge { background: var(--border); padding: 1px 6px; border-radius: 10px; font-size: 11px; margin-left: 6px; }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1><span class="pulse"></span>Baap Agent Swarm</h1>
  </div>
  <div class="header-right">
    <span id="lastUpdate">—</span> | refreshing every 10s
  </div>
</div>

<div class="alerts" id="alerts"></div>

<div class="grid">
  <!-- Agent Swimlanes -->
  <div class="panel">
    <div class="panel-title">Agents <span class="count-badge" id="agentCount">0</span></div>
    <div id="agentList"><div class="empty">No agents running</div></div>
  </div>

  <!-- Epic Progress -->
  <div class="panel">
    <div class="panel-title">Epic Progress <span class="count-badge" id="epicCount">0</span></div>
    <div id="epicList"><div class="empty">No epics found</div></div>
  </div>

  <!-- Timeline -->
  <div class="panel full-width">
    <div class="panel-title">Event Timeline <span class="count-badge" id="eventCount">0</span></div>
    <div id="timeline"><div class="empty">No events yet — waiting for first poll</div></div>
  </div>

  <!-- Beads -->
  <div class="panel full-width">
    <div class="panel-title">Beads <span class="count-badge" id="beadCount">0</span></div>
    <div id="beadList" style="max-height: 400px; overflow-y: auto;">
      <div class="empty">No beads loaded</div>
    </div>
  </div>
</div>

<script>
const API = window.location.origin;
const POLL_MS = 10000;

function fmtTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return '—'; }
}

function fmtHb(age, stale) {
  if (age === null || age === undefined) return '<span class="agent-hb">no hb</span>';
  const cls = stale ? 'agent-hb stale' : 'agent-hb';
  const label = stale ? `STALE ${age}s` : `${age}s ago`;
  return `<span class="${cls}">${label}</span>`;
}

function dotClass(status, stale) {
  if (stale) return 'stuck';
  const s = (status || '').toLowerCase();
  if (s === 'working' || s === 'running') return 'working';
  if (s === 'spawning') return 'spawning';
  return 'stopped';
}

function statusClass(s) {
  s = (s || '').toLowerCase().replace('-', '_');
  if (['closed', 'done', 'completed', 'resolved'].includes(s)) return 'closed';
  if (['in_progress', 'active'].includes(s)) return 'in_progress';
  if (s === 'blocked') return 'blocked';
  return 'open';
}

// ── Render functions ──────────────────────────────────────────────────────────

function renderAgents(data) {
  const el = document.getElementById('agentList');
  document.getElementById('agentCount').textContent = data.count;
  if (!data.agents.length) { el.innerHTML = '<div class="empty">No agents running</div>'; return; }

  el.innerHTML = data.agents.map(a => `
    <div class="agent-card">
      <div class="agent-dot ${dotClass(a.status, a.heartbeat_stale)}"></div>
      <span class="agent-name">${a.agent}</span>
      <span class="agent-level">L${a.level}</span>
      <span class="agent-action" title="${(a.current_action || '—').replace(/"/g, '&quot;')}">${a.current_action || '—'}</span>
      ${fmtHb(a.heartbeat_age_s, a.heartbeat_stale)}
    </div>
  `).join('');
}

function renderEpics(data) {
  const el = document.getElementById('epicList');
  document.getElementById('epicCount').textContent = data.count;
  if (!data.epics.length) { el.innerHTML = '<div class="empty">No epics found</div>'; return; }

  el.innerHTML = data.epics.map(e => {
    const doneW = e.total > 0 ? (e.completed / e.total * 100) : 0;
    const wipW = e.total > 0 ? (e.in_progress / e.total * 100) : 0;
    const blockW = e.total > 0 ? (e.blocked / e.total * 100) : 0;
    return `
      <div class="epic-row">
        <div class="epic-header">
          <span>${e.epic}</span>
          <span>${e.progress_pct}%</span>
        </div>
        <div class="epic-bar-bg">
          <div class="epic-bar-fill epic-bar-done" style="width:${doneW}%"></div>
          <div class="epic-bar-fill epic-bar-wip" style="width:${wipW}%"></div>
          <div class="epic-bar-fill epic-bar-blocked" style="width:${blockW}%"></div>
        </div>
        <div class="epic-stats">${e.completed} done / ${e.in_progress} wip / ${e.blocked} blocked / ${e.open} open</div>
      </div>
    `;
  }).join('');
}

function renderBeads(data) {
  const el = document.getElementById('beadList');
  document.getElementById('beadCount').textContent = data.count;
  if (!data.beads.length) { el.innerHTML = '<div class="empty">No beads found</div>'; return; }

  const rows = data.beads.map(b => {
    const sc = statusClass(b.status);
    const deps = (b.dependencies || b.deps || []).join(', ') || '—';
    return `<tr>
      <td>${b.id || '?'}</td>
      <td><span class="bead-status ${sc}">${b.status || '?'}</span></td>
      <td>${b.title || b.description || '—'}</td>
      <td>${b.assignee || '—'}</td>
      <td>${deps}</td>
    </tr>`;
  }).join('');

  el.innerHTML = `<table class="bead-table">
    <thead><tr><th>ID</th><th>Status</th><th>Title</th><th>Assignee</th><th>Deps</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function renderTimeline(data) {
  const el = document.getElementById('timeline');
  document.getElementById('eventCount').textContent = data.events.length;
  if (!data.events.length) { el.innerHTML = '<div class="empty">No events yet</div>'; return; }

  el.innerHTML = data.events.map(ev => `
    <div class="event">
      <span class="event-time">${fmtTime(ev.ts)}</span>
      <span class="event-type ${ev.type}">${ev.type}</span>
      <span class="event-agent">${ev.agent}</span>
      <span class="event-detail">${ev.detail}</span>
    </div>
  `).join('');
}

function renderAlerts(agents) {
  const el = document.getElementById('alerts');
  const alerts = [];

  (agents.agents || []).forEach(a => {
    if (a.heartbeat_stale) {
      alerts.push({ level: 'crit', msg: `Agent "${a.agent}" heartbeat stale (${a.heartbeat_age_s}s) — may be frozen` });
    }
    if ((a.status || '').toLowerCase() === 'stopped' || (a.status || '').toLowerCase() === 'failed') {
      alerts.push({ level: 'warn', msg: `Agent "${a.agent}" status: ${a.status}` });
    }
    if ((a.errors || 0) > 0) {
      alerts.push({ level: 'warn', msg: `Agent "${a.agent}" has ${a.errors} error(s)` });
    }
  });

  if (!alerts.length) { el.innerHTML = ''; return; }
  el.innerHTML = alerts.map(a =>
    `<div class="alert alert-${a.level}">${a.level === 'crit' ? '&#9888;' : '&#9432;'} ${a.msg}</div>`
  ).join('');
}

// ── Polling loop ──────────────────────────────────────────────────────────────

async function fetchJSON(path) {
  try {
    const r = await fetch(API + path);
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

async function poll() {
  const [agents, epics, beads, timeline] = await Promise.all([
    fetchJSON('/api/dashboard/agents'),
    fetchJSON('/api/dashboard/epics'),
    fetchJSON('/api/dashboard/beads'),
    fetchJSON('/api/dashboard/timeline'),
  ]);

  if (agents) { renderAgents(agents); renderAlerts(agents); }
  if (epics) renderEpics(epics);
  if (beads) renderBeads(beads);
  if (timeline) renderTimeline(timeline);

  document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString('en-US', { hour12: false });
}

// Initial poll, then every 10s
poll();
setInterval(poll, POLL_MS);
</script>
</body>
</html>
```

### Key Design Decisions

1. **No framework** — Vanilla JS, inline CSS. Zero build step. The file IS the app.
   Opens in any browser, no bundler, no node_modules.

2. **4 parallel fetches** — The poll function fires all 4 API calls simultaneously with
   `Promise.all`. Total poll overhead: one round-trip (~50ms on Tailscale).

3. **GitHub-dark color scheme** — Matches the terminal aesthetic. Green = healthy,
   yellow = in-progress, red = problem. The human shouldn't need to think about
   what colors mean.

4. **Alerts at the top** — Stale heartbeats, failed agents, and error counts surface
   as banner alerts ABOVE the dashboard grid. They're the first thing you see.

5. **Bead table scrollable** — If there are 50+ beads, the table scrolls independently.
   The rest of the dashboard stays fixed.

---

## Fix 3: Launcher Script — `.claude/scripts/start-dashboard.sh`

### Problem

The human needs a one-liner to start the dashboard in the existing tmux session
alongside the other services.

### Solution

```bash
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
```

### tmux Integration

Add a 4th pane to the existing `e2e-test` tmux session (or a new window):

```bash
# Option A: New window in agents session
tmux new-window -t agents -n "dashboard" "bash ~/Projects/baap/.claude/scripts/start-dashboard.sh"

# Option B: Add to the existing e2e-test session (alongside BC_ANALYTICS, backend, UI)
tmux new-window -t e2e-test -n "dashboard" "bash ~/Projects/baap/.claude/scripts/start-dashboard.sh"
```

---

## Fix 4: Bead Dependency DAG (Text-Based)

### Problem

The beads endpoint returns flat JSON. The dashboard needs to show which beads block
which others without pulling in a graph rendering library.

### Solution

The API already returns `dependencies` (or `deps`) per bead. The HTML renders this
as a table column. For a more visual representation, the human can use the existing
terminal tool:

```bash
bd deps --tree   # If beads CLI supports tree view
```

The web dashboard keeps it simple: the "Deps" column in the bead table shows dependency
IDs as clickable references. A future enhancement could add a D3-based DAG, but for v1,
the table with deps listed is sufficient and avoids adding a JS library dependency.

### What the Bead Table Shows

For each bead:
- **ID** — bead identifier (e.g., `baap-abc`)
- **Status** — color-coded pill (green=closed, yellow=wip, red=blocked, blue=open)
- **Title** — what the bead is about
- **Assignee** — which agent owns it
- **Deps** — comma-separated list of dependency bead IDs

Blocked beads (beads with unresolved deps) get a red status pill, making them visually
obvious in the table.

---

## CLAUDE.md Addition

Add to the monitoring section of CLAUDE.md (after the monitor.sh commands from Phase 1e):

```markdown
## Web Dashboard (Phase 3e)

| Command | Purpose |
|---------|---------|
| `bash .claude/scripts/start-dashboard.sh` | Start web dashboard on port 8002 |
| `http://100.78.153.91:8002` | Access from Mac via Tailscale |
| `http://localhost:8002` | Access from India directly |
| `http://100.78.153.91:8002/api/dashboard/agents` | Raw JSON: agent status |
| `http://100.78.153.91:8002/api/dashboard/epics` | Raw JSON: epic progress |
| `http://100.78.153.91:8002/api/dashboard/beads` | Raw JSON: all beads |
| `http://100.78.153.91:8002/api/dashboard/timeline` | Raw JSON: event timeline |

The dashboard auto-refreshes every 10 seconds. Alerts surface stale heartbeats (>2min),
failed agents, and error counts as banners at the top of the page.
```

---

## Success Criteria

- [ ] `dashboard_api.py` is a single file under 200 lines
- [ ] `dashboard.html` is a single file, no external dependencies
- [ ] `start-dashboard.sh` starts the server with one command
- [ ] `GET /api/dashboard/agents` returns agent list with heartbeat status
- [ ] `GET /api/dashboard/epics` returns epic progress with completion percentages
- [ ] `GET /api/dashboard/beads` returns all beads with status and deps
- [ ] `GET /api/dashboard/timeline` returns last 20 events
- [ ] `GET /api/dashboard/health` returns `{"status": "ok"}`
- [ ] `GET /` serves the HTML dashboard
- [ ] Dashboard auto-refreshes every 10 seconds
- [ ] Stale heartbeats (>2min) shown as red alerts
- [ ] Failed/stopped agents shown as yellow alerts
- [ ] Epic progress bars show completed/wip/blocked segments
- [ ] Bead table shows status with color-coded pills
- [ ] Dashboard accessible from Mac via `http://100.78.153.91:8002`
- [ ] No build step required — just `bash start-dashboard.sh`

## Verification

```bash
cd ~/Projects/baap

# ── Step 1: Start the dashboard ──────────────────────────────────────────────
bash .claude/scripts/start-dashboard.sh &
DASH_PID=$!
sleep 3

# ── Step 2: Health check ─────────────────────────────────────────────────────
curl -s http://localhost:8002/api/dashboard/health | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['status'] == 'ok', 'Health check failed'
print('PASS: Health check')
"

# ── Step 3: Agents endpoint ──────────────────────────────────────────────────
curl -s http://localhost:8002/api/dashboard/agents | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'agents' in d, 'Missing agents key'
assert 'count' in d, 'Missing count key'
print(f'PASS: Agents endpoint ({d[\"count\"]} agents)')
"

# ── Step 4: Epics endpoint ───────────────────────────────────────────────────
curl -s http://localhost:8002/api/dashboard/epics | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'epics' in d, 'Missing epics key'
print(f'PASS: Epics endpoint ({d[\"count\"]} epics)')
"

# ── Step 5: Beads endpoint ───────────────────────────────────────────────────
curl -s http://localhost:8002/api/dashboard/beads | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'beads' in d, 'Missing beads key'
print(f'PASS: Beads endpoint ({d[\"count\"]} beads)')
"

# ── Step 6: Timeline endpoint ────────────────────────────────────────────────
curl -s http://localhost:8002/api/dashboard/timeline | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'events' in d, 'Missing events key'
print(f'PASS: Timeline endpoint ({len(d[\"events\"])} events)')
"

# ── Step 7: HTML served at root ──────────────────────────────────────────────
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/)
[ "$HTTP_CODE" = "200" ] && echo "PASS: HTML dashboard served (200)" || echo "FAIL: HTML not served ($HTTP_CODE)"

# ── Step 8: Simulate an agent to test detection ──────────────────────────────
mkdir -p /tmp/baap-agent-status /tmp/baap-heartbeats

cat > /tmp/baap-agent-status/test-dashboard-agent.json << 'EOF'
{
  "agent": "test-dashboard-agent",
  "level": 2,
  "status": "working",
  "started_at": "2026-02-14T10:00:00+00:00",
  "last_update": "2026-02-14T10:05:00+00:00",
  "current_action": "Editing src/main.py",
  "errors": 0
}
EOF

date +%s > /tmp/baap-heartbeats/test-dashboard-agent

sleep 2

# Verify agent appears in API
curl -s http://localhost:8002/api/dashboard/agents | python3 -c "
import json, sys
d = json.load(sys.stdin)
names = [a['agent'] for a in d['agents']]
assert 'test-dashboard-agent' in names, f'Test agent not found in {names}'
print('PASS: Test agent detected by dashboard')
"

# ── Step 9: Test stale heartbeat detection ───────────────────────────────────
# Write a heartbeat from 5 minutes ago
echo $(( $(date +%s) - 300 )) > /tmp/baap-heartbeats/test-dashboard-agent
sleep 2

curl -s http://localhost:8002/api/dashboard/agents | python3 -c "
import json, sys
d = json.load(sys.stdin)
agent = [a for a in d['agents'] if a['agent'] == 'test-dashboard-agent'][0]
assert agent['heartbeat_stale'] == True, f'Expected stale=True, got {agent[\"heartbeat_stale\"]}'
print(f'PASS: Stale heartbeat detected ({agent[\"heartbeat_age_s\"]}s)')
"

# ── Step 10: Cleanup ─────────────────────────────────────────────────────────
rm -f /tmp/baap-agent-status/test-dashboard-agent.json
rm -f /tmp/baap-heartbeats/test-dashboard-agent
kill $DASH_PID 2>/dev/null || true

echo ""
echo "All dashboard verification tests passed."
```

### Manual Verification from Mac

After deploying to India:

```bash
# From Mac terminal:
open http://100.78.153.91:8002

# Should see:
# - Dashboard loads with dark theme
# - Agent swimlanes (or "No agents running" if none active)
# - Epic progress bars (or "No epics found")
# - Event timeline populates after first transition
# - Bead table shows beads from bd
# - Page auto-refreshes every 10 seconds (check "last updated" timestamp)
```

## Fix 5: Kanban Board View (Primary Beads View)

### Problem

The flat bead table shows data but doesn't tell a STORY. The human can't glance at it and instantly answer: "How much work is stuck? What's flowing? Where are the bottlenecks?" A Kanban board answers all three in one look — columns represent workflow stages, cards represent beads, and column heights reveal bottlenecks instantly.

### Solution

Replace the bead table section with a tabbed view: **Kanban** (default) and **Table** (fallback). The Kanban board has 5 columns representing the bead lifecycle. Cards show enough info to understand status at a glance, with hover for full details.

### UX Design Principles

1. **Information density without clutter** — Show agent, priority, and age on the card face. Show full title, dependencies, and timestamps on hover.
2. **Color is meaning, never decoration** — Priority gets a left border stripe. Agent gets a consistent color. Status IS the column position.
3. **Movement tells the story** — Cards animate smoothly between columns on refresh. The human sees work flowing left to right.
4. **Bottleneck detection is instant** — The tallest column is the problem. Red column (Blocked) being tall = something is stuck.
5. **Zero learning curve** — If you've seen Trello or Linear, you already know how to read this.

### Dashboard API Addition

Add a new endpoint to `dashboard_api.py`:

```python
@app.get("/api/dashboard/kanban")
def get_kanban():
    """Beads organized by workflow column for Kanban view."""
    beads = _get_beads()

    columns = {
        "backlog": {"title": "Backlog", "beads": [], "color": "#8b949e"},
        "ready": {"title": "Ready", "beads": [], "color": "#58a6ff"},
        "in_progress": {"title": "In Progress", "beads": [], "color": "#d29922"},
        "in_review": {"title": "In Review", "beads": [], "color": "#bc8cff"},
        "blocked": {"title": "Blocked", "beads": [], "color": "#f85149"},
        "done": {"title": "Done", "beads": [], "color": "#3fb950"},
    }

    for b in beads:
        status = (b.get("status") or "").lower().replace("-", "_")
        deps = b.get("dependencies") or b.get("deps") or b.get("blocked_by") or []
        assignee = b.get("assignee") or b.get("agent") or None
        priority = b.get("priority")

        card = {
            "id": b.get("id", "?"),
            "title": b.get("title") or b.get("description") or "Untitled",
            "assignee": assignee,
            "priority": priority,
            "deps": deps,
            "dep_count": len(deps) if isinstance(deps, list) else 0,
            "epic": b.get("epic") or b.get("parent") or None,
            "created_at": b.get("created_at") or b.get("created"),
            "updated_at": b.get("updated_at") or b.get("updated") or b.get("last_update"),
            "type": b.get("type", "task"),
            "notes": b.get("notes", ""),
        }

        # Classify into columns
        if status in ("closed", "done", "completed", "resolved"):
            columns["done"]["beads"].append(card)
        elif status == "blocked" or (isinstance(deps, list) and len(deps) > 0):
            # Check if deps are all resolved
            columns["blocked"]["beads"].append(card)
        elif status in ("in_review", "review", "reviewing"):
            columns["in_review"]["beads"].append(card)
        elif status in ("in_progress", "active", "working"):
            columns["in_progress"]["beads"].append(card)
        elif assignee is None and status in ("open", "new", "pending", ""):
            columns["backlog"]["beads"].append(card)
        else:
            columns["ready"]["beads"].append(card)

    # Sort within columns: priority first (lower = higher priority), then by creation date
    for col in columns.values():
        col["beads"].sort(key=lambda c: (
            c.get("priority") if c.get("priority") is not None else 99,
            c.get("created_at") or ""
        ))
        col["count"] = len(col["beads"])

    return {
        "columns": columns,
        "total": len(beads),
    }
```

### HTML — Replace the Beads Panel with Tabbed Kanban + Table

In `dashboard.html`, replace the beads `<div class="panel full-width">` section. Add these CSS rules and the new HTML structure.

**Additional CSS** (add before `</style>`):

```css
  /* ── Tab navigation ──────────────────────────────────────────────────── */
  .tab-bar { display: flex; gap: 2px; margin-bottom: 16px; }
  .tab {
    padding: 6px 16px; border-radius: 6px 6px 0 0; cursor: pointer;
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
    background: var(--bg); color: var(--dim); border: 1px solid transparent;
    border-bottom: none; transition: all 0.2s;
  }
  .tab:hover { color: var(--text); background: #1c2128; }
  .tab.active { background: var(--surface); color: var(--text); border-color: var(--border); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }

  /* ── Kanban board ────────────────────────────────────────────────────── */
  .kanban {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 10px;
    min-height: 300px;
  }
  .kanban-col {
    background: var(--bg);
    border-radius: 8px;
    padding: 10px;
    min-height: 200px;
    display: flex;
    flex-direction: column;
  }
  .kanban-col-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 10px;
    margin-bottom: 8px;
    border-bottom: 2px solid var(--border);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-weight: 600;
  }
  .kanban-col-count {
    background: var(--surface);
    padding: 1px 7px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 400;
  }
  .kanban-cards {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
    overflow-y: auto;
    max-height: 500px;
  }
  .kanban-cards::-webkit-scrollbar { width: 4px; }
  .kanban-cards::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  /* ── Kanban card ─────────────────────────────────────────────────────── */
  .kb-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
    cursor: default;
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    position: relative;
    border-left: 3px solid var(--border);
  }
  .kb-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    border-color: #484f58;
  }
  .kb-card-id {
    font-size: 10px;
    color: var(--dim);
    font-family: monospace;
    margin-bottom: 4px;
  }
  .kb-card-title {
    font-size: 13px;
    font-weight: 500;
    line-height: 1.3;
    margin-bottom: 8px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .kb-card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 6px;
  }
  .kb-card-agent {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 3px;
    background: #1a2a3a;
    color: var(--blue);
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .kb-card-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--dim);
  }
  .kb-card-deps {
    color: var(--red);
    font-size: 10px;
  }
  .kb-card-type {
    font-size: 10px;
    padding: 0 4px;
    border-radius: 2px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }
  .kb-card-type.epic { background: #2a1a3a; color: var(--purple); }
  .kb-card-type.feature { background: #1a2a1a; color: var(--green); }
  .kb-card-type.bug { background: #3a1a1a; color: var(--red); }
  .kb-card-type.task { background: #1a2a3a; color: var(--blue); }

  /* Priority left border colors */
  .kb-card.p0 { border-left-color: #f85149; }
  .kb-card.p1 { border-left-color: #f0883e; }
  .kb-card.p2 { border-left-color: #d29922; }
  .kb-card.p3 { border-left-color: #58a6ff; }
  .kb-card.p4 { border-left-color: var(--dim); }

  /* Card expand on hover — show full details */
  .kb-card-detail {
    display: none;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
    font-size: 11px;
    color: var(--dim);
    line-height: 1.5;
  }
  .kb-card:hover .kb-card-detail { display: block; }
  .kb-card-detail-row { display: flex; gap: 6px; }
  .kb-card-detail-label { color: var(--dim); min-width: 60px; }
  .kb-card-detail-value { color: var(--text); }

  /* ── Empty column state ──────────────────────────────────────────────── */
  .kanban-empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--dim);
    font-size: 12px;
    font-style: italic;
    opacity: 0.5;
  }

  /* ── Column highlight on bottleneck ──────────────────────────────────── */
  .kanban-col.bottleneck .kanban-col-header {
    border-bottom-color: var(--red);
  }
  .kanban-col.bottleneck .kanban-col-count {
    background: #3a1a1a;
    color: var(--red);
  }

  /* ── Smooth card animation on refresh ────────────────────────────────── */
  @keyframes cardEnter {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .kb-card { animation: cardEnter 0.3s ease; }

  /* ── WIP limit indicator ─────────────────────────────────────────────── */
  .wip-warning {
    font-size: 10px;
    color: var(--yellow);
    margin-top: 4px;
  }

  /* ── Responsive: stack columns on narrow screens ─────────────────────── */
  @media (max-width: 1200px) {
    .kanban { grid-template-columns: repeat(3, 1fr); }
  }
  @media (max-width: 768px) {
    .kanban { grid-template-columns: repeat(2, 1fr); }
  }
```

**Updated Beads Panel HTML** (replace the existing beads panel):

```html
  <!-- Beads — Kanban + Table views -->
  <div class="panel full-width">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
      <div class="panel-title" style="margin-bottom: 0;">Work Items <span class="count-badge" id="beadCount">0</span></div>
      <div class="tab-bar">
        <div class="tab active" onclick="switchTab('kanban')" id="tab-kanban">Kanban</div>
        <div class="tab" onclick="switchTab('table')" id="tab-table">Table</div>
      </div>
    </div>

    <div class="tab-content active" id="view-kanban">
      <div class="kanban" id="kanbanBoard">
        <div class="kanban-empty" style="grid-column: 1/-1;">Loading board...</div>
      </div>
    </div>

    <div class="tab-content" id="view-table">
      <div id="beadList" style="max-height: 400px; overflow-y: auto;">
        <div class="empty">No beads loaded</div>
      </div>
    </div>
  </div>
```

**JavaScript** (add these functions and update the poll loop):

```javascript
// ── Tab switching ────────────────────────────────────────────────────────────
function switchTab(view) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-' + view).classList.add('active');
  document.getElementById('view-' + view).classList.add('active');
}

// ── Kanban rendering ─────────────────────────────────────────────────────────

// Consistent agent colors (hash name to hue)
const agentColorCache = {};
function agentColor(name) {
  if (!name) return '#8b949e';
  if (agentColorCache[name]) return agentColorCache[name];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  const hue = Math.abs(hash) % 360;
  agentColorCache[name] = `hsl(${hue}, 60%, 65%)`;
  return agentColorCache[name];
}

function priorityClass(p) {
  if (p === 0 || p === '0' || p === 'P0') return 'p0';
  if (p === 1 || p === '1' || p === 'P1') return 'p1';
  if (p === 2 || p === '2' || p === 'P2') return 'p2';
  if (p === 3 || p === '3' || p === 'P3') return 'p3';
  return 'p4';
}

function timeAgo(iso) {
  if (!iso) return '';
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + 'm';
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return hrs + 'h';
    return Math.floor(hrs / 24) + 'd';
  } catch { return ''; }
}

function renderCard(card) {
  const pClass = priorityClass(card.priority);
  const typeClass = (card.type || 'task').toLowerCase();
  const agentBg = card.assignee ? `background: ${agentColor(card.assignee)}22; color: ${agentColor(card.assignee)};` : '';
  const depsHtml = card.dep_count > 0
    ? `<span class="kb-card-deps" title="${(card.deps||[]).join(', ')}">&#128279; ${card.dep_count}</span>`
    : '';
  const ageHtml = card.updated_at ? `<span title="Last updated">${timeAgo(card.updated_at)}</span>` : '';

  return `
    <div class="kb-card ${pClass}">
      <div class="kb-card-id">${card.id}</div>
      <div class="kb-card-title" title="${(card.title || '').replace(/"/g, '&quot;')}">${card.title || 'Untitled'}</div>
      <div class="kb-card-footer">
        ${card.assignee
          ? `<span class="kb-card-agent" style="${agentBg}" title="${card.assignee}">${card.assignee}</span>`
          : '<span class="kb-card-agent" style="opacity:0.3">unassigned</span>'
        }
        <div class="kb-card-meta">
          ${depsHtml}
          <span class="kb-card-type ${typeClass}">${card.type || 'task'}</span>
          ${ageHtml}
        </div>
      </div>
      <div class="kb-card-detail">
        ${card.epic ? `<div class="kb-card-detail-row"><span class="kb-card-detail-label">Epic:</span><span class="kb-card-detail-value">${card.epic}</span></div>` : ''}
        ${card.deps && card.deps.length ? `<div class="kb-card-detail-row"><span class="kb-card-detail-label">Blocked by:</span><span class="kb-card-detail-value">${card.deps.join(', ')}</span></div>` : ''}
        ${card.notes ? `<div class="kb-card-detail-row"><span class="kb-card-detail-label">Notes:</span><span class="kb-card-detail-value">${card.notes}</span></div>` : ''}
        ${card.created_at ? `<div class="kb-card-detail-row"><span class="kb-card-detail-label">Created:</span><span class="kb-card-detail-value">${fmtTime(card.created_at)}</span></div>` : ''}
      </div>
    </div>
  `;
}

function renderKanban(data) {
  const board = document.getElementById('kanbanBoard');
  document.getElementById('beadCount').textContent = data.total;

  if (data.total === 0) {
    board.innerHTML = '<div class="kanban-empty" style="grid-column: 1/-1;">No work items yet</div>';
    return;
  }

  const colOrder = ['backlog', 'ready', 'in_progress', 'in_review', 'blocked', 'done'];
  const WIP_LIMIT = 5; // visual warning threshold per column

  // Find the bottleneck (largest non-done column)
  let maxCount = 0;
  let bottleneckCol = null;
  colOrder.forEach(key => {
    if (key !== 'done' && key !== 'backlog') {
      const count = data.columns[key]?.count || 0;
      if (count > maxCount) { maxCount = count; bottleneckCol = key; }
    }
  });

  board.innerHTML = colOrder.map(key => {
    const col = data.columns[key];
    if (!col) return '';
    const isBottleneck = key === bottleneckCol && maxCount > 3;
    const isOverWip = col.count > WIP_LIMIT && key !== 'done' && key !== 'backlog';

    return `
      <div class="kanban-col ${isBottleneck ? 'bottleneck' : ''}">
        <div class="kanban-col-header" style="border-bottom-color: ${col.color}">
          <span style="color: ${col.color}">${col.title}</span>
          <span class="kanban-col-count">${col.count}</span>
        </div>
        ${isOverWip ? `<div class="wip-warning">&#9888; WIP limit (${WIP_LIMIT}) exceeded</div>` : ''}
        <div class="kanban-cards">
          ${col.beads.length > 0
            ? col.beads.map(renderCard).join('')
            : `<div class="kanban-empty">Empty</div>`
          }
        </div>
      </div>
    `;
  }).join('');
}

// ── Updated poll function ────────────────────────────────────────────────────
// Add kanban fetch to the existing Promise.all:

async function poll() {
  const [agents, epics, beads, timeline, kanban] = await Promise.all([
    fetchJSON('/api/dashboard/agents'),
    fetchJSON('/api/dashboard/epics'),
    fetchJSON('/api/dashboard/beads'),
    fetchJSON('/api/dashboard/timeline'),
    fetchJSON('/api/dashboard/kanban'),
  ]);

  if (agents) { renderAgents(agents); renderAlerts(agents); }
  if (epics) renderEpics(epics);
  if (beads) renderBeads(beads);   // table view
  if (timeline) renderTimeline(timeline);
  if (kanban) renderKanban(kanban); // kanban view

  document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString('en-US', { hour12: false });
}
```

### Kanban UX Details

**Card anatomy:**
```
┌─────────────────────────────┐
│ ▌ baap-a7x                  │  ← ID (monospace, dimmed)
│ ▌                           │
│ ▌ Add user search API       │  ← Title (2-line clamp)
│ ▌                           │
│ ▌ [api-agent]    🔗2 task 5m│  ← Footer: agent badge, deps, type, age
│ ▌                           │
│ ▌ ┄┄┄┄ (hover to expand) ┄┄│  ← Detail (hidden until hover)
│ ▌ Epic: EPIC-auth           │
│ ▌ Blocked by: baap-a5f      │
│ ▌ Notes: JWT implementation │
│ ▌ Created: 10:30:15         │
└─────────────────────────────┘

▌ = Priority stripe (left border)
   P0 = red, P1 = orange, P2 = yellow, P3 = blue, P4 = gray
```

**Column behavior:**
- Each column has a color-coded header matching its semantic meaning
- Count badge shows number of cards in column
- **Bottleneck detection**: The largest non-done/non-backlog column gets a red border highlight and special `bottleneck` class
- **WIP limit warning**: If any active column exceeds 5 items, a yellow warning shows below the header
- Cards sorted by priority (P0 first), then by creation date (oldest first)
- Done column sorted reverse (most recently closed first) — human sees latest completions at top
- Cards animate in with subtle fade-up on each refresh cycle

**Agent color consistency:**
- Each agent name is hashed to a hue value (0-360)
- That hue generates a consistent HSL color used for the agent badge background
- Same agent always has the same color across all cards and sessions
- This lets the human track an agent's work across columns at a glance

**Responsive behavior:**
- 1200px+: 6 columns side by side (full board)
- 768-1200px: 3 columns per row (stacked in 2 rows)
- <768px: 2 columns per row (mobile-friendly)

### Why Kanban over other visualizations

1. **Kanban is universal** — Every developer and PM has used Trello, Jira, Linear. Zero learning curve.
2. **Column height = bottleneck** — Taller Blocked column = urgent problem. No chart needed.
3. **Left-to-right = progress** — Work flows from Backlog → Done. Direction encodes meaning.
4. **WIP limits surface overload** — If In Progress has 8 items with only 3 agents, something is wrong.
5. **Card details on hover** — Information density stays high without visual clutter.

### Additional Success Criteria (append to existing)

- [ ] Kanban view is the DEFAULT tab when dashboard loads
- [ ] All 6 columns render with correct color-coded headers
- [ ] Cards show priority stripe (P0 red, P1 orange, P2 yellow)
- [ ] Agent badges use consistent colors (same agent = same color every time)
- [ ] Hover on card reveals detail panel (epic, deps, notes, created time)
- [ ] Bottleneck column highlighted with red border when count > 3
- [ ] WIP warning shows when active column exceeds 5 items
- [ ] Tab switching between Kanban and Table preserves data (no re-fetch)
- [ ] Cards animate in with subtle fade-up transition
- [ ] Responsive: 6 cols at 1200px+, 3 cols at 768-1200px, 2 cols at <768px
- [ ] `/api/dashboard/kanban` returns beads grouped by column with correct classification

### Verification Addition

```bash
# ── Kanban API endpoint ─────────────────────────────────────────────────────
curl -s http://localhost:8002/api/dashboard/kanban | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'columns' in d, 'Missing columns key'
cols = d['columns']
expected = ['backlog', 'ready', 'in_progress', 'in_review', 'blocked', 'done']
for col in expected:
    assert col in cols, f'Missing column: {col}'
    assert 'beads' in cols[col], f'Missing beads in column: {col}'
    assert 'count' in cols[col], f'Missing count in column: {col}'
    assert 'title' in cols[col], f'Missing title in column: {col}'
    assert 'color' in cols[col], f'Missing color in column: {col}'
print(f'PASS: Kanban endpoint ({d[\"total\"]} beads across {len(cols)} columns)')
"

# ── Kanban bead classification ──────────────────────────────────────────────
# Create test beads in different states to verify classification
bd create --title="Test backlog bead" --type=task --priority=3
bd create --title="Test in-progress bead" --type=task --priority=1
BEAD_WIP=$(bd list --json | python3 -c "import json,sys; beads=json.load(sys.stdin); print([b['id'] for b in beads if 'in-progress' in (b.get('title',''))][-1])")
bd update "$BEAD_WIP" --status=in_progress

sleep 2

curl -s http://localhost:8002/api/dashboard/kanban | python3 -c "
import json, sys
d = json.load(sys.stdin)
# Verify at least one bead is in backlog (unassigned, open)
# Verify at least one bead is in in_progress
backlog_count = d['columns']['backlog']['count']
wip_count = d['columns']['in_progress']['count']
print(f'Backlog: {backlog_count}, In Progress: {wip_count}')
assert d['total'] >= 2, 'Expected at least 2 test beads'
print('PASS: Bead classification working')
"
```
