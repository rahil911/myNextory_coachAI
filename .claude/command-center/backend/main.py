"""
main.py — Command Center API application.

Usage:
    uvicorn main:app --host 0.0.0.0 --port 8002
"""

import asyncio
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import PORT
from services.event_bus import event_bus
from services.agent_service import AgentService
from services.bead_service import BeadService
from services.attachment_service import AttachmentService
from services.thinktank_service import ThinkTankService
from services.command_service import CommandService
from services.notification_bridge import get_notification_router
from services.tory_service import ToryService

from routes import agents, approvals, beads, attachments, thinktank, commands, dashboard, epics, tory, websocket

# ── Service singletons ────────────────────────────────────────────────────────

_agent_service: AgentService | None = None
_bead_service: BeadService | None = None
_attachment_service: AttachmentService | None = None
_thinktank_service: ThinkTankService | None = None
_command_service: CommandService | None = None
_tory_service: ToryService | None = None


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

def get_tory_service() -> ToryService:
    assert _tory_service is not None
    return _tory_service


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
    global _thinktank_service, _command_service, _tory_service

    # Startup: create services
    _notification_router = get_notification_router()
    _agent_service = AgentService(event_bus=event_bus, notification_router=_notification_router)
    _bead_service = BeadService(event_bus=event_bus)
    _attachment_service = AttachmentService()
    _thinktank_service = ThinkTankService(event_bus=event_bus)
    _command_service = CommandService()
    _tory_service = ToryService()

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
app.include_router(approvals.router)
app.include_router(beads.router)
app.include_router(attachments.router)
app.include_router(thinktank.router)
app.include_router(commands.router)
app.include_router(dashboard.router)
app.include_router(epics.router)
app.include_router(tory.router)
app.include_router(websocket.router)


# ── Convenience endpoint ─────────────────────────────────────────────────────

@app.post("/api/test-notification")
async def test_notification():
    """Send a test notification to all configured channels."""
    from services.notification_bridge import get_notification_router
    nr = get_notification_router()
    if not nr:
        return {"success": False, "message": "Notification router not available"}
    result = await nr.send_test()
    return {"success": result.get("sent", 0) > 0, "result": result}


# ── Serve frontend static files ──────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")

    @app.get("/")
    async def root():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
else:
    @app.get("/")
    async def root():
        return {
            "name": "Baap Command Center API",
            "version": "2.0.0",
            "docs": "/docs",
            "websocket": "/ws",
        }
