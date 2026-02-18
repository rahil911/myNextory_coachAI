"""
bead_service.py — Wraps the bd (beads) CLI with structured Python interface.
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import (
    Bead, BeadComment, KanbanColumn, KanbanColumnData, KanbanResponse,
    WSEventType,
)

# TTL cache for bd CLI results (seconds)
_BEAD_CACHE_TTL = 10


# Bead status -> kanban column mapping
COLUMN_MAP: dict[str, KanbanColumn] = {
    "closed": KanbanColumn.DONE,
    "done": KanbanColumn.DONE,
    "completed": KanbanColumn.DONE,
    "resolved": KanbanColumn.DONE,
    "in_review": KanbanColumn.IN_REVIEW,
    "review": KanbanColumn.IN_REVIEW,
    "reviewing": KanbanColumn.IN_REVIEW,
    "in_progress": KanbanColumn.IN_PROGRESS,
    "active": KanbanColumn.IN_PROGRESS,
    "working": KanbanColumn.IN_PROGRESS,
    "blocked": KanbanColumn.BLOCKED,
}

# Kanban column -> bead status (for moves)
COLUMN_TO_STATUS: dict[KanbanColumn, str] = {
    KanbanColumn.BACKLOG: "open",
    KanbanColumn.READY: "open",
    KanbanColumn.IN_PROGRESS: "in_progress",
    KanbanColumn.IN_REVIEW: "in_review",
    KanbanColumn.BLOCKED: "blocked",
    KanbanColumn.DONE: "closed",
}

COLUMN_COLORS: dict[str, str] = {
    "backlog": "#8b949e",
    "ready": "#58a6ff",
    "in_progress": "#d29922",
    "in_review": "#bc8cff",
    "blocked": "#f85149",
    "done": "#3fb950",
}

COLUMN_TITLES: dict[str, str] = {
    "backlog": "Backlog",
    "ready": "Ready",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "blocked": "Blocked",
    "done": "Done",
}


class BeadService:
    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        # Resolve bd binary: check ~/.local/bin first, then fall back to bare name
        _local_bd = Path.home() / ".local" / "bin" / "bd"
        self._bd_cmd = str(_local_bd) if _local_bd.exists() else "bd"
        # Ensure ~/.local/bin is in PATH for subprocess calls
        self._env = {**os.environ, "PATH": f"{Path.home() / '.local' / 'bin'}:{os.environ.get('PATH', '')}"}
        # In-memory cache for list_beads results
        self._cache_beads: list[Bead] = []
        self._cache_ts: float = 0

    def _run_bd(self, args: list[str], timeout: int = 10) -> tuple[bool, str]:
        """Run a bd CLI command and return (success, output)."""
        try:
            result = subprocess.run(
                [self._bd_cmd] + args,
                capture_output=True, text=True, timeout=timeout,
                env=self._env,
            )
            output = result.stdout.strip() or result.stderr.strip()
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "bd command timed out"
        except FileNotFoundError:
            return False, "bd CLI not found — is beads installed?"
        except Exception as e:
            return False, str(e)

    def _invalidate_cache(self):
        """Invalidate the bead list cache after mutations."""
        self._cache_ts = 0

    def _fetch_all_beads(self) -> list[Bead]:
        """Fetch all beads from bd CLI, with TTL caching."""
        now = time.monotonic()
        if self._cache_beads and (now - self._cache_ts) < _BEAD_CACHE_TTL:
            return self._cache_beads

        ok, output = self._run_bd(["list", "--json"])
        if not ok or not output:
            return []

        try:
            raw_beads = json.loads(output)
        except json.JSONDecodeError:
            return []

        beads = []
        for b in raw_beads:
            beads.append(Bead(
                id=b.get("id", "?"),
                title=b.get("title") or b.get("description") or "Untitled",
                status=(b.get("status") or "open").lower().replace("-", "_"),
                assignee=b.get("assignee") or b.get("agent"),
                priority=b.get("priority"),
                epic=b.get("epic") or b.get("parent"),
                type=b.get("type") or b.get("issue_type") or "task",
                deps=b.get("dependencies") or b.get("deps") or b.get("blocked_by") or [],
                notes=b.get("notes", ""),
                created_at=b.get("created_at") or b.get("created"),
                updated_at=b.get("updated_at") or b.get("updated") or b.get("last_update"),
            ))

        self._cache_beads = beads
        self._cache_ts = now
        return beads

    def list_beads(self, status: str | None = None, assignee: str | None = None,
                   epic: str | None = None) -> list[Bead]:
        """List all beads, optionally filtered."""
        beads = self._fetch_all_beads()

        if not status and not assignee and not epic:
            return beads

        result = []
        for bead in beads:
            if status and bead.status != status:
                continue
            if assignee and bead.assignee != assignee:
                continue
            if epic and bead.epic != epic:
                continue
            result.append(bead)
        return result

    def get_bead(self, bead_id: str) -> Bead | None:
        """Get a single bead by ID."""
        beads = self.list_beads()
        for b in beads:
            if b.id == bead_id:
                return b
        return None

    def create_bead(self, title: str, bead_type: str = "task",
                    priority: int | None = None, epic: str | None = None,
                    assignee: str | None = None, notes: str = "") -> tuple[bool, str]:
        """Create a new bead via bd create."""
        args = ["create", title]
        if bead_type:
            args.extend(["--type", bead_type])
        if priority is not None:
            args.extend(["--priority", str(priority)])
        if epic:
            args.extend(["--epic", epic])

        ok, output = self._run_bd(args)
        if ok:
            self._invalidate_cache()
        return ok, output

    def update_bead(self, bead_id: str, **kwargs) -> tuple[bool, str]:
        """Update a bead's fields via bd update."""
        args = ["update", bead_id]
        for key, value in kwargs.items():
            if value is not None:
                args.extend([f"--{key}", str(value)])

        ok, output = self._run_bd(args)
        if ok:
            self._invalidate_cache()
        return ok, output

    async def move_bead(self, bead_id: str, column: KanbanColumn) -> tuple[bool, str]:
        """Move a bead to a different kanban column by updating its status."""
        new_status = COLUMN_TO_STATUS.get(column, "open")
        ok, output = self.update_bead(bead_id, status=new_status)

        if ok and self._event_bus:
            await self._event_bus.publish(WSEventType.BEAD_TRANSITION, {
                "bead_id": bead_id,
                "new_column": column.value,
                "new_status": new_status,
            })
            await self._event_bus.publish(WSEventType.TIMELINE_EVENT, {
                "type": "bead_moved",
                "bead": bead_id,
                "detail": f"Moved to {COLUMN_TITLES.get(column.value, column.value)}",
            })

        return ok, output

    def add_comment(self, bead_id: str, text: str, author: str = "human") -> tuple[bool, str]:
        """Add a comment to a bead by appending to its notes."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        comment_line = f"\n[{timestamp}] {author}: {text}"

        # Get current notes
        bead = self.get_bead(bead_id)
        if not bead:
            return False, f"Bead {bead_id} not found"

        new_notes = (bead.notes or "") + comment_line
        return self.update_bead(bead_id, notes=new_notes)

    def get_comments(self, bead_id: str) -> list[BeadComment]:
        """Parse comments from bead notes."""
        bead = self.get_bead(bead_id)
        if not bead or not bead.notes:
            return []

        comments = []
        for line in bead.notes.split("\n"):
            line = line.strip()
            if line.startswith("[") and "]" in line:
                # Parse: [2026-02-14 10:30 UTC] human: some text
                try:
                    ts_end = line.index("]")
                    ts = line[1:ts_end]
                    rest = line[ts_end + 2:]  # skip "] "
                    if ":" in rest:
                        author, text = rest.split(":", 1)
                        comments.append(BeadComment(
                            text=text.strip(),
                            author=author.strip(),
                            timestamp=ts,
                        ))
                except (ValueError, IndexError):
                    continue

        return comments

    def get_kanban(self) -> KanbanResponse:
        """Organize beads into kanban columns."""
        beads = self.list_beads()

        columns: dict[str, KanbanColumnData] = {}
        for col_key in ["backlog", "ready", "in_progress", "in_review", "blocked", "done"]:
            columns[col_key] = KanbanColumnData(
                title=COLUMN_TITLES[col_key],
                color=COLUMN_COLORS[col_key],
                count=0,
                beads=[],
            )

        for bead in beads:
            status = bead.status
            has_deps = len(bead.deps) > 0

            # Classify
            col_key = COLUMN_MAP.get(status)
            if col_key is None:
                if status == "blocked" or has_deps:
                    col_key = KanbanColumn.BLOCKED
                elif bead.assignee is None and status in ("open", "new", "pending", ""):
                    col_key = KanbanColumn.BACKLOG
                else:
                    col_key = KanbanColumn.READY

            columns[col_key.value].beads.append(bead)

        # Sort and count
        for col in columns.values():
            col.beads.sort(key=lambda b: (
                b.priority if b.priority is not None else 99,
                b.created_at or "",
            ))
            col.count = len(col.beads)

        return KanbanResponse(columns=columns, total=len(beads))

    def build_epics(self) -> list[dict]:
        """Group beads by epic and compute progress."""
        beads = self.list_beads()
        epics: dict[str, dict[str, Any]] = {}

        for b in beads:
            epic = b.epic or "ungrouped"
            if epic not in epics:
                epics[epic] = {
                    "epic": epic, "total": 0, "completed": 0,
                    "in_progress": 0, "blocked": 0, "open": 0, "beads": [],
                }
            epics[epic]["total"] += 1
            epics[epic]["beads"].append(b.id)

            if b.status in ("closed", "done", "completed", "resolved"):
                epics[epic]["completed"] += 1
            elif b.status in ("in_progress", "active"):
                epics[epic]["in_progress"] += 1
            elif b.status == "blocked":
                epics[epic]["blocked"] += 1
            else:
                epics[epic]["open"] += 1

        result = []
        for e in epics.values():
            e["progress_pct"] = round(e["completed"] / e["total"] * 100, 1) if e["total"] > 0 else 0
            result.append(e)
        result.sort(key=lambda x: x["progress_pct"])
        return result
