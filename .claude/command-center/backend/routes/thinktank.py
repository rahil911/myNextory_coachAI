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


@router.get("/session/{session_id}", response_model=ThinkTankSession)
async def get_session_by_id(session_id: str):
    """Get a specific session by ID (any status)."""
    svc = _get_thinktank_service()
    session = svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


@router.post("/resume/{session_id}", response_model=ThinkTankSession)
async def resume_session(session_id: str):
    """Resume a paused session, making it the active session."""
    svc = _get_thinktank_service()
    session = await svc.resume_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session permanently."""
    svc = _get_thinktank_service()
    ok = svc.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"success": True, "message": f"Session '{session_id}' deleted"}


# ── Dispatch Engine endpoints ─────────────────────────────────────────────

@router.get("/dispatch/{session_id}")
async def get_dispatch_status(session_id: str):
    """Get dispatch status for a session."""
    svc = _get_thinktank_service()
    dispatch = svc._get_dispatch_engine()
    status = dispatch.get_dispatch_status(session_id)
    if not status:
        return {"status": "not_dispatched"}
    return status


@router.post("/dispatch/{session_id}/cancel")
async def cancel_dispatch(session_id: str):
    """Cancel an active dispatch."""
    svc = _get_thinktank_service()
    dispatch = svc._get_dispatch_engine()
    success = await dispatch.cancel_dispatch(session_id)
    return {"cancelled": success}


@router.post("/dispatch/{session_id}/retry")
async def retry_dispatch(session_id: str):
    """Retry dispatch for an approved session."""
    svc = _get_thinktank_service()
    session = svc.get_session(session_id)
    if not session or session.status != "approved":
        raise HTTPException(status_code=400, detail="Session not found or not approved")
    dispatch = svc._get_dispatch_engine()
    result = await dispatch.dispatch_approved_session(session)
    return result
