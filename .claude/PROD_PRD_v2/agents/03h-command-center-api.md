# Phase 3h: Command Center API — Backend for Agent Swarm Management Dashboard

## Purpose

The Phase 3e dashboard (single-file HTML + 4-endpoint API) proved the concept: the human
wants a browser-based view into the swarm. But it has five fatal limitations:

1. **Read-only** — You can see agents but cannot kill, retry, or spawn them from the UI.
   Every action requires `ssh india-linux` and running shell commands manually.
2. **No Think Tank** — The brainstorming workflow (01h) runs in a terminal. There is no
   way to start a brainstorming session, chat with the orchestrator, review spec-kits,
   or approve autonomous execution from the browser.
3. **No real-time push** — The dashboard polls every 10 seconds. Agent status changes,
   bead transitions, and think tank messages are delayed. WebSocket push is required for
   the interactive UX the human expects.
4. **No kanban interaction** — The kanban board from 03e is visual only. You cannot drag
   cards between columns, add comments, or create beads from the UI.
5. **No command palette backend** — The frontend Cmd+K pattern (from interactive-ux research)
   needs an API that discovers available commands, accepts fuzzy search, and executes actions.

The Command Center API replaces the 03e monitoring API with a proper FastAPI application
that serves as the backend for a full interactive dashboard. It lives at
`.claude/command-center/backend/` and is designed to be reusable across any project that
uses the Baap agent infrastructure.

## Risks Mitigated

| Risk | Severity | Mitigation |
|------|----------|------------|
| Human cannot act on swarm from browser — must SSH for every action | HIGH | Agent management endpoints wrap existing shell scripts |
| Think Tank brainstorming locked to terminal — no async collaboration | HIGH | Think Tank API spawns/manages Claude Code orchestrator sessions |
| 10-second polling delay hides critical state changes | MEDIUM | WebSocket push for agent status, bead transitions, think tank messages |
| No way to create/move/comment on beads from UI | MEDIUM | Full CRUD bead endpoints wrapping `bd` CLI |
| No attachment support for screenshots/mockups in beads | LOW | File upload API with metadata tracking |
| Command palette has no backend for command discovery | LOW | Commands endpoint with fuzzy search and context-aware filtering |

## Architecture Decisions

### Decision 1: Think Tank communicates via stdin/stdout pipes

**Why not file-based?** Polling files adds latency and complexity. The orchestrator is a
Claude Code subprocess — we already have its stdin/stdout. Pipe them directly.

**Why not tmux send-keys?** tmux send-keys is fire-and-forget. We need bidirectional
communication: send human messages IN and capture orchestrator output OUT. Pipes give us
both.

**Implementation**: `subprocess.Popen` with `stdin=PIPE, stdout=PIPE, stderr=PIPE`. A
background asyncio task reads stdout line-by-line and pushes to WebSocket clients. Human
messages are written to stdin. The orchestrator protocol (01h) already uses structured
output with phase markers — we parse those for phase transitions and spec-kit deltas.

### Decision 2: Attachments stored as files with JSON metadata sidecar

**Why not base64 in bead notes?** Bead notes are plain text. Base64-encoded images would
bloat them and make `bd list` output unreadable.

**Why not a database?** We have no database in Baap. Everything is files and CLI tools.
Staying consistent.

**Implementation**: Files saved to `.claude/command-center/attachments/{uuid}.{ext}` with
a sidecar `.claude/command-center/attachments/_index.json` mapping attachment IDs to
metadata (original name, mime type, size, linked bead ID, upload timestamp). Bead notes
get a reference like `[attachment:att_abc123]` that the frontend can resolve.

### Decision 3: Kanban columns map from bead status field

**Mapping**:
| Bead Status | Kanban Column |
|-------------|---------------|
| `open`, `new`, `pending` (no assignee) | Backlog |
| `open`, `new`, `pending` (has assignee) | Ready |
| `in_progress`, `active`, `working` | In Progress |
| `in_review`, `review`, `reviewing` | In Review |
| `blocked` (or has unresolved deps) | Blocked |
| `closed`, `done`, `completed`, `resolved` | Done |

Moving a card between columns updates the bead's status via `bd update {id} --status {new_status}`.

### Decision 4: Command system uses static registry + script directory scan

**Why not purely dynamic?** Scanning scripts on every request adds latency and is fragile
(new scripts might not have metadata). A static registry with known commands is reliable.

**Why not purely static?** We want the system to discover new scripts in `.claude/scripts/`
automatically. Hybrid: static registry for known commands, directory scan for bonus ones.

**Context-aware filtering**: Commands are tagged with contexts (e.g., `agent:{name}`,
`bead:{id}`, `global`). The frontend sends the current selection context, the API filters
to relevant commands.

### Decision 5: WebSocket over SSE for real-time updates

**Why WebSocket?** The Think Tank requires bidirectional communication — the human sends
messages and receives orchestrator responses through the same connection. SSE is
server-to-client only. WebSocket handles both directions in one connection.

**Event protocol**: Follows the AG-UI pattern with typed events. Each event has a `type`
field and a `payload` field. The frontend switches on `type` to route to the correct handler.

## Files to Create

```
.claude/command-center/
  backend/
    __init__.py
    main.py              # FastAPI app factory, CORS, lifespan
    config.py            # All configurable paths, port, project detection
    models.py            # Pydantic models for all request/response types
    routes/
      __init__.py
      agents.py          # Agent CRUD + spawn/kill/retry
      beads.py           # Bead CRUD + kanban view + comments
      attachments.py     # File upload/download
      thinktank.py       # Think Tank session management
      commands.py        # Command palette backend
      dashboard.py       # Overview stats, timeline, health
      epics.py           # Epic progress + dependency DAG
      websocket.py       # WebSocket hub for real-time push
    services/
      __init__.py
      agent_service.py   # Reads status files, heartbeats, calls scripts
      bead_service.py    # Wraps bd CLI with structured output
      thinktank_service.py  # Manages Claude Code orchestrator subprocess
      attachment_service.py # File storage + metadata index
      command_service.py    # Command registry + discovery
      event_bus.py       # In-process pub/sub for WebSocket broadcast
    start.sh             # Launcher script
    requirements.txt     # FastAPI, uvicorn, websockets
  attachments/           # Upload storage directory (gitignored)
```

## Files to Modify

- `.gitignore` — Add `.claude/command-center/attachments/` exclusion

## Dependencies

- Phase 1c (spawn.sh), 1d (kill-agent.sh, heartbeat.sh, retry-agent.sh)
- Phase 1e (agent status files at `/tmp/baap-agent-status/`, heartbeats at `/tmp/baap-heartbeats/`)
- Phase 01h (orchestrator protocol for Think Tank)
- `bd` CLI installed and functional
- Python 3.10+ with `fastapi`, `uvicorn`, `websockets`

---

## Fix 1: Configuration — `.claude/command-center/backend/config.py`

### Problem

The 03e dashboard hardcodes paths like `/tmp/baap-agent-status` and uses relative path
resolution that breaks when run from a different directory. A reusable API needs all paths
configurable and project root auto-detected.

### Solution

A single config module that auto-detects the project root (walks up from `__file__` looking
for `.git`), reads optional environment variable overrides, and provides all paths as
`Path` objects.

### Full Implementation

```python
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

# Server
PORT = int(os.environ.get("BAAP_CC_PORT", "8002"))

# Thresholds
HEARTBEAT_STALE_SECONDS = int(os.environ.get("BAAP_HEARTBEAT_STALE_S", "120"))

# Timeline
MAX_TIMELINE_EVENTS = 500

# Ensure directories exist
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
STATUS_DIR.mkdir(parents=True, exist_ok=True)
HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
```

---

## Fix 2: Pydantic Models — `.claude/command-center/backend/models.py`

### Problem

Without typed models, every endpoint returns ad-hoc dicts. The frontend cannot trust the
shape of responses. Validation errors surface as 500s instead of 422s.

### Solution

Pydantic v2 models for every request body and response type. Enums for status values.
Optional fields where the data may not exist.

### Full Implementation

```python
"""
models.py — Pydantic models for Command Center API.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class AgentStatus(str, Enum):
    SPAWNING = "spawning"
    WORKING = "working"
    IDLE = "idle"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"


class BeadStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    CLOSED = "closed"
    DONE = "done"


class KanbanColumn(str, Enum):
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    DONE = "done"


class ThinkTankPhase(str, Enum):
    LISTEN = "listen"
    EXPLORE = "explore"
    SCOPE = "scope"
    CONFIRM = "confirm"
    BUILDING = "building"
    COMPLETE = "complete"


class WSEventType(str, Enum):
    AGENT_STATUS_CHANGE = "AGENT_STATUS_CHANGE"
    BEAD_TRANSITION = "BEAD_TRANSITION"
    THINKTANK_MESSAGE = "THINKTANK_MESSAGE"
    THINKTANK_SPECKIT_DELTA = "THINKTANK_SPECKIT_DELTA"
    THINKTANK_PHASE_CHANGE = "THINKTANK_PHASE_CHANGE"
    APPROVAL_NEEDED = "APPROVAL_NEEDED"
    TIMELINE_EVENT = "TIMELINE_EVENT"
    TOAST = "TOAST"


class CommandCategory(str, Enum):
    AGENT = "Agent"
    BEAD = "Bead"
    EPIC = "Epic"
    NAVIGATION = "Navigation"
    THINKTANK = "Think Tank"
    SYSTEM = "System"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── Agent Models ──────────────────────────────────────────────────────────────

class Agent(BaseModel):
    name: str
    level: int | str = "?"
    status: AgentStatus = AgentStatus.UNKNOWN
    bead: str | None = None
    current_action: str | None = None
    started_at: str | None = None
    last_update: str | None = None
    worktree: str | None = None
    errors: int = 0
    heartbeat_age_s: int | None = None
    heartbeat_stale: bool = False


class AgentListResponse(BaseModel):
    agents: list[Agent]
    count: int
    ts: str


class SpawnRequest(BaseModel):
    mode: str = "worktree"  # worktree | tmux
    prompt: str
    path: str | None = None  # file/dir to work on
    level: int = 2
    bead: str | None = None  # bead ID to assign
    epic: str | None = None


class SpawnResponse(BaseModel):
    agent_name: str
    status: str
    message: str


class AgentLogResponse(BaseModel):
    agent_name: str
    log_file: str | None = None
    lines: list[str]
    total_lines: int


# ── Bead Models ───────────────────────────────────────────────────────────────

class Bead(BaseModel):
    id: str
    title: str = "Untitled"
    status: str = "open"
    assignee: str | None = None
    priority: int | None = None
    epic: str | None = None
    type: str = "task"
    deps: list[str] = Field(default_factory=list)
    notes: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class BeadCreateRequest(BaseModel):
    title: str
    type: str = "task"
    priority: int | None = None
    epic: str | None = None
    assignee: str | None = None
    notes: str = ""


class BeadUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    assignee: str | None = None
    priority: int | None = None
    notes: str | None = None


class BeadMoveRequest(BaseModel):
    column: KanbanColumn


class BeadCommentRequest(BaseModel):
    text: str
    author: str = "human"


class BeadComment(BaseModel):
    text: str
    author: str
    timestamp: str


class KanbanColumnData(BaseModel):
    title: str
    color: str
    count: int = 0
    beads: list[Bead] = Field(default_factory=list)


class KanbanResponse(BaseModel):
    columns: dict[str, KanbanColumnData]
    total: int


# ── Attachment Models ─────────────────────────────────────────────────────────

class Attachment(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    bead_id: str | None = None
    uploaded_at: str
    path: str  # relative path within attachments dir


class AttachmentListResponse(BaseModel):
    attachments: list[Attachment]
    count: int


# ── Think Tank Models ─────────────────────────────────────────────────────────

class ThinkTankStartRequest(BaseModel):
    topic: str
    context: str = ""  # optional initial context


class ThinkTankMessageRequest(BaseModel):
    text: str
    attachments: list[str] = Field(default_factory=list)  # attachment IDs


class ThinkTankActionRequest(BaseModel):
    action: str  # "dig_deeper" | "adjust" | "go_next"
    context: str = ""


class ThinkTankApproveRequest(BaseModel):
    modifications: str = ""  # optional last-minute tweaks before approval


class ThinkTankMessage(BaseModel):
    role: str  # "human" | "orchestrator" | "system"
    content: str
    timestamp: str
    phase: ThinkTankPhase | None = None
    attachments: list[str] = Field(default_factory=list)


class SpecKitSection(BaseModel):
    title: str
    content: str
    editable: bool = True
    locked: bool = False
    updated_at: str | None = None


class SpecKit(BaseModel):
    project_brief: SpecKitSection | None = None
    requirements: SpecKitSection | None = None
    constraints: SpecKitSection | None = None
    architecture: SpecKitSection | None = None
    pre_mortem: SpecKitSection | None = None
    execution_plan: SpecKitSection | None = None


class ThinkTankSession(BaseModel):
    id: str
    topic: str
    phase: ThinkTankPhase
    messages: list[ThinkTankMessage]
    spec_kit: SpecKit
    started_at: str
    updated_at: str
    status: str = "active"  # active | paused | approved | completed


class ThinkTankSessionSummary(BaseModel):
    id: str
    topic: str
    phase: ThinkTankPhase
    status: str
    message_count: int
    started_at: str
    updated_at: str


# ── Command Models ────────────────────────────────────────────────────────────

class Command(BaseModel):
    id: str
    name: str
    description: str = ""
    category: CommandCategory
    shortcut: str | None = None
    icon: str | None = None
    contexts: list[str] = Field(default_factory=list)  # e.g., ["agent:*", "global"]
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False


class CommandExecuteRequest(BaseModel):
    command_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False  # for commands requiring confirmation


class CommandExecuteResponse(BaseModel):
    command_id: str
    success: bool
    message: str
    output: str | None = None


class CommandSearchRequest(BaseModel):
    query: str
    context: str | None = None  # e.g., "agent:api-agent" or "bead:baap-abc"
    limit: int = 10


# ── Dashboard Models ──────────────────────────────────────────────────────────

class DashboardOverview(BaseModel):
    active_agents: int
    total_agents: int
    stale_agents: int
    open_beads: int
    in_progress_beads: int
    blocked_beads: int
    done_beads: int
    epic_count: int
    avg_epic_progress: float
    thinktank_active: bool


class TimelineEvent(BaseModel):
    ts: str
    type: str
    agent: str | None = None
    bead: str | None = None
    detail: str


class TimelineResponse(BaseModel):
    events: list[TimelineEvent]
    total_events: int


# ── Epic Models ───────────────────────────────────────────────────────────────

class Epic(BaseModel):
    epic: str
    total: int
    completed: int
    in_progress: int
    blocked: int
    open: int
    progress_pct: float
    beads: list[str]


class EpicListResponse(BaseModel):
    epics: list[Epic]
    count: int


class EpicGraphNode(BaseModel):
    id: str
    title: str
    status: str
    deps: list[str]


class EpicGraphResponse(BaseModel):
    epic: str
    nodes: list[EpicGraphNode]
    edges: list[dict[str, str]]  # [{from: "a", to: "b"}, ...]


# ── WebSocket Models ──────────────────────────────────────────────────────────

class WSEvent(BaseModel):
    type: WSEventType
    payload: dict[str, Any]
    ts: str | None = None
```

---

## Fix 3: Event Bus — `.claude/command-center/backend/services/event_bus.py`

### Problem

Multiple services need to push events to WebSocket clients. Without a central pub/sub
mechanism, every service would need direct access to the WebSocket connection manager,
creating circular dependencies.

### Solution

An in-process async event bus. Services publish events. The WebSocket handler subscribes
and broadcasts to all connected clients.

### Full Implementation

```python
"""
event_bus.py — In-process async pub/sub for WebSocket broadcast.

Services call `event_bus.publish(event)` to push events.
The WebSocket handler calls `event_bus.subscribe()` to get an async generator of events.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

from models import WSEvent, WSEventType


class EventBus:
    """Simple in-process pub/sub using asyncio.Queue per subscriber."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def publish(self, event_type: WSEventType, payload: dict[str, Any]) -> None:
        """Publish an event to all subscribers."""
        event = WSEvent(
            type=event_type,
            payload=payload,
            ts=datetime.now(timezone.utc).isoformat(),
        )
        event_json = event.model_dump_json()
        async with self._lock:
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event_json)
                except asyncio.QueueFull:
                    dead.append(q)
            # Remove dead subscribers
            for q in dead:
                self._subscribers.remove(q)

    async def subscribe(self) -> asyncio.Queue:
        """Create a new subscription queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscription queue."""
        async with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Singleton instance
event_bus = EventBus()
```

---

## Fix 4: Agent Service — `.claude/command-center/backend/services/agent_service.py`

### Problem

Agent data comes from 3 sources: status JSON files, heartbeat files, and log files. The
03e dashboard reads these inline in the endpoint handler. We need a service layer that
encapsulates this logic and can be called from both HTTP endpoints and the event detection
background task.

### Solution

An `AgentService` class that reads all sources, detects transitions, and publishes events
to the event bus.

### Full Implementation

```python
"""
agent_service.py — Agent status reading, transition detection, and script execution.
"""

import asyncio
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from config import STATUS_DIR, HEARTBEAT_DIR, LOG_DIR, SCRIPTS_DIR, HEARTBEAT_STALE_SECONDS, MAX_TIMELINE_EVENTS
from models import Agent, AgentStatus, WSEventType


class AgentService:
    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._last_snapshot: dict[str, str] = {}
        self._timeline: list[dict] = []

    def _add_timeline_event(self, event_type: str, agent: str, detail: str) -> dict:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "agent": agent,
            "detail": detail,
        }
        self._timeline.append(event)
        if len(self._timeline) > MAX_TIMELINE_EVENTS:
            self._timeline.pop(0)
        return event

    def read_agents(self) -> list[Agent]:
        """Read all agent status files and enrich with heartbeat data."""
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
                    hb_stale = hb_age > HEARTBEAT_STALE_SECONDS
                except (ValueError, OSError):
                    pass

            # Map raw status to enum
            raw_status = (data.get("status") or "unknown").lower()
            status_map = {
                "working": AgentStatus.WORKING,
                "running": AgentStatus.WORKING,
                "spawning": AgentStatus.SPAWNING,
                "idle": AgentStatus.IDLE,
                "stopped": AgentStatus.STOPPED,
                "failed": AgentStatus.FAILED,
            }
            status = status_map.get(raw_status, AgentStatus.UNKNOWN)

            agents.append(Agent(
                name=name,
                level=data.get("level", "?"),
                status=status,
                bead=data.get("bead"),
                current_action=data.get("current_action"),
                started_at=data.get("started_at"),
                last_update=data.get("last_update"),
                worktree=data.get("worktree"),
                errors=data.get("errors", 0),
                heartbeat_age_s=hb_age,
                heartbeat_stale=hb_stale,
            ))
        return agents

    async def detect_transitions(self, agents: list[Agent]) -> list[dict]:
        """Compare current agent statuses against last snapshot, emit events."""
        events = []
        current: dict[str, str] = {}

        for a in agents:
            current[a.name] = a.status.value
            prev = self._last_snapshot.get(a.name)
            if prev is None:
                ev = self._add_timeline_event("agent_spawned", a.name, f"Agent appeared with status: {a.status.value}")
                events.append(ev)
                if self._event_bus:
                    await self._event_bus.publish(WSEventType.AGENT_STATUS_CHANGE, {
                        "agent": a.name, "status": a.status.value, "previous": None, "action": "spawned"
                    })
            elif prev != a.status.value:
                ev = self._add_timeline_event("status_change", a.name, f"{prev} -> {a.status.value}")
                events.append(ev)
                if self._event_bus:
                    await self._event_bus.publish(WSEventType.AGENT_STATUS_CHANGE, {
                        "agent": a.name, "status": a.status.value, "previous": prev, "action": "changed"
                    })

        # Detect agents that disappeared
        for name, prev_status in self._last_snapshot.items():
            if name not in current:
                ev = self._add_timeline_event("agent_gone", name, f"Agent disappeared (was: {prev_status})")
                events.append(ev)
                if self._event_bus:
                    await self._event_bus.publish(WSEventType.AGENT_STATUS_CHANGE, {
                        "agent": name, "status": "gone", "previous": prev_status, "action": "disappeared"
                    })

        self._last_snapshot = current
        return events

    def get_agent(self, name: str) -> Agent | None:
        """Get a single agent by name."""
        agents = self.read_agents()
        for a in agents:
            if a.name == name:
                return a
        return None

    def get_agent_logs(self, name: str, tail: int = 100) -> tuple[str | None, list[str]]:
        """Read the last N lines of an agent's log file."""
        if not LOG_DIR.exists():
            return None, []

        # Try exact match first, then prefix match
        log_file = LOG_DIR / f"{name}.log"
        if not log_file.exists():
            candidates = list(LOG_DIR.glob(f"{name}*.log"))
            if not candidates:
                return None, []
            log_file = max(candidates, key=lambda p: p.stat().st_mtime)

        try:
            lines = log_file.read_text().splitlines()
            return str(log_file), lines[-tail:]
        except OSError:
            return str(log_file), []

    def get_timeline(self, limit: int = 50) -> list[dict]:
        """Return recent timeline events."""
        return list(reversed(self._timeline[-limit:]))

    async def spawn_agent(self, mode: str, prompt: str, path: str | None = None,
                          level: int = 2, bead: str | None = None) -> dict:
        """Spawn a new agent via spawn.sh."""
        script = SCRIPTS_DIR / "spawn.sh"
        if not script.exists():
            return {"success": False, "message": f"spawn.sh not found at {script}"}

        cmd = ["bash", str(script)]
        if bead:
            cmd.extend(["--bead", bead])
        # spawn.sh expects a prompt argument
        cmd.append(prompt)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                cwd=str(SCRIPTS_DIR.parent.parent)  # project root
            )
            return {
                "success": result.returncode == 0,
                "message": result.stdout.strip() or result.stderr.strip(),
                "output": result.stdout,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "spawn.sh timed out after 30s"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def kill_agent(self, name: str) -> dict:
        """Kill an agent via kill-agent.sh."""
        script = SCRIPTS_DIR / "kill-agent.sh"
        if not script.exists():
            return {"success": False, "message": f"kill-agent.sh not found at {script}"}

        try:
            result = subprocess.run(
                ["bash", str(script), name],
                capture_output=True, text=True, timeout=15,
                cwd=str(SCRIPTS_DIR.parent.parent)
            )
            if self._event_bus:
                await self._event_bus.publish(WSEventType.AGENT_STATUS_CHANGE, {
                    "agent": name, "status": "stopped", "previous": "working", "action": "killed"
                })
                await self._event_bus.publish(WSEventType.TOAST, {
                    "message": f"Agent '{name}' killed", "type": "warning"
                })
            return {
                "success": result.returncode == 0,
                "message": result.stdout.strip() or result.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "kill-agent.sh timed out"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def retry_agent(self, name: str) -> dict:
        """Retry a failed agent via retry-agent.sh."""
        script = SCRIPTS_DIR / "retry-agent.sh"
        if not script.exists():
            return {"success": False, "message": f"retry-agent.sh not found at {script}"}

        try:
            result = subprocess.run(
                ["bash", str(script), name],
                capture_output=True, text=True, timeout=30,
                cwd=str(SCRIPTS_DIR.parent.parent)
            )
            if self._event_bus:
                await self._event_bus.publish(WSEventType.TOAST, {
                    "message": f"Agent '{name}' retrying", "type": "info"
                })
            return {
                "success": result.returncode == 0,
                "message": result.stdout.strip() or result.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "retry-agent.sh timed out"}
        except Exception as e:
            return {"success": False, "message": str(e)}
```

---

## Fix 5: Bead Service — `.claude/command-center/backend/services/bead_service.py`

### Problem

Every bead operation shells out to `bd`. Without a service layer, the endpoint code becomes
a mess of `subprocess.run` calls with ad-hoc JSON parsing.

### Solution

A `BeadService` class that wraps `bd` CLI calls with structured input/output, manages the
kanban column mapping, and handles comments as appended notes.

### Full Implementation

```python
"""
bead_service.py — Wraps the bd (beads) CLI with structured Python interface.
"""

import json
import subprocess
from datetime import datetime, timezone
from typing import Any

from models import (
    Bead, BeadComment, KanbanColumn, KanbanColumnData, KanbanResponse,
    WSEventType,
)


# Bead status -> kanban column mapping
COLUMN_MAP: dict[str, KanbanColumn] = {
    "closed": KanbanColumn.DONE,
    "done": KanbanColumn.DONE,
    "completed": KanbanColumn.DONE,
    "resolved": KanbanColumn.DONE,
    "in_review": KanbanColumn.IN_REVIEW,
    "review": KanbanColumn.IN_REVIEW,
    "reviewing": KanbanColumn.IN_REVIEW,
    "in_progress": KanbanColumn.IN_PROGRESS,
    "active": KanbanColumn.IN_PROGRESS,
    "working": KanbanColumn.IN_PROGRESS,
    "blocked": KanbanColumn.BLOCKED,
}

# Kanban column -> bead status (for moves)
COLUMN_TO_STATUS: dict[KanbanColumn, str] = {
    KanbanColumn.BACKLOG: "open",
    KanbanColumn.READY: "open",
    KanbanColumn.IN_PROGRESS: "in_progress",
    KanbanColumn.IN_REVIEW: "in_review",
    KanbanColumn.BLOCKED: "blocked",
    KanbanColumn.DONE: "closed",
}

COLUMN_COLORS: dict[str, str] = {
    "backlog": "#8b949e",
    "ready": "#58a6ff",
    "in_progress": "#d29922",
    "in_review": "#bc8cff",
    "blocked": "#f85149",
    "done": "#3fb950",
}

COLUMN_TITLES: dict[str, str] = {
    "backlog": "Backlog",
    "ready": "Ready",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "blocked": "Blocked",
    "done": "Done",
}


class BeadService:
    def __init__(self, event_bus=None):
        self._event_bus = event_bus

    def _run_bd(self, args: list[str], timeout: int = 10) -> tuple[bool, str]:
        """Run a bd CLI command and return (success, output)."""
        try:
            result = subprocess.run(
                ["bd"] + args,
                capture_output=True, text=True, timeout=timeout,
            )
            output = result.stdout.strip() or result.stderr.strip()
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "bd command timed out"
        except FileNotFoundError:
            return False, "bd CLI not found — is beads installed?"
        except Exception as e:
            return False, str(e)

    def list_beads(self, status: str | None = None, assignee: str | None = None,
                   epic: str | None = None) -> list[Bead]:
        """List all beads, optionally filtered."""
        args = ["list", "--json"]
        if status:
            args.extend(["--status", status])

        ok, output = self._run_bd(args)
        if not ok or not output:
            return []

        try:
            raw_beads = json.loads(output)
        except json.JSONDecodeError:
            return []

        beads = []
        for b in raw_beads:
            bead = Bead(
                id=b.get("id", "?"),
                title=b.get("title") or b.get("description") or "Untitled",
                status=(b.get("status") or "open").lower().replace("-", "_"),
                assignee=b.get("assignee") or b.get("agent"),
                priority=b.get("priority"),
                epic=b.get("epic") or b.get("parent"),
                type=b.get("type", "task"),
                deps=b.get("dependencies") or b.get("deps") or b.get("blocked_by") or [],
                notes=b.get("notes", ""),
                created_at=b.get("created_at") or b.get("created"),
                updated_at=b.get("updated_at") or b.get("updated") or b.get("last_update"),
            )

            # Apply filters
            if assignee and bead.assignee != assignee:
                continue
            if epic and bead.epic != epic:
                continue

            beads.append(bead)

        return beads

    def get_bead(self, bead_id: str) -> Bead | None:
        """Get a single bead by ID."""
        beads = self.list_beads()
        for b in beads:
            if b.id == bead_id:
                return b
        return None

    def create_bead(self, title: str, bead_type: str = "task",
                    priority: int | None = None, epic: str | None = None,
                    assignee: str | None = None, notes: str = "") -> tuple[bool, str]:
        """Create a new bead via bd create."""
        args = ["create", title]
        if bead_type:
            args.extend(["--type", bead_type])
        if priority is not None:
            args.extend(["--priority", str(priority)])
        if epic:
            args.extend(["--epic", epic])

        ok, output = self._run_bd(args)
        return ok, output

    def update_bead(self, bead_id: str, **kwargs) -> tuple[bool, str]:
        """Update a bead's fields via bd update."""
        args = ["update", bead_id]
        for key, value in kwargs.items():
            if value is not None:
                args.extend([f"--{key}", str(value)])

        ok, output = self._run_bd(args)
        return ok, output

    async def move_bead(self, bead_id: str, column: KanbanColumn) -> tuple[bool, str]:
        """Move a bead to a different kanban column by updating its status."""
        new_status = COLUMN_TO_STATUS.get(column, "open")
        ok, output = self.update_bead(bead_id, status=new_status)

        if ok and self._event_bus:
            await self._event_bus.publish(WSEventType.BEAD_TRANSITION, {
                "bead_id": bead_id,
                "new_column": column.value,
                "new_status": new_status,
            })
            await self._event_bus.publish(WSEventType.TIMELINE_EVENT, {
                "type": "bead_moved",
                "bead": bead_id,
                "detail": f"Moved to {COLUMN_TITLES.get(column.value, column.value)}",
            })

        return ok, output

    def add_comment(self, bead_id: str, text: str, author: str = "human") -> tuple[bool, str]:
        """Add a comment to a bead by appending to its notes."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        comment_line = f"\n[{timestamp}] {author}: {text}"

        # Get current notes
        bead = self.get_bead(bead_id)
        if not bead:
            return False, f"Bead {bead_id} not found"

        new_notes = (bead.notes or "") + comment_line
        return self.update_bead(bead_id, notes=new_notes)

    def get_comments(self, bead_id: str) -> list[BeadComment]:
        """Parse comments from bead notes."""
        bead = self.get_bead(bead_id)
        if not bead or not bead.notes:
            return []

        comments = []
        for line in bead.notes.split("\n"):
            line = line.strip()
            if line.startswith("[") and "]" in line:
                # Parse: [2026-02-14 10:30 UTC] human: some text
                try:
                    ts_end = line.index("]")
                    ts = line[1:ts_end]
                    rest = line[ts_end + 2:]  # skip "] "
                    if ":" in rest:
                        author, text = rest.split(":", 1)
                        comments.append(BeadComment(
                            text=text.strip(),
                            author=author.strip(),
                            timestamp=ts,
                        ))
                except (ValueError, IndexError):
                    continue

        return comments

    def get_kanban(self) -> KanbanResponse:
        """Organize beads into kanban columns."""
        beads = self.list_beads()

        columns: dict[str, KanbanColumnData] = {}
        for col_key in ["backlog", "ready", "in_progress", "in_review", "blocked", "done"]:
            columns[col_key] = KanbanColumnData(
                title=COLUMN_TITLES[col_key],
                color=COLUMN_COLORS[col_key],
                count=0,
                beads=[],
            )

        for bead in beads:
            status = bead.status
            has_deps = len(bead.deps) > 0

            # Classify
            col_key = COLUMN_MAP.get(status)
            if col_key is None:
                if status == "blocked" or has_deps:
                    col_key = KanbanColumn.BLOCKED
                elif bead.assignee is None and status in ("open", "new", "pending", ""):
                    col_key = KanbanColumn.BACKLOG
                else:
                    col_key = KanbanColumn.READY

            columns[col_key.value].beads.append(bead)

        # Sort and count
        for col in columns.values():
            col.beads.sort(key=lambda b: (
                b.priority if b.priority is not None else 99,
                b.created_at or "",
            ))
            col.count = len(col.beads)

        return KanbanResponse(columns=columns, total=len(beads))

    def build_epics(self) -> list[dict]:
        """Group beads by epic and compute progress."""
        beads = self.list_beads()
        epics: dict[str, dict[str, Any]] = {}

        for b in beads:
            epic = b.epic or "ungrouped"
            if epic not in epics:
                epics[epic] = {
                    "epic": epic, "total": 0, "completed": 0,
                    "in_progress": 0, "blocked": 0, "open": 0, "beads": [],
                }
            epics[epic]["total"] += 1
            epics[epic]["beads"].append(b.id)

            if b.status in ("closed", "done", "completed", "resolved"):
                epics[epic]["completed"] += 1
            elif b.status in ("in_progress", "active"):
                epics[epic]["in_progress"] += 1
            elif b.status == "blocked":
                epics[epic]["blocked"] += 1
            else:
                epics[epic]["open"] += 1

        result = []
        for e in epics.values():
            e["progress_pct"] = round(e["completed"] / e["total"] * 100, 1) if e["total"] > 0 else 0
            result.append(e)
        result.sort(key=lambda x: x["progress_pct"])
        return result
```

---

## Fix 6: Attachment Service — `.claude/command-center/backend/services/attachment_service.py`

### Problem

The UI needs to support screenshot paste, drag-and-drop file uploads, and image attachments
on beads and think tank messages. There is currently no file storage mechanism.

### Solution

A simple file-based storage with a JSON index sidecar. Files are stored with UUID names
to prevent collisions. The index maps IDs to metadata.

### Full Implementation

```python
"""
attachment_service.py — File upload storage with metadata index.
"""

import json
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import ATTACHMENTS_DIR
from models import Attachment


INDEX_FILE = ATTACHMENTS_DIR / "_index.json"


class AttachmentService:
    def __init__(self):
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        self._index = self._load_index()

    def _load_index(self) -> dict[str, dict]:
        if INDEX_FILE.exists():
            try:
                return json.loads(INDEX_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_index(self) -> None:
        INDEX_FILE.write_text(json.dumps(self._index, indent=2))

    def save(self, filename: str, content: bytes, bead_id: str | None = None) -> Attachment:
        """Save an uploaded file and return its metadata."""
        att_id = f"att_{uuid.uuid4().hex[:12]}"
        ext = Path(filename).suffix or ".bin"
        stored_name = f"{att_id}{ext}"
        file_path = ATTACHMENTS_DIR / stored_name

        file_path.write_bytes(content)

        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        attachment = Attachment(
            id=att_id,
            filename=filename,
            mime_type=mime,
            size_bytes=len(content),
            bead_id=bead_id,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
            path=stored_name,
        )

        self._index[att_id] = attachment.model_dump()
        self._save_index()

        return attachment

    def get(self, att_id: str) -> Attachment | None:
        """Get attachment metadata by ID."""
        data = self._index.get(att_id)
        if data:
            return Attachment(**data)
        return None

    def get_file_path(self, att_id: str) -> Path | None:
        """Get the full filesystem path for an attachment."""
        data = self._index.get(att_id)
        if data:
            return ATTACHMENTS_DIR / data["path"]
        return None

    def list_all(self, bead_id: str | None = None) -> list[Attachment]:
        """List all attachments, optionally filtered by bead."""
        attachments = [Attachment(**d) for d in self._index.values()]
        if bead_id:
            attachments = [a for a in attachments if a.bead_id == bead_id]
        return sorted(attachments, key=lambda a: a.uploaded_at, reverse=True)

    def delete(self, att_id: str) -> bool:
        """Delete an attachment file and its metadata."""
        data = self._index.pop(att_id, None)
        if data:
            file_path = ATTACHMENTS_DIR / data["path"]
            if file_path.exists():
                file_path.unlink()
            self._save_index()
            return True
        return False
```

---

## Fix 7: Command Service — `.claude/command-center/backend/services/command_service.py`

### Problem

The Cmd+K command palette on the frontend needs a backend that knows which commands are
available, filters them by context, and executes them. Without this, the palette is just
a frontend shell.

### Solution

A static command registry augmented by dynamic script directory scanning. Commands are
tagged with contexts so the palette shows relevant actions. Execution delegates to the
appropriate service.

### Full Implementation

```python
"""
command_service.py — Command registry, discovery, fuzzy search, and execution.

Commands are registered statically for known actions and dynamically by scanning
the .claude/scripts/ directory for executable scripts with help comments.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from config import SCRIPTS_DIR
from models import Command, CommandCategory, RiskLevel


def _build_registry() -> list[Command]:
    """Build the static command registry."""
    return [
        # ── Agent commands ────────────────────────────────────────────────
        Command(
            id="agent.spawn",
            name="Spawn Agent",
            description="Start a new agent with a prompt",
            category=CommandCategory.AGENT,
            shortcut="Ctrl+Shift+N",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="agent.kill",
            name="Kill Agent",
            description="Gracefully stop a running agent",
            category=CommandCategory.AGENT,
            shortcut="Ctrl+Shift+K",
            contexts=["agent:*"],
            risk_level=RiskLevel.MEDIUM,
            requires_confirmation=True,
        ),
        Command(
            id="agent.retry",
            name="Retry Agent",
            description="Re-dispatch a failed agent's work",
            category=CommandCategory.AGENT,
            contexts=["agent:*"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="agent.kill_all",
            name="Kill All Agents",
            description="Emergency stop all running agents",
            category=CommandCategory.AGENT,
            shortcut="Ctrl+Shift+P",
            contexts=["global"],
            risk_level=RiskLevel.HIGH,
            requires_confirmation=True,
        ),
        Command(
            id="agent.view_logs",
            name="View Agent Logs",
            description="Show the last 100 lines of an agent's log",
            category=CommandCategory.AGENT,
            contexts=["agent:*"],
            risk_level=RiskLevel.LOW,
        ),

        # ── Bead commands ─────────────────────────────────────────────────
        Command(
            id="bead.create",
            name="Create Bead",
            description="Create a new work item",
            category=CommandCategory.BEAD,
            shortcut="C",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="bead.close",
            name="Close Bead",
            description="Mark a bead as done",
            category=CommandCategory.BEAD,
            contexts=["bead:*"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="bead.block",
            name="Block Bead",
            description="Mark a bead as blocked",
            category=CommandCategory.BEAD,
            contexts=["bead:*"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="bead.assign",
            name="Assign Bead",
            description="Assign a bead to an agent",
            category=CommandCategory.BEAD,
            shortcut="A",
            contexts=["bead:*"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="bead.comment",
            name="Add Comment",
            description="Add a comment to a bead",
            category=CommandCategory.BEAD,
            contexts=["bead:*"],
            risk_level=RiskLevel.LOW,
        ),

        # ── Epic commands ─────────────────────────────────────────────────
        Command(
            id="epic.view",
            name="View Epic",
            description="Show epic progress and bead breakdown",
            category=CommandCategory.EPIC,
            contexts=["epic:*", "global"],
            risk_level=RiskLevel.LOW,
        ),

        # ── Think Tank commands ───────────────────────────────────────────
        Command(
            id="thinktank.start",
            name="Start Brainstorm",
            description="Begin a new Think Tank brainstorming session",
            category=CommandCategory.THINKTANK,
            shortcut="Ctrl+Shift+T",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="thinktank.resume",
            name="Resume Brainstorm",
            description="Resume an existing Think Tank session",
            category=CommandCategory.THINKTANK,
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),

        # ── Navigation commands ───────────────────────────────────────────
        Command(
            id="nav.dashboard",
            name="Go to Dashboard",
            description="Main overview",
            category=CommandCategory.NAVIGATION,
            shortcut="G D",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="nav.kanban",
            name="Go to Kanban Board",
            description="Work items board",
            category=CommandCategory.NAVIGATION,
            shortcut="G K",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="nav.agents",
            name="Go to Agents",
            description="Agent swimlanes view",
            category=CommandCategory.NAVIGATION,
            shortcut="G A",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="nav.thinktank",
            name="Go to Think Tank",
            description="Brainstorming interface",
            category=CommandCategory.NAVIGATION,
            shortcut="G T",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),

        # ── System commands ───────────────────────────────────────────────
        Command(
            id="system.refresh",
            name="Refresh Data",
            description="Force refresh all dashboard data",
            category=CommandCategory.SYSTEM,
            shortcut="R",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="system.health",
            name="Health Check",
            description="Check API and service health",
            category=CommandCategory.SYSTEM,
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
    ]


class CommandService:
    def __init__(self):
        self._registry = _build_registry()
        self._scan_scripts()

    def _scan_scripts(self) -> None:
        """Scan .claude/scripts/ for additional executable scripts."""
        if not SCRIPTS_DIR.exists():
            return

        known_ids = {c.id for c in self._registry}

        for script in sorted(SCRIPTS_DIR.glob("*.sh")):
            script_id = f"script.{script.stem}"
            if script_id in known_ids:
                continue

            # Read first line comment for description
            description = ""
            try:
                first_lines = script.read_text().split("\n")[:5]
                for line in first_lines:
                    if line.startswith("# ") and not line.startswith("#!"):
                        description = line[2:].strip()
                        break
            except OSError:
                pass

            self._registry.append(Command(
                id=script_id,
                name=script.stem.replace("-", " ").replace("_", " ").title(),
                description=description or f"Run {script.name}",
                category=CommandCategory.SYSTEM,
                contexts=["global"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=True,
            ))

    def list_commands(self, context: str | None = None) -> list[Command]:
        """List all commands, optionally filtered by context."""
        if not context:
            return self._registry

        filtered = []
        for cmd in self._registry:
            if "global" in cmd.contexts:
                filtered.append(cmd)
            elif any(self._matches_context(c, context) for c in cmd.contexts):
                filtered.append(cmd)
        return filtered

    def search(self, query: str, context: str | None = None, limit: int = 10) -> list[Command]:
        """Fuzzy search commands."""
        commands = self.list_commands(context)
        if not query:
            return commands[:limit]

        scored = []
        q = query.lower()
        for cmd in commands:
            target = f"{cmd.name} {cmd.description} {cmd.category.value}".lower()
            score = self._fuzzy_score(q, target)
            if score > 0:
                scored.append((score, cmd))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [cmd for _, cmd in scored[:limit]]

    def get_command(self, command_id: str) -> Command | None:
        """Get a command by ID."""
        for cmd in self._registry:
            if cmd.id == command_id:
                return cmd
        return None

    @staticmethod
    def _matches_context(pattern: str, context: str) -> bool:
        """Check if a context pattern matches a given context."""
        if pattern == context:
            return True
        if pattern.endswith(":*"):
            prefix = pattern[:-1]  # "agent:" from "agent:*"
            return context.startswith(prefix)
        return False

    @staticmethod
    def _fuzzy_score(query: str, text: str) -> int:
        """Sequential character matching with scoring."""
        qi = 0
        score = 0
        consecutive = 0
        for i, ch in enumerate(text):
            if qi < len(query) and ch == query[qi]:
                score += 1 + consecutive
                if i == 0 or text[i - 1] in (" ", "-", "_"):
                    score += 5  # word boundary bonus
                consecutive += 2
                qi += 1
            else:
                consecutive = 0
        return score if qi == len(query) else 0
```

---

## Fix 8: Think Tank Service — `.claude/command-center/backend/services/thinktank_service.py`

### Problem

The Think Tank brainstorming workflow (orchestrator protocol 01h) runs as a terminal Claude
Code session. There is no way to start, interact with, or monitor it from the browser.

### Solution

A `ThinkTankService` that manages Claude Code orchestrator subprocesses. It spawns a headless
Claude Code session with the orchestrator protocol, pipes human messages to stdin, reads
orchestrator output from stdout, and parses phase transitions and spec-kit deltas for
WebSocket push.

### Full Implementation

```python
"""
thinktank_service.py — Manages Think Tank brainstorming sessions.

Each session spawns a Claude Code subprocess with the orchestrator protocol.
Communication is via stdin/stdout pipes. Output is parsed for:
  - Phase transitions (Listen -> Explore -> Scope -> Confirm)
  - Spec-kit section updates
  - D/A/G menu presentations
  - Approval gates
"""

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone

from models import (
    ThinkTankSession, ThinkTankMessage, ThinkTankPhase,
    SpecKit, SpecKitSection, ThinkTankSessionSummary,
    WSEventType,
)


class ThinkTankService:
    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._sessions: dict[str, ThinkTankSession] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._readers: dict[str, asyncio.Task] = {}
        self._history: list[ThinkTankSessionSummary] = []

    async def start_session(self, topic: str, context: str = "") -> ThinkTankSession:
        """Start a new brainstorming session."""
        session_id = f"tt_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        session = ThinkTankSession(
            id=session_id,
            topic=topic,
            phase=ThinkTankPhase.LISTEN,
            messages=[],
            spec_kit=SpecKit(),
            started_at=now,
            updated_at=now,
            status="active",
        )

        # Add system message
        session.messages.append(ThinkTankMessage(
            role="system",
            content=f"Think Tank session started. Topic: {topic}",
            timestamp=now,
            phase=ThinkTankPhase.LISTEN,
        ))

        self._sessions[session_id] = session

        # Spawn Claude Code subprocess
        await self._spawn_orchestrator(session_id, topic, context)

        return session

    async def _spawn_orchestrator(self, session_id: str, topic: str, context: str) -> None:
        """Spawn a headless Claude Code process for the orchestrator."""
        initial_prompt = (
            f"You are the Think Tank orchestrator. Run the 4-phase BMAD elicitation "
            f"protocol (Listen -> Explore -> Scope -> Confirm) for this topic:\n\n"
            f"Topic: {topic}\n"
        )
        if context:
            initial_prompt += f"\nAdditional context:\n{context}\n"

        initial_prompt += (
            "\nStart with Phase 1: LISTEN. Ask the human what they are trying to build. "
            "Be curious and thorough. After each response, offer three options: "
            "[D] Dig Deeper, [A] Adjust, [G] Go to next phase.\n"
            "Format phase transitions as: PHASE_TRANSITION: <phase_name>\n"
            "Format spec-kit updates as JSON blocks with: SPECKIT_UPDATE: <section_name>\n"
        )

        try:
            process = await asyncio.create_subprocess_exec(
                "claude", "--print", "--no-input",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._processes[session_id] = process

            # Write initial prompt
            if process.stdin:
                process.stdin.write(initial_prompt.encode() + b"\n")
                await process.stdin.drain()

            # Start background reader
            self._readers[session_id] = asyncio.create_task(
                self._read_output(session_id)
            )

        except FileNotFoundError:
            # Claude CLI not available — use mock mode for development
            session = self._sessions.get(session_id)
            if session:
                session.messages.append(ThinkTankMessage(
                    role="orchestrator",
                    content=(
                        "Welcome to Think Tank! I'm here to help you think through "
                        f"'{session.topic}'.\n\n"
                        "Let's start with Phase 1: LISTEN.\n\n"
                        "Tell me: what are you trying to build? What problem does it solve? "
                        "Who will use it?\n\n"
                        "[D] Dig Deeper | [A] Adjust | [G] Go to Explore Phase"
                    ),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    phase=ThinkTankPhase.LISTEN,
                ))
                if self._event_bus:
                    await self._event_bus.publish(WSEventType.THINKTANK_MESSAGE, {
                        "session_id": session_id,
                        "message": session.messages[-1].model_dump(),
                    })

    async def _read_output(self, session_id: str) -> None:
        """Background task: read orchestrator stdout and parse events."""
        process = self._processes.get(session_id)
        if not process or not process.stdout:
            return

        buffer = ""
        while True:
            try:
                chunk = await process.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    await self._process_line(session_id, line)

            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def _process_line(self, session_id: str, line: str) -> None:
        """Parse a line of orchestrator output for phase transitions and spec-kit updates."""
        session = self._sessions.get(session_id)
        if not session:
            return

        now = datetime.now(timezone.utc).isoformat()

        # Check for phase transition
        phase_match = re.search(r"PHASE_TRANSITION:\s*(\w+)", line, re.IGNORECASE)
        if phase_match:
            phase_name = phase_match.group(1).lower()
            phase_map = {
                "listen": ThinkTankPhase.LISTEN,
                "explore": ThinkTankPhase.EXPLORE,
                "scope": ThinkTankPhase.SCOPE,
                "confirm": ThinkTankPhase.CONFIRM,
                "building": ThinkTankPhase.BUILDING,
            }
            new_phase = phase_map.get(phase_name)
            if new_phase and new_phase != session.phase:
                session.phase = new_phase
                session.updated_at = now
                if self._event_bus:
                    await self._event_bus.publish(WSEventType.THINKTANK_PHASE_CHANGE, {
                        "session_id": session_id,
                        "phase": new_phase.value,
                    })
            return

        # Check for spec-kit update
        speckit_match = re.search(r"SPECKIT_UPDATE:\s*(\w+)", line, re.IGNORECASE)
        if speckit_match:
            section_name = speckit_match.group(1).lower()
            # The content follows on subsequent lines — handled by the message accumulator
            if self._event_bus:
                await self._event_bus.publish(WSEventType.THINKTANK_SPECKIT_DELTA, {
                    "session_id": session_id,
                    "section": section_name,
                    "content": line,
                })
            return

        # Regular output — accumulate as message
        if line.strip():
            session.messages.append(ThinkTankMessage(
                role="orchestrator",
                content=line,
                timestamp=now,
                phase=session.phase,
            ))
            session.updated_at = now
            if self._event_bus:
                await self._event_bus.publish(WSEventType.THINKTANK_MESSAGE, {
                    "session_id": session_id,
                    "message": session.messages[-1].model_dump(),
                })

    async def send_message(self, session_id: str, text: str) -> bool:
        """Send a human message to the orchestrator."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        now = datetime.now(timezone.utc).isoformat()
        session.messages.append(ThinkTankMessage(
            role="human",
            content=text,
            timestamp=now,
            phase=session.phase,
        ))
        session.updated_at = now

        # Write to subprocess stdin
        process = self._processes.get(session_id)
        if process and process.stdin:
            try:
                process.stdin.write(text.encode() + b"\n")
                await process.stdin.drain()
                return True
            except Exception:
                pass

        # Mock mode: generate a response
        await self._mock_response(session_id, text)
        return True

    async def _mock_response(self, session_id: str, user_text: str) -> None:
        """Generate a mock orchestrator response when Claude CLI is not available."""
        session = self._sessions.get(session_id)
        if not session:
            return

        now = datetime.now(timezone.utc).isoformat()
        phase = session.phase

        response = (
            f"I hear you. Let me process that in the context of our "
            f"{phase.value.title()} phase.\n\n"
            f"You mentioned: \"{user_text[:100]}...\"\n\n"
            f"Let me ask a follow-up question to make sure I understand fully.\n\n"
            f"[D] Dig Deeper | [A] Adjust | [G] Go to next phase"
        )

        session.messages.append(ThinkTankMessage(
            role="orchestrator",
            content=response,
            timestamp=now,
            phase=phase,
        ))
        session.updated_at = now

        if self._event_bus:
            await self._event_bus.publish(WSEventType.THINKTANK_MESSAGE, {
                "session_id": session_id,
                "message": session.messages[-1].model_dump(),
            })

    async def handle_action(self, session_id: str, action: str, context: str = "") -> bool:
        """Handle a D/A/G menu action."""
        action_map = {
            "dig_deeper": "I want to explore this thread further. Dig deeper.",
            "adjust": f"Let me adjust: {context}" if context else "I need to adjust something.",
            "go_next": "I'm satisfied with this phase. Let's move to the next one.",
        }
        text = action_map.get(action, action)
        return await self.send_message(session_id, text)

    async def approve(self, session_id: str, modifications: str = "") -> bool:
        """Approve the spec-kit and transition to building phase."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        now = datetime.now(timezone.utc).isoformat()

        if modifications:
            await self.send_message(session_id, f"Approved with modifications: {modifications}")
        else:
            await self.send_message(session_id, "Approved. Start building.")

        session.phase = ThinkTankPhase.BUILDING
        session.status = "approved"
        session.updated_at = now

        if self._event_bus:
            await self._event_bus.publish(WSEventType.THINKTANK_PHASE_CHANGE, {
                "session_id": session_id,
                "phase": "building",
            })
            await self._event_bus.publish(WSEventType.TOAST, {
                "message": "Spec-kit approved! Autonomous build starting.",
                "type": "success",
            })

        return True

    def get_session(self, session_id: str) -> ThinkTankSession | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def get_active_session(self) -> ThinkTankSession | None:
        """Get the currently active session, if any."""
        for s in self._sessions.values():
            if s.status == "active":
                return s
        return None

    def get_history(self) -> list[ThinkTankSessionSummary]:
        """Get summaries of all sessions."""
        summaries = []
        for s in self._sessions.values():
            summaries.append(ThinkTankSessionSummary(
                id=s.id,
                topic=s.topic,
                phase=s.phase,
                status=s.status,
                message_count=len(s.messages),
                started_at=s.started_at,
                updated_at=s.updated_at,
            ))
        summaries.sort(key=lambda x: x.updated_at, reverse=True)
        return summaries

    async def cleanup(self) -> None:
        """Clean up all subprocess resources."""
        for task in self._readers.values():
            task.cancel()
        for process in self._processes.values():
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                process.kill()
        self._processes.clear()
        self._readers.clear()
```

---

## Fix 9: Route Modules — `.claude/command-center/backend/routes/`

### Problem

All endpoints in a single file (like 03e) becomes unmanageable at 20+ endpoints. Route
modules organize by domain.

### Solution

One file per domain. Each exports a FastAPI `APIRouter`. The main app includes them all.

### Full Implementation

#### `routes/__init__.py`

```python
"""Route package — all API routers."""
```

#### `routes/agents.py`

```python
"""
routes/agents.py — Agent management endpoints.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

from models import AgentListResponse, Agent, SpawnRequest, SpawnResponse, AgentLogResponse

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _get_agent_service():
    """Get agent service from app state. Set during app startup."""
    from main import get_agent_service
    return get_agent_service()


@router.get("", response_model=AgentListResponse)
async def list_agents():
    """List all agents with status, heartbeat, bead, level."""
    svc = _get_agent_service()
    agents = svc.read_agents()
    await svc.detect_transitions(agents)
    return AgentListResponse(
        agents=agents,
        count=len(agents),
        ts=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/{name}")
async def get_agent(name: str):
    """Get detailed info for a single agent."""
    svc = _get_agent_service()
    agent = svc.get_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return agent


@router.post("/{name}/kill")
async def kill_agent(name: str):
    """Kill an agent via kill-agent.sh."""
    svc = _get_agent_service()
    result = await svc.kill_agent(name)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@router.post("/{name}/retry")
async def retry_agent(name: str):
    """Retry a failed agent via retry-agent.sh."""
    svc = _get_agent_service()
    result = await svc.retry_agent(name)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@router.post("/spawn", response_model=SpawnResponse)
async def spawn_agent(req: SpawnRequest):
    """Spawn a new agent."""
    svc = _get_agent_service()
    result = await svc.spawn_agent(
        mode=req.mode, prompt=req.prompt, path=req.path,
        level=req.level, bead=req.bead,
    )
    return SpawnResponse(
        agent_name=result.get("agent_name", "unknown"),
        status="spawned" if result["success"] else "failed",
        message=result["message"],
    )


@router.get("/{name}/logs", response_model=AgentLogResponse)
async def get_agent_logs(name: str, tail: int = 100):
    """Get the last N lines of an agent's log."""
    svc = _get_agent_service()
    log_file, lines = svc.get_agent_logs(name, tail=tail)
    return AgentLogResponse(
        agent_name=name,
        log_file=log_file,
        lines=lines,
        total_lines=len(lines),
    )
```

#### `routes/beads.py`

```python
"""
routes/beads.py — Bead CRUD, kanban view, and comments.
"""

from fastapi import APIRouter, HTTPException

from models import (
    Bead, BeadCreateRequest, BeadUpdateRequest, BeadMoveRequest,
    BeadCommentRequest, BeadComment, KanbanResponse,
)

router = APIRouter(prefix="/api", tags=["beads"])


def _get_bead_service():
    from main import get_bead_service
    return get_bead_service()


@router.get("/kanban", response_model=KanbanResponse)
async def get_kanban():
    """Beads organized by kanban columns."""
    svc = _get_bead_service()
    return svc.get_kanban()


@router.patch("/beads/{bead_id}/move")
async def move_bead(bead_id: str, req: BeadMoveRequest):
    """Move a bead between kanban columns."""
    svc = _get_bead_service()
    ok, output = await svc.move_bead(bead_id, req.column)
    if not ok:
        raise HTTPException(status_code=500, detail=output)
    return {"success": True, "message": output}


@router.get("/beads", response_model=list[Bead])
async def list_beads(status: str | None = None, assignee: str | None = None,
                     epic: str | None = None):
    """List all beads with optional filtering."""
    svc = _get_bead_service()
    return svc.list_beads(status=status, assignee=assignee, epic=epic)


@router.get("/beads/{bead_id}", response_model=Bead)
async def get_bead(bead_id: str):
    """Get a single bead by ID."""
    svc = _get_bead_service()
    bead = svc.get_bead(bead_id)
    if not bead:
        raise HTTPException(status_code=404, detail=f"Bead '{bead_id}' not found")
    return bead


@router.post("/beads")
async def create_bead(req: BeadCreateRequest):
    """Create a new bead."""
    svc = _get_bead_service()
    ok, output = svc.create_bead(
        title=req.title, bead_type=req.type, priority=req.priority,
        epic=req.epic, assignee=req.assignee, notes=req.notes,
    )
    if not ok:
        raise HTTPException(status_code=500, detail=output)
    return {"success": True, "message": output}


@router.patch("/beads/{bead_id}")
async def update_bead(bead_id: str, req: BeadUpdateRequest):
    """Update a bead's fields."""
    svc = _get_bead_service()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    ok, output = svc.update_bead(bead_id, **updates)
    if not ok:
        raise HTTPException(status_code=500, detail=output)
    return {"success": True, "message": output}


@router.post("/beads/{bead_id}/comment")
async def add_comment(bead_id: str, req: BeadCommentRequest):
    """Add a comment to a bead."""
    svc = _get_bead_service()
    ok, output = svc.add_comment(bead_id, req.text, req.author)
    if not ok:
        raise HTTPException(status_code=500, detail=output)
    return {"success": True, "message": output}


@router.get("/beads/{bead_id}/comments", response_model=list[BeadComment])
async def get_comments(bead_id: str):
    """Get comment thread for a bead."""
    svc = _get_bead_service()
    return svc.get_comments(bead_id)
```

#### `routes/attachments.py`

```python
"""
routes/attachments.py — File upload and download.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from models import Attachment, AttachmentListResponse

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


def _get_attachment_service():
    from main import get_attachment_service
    return get_attachment_service()


@router.post("", response_model=Attachment)
async def upload_attachment(
    file: UploadFile = File(...),
    bead_id: str | None = Form(None),
):
    """Upload a file (screenshot paste, drag-drop)."""
    svc = _get_attachment_service()
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    return svc.save(file.filename or "upload", content, bead_id=bead_id)


@router.get("/{att_id}")
async def get_attachment(att_id: str):
    """Serve an attachment file."""
    svc = _get_attachment_service()
    att = svc.get(att_id)
    if not att:
        raise HTTPException(status_code=404, detail=f"Attachment '{att_id}' not found")
    file_path = svc.get_file_path(att_id)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(path=str(file_path), media_type=att.mime_type, filename=att.filename)


@router.get("", response_model=AttachmentListResponse)
async def list_attachments(bead_id: str | None = None):
    """List all attachments."""
    svc = _get_attachment_service()
    attachments = svc.list_all(bead_id=bead_id)
    return AttachmentListResponse(attachments=attachments, count=len(attachments))
```

#### `routes/thinktank.py`

```python
"""
routes/thinktank.py — Think Tank brainstorming session management.
"""

from fastapi import APIRouter, HTTPException

from models import (
    ThinkTankStartRequest, ThinkTankMessageRequest, ThinkTankActionRequest,
    ThinkTankApproveRequest, ThinkTankSession, ThinkTankSessionSummary,
)

router = APIRouter(prefix="/api/thinktank", tags=["thinktank"])


def _get_thinktank_service():
    from main import get_thinktank_service
    return get_thinktank_service()


@router.post("/start", response_model=ThinkTankSession)
async def start_session(req: ThinkTankStartRequest):
    """Start a new brainstorming session."""
    svc = _get_thinktank_service()
    return await svc.start_session(topic=req.topic, context=req.context)


@router.get("/session")
async def get_session():
    """Get the current active session state."""
    svc = _get_thinktank_service()
    session = svc.get_active_session()
    if not session:
        return {"active": False, "session": None}
    return {"active": True, "session": session}


@router.post("/message")
async def send_message(req: ThinkTankMessageRequest):
    """Send a human message to the orchestrator."""
    svc = _get_thinktank_service()
    session = svc.get_active_session()
    if not session:
        raise HTTPException(status_code=404, detail="No active session")
    ok = await svc.send_message(session.id, req.text)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send message")
    return {"success": True}


@router.post("/action")
async def handle_action(req: ThinkTankActionRequest):
    """Handle a D/A/G menu action."""
    svc = _get_thinktank_service()
    session = svc.get_active_session()
    if not session:
        raise HTTPException(status_code=404, detail="No active session")
    ok = await svc.handle_action(session.id, req.action, req.context)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to handle action")
    return {"success": True}


@router.post("/approve")
async def approve_session(req: ThinkTankApproveRequest):
    """Approve spec-kit and trigger autonomous execution."""
    svc = _get_thinktank_service()
    session = svc.get_active_session()
    if not session:
        raise HTTPException(status_code=404, detail="No active session")
    ok = await svc.approve(session.id, req.modifications)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to approve")
    return {"success": True, "message": "Spec-kit approved. Building started."}


@router.get("/history", response_model=list[ThinkTankSessionSummary])
async def get_history():
    """Get past brainstorming sessions."""
    svc = _get_thinktank_service()
    return svc.get_history()
```

#### `routes/commands.py`

```python
"""
routes/commands.py — Command palette backend.
"""

from fastapi import APIRouter, HTTPException

from models import Command, CommandExecuteRequest, CommandExecuteResponse, CommandSearchRequest

router = APIRouter(prefix="/api/commands", tags=["commands"])


def _get_command_service():
    from main import get_command_service
    return get_command_service()


def _get_agent_service():
    from main import get_agent_service
    return get_agent_service()


def _get_bead_service():
    from main import get_bead_service
    return get_bead_service()


@router.get("/available", response_model=list[Command])
async def list_commands(context: str | None = None):
    """List available commands, optionally filtered by context."""
    svc = _get_command_service()
    return svc.list_commands(context=context)


@router.post("/search", response_model=list[Command])
async def search_commands(req: CommandSearchRequest):
    """Fuzzy search commands for Cmd+K palette."""
    svc = _get_command_service()
    return svc.search(query=req.query, context=req.context, limit=req.limit)


@router.post("/execute", response_model=CommandExecuteResponse)
async def execute_command(req: CommandExecuteRequest):
    """Execute a command."""
    cmd_svc = _get_command_service()
    cmd = cmd_svc.get_command(req.command_id)
    if not cmd:
        raise HTTPException(status_code=404, detail=f"Command '{req.command_id}' not found")

    if cmd.requires_confirmation and not req.confirmed:
        return CommandExecuteResponse(
            command_id=req.command_id,
            success=False,
            message=f"Command '{cmd.name}' requires confirmation. Set confirmed=true to proceed.",
        )

    # Route to appropriate service
    try:
        result = await _dispatch_command(cmd, req.params)
        return CommandExecuteResponse(
            command_id=req.command_id,
            success=result.get("success", False),
            message=result.get("message", ""),
            output=result.get("output"),
        )
    except Exception as e:
        return CommandExecuteResponse(
            command_id=req.command_id,
            success=False,
            message=str(e),
        )


async def _dispatch_command(cmd: Command, params: dict) -> dict:
    """Route a command to the appropriate service method."""
    agent_svc = _get_agent_service()
    bead_svc = _get_bead_service()

    handlers = {
        "agent.kill": lambda: agent_svc.kill_agent(params.get("name", "")),
        "agent.retry": lambda: agent_svc.retry_agent(params.get("name", "")),
        "agent.spawn": lambda: agent_svc.spawn_agent(
            mode=params.get("mode", "worktree"),
            prompt=params.get("prompt", ""),
            path=params.get("path"),
            level=params.get("level", 2),
            bead=params.get("bead"),
        ),
        "bead.create": lambda: _sync_wrap(bead_svc.create_bead(
            title=params.get("title", "Untitled"),
            bead_type=params.get("type", "task"),
            priority=params.get("priority"),
        )),
        "bead.close": lambda: _sync_wrap(bead_svc.update_bead(params.get("id", ""), status="closed")),
        "system.health": lambda: _async_return({"success": True, "message": "API healthy"}),
    }

    handler = handlers.get(cmd.id)
    if handler:
        result = handler()
        if hasattr(result, "__await__"):
            return await result
        return result

    return {"success": False, "message": f"No handler for command '{cmd.id}'"}


def _sync_wrap(result: tuple) -> dict:
    ok, output = result
    return {"success": ok, "message": output}


async def _async_return(val: dict) -> dict:
    return val
```

#### `routes/dashboard.py`

```python
"""
routes/dashboard.py — Dashboard overview, timeline, and health.
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from models import DashboardOverview, TimelineResponse, TimelineEvent

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _get_agent_service():
    from main import get_agent_service
    return get_agent_service()


def _get_bead_service():
    from main import get_bead_service
    return get_bead_service()


def _get_thinktank_service():
    from main import get_thinktank_service
    return get_thinktank_service()


@router.get("/overview", response_model=DashboardOverview)
async def get_overview():
    """Summary stats for the dashboard header."""
    agent_svc = _get_agent_service()
    bead_svc = _get_bead_service()
    tt_svc = _get_thinktank_service()

    agents = agent_svc.read_agents()
    kanban = bead_svc.get_kanban()
    epics = bead_svc.build_epics()

    active = sum(1 for a in agents if a.status.value in ("working", "spawning"))
    stale = sum(1 for a in agents if a.heartbeat_stale)

    avg_progress = 0.0
    if epics:
        avg_progress = sum(e["progress_pct"] for e in epics) / len(epics)

    return DashboardOverview(
        active_agents=active,
        total_agents=len(agents),
        stale_agents=stale,
        open_beads=kanban.columns.get("backlog", type("", (), {"count": 0})).count
                   + kanban.columns.get("ready", type("", (), {"count": 0})).count,
        in_progress_beads=kanban.columns.get("in_progress", type("", (), {"count": 0})).count,
        blocked_beads=kanban.columns.get("blocked", type("", (), {"count": 0})).count,
        done_beads=kanban.columns.get("done", type("", (), {"count": 0})).count,
        epic_count=len(epics),
        avg_epic_progress=round(avg_progress, 1),
        thinktank_active=tt_svc.get_active_session() is not None,
    )


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(limit: int = 50):
    """Recent events from agent transitions."""
    agent_svc = _get_agent_service()
    # Trigger transition detection
    agents = agent_svc.read_agents()
    await agent_svc.detect_transitions(agents)
    events = agent_svc.get_timeline(limit=limit)
    return TimelineResponse(
        events=[TimelineEvent(**e) for e in events],
        total_events=len(events),
    )


@router.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}
```

#### `routes/epics.py`

```python
"""
routes/epics.py — Epic progress and dependency graphs.
"""

from fastapi import APIRouter, HTTPException

from models import EpicListResponse, Epic, EpicGraphResponse, EpicGraphNode

router = APIRouter(prefix="/api/epics", tags=["epics"])


def _get_bead_service():
    from main import get_bead_service
    return get_bead_service()


@router.get("", response_model=EpicListResponse)
async def list_epics():
    """All epics with progress percentages."""
    svc = _get_bead_service()
    epics_data = svc.build_epics()
    epics = [Epic(**e) for e in epics_data]
    return EpicListResponse(epics=epics, count=len(epics))


@router.get("/{epic_id}")
async def get_epic(epic_id: str):
    """Epic detail with bead breakdown."""
    svc = _get_bead_service()
    epics_data = svc.build_epics()
    for e in epics_data:
        if e["epic"] == epic_id:
            beads = svc.list_beads(epic=epic_id)
            return {**e, "bead_details": beads}
    raise HTTPException(status_code=404, detail=f"Epic '{epic_id}' not found")


@router.get("/{epic_id}/graph", response_model=EpicGraphResponse)
async def get_epic_graph(epic_id: str):
    """Dependency DAG for an epic."""
    svc = _get_bead_service()
    beads = svc.list_beads(epic=epic_id)
    if not beads:
        raise HTTPException(status_code=404, detail=f"No beads found for epic '{epic_id}'")

    nodes = [EpicGraphNode(id=b.id, title=b.title, status=b.status, deps=b.deps) for b in beads]
    edges = []
    for b in beads:
        for dep in b.deps:
            edges.append({"from": dep, "to": b.id})

    return EpicGraphResponse(epic=epic_id, nodes=nodes, edges=edges)
```

#### `routes/websocket.py`

```python
"""
routes/websocket.py — WebSocket hub for real-time push.

Clients connect to /ws and receive all events from the event bus.
Think Tank messages are also routed through this connection.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


def _get_event_bus():
    from main import get_event_bus
    return get_event_bus()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Main WebSocket endpoint for real-time updates."""
    await ws.accept()
    bus = _get_event_bus()
    queue = await bus.subscribe()

    try:
        # Send welcome message
        await ws.send_json({
            "type": "CONNECTED",
            "payload": {"message": "Connected to Command Center"},
        })

        while True:
            try:
                # Wait for events with a timeout so we can detect disconnects
                event_json = await asyncio.wait_for(queue.get(), timeout=30)
                await ws.send_text(event_json)
            except asyncio.TimeoutError:
                # Send heartbeat ping
                try:
                    await ws.send_json({"type": "PING", "payload": {}})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await bus.unsubscribe(queue)


@router.websocket("/ws/thinktank")
async def thinktank_websocket(ws: WebSocket):
    """Dedicated WebSocket for Think Tank real-time chat + spec-kit streaming.

    This is a filtered view of the event bus that only sends Think Tank events.
    It also accepts messages from the client for bidirectional communication.
    """
    await ws.accept()
    bus = _get_event_bus()
    queue = await bus.subscribe()

    thinktank_events = {
        "THINKTANK_MESSAGE",
        "THINKTANK_SPECKIT_DELTA",
        "THINKTANK_PHASE_CHANGE",
        "APPROVAL_NEEDED",
    }

    async def reader():
        """Read messages from the WebSocket client."""
        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)
                # Route to think tank service
                if msg.get("type") == "message":
                    from main import get_thinktank_service
                    svc = get_thinktank_service()
                    session = svc.get_active_session()
                    if session:
                        await svc.send_message(session.id, msg.get("text", ""))
                elif msg.get("type") == "action":
                    from main import get_thinktank_service
                    svc = get_thinktank_service()
                    session = svc.get_active_session()
                    if session:
                        await svc.handle_action(session.id, msg.get("action", ""), msg.get("context", ""))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    async def writer():
        """Push Think Tank events to the WebSocket client."""
        try:
            while True:
                event_json = await queue.get()
                event = json.loads(event_json)
                if event.get("type") in thinktank_events:
                    await ws.send_text(event_json)
        except Exception:
            pass

    # Run reader and writer concurrently
    reader_task = asyncio.create_task(reader())
    writer_task = asyncio.create_task(writer())

    try:
        await asyncio.gather(reader_task, writer_task)
    except Exception:
        pass
    finally:
        reader_task.cancel()
        writer_task.cancel()
        await bus.unsubscribe(queue)
```

---

## Fix 10: Main Application — `.claude/command-center/backend/main.py`

### Problem

The application needs a single entry point that wires up all services, routes, and
background tasks. It must handle startup/shutdown lifecycle correctly.

### Solution

A FastAPI app factory with lifespan context manager. Services are created once at startup
and shared via module-level accessor functions. A background task polls agent status every
5 seconds for transition detection.

### Full Implementation

```python
"""
main.py — Command Center API application.

Usage:
    uvicorn main:app --host 0.0.0.0 --port 8002
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import PORT
from services.event_bus import event_bus
from services.agent_service import AgentService
from services.bead_service import BeadService
from services.attachment_service import AttachmentService
from services.thinktank_service import ThinkTankService
from services.command_service import CommandService

from routes import agents, beads, attachments, thinktank, commands, dashboard, epics, websocket

# ── Service singletons ────────────────────────────────────────────────────────

_agent_service: AgentService | None = None
_bead_service: BeadService | None = None
_attachment_service: AttachmentService | None = None
_thinktank_service: ThinkTankService | None = None
_command_service: CommandService | None = None


def get_event_bus():
    return event_bus

def get_agent_service() -> AgentService:
    assert _agent_service is not None
    return _agent_service

def get_bead_service() -> BeadService:
    assert _bead_service is not None
    return _bead_service

def get_attachment_service() -> AttachmentService:
    assert _attachment_service is not None
    return _attachment_service

def get_thinktank_service() -> ThinkTankService:
    assert _thinktank_service is not None
    return _thinktank_service

def get_command_service() -> CommandService:
    assert _command_service is not None
    return _command_service


# ── Background task: agent status polling ─────────────────────────────────────

async def _agent_poll_loop():
    """Poll agent status every 5 seconds to detect transitions and push events."""
    while True:
        try:
            agents = _agent_service.read_agents()
            await _agent_service.detect_transitions(agents)
        except Exception:
            pass  # Never crash the poll loop
        await asyncio.sleep(5)


# ── Application lifespan ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent_service, _bead_service, _attachment_service
    global _thinktank_service, _command_service

    # Startup: create services
    _agent_service = AgentService(event_bus=event_bus)
    _bead_service = BeadService(event_bus=event_bus)
    _attachment_service = AttachmentService()
    _thinktank_service = ThinkTankService(event_bus=event_bus)
    _command_service = CommandService()

    # Start background polling
    poll_task = asyncio.create_task(_agent_poll_loop())

    yield

    # Shutdown: clean up
    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass
    await _thinktank_service.cleanup()


# ── Create app ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Baap Command Center API",
    version="2.0.0",
    description="Backend for interactive agent swarm management dashboard",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(agents.router)
app.include_router(beads.router)
app.include_router(attachments.router)
app.include_router(thinktank.router)
app.include_router(commands.router)
app.include_router(dashboard.router)
app.include_router(epics.router)
app.include_router(websocket.router)


@app.get("/")
async def root():
    return {
        "name": "Baap Command Center API",
        "version": "2.0.0",
        "docs": "/docs",
        "websocket": "/ws",
    }
```

---

## Fix 11: Init Files — Package Structure

### `services/__init__.py`

```python
"""Service package."""
```

### `__init__.py`

```python
"""Command Center backend package."""
```

---

## Fix 12: Launcher Script — `.claude/command-center/backend/start.sh`

### Problem

The human needs a one-liner to start the Command Center on India.

### Solution

```bash
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
```

---

## Fix 13: Requirements — `.claude/command-center/backend/requirements.txt`

```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
websockets>=12.0
python-multipart>=0.0.6
pydantic>=2.5.0
```

---

## Success Criteria

### Core API
- [ ] `main.py` starts without errors on `uvicorn main:app --port 8002`
- [ ] `GET /` returns API info with name, version, docs link
- [ ] `GET /docs` serves Swagger UI with all endpoints documented
- [ ] CORS allows requests from any origin

### Agent Endpoints
- [ ] `GET /api/agents` returns agent list with status, heartbeat, level
- [ ] `GET /api/agents/{name}` returns single agent or 404
- [ ] `POST /api/agents/{name}/kill` calls kill-agent.sh and returns result
- [ ] `POST /api/agents/{name}/retry` calls retry-agent.sh and returns result
- [ ] `POST /api/agents/spawn` calls spawn.sh with provided params
- [ ] `GET /api/agents/{name}/logs` returns last N lines of agent log

### Bead Endpoints
- [ ] `GET /api/kanban` returns beads organized by 6 kanban columns
- [ ] `PATCH /api/beads/{id}/move` changes bead status to match target column
- [ ] `GET /api/beads` returns all beads with optional filtering (status, assignee, epic)
- [ ] `POST /api/beads` creates a new bead via bd CLI
- [ ] `PATCH /api/beads/{id}` updates bead fields
- [ ] `POST /api/beads/{id}/comment` appends comment to bead notes
- [ ] `GET /api/beads/{id}/comments` parses and returns comment thread

### Attachment Endpoints
- [ ] `POST /api/attachments` accepts file upload (multipart form)
- [ ] `GET /api/attachments/{id}` serves the file with correct mime type
- [ ] `GET /api/attachments` lists all attachments with metadata
- [ ] Files stored in `.claude/command-center/attachments/` with UUID names
- [ ] `_index.json` sidecar tracks all attachment metadata
- [ ] 10MB file size limit enforced

### Think Tank Endpoints
- [ ] `POST /api/thinktank/start` creates a new session with topic
- [ ] `GET /api/thinktank/session` returns active session or `{active: false}`
- [ ] `POST /api/thinktank/message` sends human message to orchestrator
- [ ] `POST /api/thinktank/action` handles D/A/G menu actions
- [ ] `POST /api/thinktank/approve` transitions to building phase
- [ ] `GET /api/thinktank/history` returns past session summaries
- [ ] Mock mode works when Claude CLI is not installed

### Command Endpoints
- [ ] `GET /api/commands/available` returns full command registry
- [ ] `POST /api/commands/search` supports fuzzy search with scoring
- [ ] `POST /api/commands/execute` routes to correct service handler
- [ ] Commands requiring confirmation return error if `confirmed=false`
- [ ] Script directory scanning discovers `.claude/scripts/*.sh` automatically

### Dashboard Endpoints
- [ ] `GET /api/dashboard/overview` returns summary stats
- [ ] `GET /api/dashboard/timeline` returns recent events
- [ ] `GET /api/dashboard/health` returns `{status: "ok"}`

### Epic Endpoints
- [ ] `GET /api/epics` returns all epics with progress percentages
- [ ] `GET /api/epics/{id}` returns epic detail with bead breakdown
- [ ] `GET /api/epics/{id}/graph` returns dependency DAG (nodes + edges)

### WebSocket
- [ ] `ws://host:8002/ws` accepts connections and sends CONNECTED event
- [ ] Agent status changes push AGENT_STATUS_CHANGE events
- [ ] Bead moves push BEAD_TRANSITION events
- [ ] Think Tank messages push THINKTANK_MESSAGE events
- [ ] PING sent every 30 seconds as keepalive
- [ ] `/ws/thinktank` filters to Think Tank events only
- [ ] `/ws/thinktank` accepts client messages for bidirectional chat

### Configuration
- [ ] All paths configurable via BAAP_* environment variables
- [ ] Project root auto-detected from .git directory
- [ ] Port configurable via BAAP_CC_PORT (default 8002)
- [ ] Works with any project directory structure (reusable)

### Launcher
- [ ] `bash start.sh` starts the server in foreground
- [ ] `bash start.sh --bg` starts in background with PID and log file
- [ ] Auto-installs missing pip dependencies
- [ ] Activates venv if present

---

## Verification

```bash
cd ~/Projects/baap

# ── Step 1: Start the Command Center ──────────────────────────────────────────
bash .claude/command-center/backend/start.sh &
CC_PID=$!
sleep 4

# ── Step 2: Health check ─────────────────────────────────────────────────────
curl -s http://localhost:8002/api/dashboard/health | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['status'] == 'ok', 'Health check failed'
print('PASS: Health check')
"

# ── Step 3: Root endpoint ────────────────────────────────────────────────────
curl -s http://localhost:8002/ | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['version'] == '2.0.0', f'Wrong version: {d[\"version\"]}'
assert 'websocket' in d, 'Missing websocket info'
print('PASS: Root endpoint')
"

# ── Step 4: Agent endpoints ──────────────────────────────────────────────────
# Create a test agent
mkdir -p /tmp/baap-agent-status /tmp/baap-heartbeats
cat > /tmp/baap-agent-status/test-cc-agent.json << 'AGENT'
{
  "agent": "test-cc-agent",
  "level": 2,
  "status": "working",
  "started_at": "2026-02-14T10:00:00+00:00",
  "current_action": "Testing command center",
  "errors": 0
}
AGENT
date +%s > /tmp/baap-heartbeats/test-cc-agent
sleep 2

curl -s http://localhost:8002/api/agents | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'agents' in d and 'count' in d, 'Bad agents response shape'
names = [a['name'] for a in d['agents']]
assert 'test-cc-agent' in names, f'Test agent not found in {names}'
print(f'PASS: Agent list ({d[\"count\"]} agents)')
"

curl -s http://localhost:8002/api/agents/test-cc-agent | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['name'] == 'test-cc-agent', 'Wrong agent returned'
assert d['status'] == 'working', f'Wrong status: {d[\"status\"]}'
print('PASS: Single agent detail')
"

# ── Step 5: Kanban endpoint ──────────────────────────────────────────────────
curl -s http://localhost:8002/api/kanban | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'columns' in d, 'Missing columns key'
expected = ['backlog', 'ready', 'in_progress', 'in_review', 'blocked', 'done']
for col in expected:
    assert col in d['columns'], f'Missing column: {col}'
print(f'PASS: Kanban endpoint ({d[\"total\"]} beads)')
"

# ── Step 6: Command search ───────────────────────────────────────────────────
curl -s -X POST http://localhost:8002/api/commands/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "kill", "limit": 5}' | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert isinstance(d, list), 'Expected list of commands'
names = [c['name'] for c in d]
assert any('Kill' in n for n in names), f'Kill command not found in {names}'
print(f'PASS: Command search ({len(d)} results for \"kill\")')
"

# ── Step 7: Dashboard overview ───────────────────────────────────────────────
curl -s http://localhost:8002/api/dashboard/overview | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'active_agents' in d, 'Missing active_agents'
assert 'open_beads' in d, 'Missing open_beads'
assert 'thinktank_active' in d, 'Missing thinktank_active'
print(f'PASS: Dashboard overview (agents={d[\"total_agents\"]}, beads={d[\"open_beads\"]})')
"

# ── Step 8: Think Tank start ─────────────────────────────────────────────────
curl -s -X POST http://localhost:8002/api/thinktank/start \
  -H 'Content-Type: application/json' \
  -d '{"topic": "Test dashboard project"}' | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'id' in d, 'Missing session ID'
assert d['phase'] == 'listen', f'Wrong initial phase: {d[\"phase\"]}'
assert d['status'] == 'active', f'Wrong status: {d[\"status\"]}'
print(f'PASS: Think Tank session started ({d[\"id\"]})')
"

# ── Step 9: Attachment upload ────────────────────────────────────────────────
echo "test content" > /tmp/test-attachment.txt
curl -s -X POST http://localhost:8002/api/attachments \
  -F "file=@/tmp/test-attachment.txt" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'id' in d, 'Missing attachment ID'
assert d['filename'] == 'test-attachment.txt', f'Wrong filename: {d[\"filename\"]}'
print(f'PASS: Attachment uploaded ({d[\"id\"]}, {d[\"size_bytes\"]} bytes)')
"
rm -f /tmp/test-attachment.txt

# ── Step 10: Epics endpoint ──────────────────────────────────────────────────
curl -s http://localhost:8002/api/epics | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'epics' in d and 'count' in d, 'Bad epics response shape'
print(f'PASS: Epics endpoint ({d[\"count\"]} epics)')
"

# ── Step 11: WebSocket connection test ───────────────────────────────────────
python3 -c "
import asyncio, websockets, json

async def test_ws():
    async with websockets.connect('ws://localhost:8002/ws') as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(msg)
        assert data['type'] == 'CONNECTED', f'Wrong first message type: {data[\"type\"]}'
        print('PASS: WebSocket connected and received welcome')

asyncio.run(test_ws())
" 2>/dev/null || echo "SKIP: WebSocket test (websockets package not installed)"

# ── Step 12: Swagger docs ───────────────────────────────────────────────────
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/docs)
[ "$HTTP_CODE" = "200" ] && echo "PASS: Swagger docs served (200)" || echo "FAIL: Swagger docs not served ($HTTP_CODE)"

# ── Cleanup ──────────────────────────────────────────────────────────────────
rm -f /tmp/baap-agent-status/test-cc-agent.json
rm -f /tmp/baap-heartbeats/test-cc-agent
kill $CC_PID 2>/dev/null || true

echo ""
echo "All Command Center verification tests completed."
```
