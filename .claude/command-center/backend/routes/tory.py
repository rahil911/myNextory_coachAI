"""
routes/tory.py — Tory learner profile and feedback endpoints.

POST /api/tory/profile          — Generate learner profile from EPP + Q&A
GET  /api/tory/profile/{id}     — Retrieve learner profile
POST /api/tory/feedback         — Submit 'not_like_me' feedback
"""

import json
import subprocess
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any

router = APIRouter(prefix="/api/tory", tags=["tory"])


# ── Request / Response models ────────────────────────────────────────────────

class ProfileCreateRequest(BaseModel):
    learner_id: int = Field(..., description="nx_users.id of the learner")


class ProfileResponse(BaseModel):
    id: int
    nx_user_id: int
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    epp_summary: Any = None
    motivation_cluster: Any = None
    strengths: Any = None
    gaps: Any = None
    learning_style: str | None = None
    profile_narrative: str | None = None
    confidence: int = 0
    version: int = 1
    source: str | None = None
    feedback_flags: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class ProfileCreateResponse(BaseModel):
    status: str
    profile: ProfileResponse


class FeedbackRequest(BaseModel):
    learner_id: int = Field(..., description="nx_users.id of the learner")
    type: str = Field(default="not_like_me", description="Feedback type: not_like_me | too_vague | other")
    comment: str | None = Field(default=None, description="Optional learner comment")


class FeedbackResponse(BaseModel):
    id: int
    nx_user_id: int
    profile_id: int | None = None
    type: str
    comment: str | None = None
    profile_version: int | None = None
    created_at: str | None = None


# ── Service accessor ─────────────────────────────────────────────────────────

def _get_tory_service():
    from main import get_tory_service
    return get_tory_service()


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/profile", response_model=ProfileCreateResponse)
async def create_profile(req: ProfileCreateRequest):
    """Generate a learner profile from EPP scores and Q&A responses.

    Triggers the tory_interpret_profile MCP tool to parse the learner's
    onboarding data and create a structured profile with narrative summary.
    Returns 404 if the learner has no completed EPP + Q&A.
    """
    svc = _get_tory_service()

    if not svc.user_exists(req.learner_id):
        raise HTTPException(status_code=404, detail=f"User {req.learner_id} not found")

    if not svc.has_completed_onboarding(req.learner_id):
        raise HTTPException(
            status_code=404,
            detail=f"Learner {req.learner_id} has no completed EPP + Q&A onboarding data",
        )

    # Call the MCP tool's core logic directly via the tory_engine module
    # Import the interpret function from tory_engine
    import sys
    from pathlib import Path
    mcp_dir = Path(__file__).resolve().parent.parent.parent.parent / "mcp"
    if str(mcp_dir) not in sys.path:
        sys.path.insert(0, str(mcp_dir))

    from tory_engine import _tool_interpret_profile
    result_json = await _tool_interpret_profile(req.learner_id)
    result = json.loads(result_json)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    # Fetch the complete profile from DB
    profile = svc.get_profile(req.learner_id)
    if not profile:
        raise HTTPException(status_code=500, detail="Profile was created but could not be retrieved")

    return ProfileCreateResponse(
        status="profile_created",
        profile=ProfileResponse(**profile),
    )


@router.get("/profile/{learner_id}", response_model=ProfileResponse)
async def get_profile(learner_id: int):
    """Retrieve a learner's profile summary and EPP scores.

    Returns the latest version of the learner's profile including
    the narrative summary, strengths, gaps, and learning style.
    Returns 404 if no profile exists for the learner.
    """
    svc = _get_tory_service()

    if not svc.user_exists(learner_id):
        raise HTTPException(status_code=404, detail=f"User {learner_id} not found")

    profile = svc.get_profile(learner_id)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"No profile found for learner {learner_id}",
        )

    return ProfileResponse(**profile)


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(req: FeedbackRequest):
    """Submit learner feedback about their profile (e.g. 'This doesn't sound like me').

    Stores the feedback in tory_feedback and increments the feedback_flags
    counter on the associated learner profile.
    """
    svc = _get_tory_service()

    if not svc.user_exists(req.learner_id):
        raise HTTPException(status_code=404, detail=f"User {req.learner_id} not found")

    valid_types = {"not_like_me", "too_vague", "incorrect_strength", "other"}
    if req.type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid feedback type. Must be one of: {', '.join(sorted(valid_types))}",
        )

    feedback = svc.create_feedback(req.learner_id, req.type, req.comment)
    return FeedbackResponse(**feedback)
