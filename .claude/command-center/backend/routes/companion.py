"""
routes/companion.py — Companion AI endpoints for learner-facing chat.

POST /api/companion/chat              — Send message, get AI response with mode detection
GET  /api/companion/session/{user_id} — Get or create companion session
GET  /api/companion/greeting/{user_id} — Contextual greeting based on recent activity
GET  /api/companion/actions/{user_id} — Get available quick actions
POST /api/companion/quiz/{user_id}    — Generate quiz from completed lesson content
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/api/companion", tags=["companion"])

# Add RAG directory to path for imports
_RAG_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "rag")
if _RAG_DIR not in sys.path:
    sys.path.insert(0, _RAG_DIR)

DATABASE = "baap"
QUERY_TIMEOUT = 30


# ── Request / Response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    user_id: int = Field(..., description="nx_users.id of the learner")
    message: str = Field(..., min_length=1, max_length=5000, description="Learner's message")
    session_id: Optional[int] = Field(None, description="Existing session ID (optional)")
    context: Optional[dict] = Field(None, description="Additional context (e.g., just_completed_lesson)")


class ChatResponse(BaseModel):
    response: str
    mode: str
    mode_confidence: float
    session_id: int
    sources: list = []
    flags: list = []
    escalate: bool = False
    model_used: str = "sonnet"
    timestamp: str


class SessionResponse(BaseModel):
    session_id: int
    nx_user_id: int
    message_count: int
    model_tier: str
    created_at: str
    last_active_at: Optional[str] = None
    memory_stats: Optional[dict] = None


class GreetingResponse(BaseModel):
    greeting: str
    quick_actions: list
    progress: dict
    session_id: int


class QuizRequest(BaseModel):
    lesson_id: Optional[int] = Field(None, description="Specific lesson to quiz on (optional — defaults to last completed)")


class QuizResponse(BaseModel):
    questions: list
    lesson_name: str
    source_slides: list


# ── DB helpers ───────────────────────────────────────────────────────────────

def _mysql_query(sql: str) -> list[dict]:
    """Execute a read-only MySQL query, return list of row dicts."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        return []
    output = result.stdout.strip()
    if not output:
        return []
    lines = output.split("\n")
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        rows.append({h: (values[i] if i < len(values) else None) for i, h in enumerate(headers)})
    return rows


def _mysql_write(sql: str) -> None:
    """Execute a write query."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL write error: {result.stderr.strip()}")


def _escape(value: str) -> str:
    """Escape a string for safe SQL insertion."""
    if value is None:
        return "NULL"
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r")
    escaped = escaped.replace("\x00", "").replace("\x1a", "")
    return f"'{escaped}'"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── Session management ───────────────────────────────────────────────────────

def _get_or_create_session(user_id: int) -> dict:
    """Get the active companion session or create a new one."""
    # Look for existing active session
    rows = _mysql_query(
        f"SELECT id, message_count, model_tier, key_facts, "
        f"created_at, last_active_at "
        f"FROM tory_ai_sessions "
        f"WHERE nx_user_id = {int(user_id)} "
        f"AND role = 'companion' "
        f"AND archived_at IS NULL "
        f"ORDER BY last_active_at DESC LIMIT 1"
    )

    if rows:
        row = rows[0]
        return {
            "session_id": int(row["id"]),
            "nx_user_id": user_id,
            "message_count": int(row.get("message_count", 0) or 0),
            "model_tier": row.get("model_tier", "sonnet"),
            "key_facts": row.get("key_facts"),
            "created_at": row.get("created_at", ""),
            "last_active_at": row.get("last_active_at"),
        }

    # Create new session
    now = _now()
    _mysql_write(
        f"INSERT INTO tory_ai_sessions "
        f"(nx_user_id, role, message_count, model_tier, "
        f"total_input_tokens, total_output_tokens, estimated_cost_usd, "
        f"last_active_at, created_at, updated_at) "
        f"VALUES ({int(user_id)}, 'companion', 0, 'sonnet', "
        f"0, 0, 0.0000, '{now}', '{now}', '{now}')"
    )

    rows = _mysql_query(
        f"SELECT id, message_count, model_tier, created_at, last_active_at "
        f"FROM tory_ai_sessions "
        f"WHERE nx_user_id = {int(user_id)} "
        f"AND role = 'companion' "
        f"AND archived_at IS NULL "
        f"ORDER BY id DESC LIMIT 1"
    )

    row = rows[0] if rows else {}
    return {
        "session_id": int(row.get("id", 0)),
        "nx_user_id": user_id,
        "message_count": 0,
        "model_tier": "sonnet",
        "key_facts": None,
        "created_at": row.get("created_at", now),
        "last_active_at": now,
    }


def _update_session_stats(session_id: int, input_tokens: int, output_tokens: int,
                          model_tier: str, key_facts: str = None):
    """Update session counters after a chat interaction."""
    now = _now()
    kf_sql = f", key_facts = {_escape(key_facts)}" if key_facts else ""
    _mysql_write(
        f"UPDATE tory_ai_sessions SET "
        f"message_count = message_count + 1, "
        f"model_tier = '{model_tier}', "
        f"total_input_tokens = total_input_tokens + {int(input_tokens)}, "
        f"total_output_tokens = total_output_tokens + {int(output_tokens)}, "
        f"last_active_at = '{now}', "
        f"updated_at = '{now}'"
        f"{kf_sql} "
        f"WHERE id = {int(session_id)}"
    )


def _load_session_memory(session_id: int) -> dict:
    """Load session state (conversation history) from DB."""
    rows = _mysql_query(
        f"SELECT session_state, key_facts FROM tory_ai_sessions "
        f"WHERE id = {int(session_id)}"
    )
    if not rows:
        return {"messages": [], "key_facts": []}

    row = rows[0]
    state = {}
    key_facts = []

    if row.get("session_state") and row["session_state"] != "NULL":
        try:
            state = json.loads(row["session_state"])
        except (json.JSONDecodeError, TypeError):
            state = {}

    if row.get("key_facts") and row["key_facts"] != "NULL":
        try:
            key_facts = json.loads(row["key_facts"])
        except (json.JSONDecodeError, TypeError):
            key_facts = []

    return {
        "messages": state.get("messages", []),
        "key_facts": key_facts if isinstance(key_facts, list) else [],
    }


def _save_session_memory(session_id: int, messages: list, key_facts: list):
    """Persist conversation state to DB."""
    # Keep last 20 messages in state (older ones are summarized)
    recent = messages[-20:] if len(messages) > 20 else messages
    state = json.dumps({"messages": recent})
    facts = json.dumps(key_facts[:100])

    _mysql_write(
        f"UPDATE tory_ai_sessions SET "
        f"session_state = {_escape(state)}, "
        f"key_facts = {_escape(facts)}, "
        f"updated_at = '{_now()}' "
        f"WHERE id = {int(session_id)}"
    )


# ── Core chat engine ─────────────────────────────────────────────────────────

def _process_chat(user_id: int, message: str, session_id: int,
                  context: dict = None) -> dict:
    """
    Process a chat message through the full Companion pipeline:
    1. Detect mode
    2. Build context (EPP, backpack, RAG)
    3. Assemble prompt
    4. Route to correct model tier
    5. Apply guardrails
    6. Return response
    """
    from companion_context import CompanionContext
    from mode_detector import ModeDetector, Mode
    from model_harness import TierRouter, GuardrailsChecker
    from anthropic import Anthropic

    start = time.time()

    # 1. Detect mode
    detector = ModeDetector()
    mode_result = detector.detect(message, context)
    mode = mode_result.mode.value

    # 2. Load learner context
    ctx = CompanionContext(user_id)

    # 3. Load conversation memory
    memory = _load_session_memory(session_id)
    memory_messages = memory.get("messages", [])
    key_facts = memory.get("key_facts", [])

    memory_context = ""
    if key_facts:
        memory_context += "Key facts: " + "; ".join(key_facts[:10]) + "\n"
    if memory_messages:
        recent = memory_messages[-6:]
        memory_context += "Recent exchange:\n" + "\n".join(
            f"{m['role']}: {m['content'][:150]}" for m in recent
        )

    # 4. Retrieve relevant content via FAISS (if available)
    rag_context = ""
    rag_sources = []
    try:
        from hybrid_query_engine import HybridQueryEngine
        engine = HybridQueryEngine(nx_user_id=user_id)
        shared_results, personal_results = engine.parallel_retrieve(
            message, user_id, k_shared=4, k_personal=2
        )
        merged = engine.merge_and_rerank(shared_results, personal_results, top_k=5)

        # Scope filter — only assigned lessons
        merged = ctx.filter_rag_results(merged)
        rag_context = ctx.format_rag_for_prompt(merged)
        rag_sources = [
            {
                "content": r.get("content", "")[:200],
                "source": r.get("metadata", {}).get("source", "lesson"),
                "lesson_name": r.get("metadata", {}).get("lesson_name", ""),
                "slide_index": r.get("metadata", {}).get("slide_index", ""),
                "score": round(r.get("adjusted_score", 0), 3),
            }
            for r in merged[:5]
        ]
    except Exception as e:
        logger.warning("rag_retrieval_failed", error=str(e))

    # 5. Get backpack context for reflect mode
    backpack_ctx = ""
    if mode == "reflect":
        backpack_ctx = ctx.get_backpack_context()

    # 6. Build system prompt
    system_prompt = ctx.build_system_prompt(
        mode=mode,
        memory_context=memory_context,
        rag_context=rag_context,
        backpack_override=backpack_ctx,
    )

    # 7. Route to model tier
    tier_router = TierRouter()
    tier_result = tier_router.route(message, rag_chunks=rag_sources, context_text=rag_context)
    model = tier_result["model"]
    model_tier = "opus" if tier_result["use_opus"] else "sonnet"

    # 8. Build messages array with conversation history
    messages = []
    for m in memory_messages[-8:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": message})

    # 9. Call Claude
    client = Anthropic()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
            timeout=45,
        )
        answer = response.content[0].text.strip()
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
    except Exception as e:
        logger.error("claude_api_failed", error=str(e))
        answer = (
            "I'm taking a quick break — try again in a moment. "
            "Meanwhile, your learning path is waiting for you!"
        )
        input_tokens = 0
        output_tokens = 0

    # 10. Apply guardrails
    guardrails = GuardrailsChecker(user_id, scope="companion")
    assigned_ids = ctx.get_assigned_lesson_ids()
    guard_result = guardrails.check(
        answer, message,
        rag_chunks=rag_sources,
        assigned_lesson_ids=assigned_ids,
    )
    final_answer = guard_result["response"]
    flags = guard_result["flags"]
    escalate = guard_result["escalate"]

    # Override mode to escalate if guardrails detected distress
    if escalate:
        mode = "escalate"

    # 11. Update conversation memory
    memory_messages.append({"role": "user", "content": message[:500]})
    memory_messages.append({"role": "assistant", "content": final_answer[:500]})
    _save_session_memory(session_id, memory_messages, key_facts)

    # 12. Update session stats
    _update_session_stats(session_id, input_tokens, output_tokens, model_tier)

    elapsed = time.time() - start

    return {
        "response": final_answer,
        "mode": mode,
        "mode_confidence": mode_result.confidence,
        "session_id": session_id,
        "sources": rag_sources,
        "flags": [f.get("check", "") for f in flags],
        "escalate": escalate,
        "model_used": model_tier,
        "timestamp": datetime.now().isoformat(),
        "response_time_ms": round(elapsed * 1000),
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def companion_chat(req: ChatRequest):
    """Send a message to the Companion AI and get a response.

    The companion detects intent (teach, quiz, reflect, prepare, celebrate,
    connect, escalate), retrieves relevant lesson content scoped to the
    learner's path, and responds with personality-aware context.
    """
    # Validate user exists
    rows = _mysql_query(
        f"SELECT id FROM nx_users WHERE id = {int(req.user_id)} "
        f"AND deleted_at IS NULL LIMIT 1"
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"User {req.user_id} not found")

    # Get or create session
    if req.session_id:
        session = {"session_id": req.session_id, "nx_user_id": req.user_id}
    else:
        session = _get_or_create_session(req.user_id)

    # Process the chat
    result = _process_chat(
        user_id=req.user_id,
        message=req.message,
        session_id=session["session_id"],
        context=req.context,
    )

    return ChatResponse(**result)


@router.get("/session/{user_id}", response_model=SessionResponse)
async def get_session(user_id: int):
    """Get or create a companion session for a learner."""
    rows = _mysql_query(
        f"SELECT id FROM nx_users WHERE id = {int(user_id)} "
        f"AND deleted_at IS NULL LIMIT 1"
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    session = _get_or_create_session(user_id)

    # Load memory stats
    memory = _load_session_memory(session["session_id"])
    memory_stats = {
        "message_count": len(memory.get("messages", [])),
        "key_facts_count": len(memory.get("key_facts", [])),
    }

    return SessionResponse(
        session_id=session["session_id"],
        nx_user_id=user_id,
        message_count=session["message_count"],
        model_tier=session["model_tier"],
        created_at=session["created_at"],
        last_active_at=session.get("last_active_at"),
        memory_stats=memory_stats,
    )


@router.get("/greeting/{user_id}", response_model=GreetingResponse)
async def get_greeting(user_id: int):
    """Get a personalized greeting based on the learner's state and recent activity."""
    rows = _mysql_query(
        f"SELECT id FROM nx_users WHERE id = {int(user_id)} "
        f"AND deleted_at IS NULL LIMIT 1"
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    sys.path.insert(0, _RAG_DIR) if _RAG_DIR not in sys.path else None
    from companion_context import CompanionContext

    ctx = CompanionContext(user_id)
    greeting_data = ctx.build_greeting()

    session = _get_or_create_session(user_id)

    return GreetingResponse(
        greeting=greeting_data["greeting"],
        quick_actions=greeting_data["quick_actions"],
        progress=greeting_data["progress"],
        session_id=session["session_id"],
    )


@router.get("/actions/{user_id}")
async def get_quick_actions(user_id: int):
    """Get available quick action pills based on learner state."""
    from companion_context import CompanionContext

    ctx = CompanionContext(user_id)
    progress = ctx.get_progress_data()
    actions = get_available_actions(progress["has_path"], progress["has_completed"])
    return {"actions": actions, "progress": progress}


@router.post("/quiz/{user_id}", response_model=QuizResponse)
async def generate_quiz(user_id: int, req: QuizRequest = None):
    """Generate a quiz from completed lesson content.

    Uses actual slide content from FAISS — never fabricates questions.
    Defaults to the most recently completed lesson if no lesson_id specified.
    """
    from companion_context import CompanionContext
    from anthropic import Anthropic

    ctx = CompanionContext(user_id)
    progress = ctx.get_progress_data()

    if not progress["has_completed"]:
        raise HTTPException(
            status_code=400,
            detail="No completed lessons to quiz on yet"
        )

    # Determine which lesson to quiz on
    lesson_id = req.lesson_id if req and req.lesson_id else None
    if not lesson_id and progress["last_completed"]:
        lesson_id = progress["last_completed"]["nx_lesson_id"]

    if not lesson_id:
        raise HTTPException(status_code=400, detail="No lesson available for quiz")

    # Get lesson content from DB
    lesson_rows = _mysql_query(
        f"SELECT l.lesson_name, ld.id as detail_id "
        f"FROM nx_lessons l "
        f"JOIN nx_lesson_details ld ON ld.nx_lesson_id = l.id "
        f"WHERE l.id = {int(lesson_id)} AND l.deleted_at IS NULL LIMIT 1"
    )
    if not lesson_rows:
        raise HTTPException(status_code=404, detail=f"Lesson {lesson_id} not found")

    lesson_name = lesson_rows[0].get("lesson_name", "Unknown")
    detail_id = int(lesson_rows[0].get("detail_id", 0))

    # Get slide content for quiz generation
    slide_rows = _mysql_query(
        f"SELECT ls.slide_content, ls.slide_number "
        f"FROM lesson_slides ls "
        f"WHERE ls.lesson_detail_id = {detail_id} "
        f"AND ls.deleted_at IS NULL "
        f"ORDER BY ls.slide_number LIMIT 15"
    )

    # Extract text content from slides
    slide_texts = []
    source_slides = []
    for sr in slide_rows:
        content_raw = sr.get("slide_content", "")
        slide_num = sr.get("slide_number", "")
        if content_raw:
            try:
                content = json.loads(content_raw)
                text = _extract_text_from_slide(content)
                if text and len(text) > 20:
                    slide_texts.append(f"Slide {slide_num}: {text}")
                    source_slides.append({"slide_number": slide_num, "preview": text[:100]})
            except (json.JSONDecodeError, TypeError):
                pass

    if not slide_texts:
        raise HTTPException(status_code=400, detail="Not enough content to generate quiz")

    # Generate quiz via Claude
    combined_content = "\n\n".join(slide_texts[:10])
    client = Anthropic()

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=(
                "Generate a quiz from the lesson content below. Create exactly 4 questions. "
                "For each question, include: question text, 4 multiple-choice options (a-d), "
                "the correct answer letter, and a brief explanation referencing the source slide. "
                "Return as JSON array: [{\"question\": \"...\", \"options\": [\"a) ...\", ...], "
                "\"correct\": \"a\", \"explanation\": \"...\", \"source_slide\": N}]"
            ),
            messages=[{"role": "user", "content": f"Lesson: {lesson_name}\n\n{combined_content}"}],
            timeout=30,
        )
        quiz_text = response.content[0].text.strip()

        # Parse JSON from response (handle markdown code blocks)
        if "```" in quiz_text:
            quiz_text = quiz_text.split("```")[1]
            if quiz_text.startswith("json"):
                quiz_text = quiz_text[4:]
            quiz_text = quiz_text.strip()

        questions = json.loads(quiz_text)

    except Exception as e:
        logger.error("quiz_generation_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate quiz")

    return QuizResponse(
        questions=questions,
        lesson_name=lesson_name,
        source_slides=source_slides,
    )


def _extract_text_from_slide(content: dict) -> str:
    """Extract readable text from a slide content JSON object."""
    parts = []
    for key in ["slide_title", "title", "content", "question", "description",
                 "heading", "subheading", "text"]:
        val = content.get(key)
        if val and isinstance(val, str):
            from html import unescape
            import re
            clean = re.sub(r'<[^>]+>', '', unescape(val))
            parts.append(clean.strip())

    # Handle questions array
    questions = content.get("questions", [])
    if isinstance(questions, list):
        for q in questions[:3]:
            if isinstance(q, dict):
                qt = q.get("question", q.get("text", ""))
                if qt:
                    parts.append(qt)
            elif isinstance(q, str):
                parts.append(q)

    # Handle options/choices
    options = content.get("options", content.get("choices", []))
    if isinstance(options, list):
        for opt in options[:5]:
            if isinstance(opt, dict):
                parts.append(opt.get("text", opt.get("label", "")))
            elif isinstance(opt, str):
                parts.append(opt)

    return " | ".join(p for p in parts if p)


# ── WebSocket endpoint for streaming ─────────────────────────────────────────

@router.websocket("/ws/{user_id}")
async def companion_ws(ws: WebSocket, user_id: int):
    """WebSocket endpoint for streaming companion responses.

    Clients send: {"message": "...", "context": {...}}
    Server sends: {"type": "chunk"|"done"|"mode"|"error", "data": ...}
    """
    await ws.accept()

    try:
        session = _get_or_create_session(user_id)
        session_id = session["session_id"]

        await ws.send_json({
            "type": "connected",
            "data": {"session_id": session_id, "user_id": user_id},
        })

        while True:
            try:
                raw = await ws.receive_text()
                data = json.loads(raw)
                message = data.get("message", "")
                context = data.get("context")

                if not message:
                    continue

                # Send mode detection first
                from mode_detector import ModeDetector
                detector = ModeDetector()
                mode_result = detector.detect(message, context)
                await ws.send_json({
                    "type": "mode",
                    "data": {
                        "mode": mode_result.mode.value,
                        "confidence": mode_result.confidence,
                    },
                })

                # Process chat (non-streaming for now — streaming would need
                # Anthropic streaming API which requires async context)
                result = _process_chat(
                    user_id=user_id,
                    message=message,
                    session_id=session_id,
                    context=context,
                )

                # Send response as chunks for typing effect
                response_text = result["response"]
                chunk_size = 50
                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i:i + chunk_size]
                    await ws.send_json({
                        "type": "chunk",
                        "data": {"text": chunk},
                    })

                # Send completion with metadata
                await ws.send_json({
                    "type": "done",
                    "data": {
                        "mode": result["mode"],
                        "sources": result["sources"],
                        "flags": result["flags"],
                        "escalate": result["escalate"],
                        "model_used": result["model_used"],
                    },
                })

            except json.JSONDecodeError:
                await ws.send_json({
                    "type": "error",
                    "data": {"message": "Invalid JSON"},
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("companion_ws_error", error=str(e))
        try:
            await ws.send_json({
                "type": "error",
                "data": {"message": "Connection error"},
            })
        except Exception:
            pass


# ── Import helper for quick actions ──────────────────────────────────────────

def get_available_actions(has_path: bool, has_completed: bool) -> list:
    """Import and return available quick actions."""
    try:
        from companion_prompts import get_available_actions as _get_actions
        return _get_actions(has_path, has_completed)
    except ImportError:
        return []
