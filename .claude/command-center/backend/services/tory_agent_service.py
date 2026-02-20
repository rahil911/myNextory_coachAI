"""
tory_agent_service.py — Manages Tory Agent sessions with real Claude subprocesses.

Spawns Claude Code subprocesses that use tory MCP tools to process learners.
Follows the exact ThinkTank session management pattern: file-based JSON persistence,
in-memory cache, debounced writes, event bus publishing.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import SESSIONS_DIR
from models import ToryAgentEvent, ToryAgentSession, WSEventType

logger = logging.getLogger(__name__)

# Unset CLAUDECODE to allow claude subprocesses to spawn cleanly
os.environ.pop("CLAUDECODE", None)

# Prompt template for the Claude subprocess
TORY_AGENT_PROMPT = """\
You are Tory — a learning-path AI agent. You have access to MCP tools for the \
MyNextory platform. Your task is to process learner #{nx_user_id} through the \
full Tory pipeline.

Execute these steps IN ORDER using your MCP tools:

1. Call tory_get_learner_data({nx_user_id}) to load the learner's full profile
2. Call tory_interpret_profile({nx_user_id}) to parse EPP + Q&A into a structured profile
3. Call tory_score_content({nx_user_id}) to score all tagged lessons against the profile
4. Call tory_generate_path({nx_user_id}) to generate the personalized learning path

After each step, summarize what you found. At the end, provide a brief summary of \
the learner's profile and their generated learning path.

If any step fails, report the error and continue with the next step if possible.\
"""

TORY_RESUME_PROMPT = """\
The coach has a follow-up request for learner #{nx_user_id}:

{message}

Use your MCP tools to fulfill this request. Available actions include:
- tory_coach_reorder: Reorder lessons in the path
- tory_coach_swap: Swap a lesson for a different one
- tory_coach_lock: Lock a lesson so it survives re-ranking
- tory_get_path: View the current path
- tory_preview_lesson_impact: Simulate adding/removing lessons
- tory_list_content_tags: Browse available content
\
"""


class ToryAgentService:
    """Manages Claude subprocess sessions for Tory learner processing."""

    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._sessions: dict[str, ToryAgentSession] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._readers: dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(3)  # max 3 concurrent
        self._sessions_dir = SESSIONS_DIR / "tory"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._persist_timers: dict[str, asyncio.TimerHandle] = {}
        self._load_all_sessions()

    # ── Persistence helpers (ThinkTank pattern) ──────────────────────────────

    def _session_path(self, session_id: str) -> Path:
        return self._sessions_dir / f"{session_id}.json"

    def _load_all_sessions(self) -> None:
        """Load all persisted sessions from disk into memory."""
        for path in self._sessions_dir.glob("tory_*.json"):
            try:
                data = json.loads(path.read_text())
                session = ToryAgentSession(**data)
                # Mark any stale "running" sessions as failed on reload
                if session.status == "running":
                    session.status = "failed"
                    session.error_message = "Session interrupted (server restart)"
                    session.updated_at = datetime.now(timezone.utc).isoformat()
                self._sessions[session.id] = session
            except Exception:
                pass  # Skip corrupt files

    def _schedule_persist(self, session_id: str) -> None:
        """Debounced persist: max 1 write per second per session."""
        existing = self._persist_timers.pop(session_id, None)
        if existing:
            existing.cancel()
        try:
            loop = asyncio.get_event_loop()
            handle = loop.call_later(1.0, self._do_persist, session_id)
            self._persist_timers[session_id] = handle
        except RuntimeError:
            self._do_persist(session_id)

    def _do_persist(self, session_id: str) -> None:
        """Write session to disk as JSON."""
        self._persist_timers.pop(session_id, None)
        session = self._sessions.get(session_id)
        if not session:
            return
        try:
            self._session_path(session_id).write_text(
                session.model_dump_json(indent=2)
            )
        except OSError:
            pass

    def _persist_now(self, session_id: str) -> None:
        """Immediately persist a session (for critical state changes)."""
        existing = self._persist_timers.pop(session_id, None)
        if existing:
            existing.cancel()
        self._do_persist(session_id)

    # ── Event helpers ────────────────────────────────────────────────────────

    async def _publish(self, event_type: WSEventType, payload: dict) -> None:
        """Publish event to the event bus if available."""
        if self._event_bus:
            try:
                await self._event_bus.publish(event_type, payload)
            except Exception:
                pass

    # ── JSONL stdout parsing ────────────────────────────────────────────────

    async def _read_stream(self, session_id: str, process: asyncio.subprocess.Process) -> None:
        """Read Claude subprocess stdout line-by-line, parse JSONL into events."""
        session = self._sessions.get(session_id)
        if not session or not process.stdout:
            return

        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break  # EOF

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError:
                    continue  # Skip non-JSON lines

                now = datetime.now(timezone.utc).isoformat()
                event = self._parse_jsonl_event(data, now)
                if not event:
                    continue

                # Extract claude session ID from the first message
                if not session.claude_session_id:
                    sid = data.get("session_id")
                    if sid:
                        session.claude_session_id = sid

                session.events.append(event)
                session.updated_at = now

                if event.type == "tool_call":
                    session.tool_call_count += 1
                    if event.tool and event.tool not in session.pipeline_steps:
                        session.pipeline_steps.append(event.tool)

                # Publish progress event
                await self._publish(WSEventType.TORY_AGENT_PROGRESS, {
                    "session_id": session_id,
                    "nx_user_id": session.nx_user_id,
                    "event": event.model_dump(),
                })

                self._schedule_persist(session_id)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error reading stream for session {session_id}: {e}")

    def _parse_jsonl_event(self, data: dict, timestamp: str) -> ToryAgentEvent | None:
        """Parse a single JSONL line from Claude --output-format stream-json."""
        msg_type = data.get("type", "")

        if msg_type == "assistant":
            # Extract text content from assistant message
            message = data.get("message", {})
            content_blocks = message.get("content", [])
            text_parts = []
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            if text_parts:
                return ToryAgentEvent(
                    type="reasoning",
                    content="\n".join(text_parts),
                    timestamp=timestamp,
                )

        elif msg_type == "content_block_start":
            block = data.get("content_block", {})
            if block.get("type") == "tool_use":
                return ToryAgentEvent(
                    type="tool_call",
                    tool=block.get("name", ""),
                    input=block.get("input"),
                    timestamp=timestamp,
                )

        elif msg_type == "result":
            # Final result message
            result_text = data.get("result", "")
            if isinstance(result_text, dict):
                result_text = json.dumps(result_text)
            cost_usd = data.get("cost_usd")
            duration_ms = data.get("duration_ms")
            session_id = data.get("session_id")
            return ToryAgentEvent(
                type="complete",
                content=str(result_text) if result_text else None,
                output={"cost_usd": cost_usd, "duration_ms": duration_ms, "session_id": session_id},
                timestamp=timestamp,
            )

        elif msg_type == "tool_result":
            content = data.get("content", "")
            if isinstance(content, list):
                # Extract text from content blocks
                parts = []
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        parts.append(c.get("text", ""))
                content = "\n".join(parts)
            return ToryAgentEvent(
                type="tool_result",
                content=str(content)[:2000] if content else None,
                tool=data.get("name"),
                timestamp=timestamp,
            )

        elif msg_type == "error":
            return ToryAgentEvent(
                type="error",
                content=data.get("error", {}).get("message", str(data)),
                timestamp=timestamp,
            )

        return None

    # ── Core session methods ────────────────────────────────────────────────

    async def spawn_agent(self, nx_user_id: int) -> ToryAgentSession:
        """Spawn a real Claude Code subprocess to process a learner.

        Launches: claude -p "{prompt}" --output-format stream-json
        Reads stdout line by line (JSONL), parses events, stores in session.events,
        publishes to event bus for WebSocket subscribers.
        """
        # Check for existing active session for this user
        active = self.get_active_session(nx_user_id)
        if active:
            active.status = "cancelled"
            active.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_now(active.id)
            # Kill the process if running
            proc = self._processes.pop(active.id, None)
            if proc:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass

        session_id = f"tory_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        session = ToryAgentSession(
            id=session_id,
            nx_user_id=nx_user_id,
            status="running",
            created_at=now,
            updated_at=now,
        )
        self._sessions[session_id] = session
        self._persist_now(session_id)

        # Publish started event
        await self._publish(WSEventType.TORY_AGENT_STARTED, {
            "session_id": session_id,
            "nx_user_id": nx_user_id,
        })

        # Launch Claude subprocess in background
        # Small delay lets the client connect its WebSocket before events fire.
        # Missed events are still available via the catch-up mechanism, but this
        # reduces the window where the client would need to rely on it.
        asyncio.create_task(self._delayed_run_subprocess(session_id, nx_user_id))

        return session

    async def _delayed_run_subprocess(self, session_id: str, nx_user_id: int) -> None:
        """Wait briefly for WebSocket clients to connect, then run subprocess."""
        await asyncio.sleep(0.2)
        await self._run_subprocess(session_id, nx_user_id)

    async def _run_subprocess(self, session_id: str, nx_user_id: int, resume_id: str | None = None, message: str | None = None) -> None:
        """Run the Claude subprocess with semaphore-controlled concurrency."""
        session = self._sessions.get(session_id)
        if not session:
            return

        async with self._semaphore:
            try:
                if resume_id and message:
                    # Resume mode
                    prompt = TORY_RESUME_PROMPT.format(
                        nx_user_id=nx_user_id,
                        message=message,
                    )
                    cmd = [
                        "claude",
                        "--resume", resume_id,
                        "-p", prompt,
                        "--verbose",
                        "--output-format", "stream-json",
                    ]
                else:
                    # New session mode
                    prompt = TORY_AGENT_PROMPT.format(nx_user_id=nx_user_id)
                    cmd = [
                        "claude",
                        "-p", prompt,
                        "--verbose",
                        "--output-format", "stream-json",
                    ]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                self._processes[session_id] = process

                # Read stdout JSONL
                reader_task = asyncio.create_task(self._read_stream(session_id, process))
                self._readers[session_id] = reader_task

                # Wait for process to complete
                await process.wait()

                # Cancel reader and wait for it to finish
                reader_task.cancel()
                try:
                    await reader_task
                except asyncio.CancelledError:
                    pass

                # Read any stderr
                stderr_data = b""
                if process.stderr:
                    stderr_data = await process.stderr.read()

                now = datetime.now(timezone.utc).isoformat()
                session.updated_at = now

                if process.returncode == 0:
                    session.status = "completed"
                    await self._publish(WSEventType.TORY_AGENT_COMPLETED, {
                        "session_id": session_id,
                        "nx_user_id": nx_user_id,
                        "tool_call_count": session.tool_call_count,
                        "pipeline_steps": session.pipeline_steps,
                    })
                else:
                    session.status = "failed"
                    error_msg = stderr_data.decode("utf-8", errors="replace").strip() if stderr_data else f"Exit code {process.returncode}"
                    session.error_message = error_msg[:1000]
                    session.events.append(ToryAgentEvent(
                        type="error",
                        content=session.error_message,
                        timestamp=now,
                    ))
                    await self._publish(WSEventType.TORY_AGENT_FAILED, {
                        "session_id": session_id,
                        "nx_user_id": nx_user_id,
                        "error": session.error_message,
                    })

            except Exception as e:
                logger.error(f"Subprocess error for session {session_id}: {e}")
                now = datetime.now(timezone.utc).isoformat()
                session.status = "failed"
                session.error_message = str(e)[:1000]
                session.updated_at = now
                session.events.append(ToryAgentEvent(
                    type="error",
                    content=session.error_message,
                    timestamp=now,
                ))
                await self._publish(WSEventType.TORY_AGENT_FAILED, {
                    "session_id": session_id,
                    "nx_user_id": nx_user_id,
                    "error": session.error_message,
                })

            finally:
                self._processes.pop(session_id, None)
                self._readers.pop(session_id, None)
                self._persist_now(session_id)

    async def resume_agent(self, session_id: str, message: str) -> ToryAgentSession | None:
        """Resume a completed/failed agent session with a user message.

        Command: claude --resume {claude_session_id} -p "{message}"
        Same stdout monitoring as spawn_agent.
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        if not session.claude_session_id:
            # Can't resume without a claude session ID — spawn a new one instead
            return await self.spawn_agent(session.nx_user_id)

        now = datetime.now(timezone.utc).isoformat()
        session.status = "running"
        session.updated_at = now
        session.error_message = None
        self._persist_now(session_id)

        # Publish started event
        await self._publish(WSEventType.TORY_AGENT_STARTED, {
            "session_id": session_id,
            "nx_user_id": session.nx_user_id,
            "resumed": True,
        })

        # Launch Claude subprocess in background
        asyncio.create_task(
            self._run_subprocess(session_id, session.nx_user_id, resume_id=session.claude_session_id, message=message)
        )

        return session

    async def batch_spawn(self, user_ids: list[int]) -> list[str]:
        """Queue multiple users for processing. Uses semaphore for concurrency."""
        session_ids = []
        for uid in user_ids:
            session = await self.spawn_agent(uid)
            session_ids.append(session.id)
        return session_ids

    async def cancel_agent(self, session_id: str) -> bool:
        """SIGTERM the running Claude subprocess."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        process = self._processes.get(session_id)
        if process:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

        reader = self._readers.pop(session_id, None)
        if reader:
            reader.cancel()

        now = datetime.now(timezone.utc).isoformat()
        session.status = "cancelled"
        session.updated_at = now
        session.events.append(ToryAgentEvent(
            type="error",
            content="Session cancelled by user",
            timestamp=now,
        ))
        self._persist_now(session_id)

        await self._publish(WSEventType.TORY_AGENT_FAILED, {
            "session_id": session_id,
            "nx_user_id": session.nx_user_id,
            "error": "Cancelled by user",
        })

        return True

    # ── Query methods ────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> ToryAgentSession | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def get_sessions_for_user(self, nx_user_id: int) -> list[ToryAgentSession]:
        """Get all sessions for a given user, newest first."""
        sessions = [
            s for s in self._sessions.values()
            if s.nx_user_id == nx_user_id
        ]
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions

    def get_active_session(self, nx_user_id: int) -> ToryAgentSession | None:
        """Get the currently running session for a user, if any."""
        for s in self._sessions.values():
            if s.nx_user_id == nx_user_id and s.status == "running":
                return s
        return None

    # ── Cleanup ──────────────────────────────────────────────────────────────

    async def cleanup(self) -> None:
        """Clean up all subprocess resources and flush pending persists."""
        # Flush all pending debounced persists
        for session_id in list(self._persist_timers.keys()):
            self._persist_now(session_id)

        for task in self._readers.values():
            task.cancel()
        for process in self._processes.values():
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                process.kill()
        self._processes.clear()
        self._readers.clear()
