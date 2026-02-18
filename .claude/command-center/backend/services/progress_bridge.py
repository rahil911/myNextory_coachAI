"""
progress_bridge.py — Real-time agent progress streaming to UI.

Monitors heartbeat files, tmux sessions, and bead notes to stream
detailed agent progress back to the Command Center frontend.
"""

import asyncio
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

HEARTBEAT_DIR = Path("/tmp/baap-heartbeats")
HEARTBEAT_STALE_SECONDS = 60


class ProgressBridge:
    """Streams real-time agent progress to the UI."""

    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._baap_root = Path.home() / "Projects" / "baap"
        self._monitored_agents: dict[str, dict] = {}  # agent_name -> config
        self._monitor_task: asyncio.Task | None = None

    async def start_monitoring(self, agents: list[dict]) -> None:
        """Start monitoring a set of agents.

        Args:
            agents: [{name: str, bead_id: str, session_id: str}, ...]
        """
        for agent in agents:
            self._monitored_agents[agent["name"]] = agent

        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def _monitor_loop(self) -> None:
        """Main monitoring loop — polls agent status every few seconds."""
        while self._monitored_agents:
            try:
                for agent_name, config in list(self._monitored_agents.items()):
                    status = await self._get_agent_status(agent_name)

                    if self._event_bus and status:
                        try:
                            from models import WSEventType
                            await self._event_bus.publish(WSEventType.AGENT_PROGRESS, {
                                "session_id": config.get("session_id"),
                                "bead_id": config.get("bead_id"),
                                "agent": agent_name,
                                **status,
                            })
                        except (ValueError, KeyError):
                            pass  # Event type not registered yet

                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Progress monitor error: {e}")
                await asyncio.sleep(10)

    async def _get_agent_status(self, agent_name: str) -> dict | None:
        """Get detailed status for a single agent."""
        status = {
            "alive": False,
            "heartbeat_age": None,
            "tmux_active": False,
            "last_activity": None,
        }

        # Check heartbeat file
        heartbeat_info = self._check_heartbeat(agent_name)
        if heartbeat_info:
            status.update(heartbeat_info)

        # Check tmux session
        tmux_info = await self._check_tmux(agent_name)
        if tmux_info:
            status.update(tmux_info)

        # Check bead notes for progress markers
        bead_id = self._monitored_agents.get(agent_name, {}).get("bead_id")
        if bead_id:
            bead_info = await self._check_bead_progress(bead_id)
            if bead_info:
                status.update(bead_info)

        return status

    def _check_heartbeat(self, agent_name: str) -> dict | None:
        """Check agent heartbeat file for liveness."""
        hb_file = HEARTBEAT_DIR / agent_name
        if hb_file.exists():
            try:
                last_hb = float(hb_file.read_text().strip())
                age = time.time() - last_hb
                return {
                    "alive": age < HEARTBEAT_STALE_SECONDS,
                    "heartbeat_age": int(age),
                    "heartbeat_stale": age >= HEARTBEAT_STALE_SECONDS,
                }
            except (ValueError, OSError):
                pass

        return None

    async def _check_tmux(self, agent_name: str) -> dict | None:
        """Check if agent has an active tmux window."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux", "list-windows", "-t", "agents", "-F", "#{window_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if proc.returncode != 0:
                return None

            for line in stdout.decode().splitlines():
                if agent_name in line:
                    return {
                        "tmux_active": True,
                        "tmux_window": line.strip(),
                    }

        except Exception:
            pass

        return {"tmux_active": False}

    async def _check_bead_progress(self, bead_id: str) -> dict | None:
        """Check bead for progress notes."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "bd", "show", bead_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._baap_root),
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()

            progress = None
            status = "open"

            status_match = re.search(r'Status:\s*(\w+)', output, re.IGNORECASE)
            if status_match:
                status = status_match.group(1).lower()

            progress_match = re.search(r'(\d+)%', output)
            if progress_match:
                progress = int(progress_match.group(1))

            return {
                "bead_status": status,
                "progress_percent": progress,
            }

        except Exception:
            return None

    def remove_agent(self, agent_name: str) -> None:
        """Stop monitoring an agent."""
        self._monitored_agents.pop(agent_name, None)

    def stop(self) -> None:
        """Stop all monitoring."""
        self._monitored_agents.clear()
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()

    async def cleanup(self) -> None:
        """Clean up resources."""
        self.stop()
