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
