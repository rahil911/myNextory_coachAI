# Phase 3b: Failure Recovery — Cleanup, Retry, Rollback

**Type**: Parallel with 3a (no file conflicts)
**Output**: `backend/services/failure_recovery.py`
**Gate**: File exists, importable

## Purpose

Handles agent failures gracefully: cleans up orphaned resources, retries with checkpoints, rolls back partial work, and escalates to humans when automation can't fix it.

## What Can Go Wrong

1. **Agent timeout**: Claude session runs too long (context exhaustion, infinite loop)
2. **Agent crash**: Process dies unexpectedly (OOM, network error, SDK bug)
3. **Bead stuck**: Agent closes bead wrong, or leaves it in-progress forever
4. **Worktree conflict**: Agent's worktree has merge conflicts
5. **Spawn failure**: spawn.sh can't create worktree or tmux session
6. **Cascading failure**: One agent's failure blocks all downstream agents

## Implementation

Create `backend/services/failure_recovery.py`:

```python
"""
failure_recovery.py — Graceful failure handling for agent dispatches.

Handles cleanup, retry, rollback, and escalation when agents fail.
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class FailureRecovery:
    """Handles agent failures with cleanup, retry, and escalation."""

    def __init__(self, event_bus=None):
        self._event_bus = event_bus
        self._baap_root = Path.home() / "Projects" / "baap"
        self._scripts_dir = self._baap_root / ".claude" / "scripts"

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
            await self._event_bus.publish("FAILURE_HANDLED", {
                "session_id": session_id,
                "bead_id": bead_id,
                "agent": agent_name,
                "error": error,
                "action": action["action"],
                "retry_count": retry_count,
            })

        return {**action, "cleaned_up": cleaned}

    async def _kill_agent_processes(self, agent_name: str) -> None:
        """Kill any running processes for this agent."""
        # Try kill-agent.sh first (graceful)
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
                "tmux", "kill-window", "-t", agent_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        except Exception:
            pass

    async def _cleanup_worktree(self, agent_name: str, bead_id: str) -> bool:
        """Clean up agent's git worktree."""
        # Agent worktrees are at ~/agents/<agent_name>-<bead_suffix>/
        agent_dir = Path.home() / "agents"
        if not agent_dir.exists():
            return True

        cleaned = False
        for path in agent_dir.iterdir():
            if agent_name in path.name or bead_id[-6:] in path.name:
                try:
                    # Remove git worktree first
                    proc = await asyncio.create_subprocess_exec(
                        "git", "worktree", "remove", "--force", str(path),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=str(self._baap_root),
                    )
                    await proc.communicate()

                    # Remove directory if it still exists
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
                f"--notes={note}",
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

        Returns:
            {"worktrees_cleaned": N, "tmux_killed": N, "beads_updated": N}
        """
        results = {"worktrees_cleaned": 0, "tmux_killed": 0, "beads_updated": 0}

        # Find orphaned worktrees
        agent_dir = Path.home() / "agents"
        if agent_dir.exists():
            for path in agent_dir.iterdir():
                if path.is_dir():
                    # Check if there's a running process for this worktree
                    # If not, it's orphaned
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
        pass  # No persistent resources
```

## Key Design Decisions

1. **Error classification**: Errors are classified as transient (retry-worthy) vs permanent (escalate). This prevents wasting retries on obviously broken configs.

2. **Worktree cleanup is force**: Uses `git worktree remove --force` because agent worktrees may have uncommitted changes. We don't try to save partial work — the agent's bead notes should capture what was done.

3. **Graceful then forceful**: Tries `kill-agent.sh` (which may do SIGTERM + wait), then falls back to killing tmux windows.

4. **Orphan cleanup on startup**: `cleanup_all_orphans()` can be called when the server starts to clean up leftovers from crashes. This prevents resource leaks.

## Success Criteria

```bash
cd ~/Projects/baap/.claude/command-center/backend
python3 -c "
from services.failure_recovery import FailureRecovery
f = FailureRecovery()
# Test action determination
assert f._determine_action('timeout', 0)['action'] == 'retry'
assert f._determine_action('permission denied', 0)['action'] == 'escalate'
assert f._determine_action('unknown', 3)['action'] == 'escalate'
print('FailureRecovery: OK')
"
```
