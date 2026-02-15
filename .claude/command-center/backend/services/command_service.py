"""
command_service.py — Command registry, discovery, fuzzy search, and execution.

Commands are registered statically for known actions and dynamically by scanning
the .claude/scripts/ directory for executable scripts with help comments.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from config import SCRIPTS_DIR
from models import Command, CommandCategory, RiskLevel


def _build_registry() -> list[Command]:
    """Build the static command registry."""
    return [
        # ── Agent commands ────────────────────────────────────────────────
        Command(
            id="agent.spawn",
            name="Spawn Agent",
            description="Start a new agent with a prompt",
            category=CommandCategory.AGENT,
            shortcut="Ctrl+Shift+N",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="agent.kill",
            name="Kill Agent",
            description="Gracefully stop a running agent",
            category=CommandCategory.AGENT,
            shortcut="Ctrl+Shift+K",
            contexts=["agent:*"],
            risk_level=RiskLevel.MEDIUM,
            requires_confirmation=True,
        ),
        Command(
            id="agent.retry",
            name="Retry Agent",
            description="Re-dispatch a failed agent's work",
            category=CommandCategory.AGENT,
            contexts=["agent:*"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="agent.kill_all",
            name="Kill All Agents",
            description="Emergency stop all running agents",
            category=CommandCategory.AGENT,
            shortcut="Ctrl+Shift+P",
            contexts=["global"],
            risk_level=RiskLevel.HIGH,
            requires_confirmation=True,
        ),
        Command(
            id="agent.view_logs",
            name="View Agent Logs",
            description="Show the last 100 lines of an agent's log",
            category=CommandCategory.AGENT,
            contexts=["agent:*"],
            risk_level=RiskLevel.LOW,
        ),

        # ── Bead commands ─────────────────────────────────────────────────
        Command(
            id="bead.create",
            name="Create Bead",
            description="Create a new work item",
            category=CommandCategory.BEAD,
            shortcut="C",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="bead.close",
            name="Close Bead",
            description="Mark a bead as done",
            category=CommandCategory.BEAD,
            contexts=["bead:*"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="bead.block",
            name="Block Bead",
            description="Mark a bead as blocked",
            category=CommandCategory.BEAD,
            contexts=["bead:*"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="bead.assign",
            name="Assign Bead",
            description="Assign a bead to an agent",
            category=CommandCategory.BEAD,
            shortcut="A",
            contexts=["bead:*"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="bead.comment",
            name="Add Comment",
            description="Add a comment to a bead",
            category=CommandCategory.BEAD,
            contexts=["bead:*"],
            risk_level=RiskLevel.LOW,
        ),

        # ── Epic commands ─────────────────────────────────────────────────
        Command(
            id="epic.view",
            name="View Epic",
            description="Show epic progress and bead breakdown",
            category=CommandCategory.EPIC,
            contexts=["epic:*", "global"],
            risk_level=RiskLevel.LOW,
        ),

        # ── Think Tank commands ───────────────────────────────────────────
        Command(
            id="thinktank.start",
            name="Start Brainstorm",
            description="Begin a new Think Tank brainstorming session",
            category=CommandCategory.THINKTANK,
            shortcut="Ctrl+Shift+T",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="thinktank.resume",
            name="Resume Brainstorm",
            description="Resume an existing Think Tank session",
            category=CommandCategory.THINKTANK,
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),

        # ── Navigation commands ───────────────────────────────────────────
        Command(
            id="nav.dashboard",
            name="Go to Dashboard",
            description="Main overview",
            category=CommandCategory.NAVIGATION,
            shortcut="G D",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="nav.kanban",
            name="Go to Kanban Board",
            description="Work items board",
            category=CommandCategory.NAVIGATION,
            shortcut="G K",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="nav.agents",
            name="Go to Agents",
            description="Agent swimlanes view",
            category=CommandCategory.NAVIGATION,
            shortcut="G A",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="nav.thinktank",
            name="Go to Think Tank",
            description="Brainstorming interface",
            category=CommandCategory.NAVIGATION,
            shortcut="G T",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),

        # ── System commands ───────────────────────────────────────────────
        Command(
            id="system.refresh",
            name="Refresh Data",
            description="Force refresh all dashboard data",
            category=CommandCategory.SYSTEM,
            shortcut="R",
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
        Command(
            id="system.health",
            name="Health Check",
            description="Check API and service health",
            category=CommandCategory.SYSTEM,
            contexts=["global"],
            risk_level=RiskLevel.LOW,
        ),
    ]


class CommandService:
    def __init__(self):
        self._registry = _build_registry()
        self._scan_scripts()

    def _scan_scripts(self) -> None:
        """Scan .claude/scripts/ for additional executable scripts."""
        if not SCRIPTS_DIR.exists():
            return

        known_ids = {c.id for c in self._registry}

        for script in sorted(SCRIPTS_DIR.glob("*.sh")):
            script_id = f"script.{script.stem}"
            if script_id in known_ids:
                continue

            # Read first line comment for description
            description = ""
            try:
                first_lines = script.read_text().split("\n")[:5]
                for line in first_lines:
                    if line.startswith("# ") and not line.startswith("#!"):
                        description = line[2:].strip()
                        break
            except OSError:
                pass

            self._registry.append(Command(
                id=script_id,
                name=script.stem.replace("-", " ").replace("_", " ").title(),
                description=description or f"Run {script.name}",
                category=CommandCategory.SYSTEM,
                contexts=["global"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=True,
            ))

    def list_commands(self, context: str | None = None) -> list[Command]:
        """List all commands, optionally filtered by context."""
        if not context:
            return self._registry

        filtered = []
        for cmd in self._registry:
            if "global" in cmd.contexts:
                filtered.append(cmd)
            elif any(self._matches_context(c, context) for c in cmd.contexts):
                filtered.append(cmd)
        return filtered

    def search(self, query: str, context: str | None = None, limit: int = 10) -> list[Command]:
        """Fuzzy search commands."""
        commands = self.list_commands(context)
        if not query:
            return commands[:limit]

        scored = []
        q = query.lower()
        for cmd in commands:
            target = f"{cmd.name} {cmd.description} {cmd.category.value}".lower()
            score = self._fuzzy_score(q, target)
            if score > 0:
                scored.append((score, cmd))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [cmd for _, cmd in scored[:limit]]

    def get_command(self, command_id: str) -> Command | None:
        """Get a command by ID."""
        for cmd in self._registry:
            if cmd.id == command_id:
                return cmd
        return None

    @staticmethod
    def _matches_context(pattern: str, context: str) -> bool:
        """Check if a context pattern matches a given context."""
        if pattern == context:
            return True
        if pattern.endswith(":*"):
            prefix = pattern[:-1]  # "agent:" from "agent:*"
            return context.startswith(prefix)
        return False

    @staticmethod
    def _fuzzy_score(query: str, text: str) -> int:
        """Sequential character matching with scoring."""
        qi = 0
        score = 0
        consecutive = 0
        for i, ch in enumerate(text):
            if qi < len(query) and ch == query[qi]:
                score += 1 + consecutive
                if i == 0 or text[i - 1] in (" ", "-", "_"):
                    score += 5  # word boundary bonus
                consecutive += 2
                qi += 1
            else:
                consecutive = 0
        return score if qi == len(query) else 0
