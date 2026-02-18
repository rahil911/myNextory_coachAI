# Phase 2a: Dispatch Engine — The Core Orchestration Loop

**Type**: Sequential (depends on Phase 1a, 1b, 1c)
**Output**: `backend/services/dispatch_engine.py`
**Gate**: File exists, importable, can instantiate DispatchEngine

## Purpose

The heart of the system. Takes an approved spec-kit and orchestrates the entire build:
1. Calls BeadGenerator to create beads
2. Calls AgentAssigner to assign agents
3. Calls BeadsBridge to link session ↔ epic
4. Spawns agents via `spawn.sh` for unblocked beads
5. Monitors progress via beads
6. When a bead closes → checks if dependents are unblocked → spawns next wave
7. Handles failures via FailureRecovery (from Phase 3b)
8. Reports completion back to the session

## Dependencies

- `bead_generator.py` (Phase 1a) — for `BeadGenerator.spec_to_beads()`
- `agent_assigner.py` (Phase 1b) — for `AgentAssigner.assign_beads()`
- `beads_bridge.py` (Phase 1c) — for `BeadsBridge.link_session()` and monitoring
- `event_bus.py` (EXISTS) — for WebSocket event broadcasting
- `.claude/scripts/spawn.sh` (EXISTS) — for agent spawning

## Implementation

Create `backend/services/dispatch_engine.py`:

```python
"""
dispatch_engine.py — The core dispatch loop.

Converts approved Think Tank sessions into running agent swarms.
Coordinates the full lifecycle: spec → beads → assign → spawn → monitor → complete.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Limits
MAX_CONCURRENT_AGENTS = 3
SPAWN_COOLDOWN_SECONDS = 2       # Wait between spawns to avoid overwhelming
MONITOR_POLL_INTERVAL = 10       # Seconds between bead status checks
MAX_RETRIES_PER_BEAD = 2         # Max retry attempts before escalating
AGENT_TIMEOUT_MINUTES = 120      # Kill agent after this long


class DispatchEngine:
    """Orchestrates the full build lifecycle after Think Tank approval."""

    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._baap_root = Path.home() / "Projects" / "baap"
        self._scripts_dir = self._baap_root / ".claude" / "scripts"

        # Import sibling services (lazy to avoid circular imports)
        self._bead_generator = None
        self._agent_assigner = None
        self._beads_bridge = None
        self._failure_recovery = None

        # Active dispatch state
        self._active_dispatches: dict[str, dict] = {}  # session_id → dispatch state
        self._running_agents: dict[str, dict] = {}     # bead_id → {agent, process, started_at}
        self._dispatch_tasks: dict[str, asyncio.Task] = {}

    def _ensure_services(self):
        """Lazy-load sibling services."""
        if self._bead_generator is None:
            from services.bead_generator import BeadGenerator
            self._bead_generator = BeadGenerator()
        if self._agent_assigner is None:
            from services.agent_assigner import AgentAssigner
            self._agent_assigner = AgentAssigner()
        if self._beads_bridge is None:
            from services.beads_bridge import BeadsBridge
            self._beads_bridge = BeadsBridge(event_bus=self._event_bus)

    async def dispatch_approved_session(self, session) -> dict:
        """Main entry point: dispatch an approved Think Tank session.

        Called from thinktank_service.approve().

        Returns:
            {
                "epic_id": "beads-xxx",
                "task_count": 5,
                "status": "dispatching",
                "message": "Created 5 beads, dispatching first wave..."
            }
        """
        self._ensure_services()

        session_id = session.id
        logger.info(f"Dispatching session {session_id}: {session.topic}")

        # Notify UI: dispatch starting
        if self._event_bus:
            await self._event_bus.publish("DISPATCH_STARTED", {
                "session_id": session_id,
                "topic": session.topic,
                "status": "creating_beads",
            })

        # Step 1: Convert spec-kit → beads
        try:
            plan = await self._bead_generator.spec_to_beads(session)
        except Exception as e:
            logger.error(f"Bead generation failed: {e}")
            if self._event_bus:
                await self._event_bus.publish("DISPATCH_ERROR", {
                    "session_id": session_id,
                    "error": f"Failed to create beads: {e}",
                    "phase": "bead_generation",
                })
            return {"status": "error", "message": str(e)}

        if self._event_bus:
            await self._event_bus.publish("DISPATCH_PROGRESS", {
                "session_id": session_id,
                "status": "assigning_agents",
                "beads_created": len(plan.tasks),
                "epic_id": plan.epic_id,
            })

        # Step 2: Assign agents via KG
        try:
            await self._agent_assigner.assign_beads(plan)
        except Exception as e:
            logger.warning(f"Agent assignment failed, using hints: {e}")

        # Step 3: Link session ↔ epic
        self._beads_bridge.link_session(session_id, plan.epic_id)

        # Step 4: Save dispatch state
        self._active_dispatches[session_id] = {
            "plan": plan,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "dispatching",
            "completed_beads": set(),
            "failed_beads": set(),
            "retry_counts": {},
        }

        if self._event_bus:
            await self._event_bus.publish("DISPATCH_PROGRESS", {
                "session_id": session_id,
                "status": "spawning_agents",
                "task_assignments": {
                    t.id: t.suggested_agent for t in plan.tasks if t.id
                },
            })

        # Step 5: Start the dispatch loop (runs in background)
        task = asyncio.create_task(self._dispatch_loop(session_id))
        self._dispatch_tasks[session_id] = task

        return {
            "epic_id": plan.epic_id,
            "task_count": len(plan.tasks),
            "status": "dispatching",
            "message": f"Created {len(plan.tasks)} beads, dispatching first wave...",
        }

    async def _dispatch_loop(self, session_id: str) -> None:
        """Core loop: find unblocked beads → spawn agents → monitor → repeat.

        Runs until all beads are closed or max retries exhausted.
        """
        dispatch = self._active_dispatches.get(session_id)
        if not dispatch:
            return

        plan = dispatch["plan"]
        all_bead_ids = {t.id for t in plan.tasks if t.id}

        while True:
            try:
                # Find beads ready to dispatch (unblocked + not already running)
                ready_beads = await self._find_ready_beads(plan, dispatch)

                # Spawn agents for ready beads (respecting concurrency limit)
                current_running = len(self._running_agents)
                available_slots = MAX_CONCURRENT_AGENTS - current_running

                for bead in ready_beads[:available_slots]:
                    agent = bead.suggested_agent or "platform-agent"
                    await self._spawn_agent(session_id, bead.id, agent, bead.title)
                    await asyncio.sleep(SPAWN_COOLDOWN_SECONDS)

                # Check for completed/failed agents
                await self._check_agent_statuses(session_id, dispatch)

                # Check if all done
                done = dispatch["completed_beads"] | dispatch["failed_beads"]
                if done >= all_bead_ids:
                    # All beads processed
                    failed = dispatch["failed_beads"]
                    if failed:
                        dispatch["status"] = "completed_with_errors"
                        msg = f"Completed with {len(failed)} failures"
                    else:
                        dispatch["status"] = "completed"
                        msg = "All tasks completed successfully"

                    logger.info(f"Dispatch {session_id}: {msg}")
                    if self._event_bus:
                        await self._event_bus.publish("DISPATCH_COMPLETE", {
                            "session_id": session_id,
                            "epic_id": plan.epic_id,
                            "status": dispatch["status"],
                            "total": len(all_bead_ids),
                            "completed": len(dispatch["completed_beads"]),
                            "failed": len(dispatch["failed_beads"]),
                            "message": msg,
                        })
                    break

                # Wait before next check
                await asyncio.sleep(MONITOR_POLL_INTERVAL)

            except asyncio.CancelledError:
                logger.info(f"Dispatch loop cancelled for {session_id}")
                break
            except Exception as e:
                logger.error(f"Dispatch loop error: {e}")
                await asyncio.sleep(MONITOR_POLL_INTERVAL)

    async def _find_ready_beads(self, plan, dispatch) -> list:
        """Find beads that are ready to dispatch (unblocked and not running/done)."""
        completed = dispatch["completed_beads"]
        failed = dispatch["failed_beads"]
        running = set(self._running_agents.keys())

        ready = []
        for task in plan.tasks:
            if not task.id:
                continue
            if task.id in completed or task.id in failed or task.id in running:
                continue

            # Check dependencies
            deps = plan.dependency_map.get(task.id, [])
            all_deps_done = all(d in completed for d in deps)
            any_dep_failed = any(d in failed for d in deps)

            if any_dep_failed:
                # Dependency failed — mark this as failed too
                dispatch["failed_beads"].add(task.id)
                logger.warning(f"Bead {task.id} skipped: dependency failed")
                continue

            if all_deps_done:
                ready.append(task)

        return ready

    async def _spawn_agent(self, session_id: str, bead_id: str, agent_name: str, task_title: str) -> None:
        """Spawn an agent via spawn.sh to work on a bead."""
        spawn_script = self._scripts_dir / "spawn.sh"

        if not spawn_script.exists():
            logger.error(f"spawn.sh not found at {spawn_script}")
            return

        # Build the prompt for the agent
        prompt = f"Work on bead {bead_id}. Run: bd show {bead_id} to see the full task spec."

        # Agent working directory
        agent_dir = Path.home() / "agents" / f"{agent_name}-{bead_id[-6:]}"

        logger.info(f"Spawning {agent_name} for bead {bead_id}: {task_title}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "bash", str(spawn_script),
                "reactive",
                prompt,
                str(agent_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._baap_root),
                env={**os.environ, "AGENT_NAME": agent_name, "BEAD_ID": bead_id},
            )

            self._running_agents[bead_id] = {
                "agent": agent_name,
                "process": proc,
                "started_at": time.time(),
                "session_id": session_id,
                "title": task_title,
            }

            if self._event_bus:
                await self._event_bus.publish("AGENT_SPAWNED", {
                    "session_id": session_id,
                    "bead_id": bead_id,
                    "agent": agent_name,
                    "title": task_title,
                })

        except Exception as e:
            logger.error(f"Failed to spawn {agent_name}: {e}")
            if self._event_bus:
                await self._event_bus.publish("AGENT_FAILED", {
                    "session_id": session_id,
                    "bead_id": bead_id,
                    "agent": agent_name,
                    "error": str(e),
                })

    async def _check_agent_statuses(self, session_id: str, dispatch: dict) -> None:
        """Check which running agents have completed or timed out."""
        to_remove = []

        for bead_id, info in self._running_agents.items():
            if info["session_id"] != session_id:
                continue

            proc = info["process"]
            elapsed = time.time() - info["started_at"]

            # Check if process completed
            if proc.returncode is not None:
                if proc.returncode == 0:
                    dispatch["completed_beads"].add(bead_id)
                    logger.info(f"Agent completed: {info['agent']} for {bead_id}")

                    if self._event_bus:
                        await self._event_bus.publish("AGENT_COMPLETED", {
                            "session_id": session_id,
                            "bead_id": bead_id,
                            "agent": info["agent"],
                            "title": info["title"],
                        })
                else:
                    await self._handle_agent_failure(session_id, bead_id, info, dispatch)

                to_remove.append(bead_id)

            # Check timeout
            elif elapsed > AGENT_TIMEOUT_MINUTES * 60:
                logger.warning(f"Agent timed out: {info['agent']} for {bead_id}")
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=10)
                except (asyncio.TimeoutError, ProcessLookupError):
                    proc.kill()

                await self._handle_agent_failure(
                    session_id, bead_id, info, dispatch,
                    error="Agent timed out"
                )
                to_remove.append(bead_id)

            # Also try polling bd show to check if bead was closed
            # (agent might close bead without process exiting cleanly)
            else:
                status = await self._beads_bridge.get_bead_status(bead_id)
                if status and status.get("status") in ("closed", "resolved"):
                    dispatch["completed_beads"].add(bead_id)
                    to_remove.append(bead_id)
                    logger.info(f"Bead {bead_id} closed (detected via bd)")

                    if self._event_bus:
                        await self._event_bus.publish("AGENT_COMPLETED", {
                            "session_id": session_id,
                            "bead_id": bead_id,
                            "agent": info["agent"],
                        })

        for bead_id in to_remove:
            self._running_agents.pop(bead_id, None)

    async def _handle_agent_failure(self, session_id: str, bead_id: str, info: dict, dispatch: dict, error: str = "") -> None:
        """Handle a failed agent — retry or escalate."""
        retry_count = dispatch["retry_counts"].get(bead_id, 0)

        if retry_count < MAX_RETRIES_PER_BEAD:
            # Retry
            dispatch["retry_counts"][bead_id] = retry_count + 1
            logger.warning(f"Retrying bead {bead_id} (attempt {retry_count + 1}/{MAX_RETRIES_PER_BEAD})")

            if self._event_bus:
                await self._event_bus.publish("AGENT_RETRYING", {
                    "session_id": session_id,
                    "bead_id": bead_id,
                    "agent": info["agent"],
                    "attempt": retry_count + 1,
                    "error": error or "Agent failed",
                })

            # Re-spawn after a delay
            await asyncio.sleep(5)
            await self._spawn_agent(
                session_id, bead_id,
                info["agent"], info.get("title", "Retry")
            )
        else:
            # Max retries exhausted — mark as failed
            dispatch["failed_beads"].add(bead_id)
            logger.error(f"Bead {bead_id} failed after {MAX_RETRIES_PER_BEAD} retries")

            if self._event_bus:
                await self._event_bus.publish("AGENT_FAILED", {
                    "session_id": session_id,
                    "bead_id": bead_id,
                    "agent": info["agent"],
                    "error": error or "Max retries exhausted",
                    "retries": retry_count,
                })

    def get_dispatch_status(self, session_id: str) -> dict | None:
        """Get current dispatch status for a session."""
        dispatch = self._active_dispatches.get(session_id)
        if not dispatch:
            return None

        plan = dispatch["plan"]
        return {
            "session_id": session_id,
            "epic_id": plan.epic_id,
            "status": dispatch["status"],
            "total": len(plan.tasks),
            "completed": len(dispatch["completed_beads"]),
            "failed": len(dispatch["failed_beads"]),
            "running": len([
                b for b, info in self._running_agents.items()
                if info["session_id"] == session_id
            ]),
            "started_at": dispatch["started_at"],
        }

    async def cancel_dispatch(self, session_id: str) -> bool:
        """Cancel an active dispatch, killing all running agents."""
        # Cancel the dispatch loop
        task = self._dispatch_tasks.pop(session_id, None)
        if task:
            task.cancel()

        # Kill running agents
        for bead_id, info in list(self._running_agents.items()):
            if info["session_id"] == session_id:
                try:
                    info["process"].terminate()
                except ProcessLookupError:
                    pass
                self._running_agents.pop(bead_id, None)

        dispatch = self._active_dispatches.pop(session_id, None)
        if dispatch:
            dispatch["status"] = "cancelled"

        logger.info(f"Dispatch cancelled for {session_id}")
        return True

    async def cleanup(self) -> None:
        """Clean up all dispatches and agents."""
        for session_id in list(self._dispatch_tasks.keys()):
            await self.cancel_dispatch(session_id)
        if self._beads_bridge:
            await self._beads_bridge.cleanup()
```

## Key Design Decisions

1. **Background dispatch loop**: `dispatch_approved_session()` starts the loop via `asyncio.create_task()` and returns immediately with a status dict. The UI gets real-time updates via WebSocket events, not by blocking on the HTTP response.

2. **Wave-based execution**: Beads are dispatched in waves. Phase 1 beads all spawn (up to MAX_CONCURRENT=3). When they complete, phase 2 beads unblock and spawn. This respects the dependency DAG without complex scheduling.

3. **Dual completion detection**: Checks both process exit code AND bead status via `bd show`. An agent might close its bead (via `bd close`) before the tmux session exits cleanly. Either signal counts as "done".

4. **Retry with backoff**: Failed agents get 2 retries. After that, the bead is marked failed and downstream beads are skipped. This prevents infinite retry loops.

5. **Cancellation support**: `cancel_dispatch()` kills all agents and cancels the loop. The UI can trigger this via a "Stop Build" button.

6. **Event-driven UI updates**: Every significant state change emits a WebSocket event (DISPATCH_STARTED, DISPATCH_PROGRESS, AGENT_SPAWNED, AGENT_COMPLETED, AGENT_FAILED, AGENT_RETRYING, DISPATCH_COMPLETE). The frontend can render a live progress view.

## How spawn.sh Is Called

Read the actual `spawn.sh` to confirm its interface. Based on PROD_PRD v1:

```bash
spawn.sh <type> <prompt> <agent_dir>
# type: "reactive" (triggered by bead), "proactive" (cron), "team" (multi-agent)
# prompt: what the agent should do
# agent_dir: working directory for the agent
```

The dispatch engine calls it as:
```bash
bash .claude/scripts/spawn.sh reactive "Work on bead beads-xxx. Run: bd show beads-xxx" ~/agents/platform-agent-xxx123
```

**CRITICAL**: Read spawn.sh before writing this code. Confirm:
- Exact argument order and format
- How it creates worktrees
- How it starts the Claude Code session
- How it handles the MCP config
- Environment variables it expects

## Success Criteria

```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
from services.dispatch_engine import DispatchEngine
d = DispatchEngine()
print('DispatchEngine importable: OK')
print('MAX_CONCURRENT_AGENTS:', 3)
print('Methods:', [m for m in dir(d) if not m.startswith('_')])
"
```
