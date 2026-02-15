#!/usr/bin/env bash
# retry-agent.sh -- Retry a failed/timed-out agent with checkpoint context
#
# Usage:
#   retry-agent.sh <worktree_path> [--force-fresh]
#
# Behavior:
#   1. Reads the agent's exit code to determine failure mode
#   2. Finds the latest checkpoint from memory file and bead notes
#   3. Decides: --resume (timeout) vs fresh-with-context (error/kill)
#   4. Launches retry in the same worktree
#
# Exit code interpretation:
#   124 = timeout (coreutils timeout, or Claude context limit)
#     1 = error (Claude or tool failure)
#   137 = killed (SIGKILL, OOM, manual kill)
#     0 = success (should not need retry)
set -euo pipefail

WORKTREE="${1:?Usage: retry-agent.sh <worktree_path> [--force-fresh]}"
FORCE_FRESH="${2:-}"
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
MAX_RETRIES=2
CHECKPOINT_MAX_AGE_SECONDS=7200  # 2 hours

# -- Validate ----------------------------------------------------------------
if [ ! -d "$WORKTREE" ]; then
  echo "Error: Worktree not found at $WORKTREE" >&2
  exit 1
fi

# -- Read agent metadata -----------------------------------------------------
EXIT_CODE="$(cat "$WORKTREE/.agent_exit_code" 2>/dev/null || echo "unknown")"
BEAD_ID="$(cat "$WORKTREE/.agent_bead_id" 2>/dev/null || echo "")"
ORIGINAL_PROMPT="$(cat "$WORKTREE/.agent_original_prompt" 2>/dev/null || echo "")"
AGENT_TYPE="$(cat "$WORKTREE/.agent_type" 2>/dev/null || echo "reactive")"
RETRY_COUNT="$(cat "$WORKTREE/.agent_retry_count" 2>/dev/null || echo "0")"

if [ "$EXIT_CODE" = "0" ]; then
  echo "Agent exited successfully (exit 0). No retry needed."
  exit 0
fi

if [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
  echo "Error: Agent has already been retried $RETRY_COUNT times (max $MAX_RETRIES)." >&2
  echo "Manual intervention required. Worktree: $WORKTREE" >&2
  if [ -n "$BEAD_ID" ]; then
    bd update "$BEAD_ID" --notes="RETRY EXHAUSTED after $RETRY_COUNT attempts. Exit code: $EXIT_CODE. Manual intervention required." 2>/dev/null || true
  fi
  exit 1
fi

echo "=== RETRY AGENT ==="
echo "Worktree:      $WORKTREE"
echo "Exit code:     $EXIT_CODE"
echo "Bead:          ${BEAD_ID:-none}"
echo "Retry attempt: $((RETRY_COUNT + 1)) of $MAX_RETRIES"
echo ""

# -- Find latest checkpoint --------------------------------------------------
CHECKPOINT=""
CHECKPOINT_STALE=false

# Search for memory files with checkpoints
MEMORY_FILE=""
for f in "$WORKTREE"/.claude/agents/*/memory/MEMORY.md; do
  if [ -f "$f" ]; then
    MEMORY_FILE="$f"
    break
  fi
done

if [ -n "$MEMORY_FILE" ]; then
  # Extract the checkpoint block (everything from "## Checkpoint" to the next "##" or EOF)
  CHECKPOINT="$(awk '/^## Checkpoint /{found=1} found{print} /^## [^C]/{if(found) exit}' "$MEMORY_FILE" 2>/dev/null || echo "")"

  if [ -n "$CHECKPOINT" ]; then
    # Extract timestamp from checkpoint header
    CHECKPOINT_TS="$(echo "$CHECKPOINT" | head -1 | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}' || echo "")"

    if [ -n "$CHECKPOINT_TS" ]; then
      CHECKPOINT_EPOCH="$(date -d "$CHECKPOINT_TS" +%s 2>/dev/null || date -j -f "%Y-%m-%d %H:%M:%S" "$CHECKPOINT_TS" +%s 2>/dev/null || echo "0")"
      NOW_EPOCH="$(date +%s)"
      AGE=$(( NOW_EPOCH - CHECKPOINT_EPOCH ))

      if [ "$AGE" -gt "$CHECKPOINT_MAX_AGE_SECONDS" ]; then
        echo "WARNING: Checkpoint is ${AGE}s old (max ${CHECKPOINT_MAX_AGE_SECONDS}s). Marking as stale."
        CHECKPOINT_STALE=true
      else
        echo "Found checkpoint (${AGE}s ago):"
        echo "$CHECKPOINT" | head -5
        echo "  ..."
      fi
    fi
  fi
fi

# Also grab bead notes as fallback/supplement
BEAD_NOTES=""
if [ -n "$BEAD_ID" ]; then
  BEAD_NOTES="$(bd show "$BEAD_ID" 2>/dev/null | grep -A 100 "Notes:" | tail -n +2 || echo "")"
fi

# -- Decide: resume vs fresh -------------------------------------------------
USE_RESUME=false
SESSION_ID=""

if [ "$FORCE_FRESH" = "--force-fresh" ]; then
  echo "Decision: FRESH session (--force-fresh flag)"
elif [ "$EXIT_CODE" = "124" ] && [ -n "$CHECKPOINT" ] && [ "$CHECKPOINT_STALE" = "false" ]; then
  # Timeout with valid checkpoint -- try resume first
  # Look for session ID in the worktree
  SESSION_ID="$(ls -t "$WORKTREE/.claude/sessions/" 2>/dev/null | head -1 | sed 's/\.json$//' || echo "")"
  if [ -n "$SESSION_ID" ]; then
    USE_RESUME=true
    echo "Decision: RESUME session $SESSION_ID (timeout with valid checkpoint)"
  else
    echo "Decision: FRESH session (timeout, but no session ID found)"
  fi
elif [ "$EXIT_CODE" = "1" ]; then
  echo "Decision: FRESH session (agent error, checkpoint as context)"
elif [ "$EXIT_CODE" = "137" ]; then
  echo "Decision: FRESH session (agent killed, checkpoint may be stale)"
  CHECKPOINT_STALE=true
else
  echo "Decision: FRESH session (unknown exit code: $EXIT_CODE)"
fi

echo ""

# -- Build retry prompt -------------------------------------------------------
RETRY_PROMPT=""

if [ -n "$CHECKPOINT" ] && [ "$CHECKPOINT_STALE" = "false" ]; then
  RETRY_PROMPT="$(cat <<PROMPT_EOF
CHECKPOINT CONTEXT -- You are retrying a previous session that did not complete.

Previous session exit reason: $(
  case "$EXIT_CODE" in
    124) echo "Timed out (context window limit or wall-clock timeout)" ;;
    1)   echo "Error during execution" ;;
    137) echo "Process was killed (SIGKILL)" ;;
    *)   echo "Unknown (exit code $EXIT_CODE)" ;;
  esac
)

Here is the last checkpoint from the previous session:

$CHECKPOINT

$([ -n "$BEAD_NOTES" ] && echo "Bead notes from previous session:
$BEAD_NOTES" || true)

CRITICAL INSTRUCTIONS FOR THIS RETRY:
1. Do NOT redo work listed under "Completed" -- those changes are already committed in this worktree.
2. Verify completed work briefly (check files exist, look reasonable) but do not re-implement.
3. Start from the "Next" items in the checkpoint.
4. Continue writing checkpoints as you make progress.
5. If checkpoint data seems inconsistent with actual file state, trust the files -- they are the source of truth.

Original task: $ORIGINAL_PROMPT
PROMPT_EOF
)"
elif [ -n "$ORIGINAL_PROMPT" ]; then
  # No usable checkpoint -- restart with original prompt + warning
  RETRY_PROMPT="$(cat <<PROMPT_EOF
RETRY CONTEXT -- A previous session attempted this task but did not complete and left no usable checkpoint.

$([ -n "$BEAD_NOTES" ] && echo "Bead notes from previous attempt:
$BEAD_NOTES

" || true)The worktree may contain partial work from the previous attempt. Before starting:
1. Check git log for any commits from the previous session: git log --oneline -10
2. Review the current state of modified files
3. Avoid duplicating work that was already done

Original task: $ORIGINAL_PROMPT
PROMPT_EOF
)"
else
  echo "Error: No original prompt found and no checkpoint. Cannot retry." >&2
  exit 1
fi

# -- Increment retry counter -------------------------------------------------
echo "$((RETRY_COUNT + 1))" > "$WORKTREE/.agent_retry_count"

# -- MCP config ---------------------------------------------------------------
MCP_FLAG=""
if [ -f "$WORKTREE/.mcp.json" ]; then
  MCP_FLAG="--mcp-config .mcp.json"
fi

CHECKPOINT_INSTRUCTION="IMPORTANT: You MUST checkpoint your progress periodically. After completing each major subtask, after every ~15 minutes of work, and before risky operations: (1) Write a structured checkpoint to your memory file (.claude/agents/*/memory/MEMORY.md). (2) Update the bead notes. (3) Commit your work: git add -A && git commit -m \"checkpoint: summary\" --no-verify."

# -- Execute retry ------------------------------------------------------------
cd "$WORKTREE"

if [ "$USE_RESUME" = "true" ] && [ -n "$SESSION_ID" ]; then
  echo "Attempting --resume $SESSION_ID ..."
  # Try resume; if it fails within 30 seconds, fall back to fresh
  timeout 30 claude --resume "$SESSION_ID" -p "Continue from where you left off. $RETRY_PROMPT" --yes \
    --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' $MCP_FLAG \
    --append-system-prompt "$CHECKPOINT_INSTRUCTION" 2>/dev/null
  RESUME_EXIT=$?

  if [ "$RESUME_EXIT" -ne 0 ]; then
    echo ""
    echo "Resume failed (exit $RESUME_EXIT). Falling back to fresh session..."
    USE_RESUME=false
  fi
fi

if [ "$USE_RESUME" = "false" ] || [ -z "$SESSION_ID" ]; then
  echo "Starting fresh session with checkpoint context..."

  # Escape for shell
  ESCAPED_RETRY="${RETRY_PROMPT//\'/\\\'}"
  ESCAPED_CKPT="${CHECKPOINT_INSTRUCTION//\'/\\\'}"

  claude -p "$RETRY_PROMPT" --yes \
    --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' $MCP_FLAG \
    --append-system-prompt "$CHECKPOINT_INSTRUCTION"
  FRESH_EXIT=$?

  echo "$FRESH_EXIT" > "$WORKTREE/.agent_exit_code"

  if [ "$FRESH_EXIT" -ne 0 ] && [ "$((RETRY_COUNT + 1))" -lt "$MAX_RETRIES" ]; then
    echo ""
    echo "Retry also failed (exit $FRESH_EXIT). Run retry-agent.sh again for attempt $((RETRY_COUNT + 2))."
  fi
fi

echo ""
echo "=== RETRY COMPLETE ==="
