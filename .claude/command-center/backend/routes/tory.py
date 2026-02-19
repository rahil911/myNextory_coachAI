"""
routes/tory.py — Tory learner profile, feedback, and content endpoints.

POST /api/tory/profile                     — Generate learner profile from EPP + Q&A
GET  /api/tory/profile/{id}                — Retrieve learner profile
POST /api/tory/feedback                    — Submit 'not_like_me' feedback
GET  /api/tory/path/{id}                   — Full learner path (profile + recommendations + coach flags)
GET  /api/tory/blob/{container}/{path}     — Generate SAS URL and redirect to blob
GET  /api/tory/lesson/{id}/slides          — Get lesson slides with resolved Azure Blob URLs
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
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


@router.get("/path/{learner_id}")
async def get_path(learner_id: int):
    """Get the full learner path: profile + ordered recommendations + coach flags.

    Returns everything the frontend Tory roadmap view needs in a single call.
    """
    svc = _get_tory_service()

    if not svc.user_exists(learner_id):
        raise HTTPException(status_code=404, detail=f"User {learner_id} not found")

    path = svc.get_path(learner_id)
    if not path:
        raise HTTPException(
            status_code=404,
            detail=f"No path data found for learner {learner_id}",
        )

    return path


# ── Azure Blob / Lesson Slides endpoints ────────────────────────────────────

_azure_blob_service = None

def _get_azure_blob_service():
    global _azure_blob_service
    if _azure_blob_service is None:
        from services.azure_blob_service import AzureBlobService
        _azure_blob_service = AzureBlobService()
    return _azure_blob_service


@router.get("/blob/{container}/{path:path}")
async def get_blob_url(container: str, path: str):
    """Generate a SAS URL for an Azure Blob and redirect to it.

    The SAS token is valid for 1 hour. The redirect allows browsers and
    media players to load content directly from Azure Blob Storage.
    """
    svc = _get_azure_blob_service()
    try:
        url = svc.generate_sas_url(path, container=container)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate SAS URL: {e}")
    return RedirectResponse(url=url)


@router.get("/lesson/{lesson_detail_id}/slides")
async def get_lesson_slides(lesson_detail_id: int):
    """Get all slides for a lesson with resolved Azure Blob URLs.

    Returns slide content with background_image, audio, and video paths
    replaced by time-limited signed Azure Blob URLs.
    """
    svc = _get_azure_blob_service()
    try:
        slides = svc.get_lesson_slides_with_urls(lesson_detail_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch slides: {e}")
    return {"slides": slides, "count": len(slides)}
