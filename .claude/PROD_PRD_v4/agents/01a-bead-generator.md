# Phase 1a: Bead Generator — Spec-Kit to Beads Translator

**Type**: Parallel with 1b, 1c (no file conflicts)
**Output**: `backend/services/bead_generator.py`
**Gate**: File exists, importable, unit test passes

## Purpose

Convert an approved Think Tank spec-kit into structured beads (epic + tasks with dependency DAG). This is the bridge between human-approved specifications and machine-executable work units.

## Input Contract

Receives a `ThinkTankSession` object (from thinktank_service.py) with:
```python
session.id: str                    # "tt_6b0c4310"
session.topic: str                 # "Build an inventory management system"
session.phase: ThinkTankPhase      # ThinkTankPhase.BUILDING (after approval)
session.status: str                # "approved"
session.spec_kit: SpecKit          # The accumulated spec-kit
session.messages: list[ThinkTankMessage]  # Full conversation history
```

The SpecKit object has sections (read the actual `models.py` to confirm field names):
```python
spec_kit.project_brief: SpecKitSection | None    # {title, content, updated_at}
spec_kit.requirements: SpecKitSection | None
spec_kit.constraints: SpecKitSection | None
spec_kit.pre_mortem: SpecKitSection | None
spec_kit.execution_plan: SpecKitSection | None
```

## Output Contract

Returns a structured result:
```python
@dataclass
class BeadPlan:
    epic_id: str                    # "beads-xxx" — the root epic bead
    tasks: list[TaskBead]           # ordered list of task beads
    dependency_map: dict[str, list[str]]  # {bead_id: [depends_on_ids]}
    agent_hints: dict[str, str]     # {bead_id: "suggested_agent"} — hints for assigner

@dataclass
class TaskBead:
    id: str                         # bead ID (from bd create output)
    title: str                      # human-readable task title
    description: str                # detailed spec for the agent
    phase: int                      # execution phase (1, 2, 3...)
    priority: int                   # 0-4 (0=critical)
    requirements: list[str]         # what this task needs
    acceptance_criteria: list[str]  # how to verify completion
    affected_files: list[str]       # files likely to be touched (from KG or inference)
    suggested_agent: str | None     # hint based on domain analysis
```

## Implementation

Create `backend/services/bead_generator.py`:

```python
"""
bead_generator.py — Converts approved spec-kit into structured beads.

Takes a ThinkTankSession with accumulated spec-kit sections and uses Claude
to decompose the execution plan into an ordered set of beads with dependencies.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock


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

        phase_bead_ids = {}  # phase_num -> [bead_ids]
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

        return plan

    def _extract_spec_context(self, session) -> str:
        """Extract spec-kit sections into a structured string for Claude."""
        parts = []
        sk = session.spec_kit

        # Read each section — handle both SpecKitSection objects and raw strings
        for attr_name, label in [
            ("project_brief", "Project Brief"),
            ("requirements", "Requirements"),
            ("constraints", "Constraints"),
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
        import os
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
            # Fallback: create a single generic task
            return [TaskBead(
                title=f"Implement: {topic}",
                description=f"Full implementation of: {topic}",
                phase=1,
                priority=1,
                requirements=[],
                acceptance_criteria=["Feature works as specified"],
                suggested_agent="platform-agent",
            )]

        # Parse Claude's response
        return self._parse_task_json(raw, topic)

    def _parse_task_json(self, raw: str, topic: str) -> list[TaskBead]:
        """Parse Claude's JSON response into TaskBead objects."""
        # Strip markdown fences if present
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

        except (json.JSONDecodeError, ValueError):
            # Fallback: single task
            return [TaskBead(
                title=f"Implement: {topic}",
                description=f"Full implementation based on approved spec.",
                phase=1, priority=1,
                acceptance_criteria=["Feature works as specified"],
                suggested_agent="platform-agent",
            )]

    async def _create_epic(self, topic: str, session_id: str) -> str:
        """Create an epic bead via bd CLI."""
        title = f"EPIC: {topic}"
        proc = await asyncio.create_subprocess_exec(
            "bd", "create",
            f"--title={title}",
            "--type=epic",
            "--priority=1",
            f"--notes=Think Tank session: {session_id}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._baap_root),
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip()

        # Parse bead ID from bd create output (usually "Created beads-xxx")
        bead_id = self._extract_bead_id(output)
        return bead_id

    async def _create_task_bead(self, task: TaskBead, epic_id: str) -> str:
        """Create a task bead linked to the epic."""
        description = (
            f"{task.description}\n\n"
            f"## Requirements\n" + "\n".join(f"- {r}" for r in task.requirements) + "\n\n"
            f"## Acceptance Criteria\n" + "\n".join(f"- [ ] {ac}" for ac in task.acceptance_criteria)
        )

        proc = await asyncio.create_subprocess_exec(
            "bd", "create",
            f"--title={task.title}",
            "--type=task",
            f"--priority={task.priority}",
            f"--description={description}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._baap_root),
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip()
        return self._extract_bead_id(output)

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
        """Extract bead ID from bd CLI output."""
        # bd create output formats: "Created beads-abc123" or just "beads-abc123"
        match = re.search(r'(beads-[a-f0-9]+)', output)
        if match:
            return match.group(1)
        # Fallback: try to find any ID-like pattern
        match = re.search(r'([a-f0-9]{6,})', output)
        if match:
            return f"beads-{match.group(1)}"
        # Last resort
        return f"beads-unknown-{hash(output) & 0xFFFF:04x}"
```

## Key Design Decisions

1. **Claude decomposes the spec**: Rather than regex-parsing the execution_plan section, we ask Claude to decompose it into structured tasks. This handles the variety of spec formats Think Tank produces.

2. **Phase-based dependencies**: Tasks in phase N depend on ALL tasks in phase N-1. Simple but correct — mirrors how real projects work. No complex per-task dependency graphs that would confuse agents.

3. **Domain-to-agent mapping**: Simple heuristic mapping. The AgentAssigner (01b) refines this using the actual KG, but this gives good initial hints.

4. **Fallback on failure**: If Claude fails to decompose, or JSON parsing fails, we create a single generic task. The system never blocks on decomposition failure.

5. **Max 12 tasks, 4 phases**: Prevents bead explosion. A focused project should decompose into 4-12 concrete tasks, not 50.

## Success Criteria

```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
from services.bead_generator import BeadGenerator, BeadPlan, TaskBead
print('BeadGenerator importable: OK')
print('BeadPlan fields:', [f for f in BeadPlan.__dataclass_fields__])
print('TaskBead fields:', [f for f in TaskBead.__dataclass_fields__])
"
```

Expected: All imports succeed, fields listed correctly.
