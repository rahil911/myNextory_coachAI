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
    """Content library with tags, lesson info, and slide counts.

    Calls MCP tory_list_content_tags and enriches with lesson metadata.
    """
    from tory_engine import _tool_list_content_tags

    result = await _call_mcp_tool(
        _tool_list_content_tags,
        review_status=review_status,
    )

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
