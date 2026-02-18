"""
bead_generator.py — Converts approved spec-kit into structured beads.

Takes a ThinkTankSession with accumulated spec-kit sections and uses Claude
to decompose the execution plan into an ordered set of beads with dependencies.
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

logger = logging.getLogger(__name__)


@dataclass
class TaskBead:
    id: str = ""
    title: str = ""
    description: str = ""
    phase: int = 1
    priority: int = 2
    requirements: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    suggested_agent: str | None = None


@dataclass
class BeadPlan:
    epic_id: str = ""
    session_id: str = ""
    topic: str = ""
    tasks: list[TaskBead] = field(default_factory=list)
    dependency_map: dict = field(default_factory=dict)
    agent_hints: dict = field(default_factory=dict)


class BeadGenerator:
    """Converts spec-kit into executable bead plans."""

    def __init__(self):
        self._baap_root = Path.home() / "Projects" / "baap"

    async def spec_to_beads(self, session) -> BeadPlan:
        """Main entry: convert approved session into bead plan.

        Steps:
        1. Extract spec-kit content into structured text
        2. Ask Claude to decompose into phases/tasks
        3. Create beads via bd CLI
        4. Set up dependency DAG
        5. Return the complete plan
        """
        # Step 1: Build context from spec-kit
        spec_context = self._extract_spec_context(session)

        # Step 2: Ask Claude to decompose into tasks
        task_plan = await self._decompose_with_claude(session.topic, spec_context)

        # Step 3: Create the epic bead
        epic_id = await self._create_epic(session.topic, session.id)

        # Step 4: Create task beads and set dependencies
        plan = BeadPlan(
            epic_id=epic_id,
            session_id=session.id,
            topic=session.topic,
        )

        phase_bead_ids: dict[int, list[str]] = {}
        for task in task_plan:
            bead_id = await self._create_task_bead(task, epic_id)
            task.id = bead_id
            plan.tasks.append(task)

            phase_bead_ids.setdefault(task.phase, []).append(bead_id)
            if task.suggested_agent:
                plan.agent_hints[bead_id] = task.suggested_agent

        # Step 5: Set up phase dependencies (phase N depends on phase N-1)
        sorted_phases = sorted(phase_bead_ids.keys())
        for i, phase_num in enumerate(sorted_phases):
            if i > 0:
                prev_phase = sorted_phases[i - 1]
                for bead_id in phase_bead_ids[phase_num]:
                    deps = phase_bead_ids[prev_phase]
                    plan.dependency_map[bead_id] = deps
                    for dep_id in deps:
                        await self._add_dependency(bead_id, dep_id)

        logger.info(
            f"BeadPlan created: epic={epic_id}, tasks={len(plan.tasks)}, "
            f"phases={len(sorted_phases)}"
        )
        return plan

    def _extract_spec_context(self, session) -> str:
        """Extract spec-kit sections into a structured string for Claude."""
        parts = []
        sk = session.spec_kit

        for attr_name, label in [
            ("project_brief", "Project Brief"),
            ("requirements", "Requirements"),
            ("constraints", "Constraints"),
            ("architecture", "Architecture"),
            ("pre_mortem", "Pre-Mortem / Risks"),
            ("execution_plan", "Execution Plan"),
        ]:
            section = getattr(sk, attr_name, None)
            if section:
                content = section.content if hasattr(section, "content") else str(section)
                if content and content.strip():
                    parts.append(f"## {label}\n{content}")

        if not parts:
            # Fallback: extract from conversation if spec-kit is sparse
            parts.append(f"## Topic\n{session.topic}")
            for msg in session.messages:
                if msg.role == "orchestrator" and len(msg.content) > 200:
                    parts.append(f"## AI Analysis\n{msg.content[:2000]}")
                    break

        return "\n\n".join(parts)

    async def _decompose_with_claude(self, topic: str, spec_context: str) -> list[TaskBead]:
        """Ask Claude to decompose the spec into phased tasks."""
        os.environ.pop("CLAUDECODE", None)

        prompt = f"""You are a technical project manager decomposing a software project into executable tasks.

Given this approved specification, break it down into concrete, implementable tasks grouped by phase.

## Specification
Topic: {topic}

{spec_context}

## Instructions
Output a JSON array of tasks. Each task has:
- "title": short imperative title (e.g., "Create users table migration")
- "description": detailed spec for the developer (2-5 sentences)
- "phase": integer (1 = first, 2 = depends on phase 1, etc.)
- "priority": 0-4 (0=critical, 2=medium, 4=backlog)
- "requirements": list of what this task needs (tables, APIs, etc.)
- "acceptance_criteria": list of testable conditions
- "affected_domain": one of: "database", "api", "ui", "platform", "identity", "content", "engagement", "comms", "meetings", "kg"

Rules:
1. Phase 1 tasks are independent (can run in parallel)
2. Phase 2+ tasks depend on ALL tasks from the previous phase
3. Keep tasks focused — each should be completable in 1-2 hours by a single agent
4. Database/schema tasks MUST be in phase 1 (everything else depends on them)
5. API tasks that depend on schema go in phase 2
6. UI tasks that depend on APIs go in phase 3
7. Integration/testing tasks go in the last phase
8. Maximum 4 phases, maximum 12 tasks total
9. Each task must have at least 2 acceptance criteria

Output ONLY the JSON array, no markdown fences, no commentary:
[{{"title": "...", "description": "...", "phase": 1, ...}}]"""

        options = ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            cwd=str(self._baap_root),
            max_turns=1,
        )

        raw = ""
        try:
            async for msg in query(prompt=prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            raw += block.text
        except Exception as e:
            logger.warning(f"Claude decomposition failed: {e}. Using fallback.")
            return [TaskBead(
                title=f"Implement: {topic}",
                description=f"Full implementation of: {topic}",
                phase=1,
                priority=1,
                requirements=[],
                acceptance_criteria=["Feature works as specified"],
                suggested_agent="platform-agent",
            )]

        return self._parse_task_json(raw, topic)

    def _parse_task_json(self, raw: str, topic: str) -> list[TaskBead]:
        """Parse Claude's JSON response into TaskBead objects."""
        cleaned = raw.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        domain_to_agent = {
            "database": "platform-agent",
            "api": "platform-agent",
            "ui": "platform-agent",
            "platform": "platform-agent",
            "identity": "identity-agent",
            "content": "content-agent",
            "engagement": "engagement-agent",
            "comms": "comms-agent",
            "meetings": "meetings-agent",
            "kg": "kg-agent",
        }

        try:
            tasks_data = json.loads(cleaned)
            if not isinstance(tasks_data, list):
                raise ValueError("Expected JSON array")

            tasks = []
            for t in tasks_data:
                domain = t.get("affected_domain", "platform")
                tasks.append(TaskBead(
                    title=t.get("title", "Untitled task"),
                    description=t.get("description", ""),
                    phase=int(t.get("phase", 1)),
                    priority=int(t.get("priority", 2)),
                    requirements=t.get("requirements", []),
                    acceptance_criteria=t.get("acceptance_criteria", []),
                    affected_files=t.get("affected_files", []),
                    suggested_agent=domain_to_agent.get(domain, "platform-agent"),
                ))
            return tasks

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse task JSON: {e}")
            return [TaskBead(
                title=f"Implement: {topic}",
                description="Full implementation based on approved spec.",
                phase=1, priority=1,
                acceptance_criteria=["Feature works as specified"],
                suggested_agent="platform-agent",
            )]

    async def _create_epic(self, topic: str, session_id: str) -> str:
        """Create an epic bead via bd CLI."""
        title = f"EPIC: {topic}"
        proc = await asyncio.create_subprocess_exec(
            "bd", "create", title,
            "--type=epic",
            "--priority=1",
            f"--notes=Think Tank session: {session_id}",
            "--silent",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._baap_root),
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip()

        bead_id = self._extract_bead_id(output)
        logger.info(f"Created epic: {bead_id} — {title}")
        return bead_id

    async def _create_task_bead(self, task: TaskBead, epic_id: str) -> str:
        """Create a task bead linked to the epic."""
        desc_parts = [task.description]
        if task.requirements:
            desc_parts.append("\n## Requirements\n" + "\n".join(f"- {r}" for r in task.requirements))
        if task.acceptance_criteria:
            desc_parts.append("\n## Acceptance Criteria\n" + "\n".join(f"- [ ] {ac}" for ac in task.acceptance_criteria))

        description = "\n".join(desc_parts)

        proc = await asyncio.create_subprocess_exec(
            "bd", "create", task.title,
            "--type=task",
            f"--priority={task.priority}",
            f"--description={description}",
            f"--parent={epic_id}",
            "--silent",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._baap_root),
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip()
        bead_id = self._extract_bead_id(output)
        logger.info(f"Created task bead: {bead_id} — {task.title}")
        return bead_id

    async def _add_dependency(self, bead_id: str, depends_on: str) -> None:
        """Set bead dependency: bead_id depends on depends_on."""
        proc = await asyncio.create_subprocess_exec(
            "bd", "dep", "add", bead_id, depends_on,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._baap_root),
        )
        await proc.communicate()

    def _extract_bead_id(self, output: str) -> str:
        """Extract bead ID from bd CLI output.

        bd create --silent outputs just the ID like 'baap-v97'.
        bd create (verbose) outputs 'Created issue: baap-v97'.
        """
        output = output.strip()
        # --silent: raw ID on its own line
        match = re.search(r'(baap-[a-z0-9]+)', output, re.IGNORECASE)
        if match:
            return match.group(1)
        # Fallback: any alphanumeric ID pattern with prefix
        match = re.search(r'([a-z]+-[a-z0-9]+)', output, re.IGNORECASE)
        if match:
            return match.group(1)
        # Last resort
        return f"unknown-{hash(output) & 0xFFFF:04x}"
