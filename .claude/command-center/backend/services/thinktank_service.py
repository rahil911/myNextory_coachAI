"""
thinktank_service.py — Manages Think Tank brainstorming sessions.

Each session spawns a Claude Code subprocess with the orchestrator protocol.
Communication is via stdin/stdout pipes. Output is parsed for:
  - Phase transitions (Listen -> Explore -> Scope -> Confirm)
  - Spec-kit section updates
  - D/A/G menu presentations
  - Approval gates
"""

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone

from models import (
    ThinkTankSession, ThinkTankMessage, ThinkTankPhase,
    SpecKit, SpecKitSection, ThinkTankSessionSummary,
    WSEventType,
)


class ThinkTankService:
    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._sessions: dict[str, ThinkTankSession] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._readers: dict[str, asyncio.Task] = {}
        self._history: list[ThinkTankSessionSummary] = []

    async def start_session(self, topic: str, context: str = "") -> ThinkTankSession:
        """Start a new brainstorming session."""
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

        # Spawn Claude Code subprocess
        await self._spawn_orchestrator(session_id, topic, context)

        return session

    async def _spawn_orchestrator(self, session_id: str, topic: str, context: str) -> None:
        """Spawn a headless Claude Code process for the orchestrator."""
        initial_prompt = (
            f"You are the Think Tank orchestrator. Run the 4-phase BMAD elicitation "
            f"protocol (Listen -> Explore -> Scope -> Confirm) for this topic:\n\n"
            f"Topic: {topic}\n"
        )
        if context:
            initial_prompt += f"\nAdditional context:\n{context}\n"

        initial_prompt += (
            "\nStart with Phase 1: LISTEN. Ask the human what they are trying to build. "
            "Be curious and thorough. After each response, offer three options: "
            "[D] Dig Deeper, [A] Adjust, [G] Go to next phase.\n"
            "Format phase transitions as: PHASE_TRANSITION: <phase_name>\n"
            "Format spec-kit updates as JSON blocks with: SPECKIT_UPDATE: <section_name>\n"
        )

        try:
            process = await asyncio.create_subprocess_exec(
                "claude", "--print", "--no-input",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._processes[session_id] = process

            # Write initial prompt
            if process.stdin:
                process.stdin.write(initial_prompt.encode() + b"\n")
                await process.stdin.drain()

            # Start background reader
            self._readers[session_id] = asyncio.create_task(
                self._read_output(session_id)
            )

        except FileNotFoundError:
            # Claude CLI not available — use mock mode for development
            session = self._sessions.get(session_id)
            if session:
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
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    phase=ThinkTankPhase.LISTEN,
                ))
                if self._event_bus:
                    await self._event_bus.publish(WSEventType.THINKTANK_MESSAGE, {
                        "session_id": session_id,
                        "message": session.messages[-1].model_dump(),
                    })

    async def _read_output(self, session_id: str) -> None:
        """Background task: read orchestrator stdout and parse events."""
        process = self._processes.get(session_id)
        if not process or not process.stdout:
            return

        buffer = ""
        while True:
            try:
                chunk = await process.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    await self._process_line(session_id, line)

            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def _process_line(self, session_id: str, line: str) -> None:
        """Parse a line of orchestrator output for phase transitions and spec-kit updates."""
        session = self._sessions.get(session_id)
        if not session:
            return

        now = datetime.now(timezone.utc).isoformat()

        # Check for phase transition
        phase_match = re.search(r"PHASE_TRANSITION:\s*(\w+)", line, re.IGNORECASE)
        if phase_match:
            phase_name = phase_match.group(1).lower()
            phase_map = {
                "listen": ThinkTankPhase.LISTEN,
                "explore": ThinkTankPhase.EXPLORE,
                "scope": ThinkTankPhase.SCOPE,
                "confirm": ThinkTankPhase.CONFIRM,
                "building": ThinkTankPhase.BUILDING,
            }
            new_phase = phase_map.get(phase_name)
            if new_phase and new_phase != session.phase:
                session.phase = new_phase
                session.updated_at = now
                if self._event_bus:
                    await self._event_bus.publish(WSEventType.THINKTANK_PHASE_CHANGE, {
                        "session_id": session_id,
                        "phase": new_phase.value,
                    })
            return

        # Check for spec-kit update
        speckit_match = re.search(r"SPECKIT_UPDATE:\s*(\w+)", line, re.IGNORECASE)
        if speckit_match:
            section_name = speckit_match.group(1).lower()
            # The content follows on subsequent lines — handled by the message accumulator
            if self._event_bus:
                await self._event_bus.publish(WSEventType.THINKTANK_SPECKIT_DELTA, {
                    "session_id": session_id,
                    "section": section_name,
                    "content": line,
                })
            return

        # Regular output — accumulate as message
        if line.strip():
            session.messages.append(ThinkTankMessage(
                role="orchestrator",
                content=line,
                timestamp=now,
                phase=session.phase,
            ))
            session.updated_at = now
            if self._event_bus:
                await self._event_bus.publish(WSEventType.THINKTANK_MESSAGE, {
                    "session_id": session_id,
                    "message": session.messages[-1].model_dump(),
                })

    async def send_message(self, session_id: str, text: str) -> bool:
        """Send a human message to the orchestrator."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        now = datetime.now(timezone.utc).isoformat()
        session.messages.append(ThinkTankMessage(
            role="human",
            content=text,
            timestamp=now,
            phase=session.phase,
        ))
        session.updated_at = now

        # Write to subprocess stdin
        process = self._processes.get(session_id)
        if process and process.stdin:
            try:
                process.stdin.write(text.encode() + b"\n")
                await process.stdin.drain()
                return True
            except Exception:
                pass

        # Mock mode: generate a response
        await self._mock_response(session_id, text)
        return True

    async def _mock_response(self, session_id: str, user_text: str) -> None:
        """Generate a mock orchestrator response when Claude CLI is not available."""
        session = self._sessions.get(session_id)
        if not session:
            return

        now = datetime.now(timezone.utc).isoformat()
        phase = session.phase

        response = (
            f"I hear you. Let me process that in the context of our "
            f"{phase.value.title()} phase.\n\n"
            f"You mentioned: \"{user_text[:100]}...\"\n\n"
            f"Let me ask a follow-up question to make sure I understand fully.\n\n"
            f"[D] Dig Deeper | [A] Adjust | [G] Go to next phase"
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
            "dig_deeper": "I want to explore this thread further. Dig deeper.",
            "adjust": f"Let me adjust: {context}" if context else "I need to adjust something.",
            "go_next": "I'm satisfied with this phase. Let's move to the next one.",
        }
        text = action_map.get(action, action)
        return await self.send_message(session_id, text)

    async def approve(self, session_id: str, modifications: str = "") -> bool:
        """Approve the spec-kit and transition to building phase."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        now = datetime.now(timezone.utc).isoformat()

        if modifications:
            await self.send_message(session_id, f"Approved with modifications: {modifications}")
        else:
            await self.send_message(session_id, "Approved. Start building.")

        session.phase = ThinkTankPhase.BUILDING
        session.status = "approved"
        session.updated_at = now

        if self._event_bus:
            await self._event_bus.publish(WSEventType.THINKTANK_PHASE_CHANGE, {
                "session_id": session_id,
                "phase": "building",
            })
            await self._event_bus.publish(WSEventType.TOAST, {
                "message": "Spec-kit approved! Autonomous build starting.",
                "type": "success",
            })

        return True

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

    async def cleanup(self) -> None:
        """Clean up all subprocess resources."""
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
