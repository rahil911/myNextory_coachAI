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


# ── Content 360 ────────────────────────────────────────────────────────────

@router.get("/content-360")
async def get_content_360(
    search: str | None = Query(None),
    journey: str | None = Query(None),
    difficulty: int | None = Query(None, ge=1, le=5),
    emotional_tone: str | None = Query(None),
    learning_style: str | None = Query(None),
    seniority: str | None = Query(None),
):
    """Content 360: all lessons with full AI-generated metadata.

    LEFT JOINs tory_content_tags so lessons always show even without AI tags.
    """
    import subprocess

    sql = (
        "SELECT ld.id AS lesson_detail_id, ld.nx_lesson_id, "
        "nl.lesson AS lesson_name, nl.description AS lesson_desc, "
        "njd.id AS journey_detail_id, njd.journey AS journey_name, "
        "ncd.id AS chapter_detail_id, ncd.chapter AS chapter_name, "
        "COALESCE(sc.slide_count, 0) AS slide_count, "
        "ct.id AS tag_id, ct.summary, ct.difficulty, ct.learning_style, "
        "ct.emotional_tone, ct.target_seniority, ct.estimated_minutes, "
        "ct.key_concepts, ct.content_quality, ct.learning_objectives, "
        "ct.coaching_prompts, ct.pair_recommendations, ct.slide_analysis, "
        "ct.trait_tags, ct.confidence, ct.review_status "
        "FROM lesson_details ld "
        "JOIN nx_lessons nl ON ld.nx_lesson_id = nl.id "
        "LEFT JOIN nx_journey_details njd ON ld.nx_journey_detail_id = njd.id "
        "LEFT JOIN nx_chapter_details ncd ON ld.nx_chapter_detail_id = ncd.id "
        "LEFT JOIN ("
        "  SELECT lesson_detail_id, COUNT(*) AS slide_count "
        "  FROM lesson_slides WHERE deleted_at IS NULL "
        "  GROUP BY lesson_detail_id"
        ") sc ON sc.lesson_detail_id = ld.id "
        "LEFT JOIN tory_content_tags ct "
        "  ON ct.lesson_detail_id = ld.id AND ct.deleted_at IS NULL "
        "WHERE ld.deleted_at IS NULL AND nl.deleted_at IS NULL "
    )

    if journey:
        safe_j = journey.replace("'", "''")
        sql += f"AND njd.journey = '{safe_j}' "
    if difficulty:
        sql += f"AND ct.difficulty = {int(difficulty)} "
    if emotional_tone:
        safe_e = emotional_tone.replace("'", "''")
        sql += f"AND ct.emotional_tone = '{safe_e}' "
    if learning_style:
        safe_l = learning_style.replace("'", "''")
        sql += f"AND ct.learning_style = '{safe_l}' "
    if seniority:
        safe_s = seniority.replace("'", "''")
        sql += f"AND ct.target_seniority = '{safe_s}' "
    if search:
        safe_q = search.replace("'", "''").replace("%", "\\%")
        sql += (
            f"AND (nl.lesson LIKE '%{safe_q}%' "
            f"OR ct.summary LIKE '%{safe_q}%' "
            f"OR ct.key_concepts LIKE '%{safe_q}%') "
        )

    sql += "ORDER BY njd.journey, ncd.chapter, nl.priority, ld.id"

    proc = subprocess.run(
        ["mysql", "baap", "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"DB query failed: {proc.stderr.strip()}")

    output = proc.stdout.strip()
    if not output:
        return {"lessons": [], "total": 0, "journeys": [], "stats": {}}

    lines = output.split("\n")
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        vals = line.split("\t")
        rows.append({col: (vals[i] if i < len(vals) and vals[i] != "NULL" else None) for i, col in enumerate(headers)})

    json_fields = [
        "key_concepts", "content_quality", "learning_objectives",
        "coaching_prompts", "pair_recommendations", "slide_analysis", "trait_tags",
    ]
    int_fields = [
        "lesson_detail_id", "nx_lesson_id", "journey_detail_id",
        "chapter_detail_id", "slide_count", "tag_id", "difficulty",
        "estimated_minutes", "confidence",
    ]

    journeys_set = set()
    for row in rows:
        for f in int_fields:
            row[f] = int(row[f]) if row.get(f) else None
        for f in json_fields:
            if row.get(f):
                try:
                    row[f] = json.loads(row[f])
                except (json.JSONDecodeError, TypeError):
                    pass
        row["slide_count"] = row.get("slide_count") or 0
        if row.get("journey_name"):
            journeys_set.add(row["journey_name"])

    stats = {
        "total": len(rows),
        "tagged": sum(1 for r in rows if r.get("tag_id")),
        "untagged": sum(1 for r in rows if not r.get("tag_id")),
    }

    return {
        "lessons": rows,
        "total": len(rows),
        "journeys": sorted(journeys_set),
        "stats": stats,
    }


@router.get("/content-360/{lesson_detail_id}")
async def get_content_360_detail(lesson_detail_id: int):
    """Single lesson with full detail including slide breakdown."""
    import subprocess

    sql = (
        "SELECT ld.id AS lesson_detail_id, ld.nx_lesson_id, "
        "nl.lesson AS lesson_name, nl.description AS lesson_desc, "
        "njd.id AS journey_detail_id, njd.journey AS journey_name, "
        "ncd.id AS chapter_detail_id, ncd.chapter AS chapter_name, "
        "COALESCE(sc.slide_count, 0) AS slide_count, "
        "ct.id AS tag_id, ct.summary, ct.difficulty, ct.learning_style, "
        "ct.emotional_tone, ct.target_seniority, ct.estimated_minutes, "
        "ct.key_concepts, ct.content_quality, ct.learning_objectives, "
        "ct.coaching_prompts, ct.pair_recommendations, ct.slide_analysis, "
        "ct.trait_tags, ct.confidence, ct.review_status "
        "FROM lesson_details ld "
        "JOIN nx_lessons nl ON ld.nx_lesson_id = nl.id "
        "LEFT JOIN nx_journey_details njd ON ld.nx_journey_detail_id = njd.id "
        "LEFT JOIN nx_chapter_details ncd ON ld.nx_chapter_detail_id = ncd.id "
        "LEFT JOIN ("
        "  SELECT lesson_detail_id, COUNT(*) AS slide_count "
        "  FROM lesson_slides WHERE deleted_at IS NULL "
        "  GROUP BY lesson_detail_id"
        ") sc ON sc.lesson_detail_id = ld.id "
        "LEFT JOIN tory_content_tags ct "
        "  ON ct.lesson_detail_id = ld.id AND ct.deleted_at IS NULL "
        f"WHERE ld.id = {int(lesson_detail_id)} "
        "AND ld.deleted_at IS NULL AND nl.deleted_at IS NULL"
    )

    proc = subprocess.run(
        ["mysql", "baap", "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"DB query failed: {proc.stderr.strip()}")

    output = proc.stdout.strip()
    if not output:
        raise HTTPException(status_code=404, detail="Lesson not found")

    lines = output.split("\n")
    headers = lines[0].split("\t")
    if len(lines) < 2:
        raise HTTPException(status_code=404, detail="Lesson not found")

    vals = lines[1].split("\t")
    row = {col: (vals[i] if i < len(vals) and vals[i] != "NULL" else None) for i, col in enumerate(headers)}

    json_fields = [
        "key_concepts", "content_quality", "learning_objectives",
        "coaching_prompts", "pair_recommendations", "slide_analysis", "trait_tags",
    ]
    int_fields = [
        "lesson_detail_id", "nx_lesson_id", "journey_detail_id",
        "chapter_detail_id", "slide_count", "tag_id", "difficulty",
        "estimated_minutes", "confidence",
    ]

    for f in int_fields:
        row[f] = int(row[f]) if row.get(f) else None
    for f in json_fields:
        if row.get(f):
            try:
                row[f] = json.loads(row[f])
            except (json.JSONDecodeError, TypeError):
                pass
    row["slide_count"] = row.get("slide_count") or 0

    # Fetch individual slides for this lesson
    slide_sql = (
        "SELECT ls.id, ls.type, ls.priority, ls.video_library_id "
        f"FROM lesson_slides ls WHERE ls.lesson_detail_id = {int(lesson_detail_id)} "
        "AND ls.deleted_at IS NULL ORDER BY ls.priority"
    )

    slide_proc = subprocess.run(
        ["mysql", "baap", "--batch", "--raw", "-e", slide_sql],
        capture_output=True, text=True, timeout=10,
    )

    slides = []
    if slide_proc.returncode == 0 and slide_proc.stdout.strip():
        slines = slide_proc.stdout.strip().split("\n")
        sheaders = slines[0].split("\t")
        for sline in slines[1:]:
            svals = sline.split("\t")
            slide = {col: (svals[i] if i < len(svals) and svals[i] != "NULL" else None) for i, col in enumerate(sheaders)}
            slide["id"] = int(slide["id"]) if slide.get("id") else None
            slide["priority"] = int(slide["priority"]) if slide.get("priority") else None
            slide["video_library_id"] = int(slide["video_library_id"]) if slide.get("video_library_id") else None
            slides.append(slide)

    row["slides"] = slides
    return row
