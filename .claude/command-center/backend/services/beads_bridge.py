"""
beads_bridge.py — Bidirectional sync between Think Tank sessions and Beads.

Links Think Tank session IDs to epic bead IDs. Monitors bead lifecycle
and pushes status updates to the UI via the event bus.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)


class BeadsBridge:
    """Syncs Think Tank sessions with the Beads tracking system."""

    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._baap_root = PROJECT_ROOT
        # session_id -> epic bead ID
        self._session_to_epic: dict[str, str] = {}
        # epic bead ID -> session_id
        self._epic_to_session: dict[str, str] = {}
        # Monitor task handle
        self._monitor_task: asyncio.Task | None = None

    def link_session(self, session_id: str, epic_id: str) -> None:
        """Link a Think Tank session to its epic bead."""
        self._session_to_epic[session_id] = epic_id
        self._epic_to_session[epic_id] = session_id
        logger.info(f"Linked session {session_id} <-> epic {epic_id}")

    def get_epic_for_session(self, session_id: str) -> str | None:
        """Get the epic bead ID linked to a session."""
        return self._session_to_epic.get(session_id)

    def get_session_for_epic(self, epic_id: str) -> str | None:
        """Get the session ID linked to an epic bead."""
        return self._epic_to_session.get(epic_id)

    async def get_bead_status(self, bead_id: str) -> dict | None:
        """Query a single bead's current status via bd CLI."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "bd", "show", bead_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._baap_root),
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return self._parse_bd_show_output(stdout.decode(), bead_id)
        except Exception as e:
            logger.warning(f"Failed to query bead {bead_id}: {e}")

        return None

    async def get_epic_progress(self, session_id: str) -> dict:
        """Get progress of all beads in an epic for a session."""
        epic_id = self._session_to_epic.get(session_id)
        if not epic_id:
            return {"epic_id": None, "total": 0, "completed": 0, "percent": 0, "tasks": []}

        return {
            "epic_id": epic_id,
            "status": "in_progress",
        }

    async def start_monitoring(self, session_id: str, bead_ids: list[str], poll_interval: float = 5.0) -> None:
        """Start polling bead statuses and pushing updates to UI."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()

        self._monitor_task = asyncio.create_task(
            self._monitor_loop(session_id, bead_ids, poll_interval)
        )

    async def _monitor_loop(self, session_id: str, bead_ids: list[str], interval: float) -> None:
        """Poll bead statuses and emit events."""
        known_statuses: dict[str, str] = {}
        completed_count = 0

        while True:
            try:
                await asyncio.sleep(interval)

                for bead_id in bead_ids:
                    status = await self.get_bead_status(bead_id)
                    if not status:
                        continue

                    current_status = status.get("status", "open")
                    prev_status = known_statuses.get(bead_id)

                    if current_status != prev_status:
                        known_statuses[bead_id] = current_status

                        if self._event_bus:
                            from models import WSEventType
                            await self._event_bus.publish(WSEventType.BEAD_STATUS_CHANGE, {
                                "session_id": session_id,
                                "bead_id": bead_id,
                                "status": current_status,
                                "title": status.get("title", ""),
                                "agent": status.get("assignee", ""),
                            })

                        if current_status in ("closed", "resolved"):
                            completed_count += 1

                # Check if all beads are done
                if completed_count >= len(bead_ids):
                    if self._event_bus:
                        from models import WSEventType
                        await self._event_bus.publish(WSEventType.DISPATCH_COMPLETE, {
                            "session_id": session_id,
                            "epic_id": self._session_to_epic.get(session_id),
                            "total": len(bead_ids),
                            "completed": completed_count,
                        })
                    logger.info(f"All beads complete for session {session_id}")
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(interval)

    def stop_monitoring(self) -> None:
        """Stop the bead monitoring loop."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()

    def _parse_bd_show_output(self, text: str, bead_id: str) -> dict:
        """Parse bd show text output into a dict."""
        result = {"id": bead_id}
        for line in text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower().replace(" ", "_")
                result[key] = value.strip()
        return result

    async def cleanup(self) -> None:
        """Clean up monitoring tasks."""
        self.stop_monitoring()
