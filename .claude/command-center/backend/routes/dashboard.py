"""
routes/dashboard.py — Dashboard overview, timeline, and health.
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

from config import PROJECT_ROOT, SCRIPTS_DIR
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


@router.get("", response_model=DashboardOverview)
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


@router.get("/health/dispatch-ready")
async def dispatch_ready_health():
    """Pre-flight health check for dispatch readiness.

    Checks that all required binaries and paths exist for agent dispatch.
    Returns per-check results and an overall ready status.
    """
    checks = {}

    # Check bd binary
    checks["bd"] = shutil.which("bd") is not None

    # Check tmux binary
    checks["tmux"] = shutil.which("tmux") is not None

    # Check claude binary
    checks["claude"] = shutil.which("claude") is not None

    # Check spawn.sh exists
    spawn_script = SCRIPTS_DIR / "spawn.sh"
    checks["spawn_sh"] = spawn_script.exists()

    # Check project root is a git repo
    checks["git_repo"] = (PROJECT_ROOT / ".git").exists()

    # Check agents directory exists (or can be created)
    agents_dir = Path.home() / "agents"
    checks["agents_dir"] = agents_dir.exists() or agents_dir.parent.exists()

    all_ready = all(checks.values())
    missing = [k for k, v in checks.items() if not v]

    return {
        "ready": all_ready,
        "checks": checks,
        "missing": missing,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/test-notification")
async def test_notification():
    """Send a test notification to all configured channels."""
    from services.notification_bridge import get_notification_router
    router = get_notification_router()
    if not router:
        return {"success": False, "message": "Notification router not available"}
    result = await router.send_test()
    return {"success": result.get("sent", 0) > 0, "result": result}
