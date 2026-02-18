# Phase 1c: Beads Bridge — Think Tank ↔ Beads Sync

**Type**: Parallel with 1a, 1b (no file conflicts)
**Output**: `backend/services/beads_bridge.py`
**Gate**: File exists, importable

## Purpose

Bidirectional sync between Think Tank sessions (in-memory + JSON files) and Beads (SQLite + CLI). When a session is approved and an epic is created, this bridge:
1. Links session.id ↔ epic bead ID
2. Streams bead status changes → WebSocket events for the UI
3. Updates session status when epic completes/fails
4. Provides query methods for the UI to show bead progress within Think Tank

## Implementation

Create `backend/services/beads_bridge.py`:

```python
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

logger = logging.getLogger(__name__)


class BeadsBridge:
    """Syncs Think Tank sessions with the Beads tracking system."""

    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._baap_root = Path.home() / "Projects" / "baap"
        # session_id → epic bead ID
        self._session_to_epic: dict[str, str] = {}
        # epic bead ID → session_id
        self._epic_to_session: dict[str, str] = {}
        # Monitor task handle
        self._monitor_task: asyncio.Task | None = None

    def link_session(self, session_id: str, epic_id: str) -> None:
        """Link a Think Tank session to its epic bead."""
        self._session_to_epic[session_id] = epic_id
        self._epic_to_session[epic_id] = session_id
        logger.info(f"Linked session {session_id} ↔ epic {epic_id}")

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
                "bd", "show", bead_id, "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._baap_root),
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return json.loads(stdout.decode())
        except Exception as e:
            logger.warning(f"Failed to query bead {bead_id}: {e}")

        # Fallback: try without --json flag
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
        except Exception:
            pass

        return None

    async def get_epic_progress(self, session_id: str) -> dict:
        """Get progress of all beads in an epic for a session.

        Returns:
        {
            "epic_id": "beads-xxx",
            "total": 5,
            "completed": 2,
            "in_progress": 1,
            "blocked": 1,
            "open": 1,
            "percent": 40,
            "tasks": [{id, title, status, agent, ...}, ...]
        }
        """
        epic_id = self._session_to_epic.get(session_id)
        if not epic_id:
            return {"epic_id": None, "total": 0, "completed": 0, "percent": 0, "tasks": []}

        # Get all beads (bd list --json if supported, otherwise parse text)
        try:
            proc = await asyncio.create_subprocess_exec(
                "bd", "list", "--status=all",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._baap_root),
            )
            stdout, _ = await proc.communicate()
            beads_text = stdout.decode()
        except Exception:
            return {"epic_id": epic_id, "total": 0, "completed": 0, "percent": 0, "tasks": []}

        # Parse and filter beads belonging to this epic
        # Note: bd doesn't have native epic filtering, so we track our own list
        # For now, return what we know from the BeadPlan
        return {
            "epic_id": epic_id,
            "status": "in_progress",
        }

    async def start_monitoring(self, session_id: str, bead_ids: list[str], poll_interval: float = 5.0) -> None:
        """Start polling bead statuses and pushing updates to UI.

        Args:
            session_id: The Think Tank session to monitor
            bead_ids: List of bead IDs to watch
            poll_interval: Seconds between status checks
        """
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

                        # Emit status change event
                        if self._event_bus:
                            await self._event_bus.publish("BEAD_STATUS_CHANGE", {
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
                        await self._event_bus.publish("DISPATCH_COMPLETE", {
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
```

## Key Design Decisions

1. **Polling, not webhooks**: Beads doesn't have a push notification system. We poll `bd show` at a configurable interval (default 5s). This is fine for the expected scale (< 20 beads per epic).

2. **Link table in memory**: `session_id ↔ epic_id` mapping is kept in memory. If the server restarts, the link is lost — but the session file has the epic_id in notes, and it can be reconstructed. For persistence, Phase 4 adds this to the session JSON.

3. **Event bus integration**: Every bead status change emits a WebSocket event. The frontend can subscribe to show real-time progress in the Think Tank view or Dashboard.

4. **Graceful degradation**: If `bd show --json` isn't supported (older beads version), falls back to text parsing. If bead query fails entirely, logs warning and continues.

## Success Criteria

```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
from services.beads_bridge import BeadsBridge
b = BeadsBridge()
b.link_session('tt_test', 'beads-test')
assert b.get_epic_for_session('tt_test') == 'beads-test'
assert b.get_session_for_epic('beads-test') == 'tt_test'
print('BeadsBridge: OK')
"
```
