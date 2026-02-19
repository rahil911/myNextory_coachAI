"""
routes/thinktank.py — Think Tank brainstorming session management.
"""

from fastapi import APIRouter, HTTPException, Request

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


@router.post("/approve/{session_id}")
async def approve_session(session_id: str, req: ThinkTankApproveRequest, request: Request, dry_run: bool = False):
    """Approve spec-kit and trigger autonomous execution.

    Args:
        session_id: Session to approve (from URL path)
        dry_run: If true (query param), return bead plan preview without creating beads
    """
    svc = _get_thinktank_service()
    session = svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    # Idempotency check: if same key was already processed, return cached result
    idempotency_key = request.headers.get("X-Idempotency-Key", "")
    dispatch = svc._get_dispatch_engine()
    if idempotency_key:
        cached = dispatch.check_idempotency(idempotency_key)
        if cached is not None:
            return cached

    # Pre-flight health check (skip for dry-run)
    if not dry_run:
        health = dispatch.check_dispatch_health()
        if not health["ready"]:
            missing = ", ".join(health["missing"])
            raise HTTPException(
                status_code=503,
                detail=f"Dispatch prerequisites missing: {missing}. Install required binaries before approving.",
            )

    result = await svc.approve(session_id, req.modifications, dry_run=dry_run)

    # Cache result for idempotency
    if idempotency_key and result.get("success"):
        dispatch.cache_idempotency(idempotency_key, result)

    if not result.get("success") and not dry_run:
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Dispatch failed"),
        )

    return result


# Keep legacy route for backwards compatibility (redirects to new path)
@router.post("/approve")
async def approve_session_legacy(req: ThinkTankApproveRequest, request: Request):
    """Legacy approve route — uses active session."""
    svc = _get_thinktank_service()
    session = svc.get_active_session()
    if not session:
        raise HTTPException(status_code=404, detail="No active session")
    return await approve_session(session.id, req, request)


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


@router.post("/session/{session_id}/phase")
async def set_session_phase(session_id: str, phase: int):
    """Set session phase (supports backward navigation)."""
    svc = _get_thinktank_service()
    from models import ThinkTankPhase
    try:
        target_phase = list(ThinkTankPhase)[phase]
    except (IndexError, KeyError):
        raise HTTPException(status_code=400, detail=f"Invalid phase index: {phase}")
    ok = await svc.set_phase(session_id, target_phase)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"success": True, "phase": target_phase.value}


@router.post("/session/{session_id}/draft")
async def save_as_draft(session_id: str):
    """Save session as draft."""
    svc = _get_thinktank_service()
    ok = svc.save_as_draft(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"success": True}


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


@router.get("/dispatch/{session_id}/audit")
async def get_dispatch_audit(session_id: str, limit: int = 100):
    """Get durable audit trail for a dispatch session.

    Returns timestamped events that survive server restarts.
    """
    svc = _get_thinktank_service()
    dispatch = svc._get_dispatch_engine()
    entries = [e for e in dispatch._audit_log if e.get("session_id") == session_id]
    return {"session_id": session_id, "entries": entries[-limit:], "total": len(entries)}


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
