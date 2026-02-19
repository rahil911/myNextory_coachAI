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
    AGENT_SPAWNED = "AGENT_SPAWNED"
    AGENT_WORKING = "AGENT_WORKING"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    AGENT_FAILED = "AGENT_FAILED"
    BEAD_TRANSITION = "BEAD_TRANSITION"
    THINKTANK_MESSAGE = "THINKTANK_MESSAGE"
    THINKTANK_SPECKIT_DELTA = "THINKTANK_SPECKIT_DELTA"
    THINKTANK_PHASE_CHANGE = "THINKTANK_PHASE_CHANGE"
    APPROVAL_NEEDED = "APPROVAL_NEEDED"
    APPROVAL_RESOLVED = "APPROVAL_RESOLVED"
    TIMELINE_EVENT = "TIMELINE_EVENT"
    TOAST = "TOAST"
    # Dispatch Engine events
    DISPATCH_STARTED = "DISPATCH_STARTED"
    DISPATCH_PROGRESS = "DISPATCH_PROGRESS"
    DISPATCH_COMPLETE = "DISPATCH_COMPLETE"
    DISPATCH_ERROR = "DISPATCH_ERROR"
    AGENT_PROGRESS = "AGENT_PROGRESS"
    AGENT_RETRYING = "AGENT_RETRYING"
    BEAD_STATUS_CHANGE = "BEAD_STATUS_CHANGE"
    FAILURE_HANDLED = "FAILURE_HANDLED"
    # Tory Agent events
    TORY_AGENT_STARTED = "TORY_AGENT_STARTED"
    TORY_AGENT_PROGRESS = "TORY_AGENT_PROGRESS"
    TORY_AGENT_COMPLETED = "TORY_AGENT_COMPLETED"
    TORY_AGENT_FAILED = "TORY_AGENT_FAILED"


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
    epic_id: str | None = None  # linked beads epic ID (set after dispatch)


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


# ── Approval Models ──────────────────────────────────────────────────────────

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalSource(str, Enum):
    OWNERSHIP = "ownership"
    AGENT_ACTION = "agent_action"


class Approval(BaseModel):
    id: str
    source: ApprovalSource = ApprovalSource.OWNERSHIP
    file: str | None = None
    agent: str | None = None
    evidence: str = ""
    proposed_at: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    auto_approved: bool = False
    reason: str = ""
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    reject_reason: str | None = None


class ApprovalListResponse(BaseModel):
    pending: list[Approval]
    history: list[Approval]
    pending_count: int


class ApprovalRejectRequest(BaseModel):
    reason: str = ""
