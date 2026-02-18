"""
routes/approvals.py — Approval management for ownership proposals and agent actions.

Reads from .claude/kg/proposals.json and exposes approve/reject endpoints.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from config import PROJECT_ROOT
from models import (
    Approval, ApprovalListResponse, ApprovalRejectRequest,
    ApprovalSource, ApprovalStatus, WSEventType,
)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

PROPOSALS_FILE = PROJECT_ROOT / ".claude" / "kg" / "proposals.json"


def _get_event_bus():
    from main import get_event_bus
    return get_event_bus()


def _read_proposals() -> list[dict]:
    """Read proposals.json from disk."""
    if not PROPOSALS_FILE.exists():
        return []
    try:
        with open(PROPOSALS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _write_proposals(proposals: list[dict]) -> None:
    """Write proposals.json to disk."""
    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROPOSALS_FILE, "w") as f:
        json.dump(proposals, f, indent=2)


def _proposal_to_approval(p: dict) -> Approval:
    """Convert a raw proposal dict to an Approval model."""
    return Approval(
        id=p.get("id", "?"),
        source=ApprovalSource.OWNERSHIP,
        file=p.get("file"),
        agent=p.get("agent"),
        evidence=p.get("evidence", ""),
        proposed_at=p.get("proposed_at", ""),
        status=ApprovalStatus(p.get("status", "pending")),
        auto_approved=p.get("auto_approved", False),
        reason=p.get("reason", ""),
        reviewed_by=p.get("reviewed_by"),
        reviewed_at=p.get("reviewed_at"),
        reject_reason=p.get("reject_reason"),
    )


@router.get("", response_model=ApprovalListResponse)
async def list_approvals():
    """List all approvals, split into pending and history."""
    proposals = _read_proposals()
    pending = []
    history = []

    for p in proposals:
        approval = _proposal_to_approval(p)
        if approval.status == ApprovalStatus.PENDING:
            pending.append(approval)
        else:
            history.append(approval)

    # Sort: pending by proposed_at desc, history by reviewed_at desc
    pending.sort(key=lambda a: a.proposed_at, reverse=True)
    history.sort(key=lambda a: a.reviewed_at or a.proposed_at, reverse=True)

    return ApprovalListResponse(
        pending=pending,
        history=history,
        pending_count=len(pending),
    )


@router.post("/{approval_id}/approve")
async def approve(approval_id: str):
    """Approve an ownership proposal."""
    proposals = _read_proposals()
    now = datetime.now(timezone.utc).isoformat()

    found = False
    for p in proposals:
        if p.get("id") == approval_id:
            if p.get("status") != "pending":
                raise HTTPException(
                    status_code=400,
                    detail=f"Proposal '{approval_id}' is already {p.get('status')}",
                )
            p["status"] = "approved"
            p["reviewed_by"] = "human"
            p["reviewed_at"] = now
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Proposal '{approval_id}' not found")

    _write_proposals(proposals)

    # Push WebSocket events
    bus = _get_event_bus()
    await bus.publish(WSEventType.APPROVAL_RESOLVED, {
        "id": approval_id,
        "action": "approved",
    })
    await bus.publish(WSEventType.TOAST, {
        "message": f"Proposal {approval_id} approved",
        "type": "success",
    })

    return {"success": True, "message": f"Proposal {approval_id} approved"}


@router.post("/{approval_id}/reject")
async def reject(approval_id: str, req: ApprovalRejectRequest | None = None):
    """Reject an ownership proposal with optional reason."""
    proposals = _read_proposals()
    now = datetime.now(timezone.utc).isoformat()
    reason = req.reason if req else ""

    found = False
    for p in proposals:
        if p.get("id") == approval_id:
            if p.get("status") != "pending":
                raise HTTPException(
                    status_code=400,
                    detail=f"Proposal '{approval_id}' is already {p.get('status')}",
                )
            p["status"] = "rejected"
            p["reviewed_by"] = "human"
            p["reviewed_at"] = now
            if reason:
                p["reject_reason"] = reason
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Proposal '{approval_id}' not found")

    _write_proposals(proposals)

    # Push WebSocket events
    bus = _get_event_bus()
    await bus.publish(WSEventType.APPROVAL_RESOLVED, {
        "id": approval_id,
        "action": "rejected",
        "reason": reason,
    })
    await bus.publish(WSEventType.TOAST, {
        "message": f"Proposal {approval_id} rejected",
        "type": "warning",
    })

    return {"success": True, "message": f"Proposal {approval_id} rejected"}


@router.post("/approve-all")
async def approve_all():
    """Approve all pending proposals at once."""
    proposals = _read_proposals()
    now = datetime.now(timezone.utc).isoformat()

    count = 0
    for p in proposals:
        if p.get("status") == "pending":
            p["status"] = "approved"
            p["reviewed_by"] = "human"
            p["reviewed_at"] = now
            count += 1

    if count == 0:
        return {"success": True, "message": "No pending proposals to approve", "count": 0}

    _write_proposals(proposals)

    bus = _get_event_bus()
    await bus.publish(WSEventType.APPROVAL_RESOLVED, {
        "action": "approved_all",
        "count": count,
    })
    await bus.publish(WSEventType.TOAST, {
        "message": f"Approved {count} proposal(s)",
        "type": "success",
    })

    return {"success": True, "message": f"Approved {count} proposals", "count": count}
