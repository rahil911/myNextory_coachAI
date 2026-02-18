"""
thinktank_service.py — Manages Think Tank brainstorming sessions.

Uses the Anthropic Claude API for real multi-turn AI conversations
following the 4-phase protocol (Listen -> Explore -> Scope -> Confirm).
"""

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Unset CLAUDECODE to allow claude_agent_sdk to spawn Claude processes
# (the dashboard server may be started from within a Claude Code session)
os.environ.pop("CLAUDECODE", None)

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

from config import PROJECT_ROOT, SESSIONS_DIR
from models import (
    ThinkTankSession, ThinkTankMessage, ThinkTankPhase,
    SpecKit, SpecKitSection, ThinkTankSessionSummary,
    WSEventType,
)


# ── Configuration ────────────────────────────────────────────────────────────

THINKTANK_SYSTEM_PROMPT = """\
You are Think Tank — an elite AI product architect. You help humans think \
through software projects BEFORE any code is written. You are rigorous, \
probing, and collaborative.

You operate in 4 strict phases:

## Phase 1: LISTEN {phase_marker_listen}
Goal: Deeply understand the vision.
- Ask specific, probing questions about what they want to build
- Understand: the problem, the users, the business context, existing systems
- Don't suggest solutions yet — be a curious interviewer
- After 2-3 exchanges with solid understanding, suggest "ready to Explore"

## Phase 2: EXPLORE {phase_marker_explore}
Goal: Map the technical solution space.
- Propose architecture approaches with tradeoffs
- List functional and non-functional requirements
- Identify what data/APIs/services are needed
- Consider 2-3 alternatives, recommend one with reasoning
- After requirements are clear, suggest "ready to Scope"

## Phase 3: SCOPE {phase_marker_scope}
Goal: Stress-test and de-risk the plan.
- Play devil's advocate — what could go wrong?
- Run a pre-mortem: "It's 3 months later and this failed. Why?"
- Define hard constraints (time, budget, tech stack)
- Draw the line: what's in scope vs out of scope for v1
- After risks are addressed, suggest "ready to Confirm"

## Phase 4: CONFIRM {phase_marker_confirm}
Goal: Final review and handoff to execution.
- Present the complete spec as a structured summary
- List execution phases in order with dependencies
- Get explicit approval: "Does this look right?"
- When approved, output "APPROVED — Ready to build"

## RULES
1. Stay in the current phase. Don't skip ahead.
2. After each response, show exactly one of these action lines:
   [D] Dig Deeper — ask me more | [A] Adjust — I want to change something | [G] Go to {next_phase_name}
3. When you update your understanding, output a spec-kit block:
   ```spec-kit
   {{"section": "project_brief|requirements|constraints|pre_mortem|execution_plan", "content": "your updated understanding in clear bullet points"}}
   ```
4. Keep responses concise — 3-5 paragraphs max. This is a conversation, not an essay.
5. You may output multiple spec-kit blocks in one response if multiple sections update.

Current phase: {current_phase}
Session topic: {topic}
Messages so far: {message_count}\
"""


class ThinkTankService:
    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._sessions: dict[str, ThinkTankSession] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._readers: dict[str, asyncio.Task] = {}
        self._history: list[ThinkTankSessionSummary] = []
        # Persistence
        self._sessions_dir = SESSIONS_DIR
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._persist_timers: dict[str, asyncio.TimerHandle] = {}
        self._load_all_sessions()
        # Claude Agent SDK (handles auth via claude binary)
        self._claude_available = True
        # Dispatch engine (lazy-loaded to avoid circular imports)
        self._dispatch_engine = None

    def _get_dispatch_engine(self):
        """Lazy-load the dispatch engine."""
        if self._dispatch_engine is None:
            from services.dispatch_engine import DispatchEngine
            self._dispatch_engine = DispatchEngine(event_bus=self._event_bus)
        return self._dispatch_engine

    # ── Persistence helpers ──────────────────────────────────────────────────

    def _session_path(self, session_id: str) -> Path:
        return self._sessions_dir / f"{session_id}.json"

    def _load_all_sessions(self) -> None:
        """Load all persisted sessions from disk into memory."""
        for path in self._sessions_dir.glob("tt_*.json"):
            try:
                data = json.loads(path.read_text())
                session = ThinkTankSession(**data)
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

    # ── Claude API helpers ───────────────────────────────────────────────────

    def _detect_action(self, text: str) -> str | None:
        """Detect if user input is a D/A/G action."""
        t = text.strip().lower()
        if t == "d" or t.startswith("dig"):
            return "dig"
        if t == "a" or t.startswith("adjust"):
            return "adjust"
        if t == "g" or t.startswith("go"):
            return "go"
        return None

    def _build_system_prompt(self, session: ThinkTankSession, user_action: str | None = None) -> str:
        """Build the system prompt with current phase context."""
        phases = [ThinkTankPhase.LISTEN, ThinkTankPhase.EXPLORE,
                  ThinkTankPhase.SCOPE, ThinkTankPhase.CONFIRM]
        current = session.phase

        markers = {}
        for p in phases:
            markers[p.value] = "◀ ACTIVE" if p == current else ""

        next_phase_names = {
            ThinkTankPhase.LISTEN: "Explore",
            ThinkTankPhase.EXPLORE: "Scope",
            ThinkTankPhase.SCOPE: "Confirm",
            ThinkTankPhase.CONFIRM: "Approve",
        }
        next_phase_name = next_phase_names.get(current, "next")

        prompt = THINKTANK_SYSTEM_PROMPT.format(
            phase_marker_listen=markers.get("listen", ""),
            phase_marker_explore=markers.get("explore", ""),
            phase_marker_scope=markers.get("scope", ""),
            phase_marker_confirm=markers.get("confirm", ""),
            current_phase=current.value.title(),
            topic=session.topic,
            message_count=len([m for m in session.messages if m.role != "system"]),
            next_phase_name=next_phase_name,
        )

        if user_action == "dig":
            prompt += (
                "\n\nThe user chose [D] Dig Deeper — they want you to ask more "
                "probing questions and go deeper on the current topic."
            )
        elif user_action == "adjust":
            prompt += (
                "\n\nThe user chose [A] Adjust — they want to change or correct "
                "something. Ask what they'd like to adjust."
            )
        elif user_action == "go":
            prompt += (
                f"\n\nThe user chose [G] Go — you have transitioned to the "
                f"{current.value.title()} phase. Acknowledge the transition and "
                f"begin this phase's activities."
            )

        return prompt

    def _parse_spec_kit(self, text: str) -> tuple[str, dict[str, str]]:
        """Extract ```spec-kit blocks from Claude's response.

        Returns (cleaned_text, {section_name: content}).
        """
        spec_updates: dict[str, str] = {}

        def replace_block(match: re.Match) -> str:
            try:
                data = json.loads(match.group(1))
                section = data.get("section", "")
                content = data.get("content", "")
                if section and content:
                    spec_updates[section] = content
            except (json.JSONDecodeError, AttributeError):
                pass
            return ""

        cleaned = re.sub(
            r"```spec-kit\s*\n(.*?)\n```",
            replace_block,
            text,
            flags=re.DOTALL,
        )
        return cleaned.strip(), spec_updates

    async def _call_claude(self, session: ThinkTankSession, user_action: str | None = None) -> None:
        """Call Claude via the Agent SDK and process the response."""
        # Build single prompt with conversation history
        system_prompt = self._build_system_prompt(session, user_action)
        conversation = ""
        for msg in session.messages:
            if msg.role == "human":
                conversation += f"\nHuman: {msg.content}\n"
            elif msg.role == "orchestrator":
                conversation += f"\nAssistant: {msg.content}\n"

        full_prompt = system_prompt + "\n\n" + conversation + "\nAssistant:"

        options = ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            cwd=str(PROJECT_ROOT),
        )

        raw_text = ""
        try:
            async for msg in query(prompt=full_prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            raw_text += block.text
        except Exception as e:
            raw_text = f"Error: {str(e)}. Please try again."

        if not raw_text:
            raw_text = "I didn't generate a response. Please try again."

        # Parse spec-kit blocks
        cleaned_text, spec_updates = self._parse_spec_kit(raw_text)

        now = datetime.now(timezone.utc).isoformat()

        # Update session spec-kit
        section_titles = {
            "project_brief": "Project Brief",
            "requirements": "Requirements",
            "constraints": "Constraints",
            "architecture": "Architecture",
            "pre_mortem": "Pre-Mortem",
            "execution_plan": "Execution Plan",
        }
        for section_name, content in spec_updates.items():
            if hasattr(session.spec_kit, section_name):
                section = SpecKitSection(
                    title=section_titles.get(section_name, section_name.replace("_", " ").title()),
                    content=content,
                    updated_at=now,
                )
                setattr(session.spec_kit, section_name, section)
                if self._event_bus:
                    await self._event_bus.publish(WSEventType.THINKTANK_SPECKIT_DELTA, {
                        "session_id": session.id,
                        "section": section_name,
                        "content": content,
                        "status": "draft",
                    })

        # Append response as orchestrator message
        session.messages.append(ThinkTankMessage(
            role="orchestrator",
            content=cleaned_text,
            timestamp=now,
            phase=session.phase,
        ))
        session.updated_at = now

        if self._event_bus:
            await self._event_bus.publish(WSEventType.THINKTANK_MESSAGE, {
                "session_id": session.id,
                "message": session.messages[-1].model_dump(),
            })

    # ── Session lifecycle ───────────────────────────────────────────────────

    async def start_session(self, topic: str, context: str = "") -> ThinkTankSession:
        """Start a new brainstorming session."""
        # Auto-pause any currently active session
        active = self.get_active_session()
        if active:
            active.status = "paused"
            active.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_now(active.id)

        session_id = f"tt_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        session = ThinkTankSession(
            id=session_id,
            topic=topic,
            phase=ThinkTankPhase.LISTEN,
            messages=[],
            spec_kit=SpecKit(),
            started_at=now,
            updated_at=now,
            status="active",
        )

        # Add system message
        session.messages.append(ThinkTankMessage(
            role="system",
            content=f"Think Tank session started. Topic: {topic}",
            timestamp=now,
            phase=ThinkTankPhase.LISTEN,
        ))

        self._sessions[session_id] = session
        self._persist_now(session_id)

        # Generate welcome via Claude API in background (don't block HTTP response)
        asyncio.create_task(self._spawn_orchestrator(session_id, topic, context))

        return session

    async def _spawn_orchestrator(self, session_id: str, topic: str, context: str) -> None:
        """Generate the initial welcome message using Claude API."""
        session = self._sessions.get(session_id)
        if not session:
            return

        now = datetime.now(timezone.utc).isoformat()

        if self._claude_available:
            # Add the topic as the initial user message
            initial_msg = f"I want to brainstorm about: {topic}"
            if context:
                initial_msg += f"\n\nAdditional context: {context}"

            session.messages.append(ThinkTankMessage(
                role="human",
                content=initial_msg,
                timestamp=now,
                phase=ThinkTankPhase.LISTEN,
            ))

            if self._event_bus:
                await self._event_bus.publish(WSEventType.THINKTANK_MESSAGE, {
                    "session_id": session_id,
                    "message": session.messages[-1].model_dump(),
                })

            await self._call_claude(session)
            return
        else:
            # Fallback: mock welcome when no API key is available
            session.messages.append(ThinkTankMessage(
                role="orchestrator",
                content=(
                    "Welcome to Think Tank! I'm here to help you think through "
                    f"'{session.topic}'.\n\n"
                    "Let's start with Phase 1: LISTEN.\n\n"
                    "Tell me: what are you trying to build? What problem does it solve? "
                    "Who will use it?\n\n"
                    "[D] Dig Deeper | [A] Adjust | [G] Go to Explore Phase"
                ),
                timestamp=now,
                phase=ThinkTankPhase.LISTEN,
            ))

    async def send_message(self, session_id: str, text: str) -> bool:
        """Send a human message to the orchestrator."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        now = datetime.now(timezone.utc).isoformat()

        # Detect D/A/G action
        user_action = self._detect_action(text)

        # Handle phase transition for "go" action
        if user_action == "go":
            phase_order = [
                ThinkTankPhase.LISTEN, ThinkTankPhase.EXPLORE,
                ThinkTankPhase.SCOPE, ThinkTankPhase.CONFIRM,
            ]
            try:
                idx = phase_order.index(session.phase)
                if idx < len(phase_order) - 1:
                    session.phase = phase_order[idx + 1]
                    session.updated_at = now
                    if self._event_bus:
                        await self._event_bus.publish(WSEventType.THINKTANK_PHASE_CHANGE, {
                            "session_id": session_id,
                            "phase": session.phase.value,
                        })
            except ValueError:
                pass

        # Store the human message
        session.messages.append(ThinkTankMessage(
            role="human",
            content=text,
            timestamp=now,
            phase=session.phase,
        ))
        session.updated_at = now

        if self._event_bus:
            await self._event_bus.publish(WSEventType.THINKTANK_MESSAGE, {
                "session_id": session_id,
                "message": session.messages[-1].model_dump(),
            })

        # Generate AI response in background (don't block HTTP response)
        if self._claude_available:
            asyncio.create_task(self._call_claude(session, user_action))
        else:
            await self._mock_response(session_id, text)

        self._schedule_persist(session_id)
        return True

    async def set_phase(self, session_id: str, phase: ThinkTankPhase) -> bool:
        """Set session phase (allows backward transitions)."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.phase = phase
        session.updated_at = datetime.now(timezone.utc).isoformat()

        if self._event_bus:
            await self._event_bus.publish(WSEventType.THINKTANK_PHASE_CHANGE, {
                "session_id": session_id,
                "phase": session.phase.value,
            })

        self._schedule_persist(session_id)
        return True

    def save_as_draft(self, session_id: str) -> bool:
        """Save session as draft (pauses without losing state)."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.status = "draft"
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist_session(session_id)
        return True

    async def _mock_response(self, session_id: str, user_text: str) -> None:
        """Generate a mock orchestrator response when Claude API is not available."""
        session = self._sessions.get(session_id)
        if not session:
            return

        now = datetime.now(timezone.utc).isoformat()
        phase = session.phase

        next_phase_labels = {
            ThinkTankPhase.LISTEN: "Explore",
            ThinkTankPhase.EXPLORE: "Scope",
            ThinkTankPhase.SCOPE: "Confirm",
            ThinkTankPhase.CONFIRM: "Approve",
        }
        next_label = next_phase_labels.get(phase, "next")

        response = (
            f"[Mock mode — no API key] Processing in {phase.value.title()} phase.\n\n"
            f"You said: \"{user_text[:100]}\"\n\n"
            f"[D] Dig Deeper | [A] Adjust | [G] Go to {next_label} Phase"
        )

        session.messages.append(ThinkTankMessage(
            role="orchestrator",
            content=response,
            timestamp=now,
            phase=phase,
        ))
        session.updated_at = now

        if self._event_bus:
            await self._event_bus.publish(WSEventType.THINKTANK_MESSAGE, {
                "session_id": session_id,
                "message": session.messages[-1].model_dump(),
            })

    async def handle_action(self, session_id: str, action: str, context: str = "") -> bool:
        """Handle a D/A/G menu action."""
        action_map = {
            "dig_deeper": "D",
            "adjust": f"Adjust: {context}" if context else "A",
            "go_next": "G",
        }
        text = action_map.get(action, action)
        return await self.send_message(session_id, text)

    async def approve(self, session_id: str, modifications: str = "", dry_run: bool = False) -> dict:
        """Approve the spec-kit and transition to building phase.

        Args:
            session_id: Session to approve
            modifications: Optional last-minute tweaks
            dry_run: If True, return bead plan preview without creating beads

        Returns:
            Dict with success, dispatch_status, and optional preview/epic_id
        """
        session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}

        now = datetime.now(timezone.utc).isoformat()

        if not dry_run:
            if modifications:
                await self.send_message(session_id, f"Approved with modifications: {modifications}")
            else:
                await self.send_message(session_id, "Approved. Start building.")

            session.phase = ThinkTankPhase.BUILDING
            session.status = "approved"
            session.updated_at = now
            self._persist_now(session_id)

            if self._event_bus:
                await self._event_bus.publish(WSEventType.THINKTANK_PHASE_CHANGE, {
                    "session_id": session_id,
                    "phase": "building",
                })
                await self._event_bus.publish(WSEventType.TOAST, {
                    "message": "Spec-kit approved! Creating build plan...",
                    "type": "success",
                })

        # Trigger dispatch engine
        try:
            dispatch = self._get_dispatch_engine()
            result = await dispatch.dispatch_approved_session(session, dry_run=dry_run)

            if not dry_run:
                # Store epic ID in session for later reference
                if result.get("epic_id"):
                    session.epic_id = result["epic_id"]
                    self._persist_now(session_id)

                if self._event_bus and result.get("success"):
                    await self._event_bus.publish(WSEventType.TOAST, {
                        "message": "Build queued: agents being dispatched...",
                        "type": "success",
                    })

            return {
                "success": result.get("success", True),
                "dispatch_status": result.get("dispatch_status", "queued"),
                **result,
            }

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Dispatch failed: {e}")
            if self._event_bus and not dry_run:
                await self._event_bus.publish(WSEventType.TOAST, {
                    "message": f"Dispatch failed: {e}. You can retry from the dashboard.",
                    "type": "error",
                })
            return {
                "success": False,
                "dispatch_status": "failed",
                "error": str(e),
            }

    def get_session(self, session_id: str) -> ThinkTankSession | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def get_active_session(self) -> ThinkTankSession | None:
        """Get the currently active session, if any."""
        for s in self._sessions.values():
            if s.status == "active":
                return s
        return None

    def get_history(self) -> list[ThinkTankSessionSummary]:
        """Get summaries of all sessions."""
        summaries = []
        for s in self._sessions.values():
            summaries.append(ThinkTankSessionSummary(
                id=s.id,
                topic=s.topic,
                phase=s.phase,
                status=s.status,
                message_count=len(s.messages),
                started_at=s.started_at,
                updated_at=s.updated_at,
            ))
        summaries.sort(key=lambda x: x.updated_at, reverse=True)
        return summaries

    async def resume_session(self, session_id: str) -> ThinkTankSession | None:
        """Resume a paused/completed session, making it the active session."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        # Pause currently active session first
        active = self.get_active_session()
        if active and active.id != session_id:
            active.status = "paused"
            active.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_now(active.id)

        session.status = "active"
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist_now(session_id)
        return session

    def delete_session(self, session_id: str) -> bool:
        """Delete a session from memory and disk."""
        session = self._sessions.pop(session_id, None)
        if not session:
            return False
        timer = self._persist_timers.pop(session_id, None)
        if timer:
            timer.cancel()
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
        return True

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
