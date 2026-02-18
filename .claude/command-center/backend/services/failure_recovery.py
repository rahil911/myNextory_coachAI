"""
failure_recovery.py — Graceful failure handling for agent dispatches.

Handles cleanup, retry, rollback, and escalation when agents fail.
"""

import asyncio
import logging
import shutil
from pathlib import Path

from config import PROJECT_ROOT, SCRIPTS_DIR

logger = logging.getLogger(__name__)


class FailureRecovery:
    """Handles agent failures with cleanup, retry, and escalation."""

    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._baap_root = PROJECT_ROOT
        self._scripts_dir = SCRIPTS_DIR

    async def handle_agent_failure(
        self,
        bead_id: str,
        agent_name: str,
        session_id: str,
        error: str = "",
        retry_count: int = 0,
    ) -> dict:
        """Handle a failed agent.

        Steps:
        1. Kill any remaining processes
        2. Clean up worktree
        3. Update bead status
        4. Determine if retryable
        5. Return action recommendation

        Returns:
            {"action": "retry"|"escalate"|"skip", "reason": "...", "cleaned_up": True}
        """
        logger.warning(f"Handling failure: agent={agent_name} bead={bead_id} error={error}")

        # Step 1: Kill remaining processes
        await self._kill_agent_processes(agent_name)

        # Step 2: Clean up worktree
        cleaned = await self._cleanup_worktree(agent_name, bead_id)

        # Step 3: Update bead with failure info
        await self._update_bead_failure(bead_id, agent_name, error)

        # Step 4: Determine action
        action = self._determine_action(error, retry_count)

        # Step 5: Emit event
        if self._event_bus:
            try:
                from models import WSEventType
                await self._event_bus.publish(WSEventType.FAILURE_HANDLED, {
                    "session_id": session_id,
                    "bead_id": bead_id,
                    "agent": agent_name,
                    "error": error,
                    "action": action["action"],
                    "retry_count": retry_count,
                })
            except (ValueError, KeyError):
                pass  # Event type not registered yet

        return {**action, "cleaned_up": cleaned}

    async def _kill_agent_processes(self, agent_name: str) -> None:
        """Kill any running processes for this agent."""
        kill_script = self._scripts_dir / "kill-agent.sh"
        if kill_script.exists():
            try:
                proc = await asyncio.create_subprocess_exec(
                    "bash", str(kill_script), agent_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self._baap_root),
                )
                await asyncio.wait_for(proc.communicate(), timeout=15)
                return
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"kill-agent.sh failed: {e}")

        # Fallback: kill tmux window
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux", "kill-window", "-t", f"agents:{agent_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        except Exception:
            pass

    async def _cleanup_worktree(self, agent_name: str, bead_id: str) -> bool:
        """Clean up agent's git worktree."""
        agent_dir = Path.home() / "agents"
        if not agent_dir.exists():
            return True

        cleaned = False
        bead_suffix = bead_id[-6:] if len(bead_id) >= 6 else bead_id
        for path in agent_dir.iterdir():
            if agent_name in path.name or bead_suffix in path.name:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "git", "worktree", "remove", "--force", str(path),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=str(self._baap_root),
                    )
                    await proc.communicate()

                    if path.exists():
                        shutil.rmtree(path, ignore_errors=True)

                    cleaned = True
                    logger.info(f"Cleaned worktree: {path}")
                except Exception as e:
                    logger.warning(f"Failed to clean worktree {path}: {e}")

        return cleaned

    async def _update_bead_failure(self, bead_id: str, agent_name: str, error: str) -> None:
        """Update bead with failure information."""
        note = f"Agent {agent_name} failed: {error or 'unknown error'}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "bd", "update", bead_id,
                f"--append-notes={note}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._baap_root),
            )
            await proc.communicate()
        except Exception as e:
            logger.warning(f"Failed to update bead {bead_id}: {e}")

    def _determine_action(self, error: str, retry_count: int) -> dict:
        """Determine what to do about a failure."""
        error_lower = (error or "").lower()

        # Non-retryable errors
        if any(kw in error_lower for kw in [
            "permission denied", "file not found", "invalid config",
            "schema error", "import error",
        ]):
            return {
                "action": "escalate",
                "reason": f"Non-retryable error: {error}",
            }

        # Likely transient errors (retry-worthy)
        if any(kw in error_lower for kw in [
            "timeout", "connection", "rate limit", "503", "502",
            "context window", "oom",
        ]):
            if retry_count < 2:
                return {
                    "action": "retry",
                    "reason": f"Transient error, retrying (attempt {retry_count + 1})",
                }

        # Max retries exceeded
        if retry_count >= 2:
            return {
                "action": "escalate",
                "reason": f"Max retries ({retry_count}) exhausted",
            }

        # Default: retry once more
        return {
            "action": "retry",
            "reason": "Unknown error, will retry once",
        }

    async def cleanup_all_orphans(self) -> dict:
        """Find and clean up orphaned agent resources.

        Useful on startup or after server crash.
        """
        results = {"worktrees_cleaned": 0, "tmux_killed": 0, "beads_updated": 0}

        agent_dir = Path.home() / "agents"
        if agent_dir.exists():
            for path in agent_dir.iterdir():
                if path.is_dir():
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "git", "worktree", "remove", "--force", str(path),
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            cwd=str(self._baap_root),
                        )
                        await proc.communicate()
                        if path.exists():
                            shutil.rmtree(path, ignore_errors=True)
                        results["worktrees_cleaned"] += 1
                    except Exception:
                        pass

        logger.info(f"Orphan cleanup: {results}")
        return results

    async def cleanup(self) -> None:
        """Clean up resources."""
        pass
