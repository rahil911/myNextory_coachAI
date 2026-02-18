"""
agent_service.py — Agent status reading, transition detection, and script execution.
"""

import asyncio
import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from config import STATUS_DIR, HEARTBEAT_DIR, LOG_DIR, SCRIPTS_DIR, HEARTBEAT_STALE_SECONDS, MAX_TIMELINE_EVENTS
from models import Agent, AgentStatus, WSEventType

logger = logging.getLogger("baap.agent_service")

# Standalone event bus URL (for bridging lifecycle events)
EVENT_BUS_URL = "http://localhost:8003/api/emit"

# TTL cache for agent file reads (seconds)
_AGENT_CACHE_TTL = 5


class AgentService:
    def __init__(self, event_bus=None, notification_router=None):
        self._event_bus = event_bus
        self._notification_router = notification_router
        self._last_snapshot: dict[str, str] = {}
        self._timeline: list[dict] = []
        self._http_client = None
        # In-memory cache for read_agents results
        self._cache_agents: list[Agent] = []
        self._cache_ts: float = 0

    def _add_timeline_event(self, event_type: str, agent: str, detail: str) -> dict:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "agent": agent,
            "detail": detail,
        }
        self._timeline.append(event)
        if len(self._timeline) > MAX_TIMELINE_EVENTS:
            self._timeline.pop(0)
        return event

    def read_agents(self) -> list[Agent]:
        """Read all agent status files and enrich with heartbeat data. Cached for 5s."""
        now_mono = time.monotonic()
        if self._cache_agents and (now_mono - self._cache_ts) < _AGENT_CACHE_TTL:
            return self._cache_agents

        agents = []
        if not STATUS_DIR.exists():
            return agents

        now = time.time()
        for f in sorted(STATUS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            name = data.get("agent", f.stem)

            # Heartbeat check
            hb_file = HEARTBEAT_DIR / name
            hb_age = None
            hb_stale = False
            if hb_file.exists():
                try:
                    last_hb = float(hb_file.read_text().strip())
                    hb_age = int(now - last_hb)
                    hb_stale = hb_age > HEARTBEAT_STALE_SECONDS
                except (ValueError, OSError):
                    pass

            # Map raw status to enum
            raw_status = (data.get("status") or "unknown").lower()
            status_map = {
                "working": AgentStatus.WORKING,
                "running": AgentStatus.WORKING,
                "spawning": AgentStatus.SPAWNING,
                "idle": AgentStatus.IDLE,
                "stopped": AgentStatus.STOPPED,
                "failed": AgentStatus.FAILED,
            }
            status = status_map.get(raw_status, AgentStatus.UNKNOWN)

            agents.append(Agent(
                name=name,
                level=data.get("level", "?"),
                status=status,
                bead=data.get("bead"),
                current_action=data.get("current_action"),
                started_at=data.get("started_at"),
                last_update=data.get("last_update"),
                worktree=data.get("worktree"),
                errors=data.get("errors", 0),
                heartbeat_age_s=hb_age,
                heartbeat_stale=hb_stale,
            ))

        self._cache_agents = agents
        self._cache_ts = now_mono
        return agents

    async def _bridge_to_event_bus(self, event_name: str, payload: dict):
        """Forward lifecycle events to the standalone event bus (port 8003)."""
        try:
            import httpx
        except ImportError:
            return
        try:
            if self._http_client is None:
                self._http_client = httpx.AsyncClient(timeout=5.0)
            await self._http_client.post(
                EVENT_BUS_URL,
                json={"event": event_name, "payload": payload},
            )
        except Exception:
            pass  # Best-effort bridging — don't crash if event bus is down

    async def _notify(self, agent: str, event: str, detail: str):
        """Send notification via notification router (if configured)."""
        if self._notification_router:
            try:
                await self._notification_router.notify_agent_event(agent, event, detail)
            except Exception:
                pass  # Best-effort notifications

    def _lifecycle_event_type(self, status: str, prev: str | None) -> WSEventType:
        """Map agent status to specific lifecycle WSEventType."""
        if prev is None:
            return WSEventType.AGENT_SPAWNED
        if status == "working":
            return WSEventType.AGENT_WORKING
        if status == "failed":
            return WSEventType.AGENT_FAILED
        if status in ("stopped", "gone"):
            return WSEventType.AGENT_COMPLETED
        return WSEventType.AGENT_STATUS_CHANGE

    async def detect_transitions(self, agents: list[Agent]) -> list[dict]:
        """Compare current agent statuses against last snapshot, emit events."""
        events = []
        current: dict[str, str] = {}

        for a in agents:
            current[a.name] = a.status.value
            prev = self._last_snapshot.get(a.name)
            if prev is None:
                ev = self._add_timeline_event("agent_spawned", a.name, f"Agent appeared with status: {a.status.value}")
                events.append(ev)
                payload = {"agent": a.name, "status": a.status.value, "previous": None, "action": "spawned",
                           "bead": a.bead, "level": a.level}
                if self._event_bus:
                    await self._event_bus.publish(WSEventType.AGENT_SPAWNED, payload)
                    await self._event_bus.publish(WSEventType.AGENT_STATUS_CHANGE, payload)
                await self._bridge_to_event_bus("agent.spawned", payload)
                await self._notify(a.name, "spawned", f"Agent appeared with status: {a.status.value}")
            elif prev != a.status.value:
                ev = self._add_timeline_event("status_change", a.name, f"{prev} -> {a.status.value}")
                events.append(ev)
                lifecycle_type = self._lifecycle_event_type(a.status.value, prev)
                payload = {"agent": a.name, "status": a.status.value, "previous": prev, "action": "changed",
                           "bead": a.bead, "level": a.level}
                if self._event_bus:
                    await self._event_bus.publish(lifecycle_type, payload)
                    if lifecycle_type != WSEventType.AGENT_STATUS_CHANGE:
                        await self._event_bus.publish(WSEventType.AGENT_STATUS_CHANGE, payload)
                bus_event = f"agent.{a.status.value}"
                await self._bridge_to_event_bus(bus_event, payload)
                await self._notify(a.name, a.status.value, f"{prev} -> {a.status.value}")

        # Detect agents that disappeared
        for name, prev_status in self._last_snapshot.items():
            if name not in current:
                ev = self._add_timeline_event("agent_gone", name, f"Agent disappeared (was: {prev_status})")
                events.append(ev)
                payload = {"agent": name, "status": "gone", "previous": prev_status, "action": "disappeared"}
                if self._event_bus:
                    await self._event_bus.publish(WSEventType.AGENT_COMPLETED, payload)
                    await self._event_bus.publish(WSEventType.AGENT_STATUS_CHANGE, payload)
                await self._bridge_to_event_bus("agent.completed", payload)
                await self._notify(name, "complete", f"Agent disappeared (was: {prev_status})")

        self._last_snapshot = current
        return events

    def get_agent(self, name: str) -> Agent | None:
        """Get a single agent by name."""
        agents = self.read_agents()
        for a in agents:
            if a.name == name:
                return a
        return None

    def get_agent_logs(self, name: str, tail: int = 100) -> tuple[str | None, list[str]]:
        """Read the last N lines of an agent's log file."""
        if not LOG_DIR.exists():
            return None, []

        # Try exact match first, then prefix match
        log_file = LOG_DIR / f"{name}.log"
        if not log_file.exists():
            candidates = list(LOG_DIR.glob(f"{name}*.log"))
            if not candidates:
                return None, []
            log_file = max(candidates, key=lambda p: p.stat().st_mtime)

        try:
            lines = log_file.read_text().splitlines()
            return str(log_file), lines[-tail:]
        except OSError:
            return str(log_file), []

    def get_timeline(self, limit: int = 50) -> list[dict]:
        """Return recent timeline events."""
        return list(reversed(self._timeline[-limit:]))

    async def spawn_agent(self, mode: str, prompt: str, path: str | None = None,
                          level: int = 2, bead: str | None = None) -> dict:
        """Spawn a new agent via spawn.sh."""
        script = SCRIPTS_DIR / "spawn.sh"
        if not script.exists():
            return {"success": False, "message": f"spawn.sh not found at {script}"}

        cmd = ["bash", str(script)]
        if bead:
            cmd.extend(["--bead", bead])
        # spawn.sh expects a prompt argument
        cmd.append(prompt)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                cwd=str(SCRIPTS_DIR.parent.parent)  # project root
            )
            return {
                "success": result.returncode == 0,
                "message": result.stdout.strip() or result.stderr.strip(),
                "output": result.stdout,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "spawn.sh timed out after 30s"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def kill_agent(self, name: str) -> dict:
        """Kill an agent via kill-agent.sh."""
        script = SCRIPTS_DIR / "kill-agent.sh"
        if not script.exists():
            return {"success": False, "message": f"kill-agent.sh not found at {script}"}

        try:
            result = subprocess.run(
                ["bash", str(script), name],
                capture_output=True, text=True, timeout=15,
                cwd=str(SCRIPTS_DIR.parent.parent)
            )
            if self._event_bus:
                await self._event_bus.publish(WSEventType.AGENT_STATUS_CHANGE, {
                    "agent": name, "status": "stopped", "previous": "working", "action": "killed"
                })
                await self._event_bus.publish(WSEventType.TOAST, {
                    "message": f"Agent '{name}' killed", "type": "warning"
                })
            return {
                "success": result.returncode == 0,
                "message": result.stdout.strip() or result.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "kill-agent.sh timed out"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def retry_agent(self, name: str) -> dict:
        """Retry a failed agent via retry-agent.sh."""
        script = SCRIPTS_DIR / "retry-agent.sh"
        if not script.exists():
            return {"success": False, "message": f"retry-agent.sh not found at {script}"}

        try:
            result = subprocess.run(
                ["bash", str(script), name],
                capture_output=True, text=True, timeout=30,
                cwd=str(SCRIPTS_DIR.parent.parent)
            )
            if self._event_bus:
                await self._event_bus.publish(WSEventType.TOAST, {
                    "message": f"Agent '{name}' retrying", "type": "info"
                })
            return {
                "success": result.returncode == 0,
                "message": result.stdout.strip() or result.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "retry-agent.sh timed out"}
        except Exception as e:
            return {"success": False, "message": str(e)}
