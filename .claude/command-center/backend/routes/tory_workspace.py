"""
routes/tory_workspace.py — Tory Workspace routes for the split-view path builder.

All routes query REAL data via MCP tool wrappers (tory_engine.py functions).
Agent session management is via ToryAgentService.

GET  /api/tory/users                                  — Paginated user list with status
GET  /api/tory/users/{user_id}/detail                 — Learner data + path
POST /api/tory/process/{user_id}                      — Spawn Claude agent for user
POST /api/tory/batch-process                          — Batch spawn agents
GET  /api/tory/preview-impact                         — Dry-run lesson impact simulation
GET  /api/tory/agent-sessions/{user_id}               — List agent sessions for user
GET  /api/tory/agent-sessions/{user_id}/{session_id}  — Get session with events
POST /api/tory/agent-sessions/{user_id}/{session_id}/chat — Resume agent with message
DELETE /api/tory/agent-sessions/{user_id}/{session_id} — Cancel running agent
GET  /api/tory/content-library                        — Content tags with lesson info
PUT  /api/tory/path/{user_id}/reorder                 — Reorder path items
POST /api/tory/path/{user_id}/swap                    — Swap a lesson
POST /api/tory/path/{user_id}/lock/{recommendation_id} — Lock a recommendation
"""

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/tory", tags=["tory-workspace"])


# ── Ensure MCP module is importable ─────────────────────────────────────────

_mcp_dir = Path(__file__).resolve().parent.parent.parent.parent / "mcp"
if str(_mcp_dir) not in sys.path:
    sys.path.insert(0, str(_mcp_dir))


# ── Service accessors (lazy imports to avoid circular deps) ──────────────────

def _get_tory_agent_service():
    from main import get_tory_agent_service
    return get_tory_agent_service()


def _get_azure_blob_service():
    from main import get_azure_blob_service
    return get_azure_blob_service()


# ── Request models ──────────────────────────────────────────────────────────

class BatchProcessRequest(BaseModel):
    user_ids: list[int] = Field(..., description="List of nx_user_ids to process")


class ReorderItem(BaseModel):
    recommendation_id: int
    new_sequence: int


class ReorderRequest(BaseModel):
    coach_id: int
    ordering: list[ReorderItem]
    reason: str


class SwapRequest(BaseModel):
    coach_id: int
    remove_lesson_id: int
    add_lesson_id: int
    reason: str


class LockRequest(BaseModel):
    coach_id: int
    reason: str


class ChatRequest(BaseModel):
    text: str


# ── Helper: call MCP tool and parse JSON result ────────────────────────────

async def _call_mcp_tool(tool_func, *args, **kwargs) -> Any:
    """Call an async MCP tool function and parse its JSON result."""
    result_json = await tool_func(*args, **kwargs)
    result = json.loads(result_json)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── User management ─────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
    status_filter: str | None = Query(None),
    company_filter: int | None = Query(None),
):
    """Paginated user list with Tory processing status.

    Calls MCP tory_list_users_with_status for real DB data.
    """
    from tory_engine import _tool_list_users_with_status

    return await _call_mcp_tool(
        _tool_list_users_with_status,
        page=page,
        limit=limit,
        search=search,
        status_filter=status_filter,
        company_filter=company_filter,
    )


@router.get("/users/{user_id}/detail")
async def get_user_detail(user_id: int):
    """Full learner detail: profile data + current path.

    Calls MCP tory_get_learner_data + tory_get_path for real DB data.
    """
    from tory_engine import _tool_get_learner_data, _tool_get_path

    # Fetch learner data and path in parallel
    learner_json = await _tool_get_learner_data(user_id)
    learner_data = json.loads(learner_json)

    path_json = await _tool_get_path(user_id)
    path_data = json.loads(path_json)

    # path_data may have an error if no path exists yet — that's OK
    if "error" in path_data:
        path_data = None

    return {
        "learner": learner_data,
        "path": path_data,
    }


# ── Processing ──────────────────────────────────────────────────────────────

@router.post("/process/{user_id}")
async def process_user(user_id: int):
    """Spawn a Claude agent to process a learner through the Tory pipeline.

    Launches a real Claude subprocess that uses MCP tools.
    Returns the session_id for WebSocket event streaming.
    """
    svc = _get_tory_agent_service()
    session = await svc.spawn_agent(user_id)
    return {
        "session_id": session.id,
        "nx_user_id": user_id,
        "status": session.status,
    }


@router.post("/batch-process")
async def batch_process(req: BatchProcessRequest):
    """Queue multiple users for processing.

    Launches Claude agents for each user. Concurrency is controlled
    by the service's semaphore (max 3 simultaneous).
    """
    svc = _get_tory_agent_service()
    session_ids = await svc.batch_spawn(req.user_ids)
    return {
        "session_ids": session_ids,
        "count": len(session_ids),
    }


# ── Impact simulation ───────────────────────────────────────────────────────

@router.get("/preview-impact")
async def preview_impact(
    user_id: int = Query(...),
    add_lesson_ids: str = Query("", description="Comma-separated lesson IDs to add"),
    remove_lesson_ids: str = Query("", description="Comma-separated lesson IDs to remove"),
):
    """Dry-run impact simulation — what happens if we add/remove lessons.

    Calls MCP tory_preview_lesson_impact for real computation.
    """
    from tory_engine import _tool_preview_lesson_impact

    add_ids = [int(x) for x in add_lesson_ids.split(",") if x.strip()] if add_lesson_ids else []
    remove_ids = [int(x) for x in remove_lesson_ids.split(",") if x.strip()] if remove_lesson_ids else []

    return await _call_mcp_tool(
        _tool_preview_lesson_impact,
        nx_user_id=user_id,
        add_lesson_ids=add_ids,
        remove_lesson_ids=remove_ids,
    )


# ── Agent sessions ──────────────────────────────────────────────────────────

@router.get("/agent-sessions/{user_id}")
async def list_agent_sessions(user_id: int):
    """List all agent sessions for a user, newest first."""
    svc = _get_tory_agent_service()
    sessions = svc.get_sessions_for_user(user_id)
    return {
        "sessions": [
            {
                "id": s.id,
                "status": s.status,
                "tool_call_count": s.tool_call_count,
                "pipeline_steps": s.pipeline_steps,
                "error_message": s.error_message,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in sessions
        ],
        "count": len(sessions),
    }


@router.get("/agent-sessions/{user_id}/{session_id}")
async def get_agent_session(user_id: int, session_id: str):
    """Get a specific agent session with full event log."""
    svc = _get_tory_agent_service()
    session = svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if session.nx_user_id != user_id:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found for user {user_id}")

    return session.model_dump()


@router.post("/agent-sessions/{user_id}/{session_id}/chat")
async def chat_with_agent(user_id: int, session_id: str, req: ChatRequest):
    """Resume an agent session with a follow-up message.

    Uses claude --resume {claude_session_id} to continue the conversation.
    """
    svc = _get_tory_agent_service()
    session = svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if session.nx_user_id != user_id:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found for user {user_id}")

    if session.status == "running":
        raise HTTPException(status_code=409, detail="Agent is already running")

    result = await svc.resume_agent(session_id, req.text)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to resume agent")

    return {
        "session_id": session_id,
        "status": result.status,
    }


@router.delete("/agent-sessions/{user_id}/{session_id}")
async def cancel_agent_session(user_id: int, session_id: str):
    """Cancel a running agent session."""
    svc = _get_tory_agent_service()
    session = svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if session.nx_user_id != user_id:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found for user {user_id}")

    success = await svc.cancel_agent(session_id)
    return {"cancelled": success}


# ── Content library ─────────────────────────────────────────────────────────

@router.get("/content-library")
async def get_content_library(
    review_status: str | None = Query(None),
):
    """Content library: all lessons grouped by journey, with optional tag metadata.

    Queries lesson_details + nx_lessons + nx_journey_details + lesson_slides directly.
    LEFT JOINs tory_content_tags for supplementary tag metadata when available.
    Works even when tory_content_tags has 0 rows.
    """
    import subprocess

    sql = (
        "SELECT ld.id AS lesson_detail_id, ld.nx_lesson_id, "
        "nl.lesson AS lesson_name, nl.description AS lesson_desc, "
        "jd.id AS journey_detail_id, jd.journey AS journey_name, "
        "COALESCE(sc.slide_count, 0) AS slide_count, "
        "ct.id AS tag_id, ct.trait_tags, ct.confidence, "
        "ct.review_status, ct.difficulty, ct.learning_style, ct.pass_agreement "
        "FROM lesson_details ld "
        "JOIN nx_lessons nl ON ld.nx_lesson_id = nl.id "
        "JOIN nx_journey_details jd ON nl.nx_journey_detail_id = jd.id "
        "LEFT JOIN ("
        "  SELECT lesson_detail_id, COUNT(*) AS slide_count "
        "  FROM lesson_slides WHERE deleted_at IS NULL "
        "  GROUP BY lesson_detail_id"
        ") sc ON sc.lesson_detail_id = ld.id "
        "LEFT JOIN tory_content_tags ct "
        "  ON ct.lesson_detail_id = ld.id AND ct.deleted_at IS NULL "
        "WHERE ld.deleted_at IS NULL AND nl.deleted_at IS NULL "
    )
    valid_statuses = {"pending", "approved", "needs_review", "dismissed", "corrected"}
    if review_status and review_status in valid_statuses:
        sql += f"AND ct.review_status = '{review_status}' "
    sql += "GROUP BY ld.id, ct.id ORDER BY jd.id, nl.id"

    proc = subprocess.run(
        ["mysql", "baap", "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"DB query failed: {proc.stderr.strip()}")

    output = proc.stdout.strip()
    if not output:
        return {"journeys": [], "total_lessons": 0, "tag_count": 0, "review_stats": {}}

    lines = output.split("\n")
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        vals = line.split("\t")
        rows.append({col: (vals[i] if i < len(vals) and vals[i] != "NULL" else None) for i, col in enumerate(headers)})

    for row in rows:
        if row.get("trait_tags"):
            try:
                row["trait_tags"] = json.loads(row["trait_tags"])
            except (json.JSONDecodeError, TypeError):
                row["trait_tags"] = []
        else:
            row["trait_tags"] = []
        for field in ("confidence", "difficulty", "pass_agreement"):
            row[field] = int(row[field]) if row.get(field) else None
        row["journey_detail_id"] = int(row["journey_detail_id"]) if row.get("journey_detail_id") else None
        row["lesson_detail_id"] = int(row["lesson_detail_id"]) if row.get("lesson_detail_id") else None
        row["nx_lesson_id"] = int(row["nx_lesson_id"]) if row.get("nx_lesson_id") else None
        row["slide_count"] = int(row["slide_count"]) if row.get("slide_count") else 0
        row["tag_id"] = int(row["tag_id"]) if row.get("tag_id") else None

    journey_map = {}
    ungrouped = []
    for row in rows:
        jid = row.get("journey_detail_id")
        if jid:
            if jid not in journey_map:
                journey_map[jid] = {
                    "journey_detail_id": jid,
                    "journey_name": row.get("journey_name", ""),
                    "lessons": [],
                }
            journey_map[jid]["lessons"].append(row)
        else:
            ungrouped.append(row)

    journeys = sorted(journey_map.values(), key=lambda j: j["journey_detail_id"])
    if ungrouped:
        journeys.append({
            "journey_detail_id": None,
            "journey_name": "Other Content",
            "lessons": ungrouped,
        })

    stats = {"pending": 0, "approved": 0, "needs_review": 0, "dismissed": 0, "corrected": 0, "untagged": 0}
    for row in rows:
        if row.get("tag_id"):
            s = row.get("review_status", "pending")
            if s in stats:
                stats[s] += 1
        else:
            stats["untagged"] += 1

    return {"journeys": journeys, "total_lessons": len(rows), "tag_count": sum(1 for r in rows if r.get("tag_id")), "review_stats": stats}


# ── Content tag review ─────────────────────────────────────────────────────

class ReviewApproveRequest(BaseModel):
    reviewer_id: int
    notes: str | None = None


class CorrectedTag(BaseModel):
    trait: str
    relevance_score: int = Field(ge=0, le=100)
    direction: str = Field(pattern="^(builds|leverages|challenges)$")


class ReviewCorrectRequest(BaseModel):
    reviewer_id: int
    corrected_tags: list[CorrectedTag]
    corrected_difficulty: int | None = Field(None, ge=1, le=5)
    corrected_learning_style: str | None = None
    notes: str | None = None


class ReviewDismissRequest(BaseModel):
    reviewer_id: int
    notes: str | None = None


class BulkApproveRequest(BaseModel):
    reviewer_id: int
    min_confidence: int = 70
    tag_ids: list[int] | None = None
    notes: str | None = None


@router.post("/review/{tag_id}/approve")
async def review_approve(tag_id: int, req: ReviewApproveRequest):
    """Approve a content tag. Preserves existing trait_tags."""
    from tory_engine import _tool_review_approve

    return await _call_mcp_tool(
        _tool_review_approve,
        tag_id=tag_id,
        reviewer_id=req.reviewer_id,
        notes=req.notes,
    )


@router.post("/review/{tag_id}/correct")
async def review_correct(tag_id: int, req: ReviewCorrectRequest):
    """Correct a content tag with updated trait_tags."""
    from tory_engine import _tool_review_correct

    corrected = [t.model_dump() for t in req.corrected_tags]
    return await _call_mcp_tool(
        _tool_review_correct,
        tag_id=tag_id,
        reviewer_id=req.reviewer_id,
        corrected_tags=corrected,
        corrected_difficulty=req.corrected_difficulty,
        corrected_learning_style=req.corrected_learning_style,
        notes=req.notes,
    )


@router.post("/review/{tag_id}/dismiss")
async def review_dismiss(tag_id: int, req: ReviewDismissRequest):
    """Dismiss a content tag from review queue."""
    from tory_engine import _tool_review_dismiss

    return await _call_mcp_tool(
        _tool_review_dismiss,
        tag_id=tag_id,
        reviewer_id=req.reviewer_id,
        notes=req.notes,
    )


@router.post("/review/bulk-approve")
async def review_bulk_approve(req: BulkApproveRequest):
    """Bulk approve tags by confidence threshold or specific IDs."""
    from tory_engine import _tool_review_bulk_approve

    return await _call_mcp_tool(
        _tool_review_bulk_approve,
        reviewer_id=req.reviewer_id,
        min_confidence=req.min_confidence,
        tag_ids=req.tag_ids,
        notes=req.notes,
    )


@router.get("/review/stats")
async def review_stats():
    """Get review queue statistics."""
    from tory_engine import _tool_review_queue_stats

    result_json = await _tool_review_queue_stats()
    result = json.loads(result_json)
    return result


# ── EPP Profile Display ────────────────────────────────────────────────────

# EPP personality dimensions (13) — in raw data these are prefixed with "EPP"
_PERSONALITY_DIMS = [
    "Achievement", "Motivation", "Competitiveness", "Managerial",
    "Assertiveness", "Extroversion", "Cooperativeness", "Patience",
    "SelfConfidence", "Conscientiousness", "Openness", "Stability",
    "StressTolerance",
]

# EPP job fit dimensions (12) — in raw data these lack the _JobFit suffix
_JOBFIT_DIMS = [
    "Accounting_JobFit", "AdminAsst_JobFit", "Analyst_JobFit",
    "BankTeller_JobFit", "Collections_JobFit", "CustomerService_JobFit",
    "FrontDesk_JobFit", "Manager_JobFit", "MedicalAsst_JobFit",
    "Production_JobFit", "Programmer_JobFit", "Sales_JobFit",
]

# Mapping from raw assessment key to canonical dimension name
_RAW_JOBFIT_MAP = {
    "Accounting": "Accounting_JobFit",
    "AdminAsst": "AdminAsst_JobFit",
    "Analyst": "Analyst_JobFit",
    "BankTeller": "BankTeller_JobFit",
    "Collections": "Collections_JobFit",
    "CustomerService": "CustomerService_JobFit",
    "FrontDesk": "FrontDesk_JobFit",
    "Manager": "Manager_JobFit",
    "MedicalAsst": "MedicalAsst_JobFit",
    "Production": "Production_JobFit",
    "Programmer": "Programmer_JobFit",
    "Sales": "Sales_JobFit",
}

# Onboarding Q&A fields to extract
_QA_FIELDS = [
    ("why_did_you_come", "Why I'm here"),
    ("own_reason", "In my own words"),
    ("call_yourself", "How I see myself"),
    ("advance_your_career", "My career drive"),
    ("imp_thing_career_plan", "What matters most"),
    ("best_boss", "My ideal manager"),
    ("success_look_like", "Success means"),
    ("stay_longer", "Retention intent"),
    ("future_months", "Time horizon"),
]


def _parse_epp_from_assessment(assessment_json: str) -> dict:
    """Parse EPP scores from raw nx_user_onboardings.assesment_result JSON."""
    try:
        data = json.loads(assessment_json)
    except (json.JSONDecodeError, TypeError):
        return {}

    scores_raw = data.get("scores", {})
    if not scores_raw:
        return {}

    epp = {}
    # Personality dimensions (prefixed EPP*)
    for dim in _PERSONALITY_DIMS:
        key = f"EPP{dim}"
        val = scores_raw.get(key)
        if val is not None and val is not False:
            try:
                epp[dim] = float(val)
            except (ValueError, TypeError):
                pass

    # Job fit dimensions (no prefix, no _JobFit suffix in raw data)
    for raw_key, canonical in _RAW_JOBFIT_MAP.items():
        val = scores_raw.get(raw_key)
        if val is not None and val is not False:
            try:
                epp[canonical] = float(val)
            except (ValueError, TypeError):
                pass

    return epp


def _compute_strengths_gaps(epp_scores: dict) -> tuple[list, list]:
    """Compute top 3 strengths (>70) and top 3 gaps (<30) from EPP scores."""
    personality_scores = {k: v for k, v in epp_scores.items() if k in _PERSONALITY_DIMS}

    strengths = sorted(
        [{"trait": k, "score": v} for k, v in personality_scores.items() if v >= 70],
        key=lambda x: x["score"], reverse=True,
    )[:3]

    gaps = sorted(
        [{"trait": k, "score": v} for k, v in personality_scores.items() if v <= 30],
        key=lambda x: x["score"],
    )[:3]

    return strengths, gaps


def _parse_qa_value(val):
    """Parse a Q&A field value — handles JSON arrays, strings, None."""
    if val is None or val == "NULL" or val == "":
        return None
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("["):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        return val
    return val


@router.get("/users/{user_id}/profile")
async def get_user_profile(user_id: int):
    """Full EPP profile display data for a learner.

    Returns EPP scores (25 dimensions), onboarding Q&A, profile narrative,
    top strengths/gaps. Falls back to raw assessment_result if no
    tory_learner_profiles entry exists.
    """
    import subprocess

    result = {
        "nx_user_id": user_id,
        "epp_scores": {},
        "personality_scores": {},
        "jobfit_scores": {},
        "onboarding_qa": [],
        "profile_narrative": None,
        "motivation_cluster": [],
        "learning_style": None,
        "top_strengths": [],
        "top_gaps": [],
        "source": "none",
    }

    # 1. Try tory_learner_profiles first (most recent version)
    profile_sql = (
        "SELECT epp_summary, profile_narrative, strengths, gaps, "
        "motivation_cluster, learning_style, confidence, version "
        "FROM tory_learner_profiles "
        f"WHERE nx_user_id = {int(user_id)} AND deleted_at IS NULL "
        "ORDER BY version DESC LIMIT 1"
    )
    proc = subprocess.run(
        ["mysql", "baap", "--batch", "--raw", "-e", profile_sql],
        capture_output=True, text=True, timeout=10,
    )

    has_profile = False
    if proc.returncode == 0 and proc.stdout.strip():
        lines = proc.stdout.strip().split("\n")
        if len(lines) >= 2:
            headers = lines[0].split("\t")
            vals = lines[1].split("\t")
            row = {h: (vals[i] if i < len(vals) and vals[i] != "NULL" else None) for i, h in enumerate(headers)}

            if row.get("epp_summary"):
                try:
                    epp = json.loads(row["epp_summary"])
                    result["epp_scores"] = epp
                    result["source"] = "tory_profile"
                    has_profile = True
                except (json.JSONDecodeError, TypeError):
                    pass

            if row.get("profile_narrative"):
                result["profile_narrative"] = row["profile_narrative"]

            if row.get("motivation_cluster"):
                try:
                    result["motivation_cluster"] = json.loads(row["motivation_cluster"])
                except (json.JSONDecodeError, TypeError):
                    result["motivation_cluster"] = []

            result["learning_style"] = row.get("learning_style")

            # Use pre-computed strengths/gaps from profile if available
            if row.get("strengths"):
                try:
                    result["top_strengths"] = json.loads(row["strengths"])[:3]
                except (json.JSONDecodeError, TypeError):
                    pass
            if row.get("gaps"):
                try:
                    result["top_gaps"] = json.loads(row["gaps"])[:3]
                except (json.JSONDecodeError, TypeError):
                    pass

    # 2. Fallback: parse from nx_user_onboardings.assesment_result
    onboarding_sql = (
        "SELECT assesment_result, why_did_you_come, own_reason, "
        "call_yourself, advance_your_career, imp_thing_career_plan, "
        "best_boss, success_look_like, stay_longer, future_months "
        "FROM nx_user_onboardings "
        f"WHERE nx_user_id = {int(user_id)} AND deleted_at IS NULL "
        "ORDER BY id DESC LIMIT 1"
    )
    proc2 = subprocess.run(
        ["mysql", "baap", "--batch", "--raw", "-e", onboarding_sql],
        capture_output=True, text=True, timeout=10,
    )

    if proc2.returncode == 0 and proc2.stdout.strip():
        lines2 = proc2.stdout.strip().split("\n")
        if len(lines2) >= 2:
            headers2 = lines2[0].split("\t")
            vals2 = lines2[1].split("\t")
            row2 = {h: (vals2[i] if i < len(vals2) and vals2[i] != "NULL" else None) for i, h in enumerate(headers2)}

            # Parse EPP from raw assessment if we don't have a profile
            if not has_profile and row2.get("assesment_result"):
                epp = _parse_epp_from_assessment(row2["assesment_result"])
                if epp:
                    result["epp_scores"] = epp
                    result["source"] = "raw_assessment"

            # Build onboarding Q&A
            for field_name, label in _QA_FIELDS:
                raw_val = row2.get(field_name)
                parsed = _parse_qa_value(raw_val)
                if parsed is not None:
                    result["onboarding_qa"].append({
                        "field": field_name,
                        "label": label,
                        "value": parsed,
                    })

    # 3. Split EPP scores into personality vs job fit
    for dim in _PERSONALITY_DIMS:
        if dim in result["epp_scores"]:
            result["personality_scores"][dim] = result["epp_scores"][dim]
    for dim in _JOBFIT_DIMS:
        if dim in result["epp_scores"]:
            result["jobfit_scores"][dim] = result["epp_scores"][dim]

    # 4. Compute strengths/gaps if not already set from profile
    if not result["top_strengths"] and not result["top_gaps"] and result["epp_scores"]:
        strengths, gaps = _compute_strengths_gaps(result["epp_scores"])
        result["top_strengths"] = strengths
        result["top_gaps"] = gaps

    return result


# ── Path editing ────────────────────────────────────────────────────────────

@router.put("/path/{user_id}/reorder")
async def reorder_path(user_id: int, req: ReorderRequest):
    """Reorder a learner's path items.

    Calls MCP tory_coach_reorder with the new ordering.
    """
    from tory_engine import _tool_coach_reorder

    ordering = [item.model_dump() for item in req.ordering]
    return await _call_mcp_tool(
        _tool_coach_reorder,
        nx_user_id=user_id,
        coach_id=req.coach_id,
        ordering=ordering,
        reason=req.reason,
    )


@router.post("/path/{user_id}/swap")
async def swap_lesson(user_id: int, req: SwapRequest):
    """Swap a lesson in a learner's path.

    Calls MCP tory_coach_swap to replace one lesson with another.
    """
    from tory_engine import _tool_coach_swap

    return await _call_mcp_tool(
        _tool_coach_swap,
        nx_user_id=user_id,
        coach_id=req.coach_id,
        remove_lesson_id=req.remove_lesson_id,
        add_lesson_id=req.add_lesson_id,
        reason=req.reason,
    )


@router.post("/path/{user_id}/lock/{recommendation_id}")
async def lock_recommendation(user_id: int, recommendation_id: int, req: LockRequest):
    """Lock a recommendation so it survives future Tory re-ranking.

    Calls MCP tory_coach_lock to set locked_by_coach=1.
    """
    from tory_engine import _tool_coach_lock

    return await _call_mcp_tool(
        _tool_coach_lock,
        nx_user_id=user_id,
        coach_id=req.coach_id,
        recommendation_id=recommendation_id,
        reason=req.reason,
    )
