"""
dispatch_engine.py — The core dispatch loop.

Converts approved Think Tank sessions into running agent swarms.
Coordinates the full lifecycle: spec -> beads -> assign -> spawn -> monitor -> complete.
"""

import asyncio
import json
import logging
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from config import PROJECT_ROOT, SCRIPTS_DIR, SESSIONS_DIR, HEARTBEAT_DIR, HEARTBEAT_STALE_SECONDS

# Structured logger with session/bead correlation
logger = logging.getLogger("dispatch")

# Limits
MAX_CONCURRENT_AGENTS = 3
SPAWN_COOLDOWN_SECONDS = 2       # Wait between spawns to avoid overwhelming
MONITOR_POLL_INTERVAL = 10       # Seconds between bead status checks
MAX_RETRIES_PER_BEAD = 2         # Max retry attempts before escalating
AGENT_TIMEOUT_MINUTES = 120      # Kill agent after this long

DISPATCH_STATE_FILE = SESSIONS_DIR / "dispatch_state.json"


def _log(level: int, msg: str, session_id: str = "", bead_id: str = "", agent: str = "") -> None:
    """Structured log helper with correlation IDs."""
    extra_parts = []
    if session_id:
        extra_parts.append(f"session={session_id}")
    if bead_id:
        extra_parts.append(f"bead={bead_id}")
    if agent:
        extra_parts.append(f"agent={agent}")
    prefix = f"[{' '.join(extra_parts)}] " if extra_parts else ""
    logger.log(level, f"{prefix}{msg}")


class DispatchEngine:
    """Orchestrates the full build lifecycle after Think Tank approval."""

    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._baap_root = PROJECT_ROOT
        self._scripts_dir = SCRIPTS_DIR

        # Lazy-loaded sibling services
        self._bead_generator = None
        self._agent_assigner = None
        self._beads_bridge = None
        self._failure_recovery = None
        self._progress_bridge = None

        # Active dispatch state
        self._active_dispatches: dict[str, dict] = {}  # session_id -> dispatch state
        self._running_agents: dict[str, dict] = {}     # bead_id -> {agent, process, started_at}
        self._dispatch_tasks: dict[str, asyncio.Task] = {}

        # Durable audit log — survives restarts via dispatch_state.json
        self._audit_log: list[dict] = []

        # Idempotency cache: idempotency_key -> (cached_response, timestamp)
        self._idempotency_cache: dict[str, tuple[dict, float]] = {}
        self._idempotency_ttl = 300  # 5 minutes
        self._idempotency_max_size = 100

        # Load persisted dispatch state
        self._load_dispatch_state()

    def _load_dispatch_state(self) -> None:
        """Load persisted dispatch state from disk."""
        if DISPATCH_STATE_FILE.exists():
            try:
                data = json.loads(DISPATCH_STATE_FILE.read_text())
                # Restore running agents and dispatch metadata (not asyncio tasks)
                for session_id, dispatch_data in data.get("dispatches", {}).items():
                    self._active_dispatches[session_id] = {
                        "started_at": dispatch_data.get("started_at"),
                        "status": dispatch_data.get("status", "unknown"),
                        "completed_beads": set(dispatch_data.get("completed_beads", [])),
                        "failed_beads": set(dispatch_data.get("failed_beads", [])),
                        "retry_counts": dispatch_data.get("retry_counts", {}),
                        "epic_id": dispatch_data.get("epic_id"),
                        "task_count": dispatch_data.get("task_count", 0),
                    }
                    # Restore plan from persisted task data (or reconstruct from bd CLI)
                    persisted_tasks = dispatch_data.get("tasks", [])
                    if not persisted_tasks:
                        # Fallback: reconstruct from bd CLI if epic_id exists
                        epic_id = dispatch_data.get("epic_id")
                        if epic_id:
                            persisted_tasks = self._reconstruct_tasks_from_bd(epic_id)
                    if persisted_tasks:
                        from .bead_generator import TaskBead, BeadPlan
                        plan = BeadPlan(
                            epic_id=dispatch_data.get("epic_id", ""),
                            session_id=session_id,
                            topic="(restored from state)",
                        )
                        for td in persisted_tasks:
                            task = TaskBead(title=td.get("title", ""))
                            task.id = td.get("id", "")
                            task.phase = td.get("phase", 1)
                            task.suggested_agent = td.get("suggested_agent")
                            task.type = td.get("type", "task")
                            plan.tasks.append(task)
                        plan.dependency_map = dispatch_data.get("dependency_map", {})
                        plan.agent_hints = dispatch_data.get("agent_hints", {})
                        self._active_dispatches[session_id]["plan"] = plan

                for bead_id, agent_data in data.get("running_agents", {}).items():
                    self._running_agents[bead_id] = agent_data
                self._audit_log = data.get("audit_log", [])

                # Mark stale dispatches (stuck >1 hour with no running agents)
                for session_id, dispatch in self._active_dispatches.items():
                    if dispatch["status"] == "dispatching" and not any(
                        info.get("session_id") == session_id for info in self._running_agents.values()
                    ):
                        started = dispatch.get("started_at", "")
                        if started:
                            try:
                                start_dt = datetime.fromisoformat(started)
                                if (datetime.now(timezone.utc) - start_dt).total_seconds() > 3600:
                                    dispatch["status"] = "stale"
                                    _log(logging.WARNING, f"Marked stale dispatch (>1h, no agents)", session_id=session_id)
                            except (ValueError, TypeError):
                                pass

                _log(logging.INFO, f"Loaded dispatch state: {len(self._active_dispatches)} dispatches, {len(self._running_agents)} agents, {len(self._audit_log)} audit entries")
            except Exception as e:
                _log(logging.WARNING, f"Failed to load dispatch state: {e}")

    def _reconstruct_tasks_from_bd(self, epic_id: str) -> list[dict]:
        """Reconstruct task list from bd CLI when no persisted tasks exist."""
        import subprocess
        bd_path = Path.home() / ".local" / "bin" / "bd"
        bd_cmd = str(bd_path) if bd_path.exists() else "bd"
        env = {**__import__("os").environ, "PATH": f"{Path.home() / '.local' / 'bin'}:{__import__('os').environ.get('PATH', '')}"}
        try:
            result = subprocess.run(
                [bd_cmd, "list", "--json"],
                capture_output=True, text=True, timeout=10, env=env,
            )
            if result.returncode != 0:
                return []
            all_beads = json.loads(result.stdout)
            tasks = []
            for b in all_beads:
                bead_id = b.get("id", "")
                # Include child beads of this epic (format: epic_id.N)
                if bead_id.startswith(f"{epic_id}.") and b.get("issue_type") != "epic":
                    tasks.append({
                        "id": bead_id,
                        "title": b.get("title", ""),
                        "phase": 1,  # Cannot reconstruct phase; default to 1
                        "suggested_agent": b.get("assignee"),
                        "type": b.get("issue_type", "task"),
                    })
            _log(logging.INFO, f"Reconstructed {len(tasks)} tasks from bd for epic {epic_id}")
            return tasks
        except Exception as e:
            _log(logging.WARNING, f"Failed to reconstruct tasks from bd: {e}")
            return []

    def _persist_dispatch_state(self) -> None:
        """Save dispatch state to disk for crash recovery."""
        try:
            data = {
                "dispatches": {},
                "running_agents": self._running_agents,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            for session_id, dispatch in self._active_dispatches.items():
                plan = dispatch.get("plan")
                data["dispatches"][session_id] = {
                    "started_at": dispatch.get("started_at"),
                    "status": dispatch.get("status"),
                    "completed_beads": list(dispatch.get("completed_beads", set())),
                    "failed_beads": list(dispatch.get("failed_beads", set())),
                    "retry_counts": dispatch.get("retry_counts", {}),
                    "epic_id": dispatch.get("epic_id") or (plan.epic_id if plan else None),
                    "task_count": dispatch.get("task_count") or (len(plan.tasks) if plan else 0),
                    "tasks": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "phase": getattr(t, "phase", 1),
                            "suggested_agent": getattr(t, "suggested_agent", None),
                            "type": getattr(t, "type", "task"),
                        }
                        for t in (plan.tasks if plan else [])
                    ],
                    "dependency_map": {
                        k: list(v) for k, v in
                        (plan.dependency_map.items() if plan else {}.items())
                    },
                    "agent_hints": dict(plan.agent_hints) if plan else {},
                }
            # Include last 500 audit entries for durability
            data["audit_log"] = self._audit_log[-500:]
            DISPATCH_STATE_FILE.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            _log(logging.WARNING, f"Failed to persist dispatch state: {e}")

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
        if self._failure_recovery is None:
            from services.failure_recovery import FailureRecovery
            self._failure_recovery = FailureRecovery(event_bus=self._event_bus)
        if self._progress_bridge is None:
            from services.progress_bridge import ProgressBridge
            self._progress_bridge = ProgressBridge(event_bus=self._event_bus)

    def check_dispatch_health(self) -> dict:
        """Pre-flight check: verify all required binaries and paths exist."""
        checks = {
            "bd": shutil.which("bd") is not None,
            "tmux": shutil.which("tmux") is not None,
            "claude": shutil.which("claude") is not None,
            "spawn_sh": (self._scripts_dir / "spawn.sh").exists(),
            "git_repo": (self._baap_root / ".git").exists(),
        }
        missing = [k for k, v in checks.items() if not v]
        return {
            "ready": all(checks.values()),
            "checks": checks,
            "missing": missing,
        }

    def check_idempotency(self, key: str) -> dict | None:
        """Check if an idempotency key has a cached result."""
        if not key:
            return None
        entry = self._idempotency_cache.get(key)
        if entry is None:
            return None
        result, ts = entry
        if time.time() - ts > self._idempotency_ttl:
            self._idempotency_cache.pop(key, None)
            return None
        return result

    def cache_idempotency(self, key: str, result: dict) -> None:
        """Cache a result for an idempotency key with TTL."""
        if not key:
            return
        # Evict old entries if cache is full
        if len(self._idempotency_cache) >= self._idempotency_max_size:
            now = time.time()
            expired = [k for k, (_, ts) in self._idempotency_cache.items() if now - ts > self._idempotency_ttl]
            for k in expired:
                self._idempotency_cache.pop(k, None)
            # If still full, evict oldest
            if len(self._idempotency_cache) >= self._idempotency_max_size:
                oldest_key = min(self._idempotency_cache, key=lambda k: self._idempotency_cache[k][1])
                self._idempotency_cache.pop(oldest_key, None)
        self._idempotency_cache[key] = (result, time.time())

    async def dispatch_approved_session(self, session, dry_run: bool = False) -> dict:
        """Main entry point: dispatch an approved Think Tank session.

        Args:
            session: Approved ThinkTankSession
            dry_run: If True, return bead plan preview without creating beads

        Returns:
            {
                "success": true,
                "dispatch_status": "queued" | "preview",
                "epic_id": "baap-xxx",
                "task_count": 5,
                ...
            }
        """
        self._ensure_services()

        session_id = session.id
        _log(logging.INFO, f"Dispatch requested: {session.topic}", session_id=session_id)

        # Pre-flight health check
        health = self.check_dispatch_health()
        if not health["ready"] and not dry_run:
            missing = ", ".join(health["missing"])
            _log(logging.ERROR, f"Pre-flight failed: missing {missing}", session_id=session_id)
            return {
                "success": False,
                "dispatch_status": "failed",
                "error": f"Dispatch prerequisites missing: {missing}",
                "health": health,
            }

        # Dry-run mode: return preview without creating beads
        if dry_run:
            _log(logging.INFO, "Dry-run mode: generating preview", session_id=session_id)
            try:
                plan = await self._bead_generator.spec_to_beads(session, dry_run=dry_run)
                preview = {
                    "success": True,
                    "dispatch_status": "preview",
                    "dry_run": True,
                    "preview": {
                        "task_count": len(plan.tasks),
                        "tasks": [
                            {
                                "title": t.title,
                                "description": t.description,
                                "phase": t.phase,
                                "suggested_agent": t.suggested_agent,
                                "acceptance_criteria": t.acceptance_criteria,
                            }
                            for t in plan.tasks
                        ],
                        "dependency_map": {k: list(v) for k, v in plan.dependency_map.items()},
                    },
                }
                return preview
            except Exception as e:
                _log(logging.ERROR, f"Dry-run preview failed: {e}", session_id=session_id)
                return {"success": False, "dispatch_status": "failed", "error": str(e)}

        # Real dispatch: run in background, return immediately
        _log(logging.INFO, f"Starting background dispatch for: {session.topic}", session_id=session_id)
        asyncio.create_task(self._dispatch_in_background(session_id, session))

        return {
            "success": True,
            "dispatch_status": "queued",
            "session_id": session_id,
            "message": "Dispatch queued. Creating beads and spawning agents...",
        }

    async def _dispatch_in_background(self, session_id: str, session) -> None:
        """Full dispatch flow that runs as a background task.

        HTTP returns immediately with 'queued' status. This method handles
        bead creation, agent assignment, and spawning.
        """
        try:
            # Notify UI: dispatch starting
            await self._publish("DISPATCH_STARTED", {
                "session_id": session_id,
                "topic": session.topic,
                "status": "creating_beads",
            })

            # Step 1: Convert spec-kit -> beads
            try:
                plan = await self._bead_generator.spec_to_beads(session)
            except Exception as e:
                _log(logging.ERROR, f"Bead generation failed: {e}", session_id=session_id)
                await self._publish("DISPATCH_ERROR", {
                    "session_id": session_id,
                    "error": f"Failed to create beads: {e}",
                    "phase": "bead_generation",
                })
                return

            await self._publish("DISPATCH_PROGRESS", {
                "session_id": session_id,
                "status": "assigning_agents",
                "beads_created": len(plan.tasks),
                "epic_id": plan.epic_id,
            })

            # Step 2: Assign agents via KG
            try:
                await self._agent_assigner.assign_beads(plan)
            except Exception as e:
                _log(logging.WARNING, f"Agent assignment failed, using hints: {e}", session_id=session_id)

            # Step 3: Link session <-> epic
            self._beads_bridge.link_session(session_id, plan.epic_id)

            # Step 4: Save dispatch state
            self._active_dispatches[session_id] = {
                "plan": plan,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "dispatching",
                "completed_beads": set(),
                "failed_beads": set(),
                "retry_counts": {},
                "epic_id": plan.epic_id,
                "task_count": len(plan.tasks),
            }
            self._persist_dispatch_state()

            # Build assignment detail with reasoning
            reasoning = getattr(plan, "assignment_reasoning", {})
            task_assignments = {}
            for t in plan.tasks:
                if t.id:
                    task_assignments[t.id] = {
                        "agent": t.suggested_agent,
                        "reasoning": reasoning.get(t.id, {}),
                    }

            await self._publish("DISPATCH_PROGRESS", {
                "session_id": session_id,
                "status": "spawning_agents",
                "task_assignments": task_assignments,
            })

            # Step 5: Start the dispatch loop
            task = asyncio.create_task(self._dispatch_loop(session_id))
            self._dispatch_tasks[session_id] = task

        except Exception as e:
            _log(logging.ERROR, f"Background dispatch failed: {e}", session_id=session_id)
            await self._publish("DISPATCH_ERROR", {
                "session_id": session_id,
                "error": str(e),
                "phase": "dispatch_setup",
            })

    async def _publish(self, event_type_name: str, payload: dict) -> None:
        """Publish an event via the event bus and append to durable audit log."""
        # Append to audit log (skip cycle snapshots to avoid noise)
        if not payload.get("cycle"):
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": event_type_name,
                "session_id": payload.get("session_id", ""),
                "bead_id": payload.get("bead_id", ""),
                "agent": payload.get("agent", ""),
                "summary": payload.get("message") or payload.get("status") or payload.get("error") or "",
            }
            self._audit_log.append(entry)
            if len(self._audit_log) > 2000:
                self._audit_log = self._audit_log[-1500:]

        if not self._event_bus:
            return
        try:
            from models import WSEventType
            event_type = WSEventType(event_type_name)
            await self._event_bus.publish(event_type, payload)
        except (ValueError, KeyError):
            logger.debug(f"Skipping unregistered event type: {event_type_name}")

    async def _dispatch_loop(self, session_id: str) -> None:
        """Core loop: find unblocked beads -> spawn agents -> monitor -> repeat.

        Runs until all beads are closed or max retries exhausted.
        """
        dispatch = self._active_dispatches.get(session_id)
        if not dispatch:
            return

        plan = dispatch.get("plan")
        if not plan:
            return

        all_bead_ids = {t.id for t in plan.tasks if t.id}

        while True:
            try:
                # Find beads ready to dispatch (unblocked + not already running)
                ready_beads = self._find_ready_beads(plan, dispatch)

                # Spawn agents for ready beads (respecting concurrency limit)
                current_running = sum(
                    1 for info in self._running_agents.values()
                    if info["session_id"] == session_id
                )
                available_slots = MAX_CONCURRENT_AGENTS - current_running

                for bead in ready_beads[:available_slots]:
                    agent = bead.suggested_agent or "platform-agent"
                    await self._spawn_agent(session_id, bead.id, agent, bead.title)
                    await asyncio.sleep(SPAWN_COOLDOWN_SECONDS)

                # Check for completed/failed agents
                await self._check_agent_statuses(session_id, dispatch)

                # Persist state after every check cycle
                self._persist_dispatch_state()

                # Emit continuous progress snapshot for Control Tower
                status_snapshot = self.get_dispatch_status(session_id)
                if status_snapshot:
                    await self._publish("DISPATCH_PROGRESS", {
                        **status_snapshot,
                        "cycle": True,
                    })

                # Check if all done
                done = dispatch["completed_beads"] | dispatch["failed_beads"]
                if done >= all_bead_ids:
                    failed = dispatch["failed_beads"]
                    if failed:
                        dispatch["status"] = "completed_with_errors"
                        msg = f"Completed with {len(failed)} failures"
                    else:
                        dispatch["status"] = "completed"
                        msg = "All tasks completed successfully"

                    _log(logging.INFO, msg, session_id=session_id)
                    self._persist_dispatch_state()
                    await self._publish("DISPATCH_COMPLETE", {
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
                _log(logging.INFO, "Dispatch loop cancelled", session_id=session_id)
                break
            except Exception as e:
                _log(logging.ERROR, f"Dispatch loop error: {e}", session_id=session_id)
                await asyncio.sleep(MONITOR_POLL_INTERVAL)

    def _find_ready_beads(self, plan, dispatch) -> list:
        """Find beads that are ready to dispatch (unblocked and not running/done).

        Only dispatches TASK-type beads — epics are skipped.
        """
        completed = dispatch["completed_beads"]
        failed = dispatch["failed_beads"]
        running = set(self._running_agents.keys())

        ready = []
        for task in plan.tasks:
            if not task.id:
                continue
            # Skip epic-type beads — only dispatch tasks
            if getattr(task, 'type', 'task') == 'epic':
                continue
            if task.id in completed or task.id in failed or task.id in running:
                continue

            # Check dependencies
            deps = plan.dependency_map.get(task.id, [])
            all_deps_done = all(d in completed for d in deps)
            any_dep_failed = any(d in failed for d in deps)

            if any_dep_failed:
                dispatch["failed_beads"].add(task.id)
                _log(logging.WARNING, f"Bead skipped: dependency failed", bead_id=task.id)
                continue

            if all_deps_done:
                ready.append(task)

        return ready

    async def _spawn_agent(self, session_id: str, bead_id: str, agent_name: str, task_title: str) -> None:
        """Spawn an agent via spawn.sh to work on a bead.

        Injects agent identity (agent.md + MEMORY.md) via --agent-name flag.
        """
        spawn_script = self._scripts_dir / "spawn.sh"

        if not spawn_script.exists():
            _log(logging.ERROR, f"spawn.sh not found at {spawn_script}", session_id=session_id, bead_id=bead_id)
            return

        # Build the prompt for the agent
        prompt = (
            f"Work on bead {bead_id}. Run: bd show {bead_id} to see the full task spec. "
            f"Then implement the task according to its spec and acceptance criteria. "
            f"When done, close the bead: bd close {bead_id} --reason='description of what you did'"
        )

        _log(logging.INFO, f"Spawning agent for task: {task_title}", session_id=session_id, bead_id=bead_id, agent=agent_name)

        try:
            # spawn.sh <type> <prompt> [project_path] [--bead BEAD_ID] [--agent-name NAME]
            cmd_args = [
                "bash", str(spawn_script),
                "reactive",
                prompt,
                str(self._baap_root),
                "--bead", bead_id,
                "--agent-name", agent_name,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._baap_root),
            )

            stdout, stderr = await proc.communicate()
            output = stdout.decode().strip()
            _log(logging.INFO, f"spawn.sh output: {output}", session_id=session_id, bead_id=bead_id, agent=agent_name)

            if proc.returncode != 0:
                stderr_text = stderr.decode().strip()
                _log(logging.ERROR, f"spawn.sh failed (exit {proc.returncode}): {stderr_text}", session_id=session_id, bead_id=bead_id, agent=agent_name)
                await self._publish("AGENT_FAILED", {
                    "session_id": session_id,
                    "bead_id": bead_id,
                    "agent": agent_name,
                    "error": f"spawn.sh failed: {stderr_text}",
                })
                return

            # Extract agent name from spawn.sh output (format: "Launched agent: <name>")
            name_match = re.search(r'Launched agent:\s*(\S+)', output)
            spawned_name = name_match.group(1) if name_match else f"{agent_name}-{bead_id[-6:]}"

            self._running_agents[bead_id] = {
                "agent": agent_name,
                "spawned_name": spawned_name,
                "started_at": time.time(),
                "session_id": session_id,
                "title": task_title,
            }
            self._persist_dispatch_state()

            # Start monitoring this agent via progress_bridge
            if self._progress_bridge:
                await self._progress_bridge.start_monitoring([{
                    "name": spawned_name,
                    "bead_id": bead_id,
                    "session_id": session_id,
                }])

            await self._publish("AGENT_SPAWNED", {
                "session_id": session_id,
                "bead_id": bead_id,
                "agent": agent_name,
                "spawned_name": spawned_name,
                "title": task_title,
            })

        except Exception as e:
            _log(logging.ERROR, f"Failed to spawn agent: {e}", session_id=session_id, bead_id=bead_id, agent=agent_name)
            await self._publish("AGENT_FAILED", {
                "session_id": session_id,
                "bead_id": bead_id,
                "agent": agent_name,
                "error": str(e),
            })

    async def _check_agent_statuses(self, session_id: str, dispatch: dict) -> None:
        """Check which running agents have completed or timed out.

        Implements:
        - Bead status check (primary signal)
        - Exit code check with bead status reconciliation
        - Tmux window watchdog (detects vanished agents)
        - Timeout detection
        - Acceptance criteria verification
        """
        self._ensure_services()
        to_remove = []

        for bead_id, info in list(self._running_agents.items()):
            if info["session_id"] != session_id:
                continue

            elapsed = time.time() - info["started_at"]
            spawned_name = info.get("spawned_name", "")

            # Check bead status via bd show — primary completion signal
            status = await self._beads_bridge.get_bead_status(bead_id)
            if status and status.get("status") in ("closed", "resolved"):
                # Acceptance criteria check
                criteria_status = await self._check_acceptance_criteria(bead_id, info)
                dispatch["completed_beads"].add(bead_id)
                to_remove.append(bead_id)
                _log(logging.INFO, f"Bead closed", session_id=session_id, bead_id=bead_id, agent=info['agent'])

                await self._publish("AGENT_COMPLETED", {
                    "session_id": session_id,
                    "bead_id": bead_id,
                    "agent": info["agent"],
                    "title": info.get("title", ""),
                    "criteria_status": criteria_status,
                })
                continue

            # Check agent exit code file (written by spawn.sh on completion)
            if spawned_name:
                exit_code_file = Path.home() / "agents" / spawned_name / ".agent_exit_code"
                if exit_code_file.exists():
                    try:
                        exit_code = int(exit_code_file.read_text().strip())
                        if exit_code == 0:
                            # Exit 0 but bead not closed — reconciliation check
                            _log(logging.WARNING, f"Agent exited 0 but bead still open — verifying",
                                 session_id=session_id, bead_id=bead_id, agent=info['agent'])

                            # Re-check bead status (may have just closed)
                            await asyncio.sleep(2)
                            status = await self._beads_bridge.get_bead_status(bead_id)
                            if status and status.get("status") in ("closed", "resolved"):
                                dispatch["completed_beads"].add(bead_id)
                                to_remove.append(bead_id)
                                _log(logging.INFO, "Bead closed after recheck",
                                     session_id=session_id, bead_id=bead_id, agent=info['agent'])
                                await self._publish("AGENT_COMPLETED", {
                                    "session_id": session_id,
                                    "bead_id": bead_id,
                                    "agent": info["agent"],
                                })
                                continue
                            else:
                                # Agent exited successfully but didn't close bead
                                diagnostics = self._capture_agent_diagnostics(spawned_name)
                                _log(logging.ERROR,
                                     f"Agent exited 0 but bead not closed — marking failed",
                                     session_id=session_id, bead_id=bead_id, agent=info['agent'])
                                await self._handle_agent_failure(
                                    session_id, bead_id, info, dispatch,
                                    error=f"Agent exited successfully but did not close bead. {diagnostics}"
                                )
                                to_remove.append(bead_id)
                                continue
                        else:
                            diagnostics = self._capture_agent_diagnostics(spawned_name)
                            await self._handle_agent_failure(
                                session_id, bead_id, info, dispatch,
                                error=f"Agent exited with code {exit_code}. {diagnostics}"
                            )
                            to_remove.append(bead_id)
                            continue
                    except (ValueError, OSError):
                        pass

            # Watchdog: check tmux window still exists
            if spawned_name and elapsed > 30:
                tmux_alive = await self._check_tmux_window(spawned_name)
                if not tmux_alive:
                    # Tmux window gone but no exit code and bead not closed
                    diagnostics = self._capture_agent_diagnostics(spawned_name)
                    _log(logging.WARNING, f"Tmux window vanished — agent likely crashed",
                         session_id=session_id, bead_id=bead_id, agent=info['agent'])
                    await self._handle_agent_failure(
                        session_id, bead_id, info, dispatch,
                        error=f"Tmux window disappeared (agent crashed). {diagnostics}"
                    )
                    to_remove.append(bead_id)
                    continue

            # Check heartbeat freshness (soft signal — logs warning, doesn't kill)
            if spawned_name and elapsed > 60:
                hb_file = HEARTBEAT_DIR / spawned_name
                if hb_file.exists():
                    try:
                        hb_age = time.time() - float(hb_file.read_text().strip())
                        if hb_age > HEARTBEAT_STALE_SECONDS:
                            _log(logging.WARNING, f"Heartbeat stale ({int(hb_age)}s old)",
                                 session_id=session_id, bead_id=bead_id, agent=info['agent'])
                    except (ValueError, OSError):
                        pass

            # Check timeout
            if elapsed > AGENT_TIMEOUT_MINUTES * 60:
                diagnostics = self._capture_agent_diagnostics(spawned_name)
                _log(logging.WARNING, f"Agent timed out after {int(elapsed/60)}m",
                     session_id=session_id, bead_id=bead_id, agent=info['agent'])
                await self._handle_agent_failure(
                    session_id, bead_id, info, dispatch,
                    error=f"Agent timed out after {int(elapsed/60)} minutes. {diagnostics}"
                )
                to_remove.append(bead_id)

        for bead_id in to_remove:
            self._running_agents.pop(bead_id, None)

    def _capture_agent_diagnostics(self, spawned_name: str) -> str:
        """Capture last 50 lines of agent log for diagnostics."""
        if not spawned_name:
            return ""
        log_file = Path.home() / "agents" / spawned_name / "agent.log"
        if not log_file.exists():
            return ""
        try:
            lines = log_file.read_text().splitlines()
            last_50 = lines[-50:] if len(lines) > 50 else lines
            return "Last log lines:\n" + "\n".join(last_50)
        except OSError:
            return ""

    async def _check_tmux_window(self, spawned_name: str) -> bool:
        """Check if a tmux window for this agent still exists."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux", "list-windows", "-t", "agents", "-F", "#{window_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode != 0:
                return False
            windows = stdout.decode().strip().splitlines()
            return any(spawned_name in w for w in windows)
        except Exception:
            return False

    async def _check_acceptance_criteria(self, bead_id: str, info: dict) -> str:
        """After bead is closed, check if acceptance criteria were addressed."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "bd", "show", bead_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._baap_root),
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()

            # Find acceptance criteria (unchecked checkboxes)
            criteria = re.findall(r'-\s*\[\s*\]\s*(.+)', output)
            if not criteria:
                return "verified"

            # Check if closing notes mention the criteria
            notes_match = re.search(r'(?:Notes|Reason|Close):\s*(.+)', output, re.IGNORECASE | re.DOTALL)
            if notes_match:
                notes = notes_match.group(1).lower()
                unmet = [c for c in criteria if c.lower()[:20] not in notes]
                if unmet:
                    _log(logging.WARNING, f"Unverified criteria: {unmet}", bead_id=bead_id, agent=info.get('agent', ''))
                    return "closed_but_unverified"
            else:
                return "closed_but_unverified"

            return "verified"
        except Exception:
            return "unknown"

    async def _handle_agent_failure(self, session_id: str, bead_id: str, info: dict, dispatch: dict, error: str = "") -> None:
        """Handle a failed agent — retry or escalate."""
        retry_count = dispatch["retry_counts"].get(bead_id, 0)

        if retry_count < MAX_RETRIES_PER_BEAD:
            dispatch["retry_counts"][bead_id] = retry_count + 1
            _log(logging.WARNING, f"Retrying (attempt {retry_count + 1}/{MAX_RETRIES_PER_BEAD})",
                 session_id=session_id, bead_id=bead_id, agent=info["agent"])

            await self._publish("AGENT_RETRYING", {
                "session_id": session_id,
                "bead_id": bead_id,
                "agent": info["agent"],
                "attempt": retry_count + 1,
                "error": error or "Agent failed",
            })

            # Clean up before retry
            if self._failure_recovery:
                await self._failure_recovery.handle_agent_failure(
                    bead_id, info["agent"], session_id, error, retry_count
                )

            # Re-spawn after a delay
            await asyncio.sleep(5)
            await self._spawn_agent(
                session_id, bead_id,
                info["agent"], info.get("title", "Retry")
            )
        else:
            # Max retries exhausted — mark as failed
            dispatch["failed_beads"].add(bead_id)
            _log(logging.ERROR, f"Failed after {MAX_RETRIES_PER_BEAD} retries",
                 session_id=session_id, bead_id=bead_id, agent=info["agent"])

            if self._failure_recovery:
                await self._failure_recovery.handle_agent_failure(
                    bead_id, info["agent"], session_id, error, retry_count
                )

            await self._publish("AGENT_FAILED", {
                "session_id": session_id,
                "bead_id": bead_id,
                "agent": info["agent"],
                "error": error or "Max retries exhausted",
                "retries": retry_count,
            })

    def get_dispatch_status(self, session_id: str) -> dict | None:
        """Get current dispatch status for a session.

        Returns aggregate counters plus a per-task breakdown with status,
        elapsed time, and retry count for full Control Tower visibility.
        """
        dispatch = self._active_dispatches.get(session_id)
        if not dispatch:
            return None

        plan = dispatch.get("plan")
        epic_id = dispatch.get("epic_id") or (plan.epic_id if plan else None)
        total = dispatch.get("task_count") or (len(plan.tasks) if plan else 0)

        # Build per-task breakdown
        tasks_detail = []
        if plan:
            reasoning = getattr(plan, "assignment_reasoning", {})
            for task in plan.tasks:
                if not task.id:
                    continue
                if getattr(task, "type", "task") == "epic":
                    continue
                bead_id = task.id
                agent_info = self._running_agents.get(bead_id)

                if bead_id in dispatch["completed_beads"]:
                    status = "completed"
                elif bead_id in dispatch["failed_beads"]:
                    status = "failed"
                elif agent_info:
                    status = "running"
                else:
                    deps = getattr(plan, "dependency_map", {}).get(bead_id, [])
                    any_dep_failed = any(d in dispatch["failed_beads"] for d in deps)
                    all_deps_done = all(d in dispatch["completed_beads"] for d in deps)
                    if any_dep_failed:
                        status = "blocked_by_failure"
                    elif not all_deps_done:
                        status = "waiting"
                    else:
                        status = "ready"

                elapsed_s = None
                if agent_info and "started_at" in agent_info:
                    started = agent_info["started_at"]
                    if isinstance(started, (int, float)):
                        elapsed_s = int(time.time() - started)

                task_entry = {
                    "bead_id": bead_id,
                    "title": task.title,
                    "agent": (agent_info or {}).get("agent") or getattr(task, "suggested_agent", None),
                    "status": status,
                    "elapsed_s": elapsed_s,
                    "retry_count": dispatch["retry_counts"].get(bead_id, 0),
                }
                # Include assignment scores if available
                if bead_id in reasoning:
                    task_entry["assignment_scores"] = reasoning[bead_id]
                tasks_detail.append(task_entry)

        return {
            "session_id": session_id,
            "epic_id": epic_id,
            "status": dispatch["status"],
            "total": total,
            "completed": len(dispatch["completed_beads"]),
            "failed": len(dispatch["failed_beads"]),
            "running": sum(
                1 for info in self._running_agents.values()
                if info["session_id"] == session_id
            ),
            "started_at": dispatch["started_at"],
            "tasks": tasks_detail,
            "health": self.check_dispatch_health(),
            "token_usage": getattr(plan, "token_usage", {}) if plan else {},
        }

    async def cancel_dispatch(self, session_id: str) -> bool:
        """Cancel an active dispatch, killing all running agents."""
        # Cancel the dispatch loop
        task = self._dispatch_tasks.pop(session_id, None)
        if task:
            task.cancel()

        # Kill running agents via kill-agent.sh
        kill_script = self._scripts_dir / "kill-agent.sh"
        for bead_id, info in list(self._running_agents.items()):
            if info["session_id"] == session_id:
                spawned_name = info.get("spawned_name", "")
                if spawned_name and kill_script.exists():
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "bash", str(kill_script), spawned_name,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            cwd=str(self._baap_root),
                        )
                        await asyncio.wait_for(proc.communicate(), timeout=15)
                    except Exception:
                        pass
                self._running_agents.pop(bead_id, None)

        dispatch = self._active_dispatches.pop(session_id, None)
        if dispatch:
            dispatch["status"] = "cancelled"

        self._persist_dispatch_state()
        _log(logging.INFO, "Dispatch cancelled", session_id=session_id)
        await self._publish("DISPATCH_CANCELLED", {
            "session_id": session_id,
            "message": "Dispatch cancelled by user",
        })
        return True

    async def cleanup(self) -> None:
        """Clean up all dispatches and agents."""
        for session_id in list(self._dispatch_tasks.keys()):
            await self.cancel_dispatch(session_id)
        if self._beads_bridge:
            await self._beads_bridge.cleanup()
        if self._progress_bridge:
            await self._progress_bridge.cleanup()
        self._persist_dispatch_state()
