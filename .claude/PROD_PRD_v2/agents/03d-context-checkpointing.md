# 03d -- Context Window Checkpointing

## Purpose

Claude Code agents running in git worktrees on the India compute machine hit context window limits and time out on long investigations. When `retry-agent.sh` re-spawns them, they start from scratch -- repeating work, re-reading files, re-running queries, and potentially making different decisions the second time. This wastes tokens, wastes wall-clock time, and produces inconsistent results.

Context checkpointing solves this by making agent progress durable. Agents write structured checkpoints to two locations (their memory file and the bead notes), commit in-progress work on every checkpoint, and when retried, get a focused prompt that tells them exactly where they left off and what not to redo.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Checkpoint overhead slows agents | Medium | Cap at 4 checkpoints per session. Each is a single file write + bead update + git commit -- under 5 seconds total. |
| Stale checkpoint misleads retry | High | Timestamp every checkpoint. In retry logic, discard checkpoints older than 2 hours. On SIGKILL (exit 137), mark checkpoint as `potentially_stale`. |
| `--resume` silently drops context | Medium | Always fall back to fresh-session-with-checkpoint if `--resume` exits non-zero within 30 seconds (indicates session corruption). |
| Git commit conflicts in worktree | Low | Commits use `--no-verify` and go to the agent's own branch. No merge conflicts possible until cleanup.sh runs. |
| Memory file grows unbounded | Low | Each checkpoint overwrites the previous one (not append). Only the latest checkpoint matters. |
| Bead notes get cluttered | Low | Use a single `## Agent Checkpoint` section that gets replaced on each update, not appended. |

## Files

| File | Change | Purpose |
|------|--------|---------|
| `.claude/scripts/spawn.sh` | Modify | Inject checkpoint instruction via `--append-system-prompt` |
| `.claude/scripts/retry-agent.sh` | **Create** | New script: read checkpoint, decide resume vs fresh, retry with context |
| `.claude/scripts/checkpoint.sh` | **Create** | Helper: commit worktree progress + update bead notes from memory file |
| `.claude/CLAUDE.md` | Modify | Add checkpoint protocol section for all agents |
| `.claude/CLAUDE.md` | Modify | Document retry and checkpoint workflows |

## Fixes

### 1. Checkpoint Protocol in CLAUDE.md

Add to the end of `.claude/CLAUDE.md`, before the `## Getting Started` section:

```markdown
---

## Checkpoint Protocol

**MANDATORY**: Every agent MUST checkpoint progress to survive context window limits and session timeouts.

### When to Checkpoint

Checkpoint after each of these events:
- Completing a major subtask (finished a function, created a file, resolved an issue)
- Reaching a natural break point (moving from investigation to recommendation)
- Every ~15 minutes of continuous work (set a mental timer)
- Before starting a risky or expensive operation (large refactor, bulk API calls)

### How to Checkpoint

Write a checkpoint block to your memory file at `.claude/agents/{your-agent-name}/memory/MEMORY.md`:

```
## Checkpoint {YYYY-MM-DD HH:MM:SS}
- **Bead**: {bead_id}
- **Status**: {in_progress|blocked|nearly_done}
- **Completed**:
  - {what you finished, be specific}
  - {include key findings/decisions}
- **Next**:
  - {what remains to be done}
  - {in priority order}
- **Files modified**:
  - {path/to/file1.py} - {what changed}
  - {path/to/file2.ts} - {what changed}
- **Decisions made**:
  - {decision}: {reasoning}
- **Key data**:
  - {any values/results the next session needs to know}
```

Then update the bead with a condensed version:

```bash
bd update {bead_id} --notes="Checkpoint: {one-line summary}. Completed: {list}. Next: {list}. Files: {list}."
```

Then commit your in-progress work:

```bash
cd {worktree_path}
git add -A
git commit -m "checkpoint: {summary}" --no-verify
```

### On Session Start (Retry Recovery)

If your prompt includes a `CHECKPOINT CONTEXT` section, you are a retry of a previous session. Follow these rules:
1. **Read the checkpoint carefully** -- it tells you what was already done
2. **Do NOT redo completed work** -- the files are already modified and committed
3. **Verify the checkpoint** -- quickly check that mentioned files exist and look correct
4. **Continue from "Next"** -- pick up exactly where the previous session left off
5. **Write your own checkpoint** after making progress -- the chain continues
```

### 2. spawn.sh Modifications

Replace the entire `spawn.sh`:

```bash
#!/usr/bin/env bash
# spawn.sh -- Spawn a Claude agent in an isolated git worktree + tmux window
#
# Usage:
#   spawn.sh <type> <prompt> [project_path] [--bead BEAD_ID]
#
# Types:
#   reactive   -- User-triggered investigation (stays open for interaction)
#   proactive  -- Scheduled task (auto-cleanup on completion)
#   team       -- Agent team with parallel teammates
#
# Examples:
#   spawn.sh reactive "Investigate ROAS breach" ~/Projects/my-repo --bead BC-a7x
#   spawn.sh proactive "Run health check" ~/Projects/my-repo
set -euo pipefail

TYPE="${1:?Usage: spawn.sh <reactive|proactive|team> <prompt> [project_path] [--bead BEAD_ID]}"
PROMPT="${2:?Missing prompt}"
PROJECT="${3:-$(pwd)}"
BEAD_ID=""

# Parse optional flags
shift 3 2>/dev/null || shift $#
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bead) BEAD_ID="$2"; shift 2 ;;
    *) shift ;;
  esac
done

AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
TMUX_SESSION="${AGENT_TMUX_SESSION:-agents}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
NAME="${TYPE}-${TIMESTAMP}"
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"

# -- Validate ----------------------------------------------------------------
if [ ! -d "$PROJECT/.git" ]; then
  echo "Error: $PROJECT is not a git repo" >&2
  exit 1
fi

# -- Ensure tmux session exists ----------------------------------------------
if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
  tmux new-session -d -s "$TMUX_SESSION" -n "monitor"
  echo "Created tmux session: $TMUX_SESSION"
fi

# -- Create git worktree ----------------------------------------------------
mkdir -p "$AGENT_DIR"
cd "$PROJECT"
git worktree add "$AGENT_DIR/$NAME" -b "agent/$NAME" 2>/dev/null || {
  git worktree add "$AGENT_DIR/$NAME" "agent/$NAME" 2>/dev/null || {
    echo "Error: Failed to create worktree at $AGENT_DIR/$NAME" >&2
    exit 1
  }
}
echo "Created worktree: $AGENT_DIR/$NAME (branch: agent/$NAME)"

# -- Checkpoint system prompt injection --------------------------------------
CHECKPOINT_INSTRUCTION="IMPORTANT: You MUST checkpoint your progress periodically. After completing each major subtask, after every ~15 minutes of work, and before risky operations: (1) Write a structured checkpoint to your memory file (.claude/agents/*/memory/MEMORY.md) with Completed/Next/Files/Decisions sections. (2) Update the bead notes with a condensed version: bd update BEAD_ID --notes=\"Checkpoint: summary\". (3) Commit your work: git add -A && git commit -m \"checkpoint: summary\" --no-verify. This ensures your progress survives if the session times out or hits context limits."

if [ -n "$BEAD_ID" ]; then
  CHECKPOINT_INSTRUCTION="You are working on bead $BEAD_ID. $CHECKPOINT_INSTRUCTION"
fi

# -- Build Claude command ----------------------------------------------------
CLAUDE_CMD="cd $AGENT_DIR/$NAME"

# MCP config (use project's if exists)
if [ -f "$AGENT_DIR/$NAME/.mcp.json" ]; then
  MCP_FLAG="--mcp-config .mcp.json"
else
  MCP_FLAG=""
fi

# Escape prompt for shell embedding
ESCAPED_PROMPT="${PROMPT//\'/\\\'}"
ESCAPED_CHECKPOINT="${CHECKPOINT_INSTRUCTION//\'/\\\'}"

case "$TYPE" in
  reactive)
    CLAUDE_CMD="$CLAUDE_CMD && claude -p '$ESCAPED_PROMPT' --yes --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' $MCP_FLAG --append-system-prompt '$ESCAPED_CHECKPOINT'"
    CLAUDE_CMD="$CLAUDE_CMD; EXIT_CODE=\$?; echo ''; echo '=== AGENT DONE (exit \$EXIT_CODE) ==='"
    # Store exit code and metadata for retry-agent.sh
    CLAUDE_CMD="$CLAUDE_CMD; echo \"\$EXIT_CODE\" > $AGENT_DIR/$NAME/.agent_exit_code"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$BEAD_ID' > $AGENT_DIR/$NAME/.agent_bead_id"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$ESCAPED_PROMPT' > $AGENT_DIR/$NAME/.agent_original_prompt"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$TYPE' > $AGENT_DIR/$NAME/.agent_type"
    CLAUDE_CMD="$CLAUDE_CMD; echo 'Type next prompt or press Ctrl+D to exit'; claude --continue --yes"
    ;;
  proactive)
    CLAUDE_CMD="$CLAUDE_CMD && claude -p '$ESCAPED_PROMPT' --yes --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' $MCP_FLAG --output-format text --append-system-prompt '$ESCAPED_CHECKPOINT'"
    CLAUDE_CMD="$CLAUDE_CMD; EXIT_CODE=\$?; echo \"\$EXIT_CODE\" > $AGENT_DIR/$NAME/.agent_exit_code"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$BEAD_ID' > $AGENT_DIR/$NAME/.agent_bead_id"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$ESCAPED_PROMPT' > $AGENT_DIR/$NAME/.agent_original_prompt"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$TYPE' > $AGENT_DIR/$NAME/.agent_type"
    # Auto-retry if timed out with checkpoint
    CLAUDE_CMD="$CLAUDE_CMD; if [ \"\$EXIT_CODE\" = '124' ] && [ -f '.claude/agents/*/memory/MEMORY.md' ]; then echo '=== TIMEOUT WITH CHECKPOINT -- AUTO-RETRYING ==='; $SCRIPTS_DIR/retry-agent.sh $AGENT_DIR/$NAME; fi"
    CLAUDE_CMD="$CLAUDE_CMD && echo '=== AUTO-CLEANUP ===' && cd $PROJECT && git add $AGENT_DIR/$NAME && git stash 2>/dev/null; true"
    ;;
  team)
    CLAUDE_CMD="$CLAUDE_CMD && CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 claude -p '$ESCAPED_PROMPT' --yes --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' $MCP_FLAG --teammate-mode tmux --append-system-prompt '$ESCAPED_CHECKPOINT'"
    CLAUDE_CMD="$CLAUDE_CMD; EXIT_CODE=\$?; echo \"\$EXIT_CODE\" > $AGENT_DIR/$NAME/.agent_exit_code"
    CLAUDE_CMD="$CLAUDE_CMD; echo ''; echo '=== TEAM DONE (exit \$EXIT_CODE) === Press enter to close'; read"
    ;;
  *)
    echo "Error: Unknown type '$TYPE'. Use: reactive, proactive, team" >&2
    exit 1
    ;;
esac

# -- Launch in tmux ----------------------------------------------------------
tmux new-window -t "$TMUX_SESSION" -n "$NAME" "$CLAUDE_CMD"
echo "Launched agent: $NAME (tmux window in session '$TMUX_SESSION')"
echo ""
echo "Monitor:  tmux attach -t $TMUX_SESSION"
echo "Retry:    $(dirname "$0")/retry-agent.sh $AGENT_DIR/$NAME"
echo "Cleanup:  $(dirname "$0")/cleanup.sh $NAME merge"
```

### 3. retry-agent.sh (New Script)

Create `.claude/scripts/retry-agent.sh`:

```bash
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
```

### 4. checkpoint.sh (New Helper Script)

Create `.claude/scripts/checkpoint.sh`:

```bash
#!/usr/bin/env bash
# checkpoint.sh -- Commit worktree progress and update bead notes
#
# Usage:
#   checkpoint.sh <worktree_path> <summary> [bead_id]
#
# Called by agents via Bash tool, or manually.
# Performs: git add + commit + bead update in one atomic operation.
set -euo pipefail

WORKTREE="${1:?Usage: checkpoint.sh <worktree_path> <summary> [bead_id]}"
SUMMARY="${2:?Missing checkpoint summary}"
BEAD_ID="${3:-}"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

# -- Validate ----------------------------------------------------------------
if [ ! -d "$WORKTREE/.git" ] && [ ! -f "$WORKTREE/.git" ]; then
  echo "Error: $WORKTREE is not a git worktree" >&2
  exit 1
fi

cd "$WORKTREE"

# -- Git commit ---------------------------------------------------------------
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  git add -A
  git commit -m "checkpoint: $SUMMARY" --no-verify 2>/dev/null || {
    echo "Warning: git commit failed (possibly nothing to commit)" >&2
  }
  echo "Committed checkpoint: $SUMMARY"
else
  echo "No changes to commit."
fi

# -- Update bead notes --------------------------------------------------------
if [ -n "$BEAD_ID" ]; then
  bd update "$BEAD_ID" --notes="Checkpoint [$TIMESTAMP]: $SUMMARY" 2>/dev/null && {
    echo "Updated bead $BEAD_ID with checkpoint."
  } || {
    echo "Warning: Failed to update bead $BEAD_ID" >&2
  }
fi

# -- Report -------------------------------------------------------------------
COMMIT_HASH="$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")"
FILES_CHANGED="$(git diff --name-only HEAD~1 2>/dev/null | wc -l | tr -d ' ')"
echo ""
echo "Checkpoint saved:"
echo "  Time:    $TIMESTAMP"
echo "  Commit:  $COMMIT_HASH"
echo "  Files:   $FILES_CHANGED changed"
echo "  Bead:    ${BEAD_ID:-none}"
echo "  Summary: $SUMMARY"
```

### 5. SKILL.md Additions

Add the following section to `.claude/CLAUDE.md` after the `### 3. Merge Results + Cleanup` section:

```markdown
### 4. Retry a Failed Agent

When an agent times out or errors, retry it with checkpoint context:

```bash
# Retry with automatic resume/fresh decision
bash .claude/scripts/retry-agent.sh ~/agents/reactive-20260210_143000

# Force a fresh session (skip --resume attempt)
bash .claude/scripts/retry-agent.sh ~/agents/reactive-20260210_143000 --force-fresh
```

The retry script:
1. Reads the agent's exit code (124=timeout, 1=error, 137=killed)
2. Finds the latest checkpoint from the agent's memory file
3. For timeouts with valid checkpoints: tries `--resume` first, falls back to fresh
4. For errors: always starts fresh with checkpoint context injected
5. For kills: starts fresh, marks checkpoint as potentially stale
6. Caps at 2 retries per agent to prevent infinite loops

### 5. Manual Checkpoint

Force a checkpoint commit from outside the agent:

```bash
bash .claude/scripts/checkpoint.sh ~/agents/reactive-20260210_143000 "Finished API integration" BC-a7x
```

### Checkpoint Protocol

Agents are instructed (via `--append-system-prompt`) to checkpoint every ~15 minutes. Each checkpoint:
- Writes structured progress to `.claude/agents/{name}/memory/MEMORY.md`
- Updates bead notes with condensed summary
- Commits all in-progress work to the worktree branch

This means even if a session is killed, the git history preserves partial work.
```

### 6. Resume vs Fresh Decision Logic

This table codifies the decision tree implemented in `retry-agent.sh`:

| Exit Code | Meaning | Checkpoint? | Checkpoint Age | Action |
|-----------|---------|-------------|----------------|--------|
| 0 | Success | N/A | N/A | No retry needed |
| 124 | Timeout | Yes, valid | < 2 hours | Try `--resume SESSION_ID` first. If resume fails within 30s, fall back to fresh with checkpoint context. |
| 124 | Timeout | Yes, stale | > 2 hours | Fresh session. Include stale checkpoint with warning: "verify before relying on this." |
| 124 | Timeout | No | N/A | Fresh session with original prompt. Agent checks git log for partial work. |
| 1 | Error | Yes, valid | < 2 hours | Fresh session with checkpoint context. Never resume -- the error may be in session state. |
| 1 | Error | No | N/A | Fresh session with original prompt + "previous attempt errored" warning. |
| 137 | Killed | Any | Any | Fresh session. Mark any checkpoint as `potentially_stale`. Agent must verify file state before trusting checkpoint. |
| Other | Unknown | Any | Any | Fresh session. Same as exit 1 handling. |

### 7. Why `--resume` is Timeout-Only

Claude Code's `--resume SESSION_ID` loads the full conversation history from the previous session. This is ideal for timeouts because:

- The conversation was coherent up to the point it stopped
- The context window was the limiting factor, not an error
- Resume gives Claude the full prior context without re-explaining

But resume is **dangerous for errors** because:
- The error state may be encoded in the conversation (bad tool output, wrong assumption)
- Resuming replays that error context, potentially causing the same mistake
- A fresh session with just the checkpoint summary avoids poisoning the context

And resume is **unreliable after SIGKILL** because:
- The session file may be partially written (corrupted JSON)
- The checkpoint may not reflect the true final state
- Better to start fresh and verify file state

## Success Criteria

1. **Checkpoint written**: After any agent session longer than 10 minutes, `MEMORY.md` contains a valid `## Checkpoint` block with timestamp, Completed, Next, and Files sections.

2. **Bead updated**: The corresponding bead's notes contain a condensed checkpoint summary matching the memory file.

3. **Git commit on checkpoint**: Every checkpoint produces a git commit on the agent's worktree branch with message prefix `checkpoint:`.

4. **Retry uses context**: When `retry-agent.sh` retries an agent that has a checkpoint, the retry prompt includes the full checkpoint content and the agent does not redo completed work.

5. **Resume attempted on timeout**: When exit code is 124 and a valid checkpoint exists, the retry script attempts `--resume` before falling back to fresh.

6. **Stale checkpoints flagged**: Checkpoints older than 2 hours are marked stale and the retry prompt warns the agent to verify file state.

7. **Retry cap enforced**: No agent is retried more than 2 times. After exhausting retries, the bead is updated with `RETRY EXHAUSTED` and the script exits with error.

8. **Metadata files written**: After every agent session, the worktree contains `.agent_exit_code`, `.agent_bead_id`, `.agent_original_prompt`, and `.agent_type` files for retry-agent.sh to consume.

## Verification

### Manual Test: Checkpoint Write

```bash
# 1. Spawn an agent with a long task
bash .claude/scripts/spawn.sh reactive \
  "Refactor the capsule validator: split validation logic into separate functions for schema, business rules, and approval chain. This is a large task -- checkpoint your progress." \
  ~/Projects/baap --bead TEST-001

# 2. Wait 15+ minutes, then check:
cat ~/agents/reactive-*/. claude/agents/*/memory/MEMORY.md | grep -A 20 "## Checkpoint"
# Expected: Checkpoint block with timestamp, Completed, Next, Files

# 3. Check git log in worktree:
cd ~/agents/reactive-* && git log --oneline -5
# Expected: At least one "checkpoint: ..." commit

# 4. Check bead:
bd show TEST-001
# Expected: Notes contain "Checkpoint:" summary
```

### Manual Test: Retry with Checkpoint

```bash
# 1. Simulate a timeout by killing the agent after it checkpoints:
# (watch the tmux window, wait for a checkpoint commit, then)
tmux send-keys -t agents:reactive-* C-c

# 2. Manually set exit code to 124 (timeout):
echo "124" > ~/agents/reactive-*/.agent_exit_code

# 3. Retry:
bash .claude/scripts/retry-agent.sh ~/agents/reactive-*

# 4. Verify the retry prompt includes checkpoint context:
# (watch the tmux window -- the prompt should start with "CHECKPOINT CONTEXT")

# 5. Verify the agent does NOT redo completed work:
# (compare git log before and after -- no duplicate commits)
```

### Manual Test: Resume Fallback

```bash
# 1. After a timeout retry that uses --resume:
# If resume fails, the script should print:
#   "Resume failed (exit X). Falling back to fresh session..."
# and then start a fresh session with checkpoint context.

# 2. Verify by corrupting the session file:
mv ~/agents/reactive-*/.claude/sessions/*.json ~/agents/reactive-*/.claude/sessions/backup.json
bash .claude/scripts/retry-agent.sh ~/agents/reactive-*
# Expected: Falls back to fresh session gracefully
```

### Automated Verification (run after deployment)

```bash
#!/usr/bin/env bash
# verify-checkpointing.sh -- Verify checkpoint infrastructure is in place
set -euo pipefail

SCRIPTS=".claude/scripts"
ERRORS=0

echo "Verifying checkpoint infrastructure..."

# Check scripts exist and are executable
for script in spawn.sh retry-agent.sh checkpoint.sh; do
  if [ -x "$SCRIPTS/$script" ]; then
    echo "  OK: $script exists and is executable"
  else
    echo "  FAIL: $script missing or not executable"
    ERRORS=$((ERRORS + 1))
  fi
done

# Check spawn.sh injects checkpoint instruction
if grep -q "append-system-prompt" "$SCRIPTS/spawn.sh"; then
  echo "  OK: spawn.sh injects checkpoint system prompt"
else
  echo "  FAIL: spawn.sh missing --append-system-prompt"
  ERRORS=$((ERRORS + 1))
fi

# Check spawn.sh writes metadata files
if grep -q ".agent_exit_code" "$SCRIPTS/spawn.sh"; then
  echo "  OK: spawn.sh writes agent metadata files"
else
  echo "  FAIL: spawn.sh missing metadata file writes"
  ERRORS=$((ERRORS + 1))
fi

# Check retry-agent.sh reads checkpoints
if grep -q "MEMORY.md" "$SCRIPTS/retry-agent.sh"; then
  echo "  OK: retry-agent.sh reads memory checkpoints"
else
  echo "  FAIL: retry-agent.sh missing checkpoint reader"
  ERRORS=$((ERRORS + 1))
fi

# Check retry-agent.sh has resume logic
if grep -q "\-\-resume" "$SCRIPTS/retry-agent.sh"; then
  echo "  OK: retry-agent.sh has --resume logic"
else
  echo "  FAIL: retry-agent.sh missing --resume logic"
  ERRORS=$((ERRORS + 1))
fi

# Check retry cap
if grep -q "MAX_RETRIES" "$SCRIPTS/retry-agent.sh"; then
  echo "  OK: retry-agent.sh has retry cap"
else
  echo "  FAIL: retry-agent.sh missing retry cap"
  ERRORS=$((ERRORS + 1))
fi

# Check CLAUDE.md has checkpoint protocol
CLAUDE_MD="$(git rev-parse --show-toplevel 2>/dev/null)/.claude/CLAUDE.md"
if [ -f "$CLAUDE_MD" ] && grep -q "Checkpoint Protocol" "$CLAUDE_MD"; then
  echo "  OK: CLAUDE.md contains Checkpoint Protocol section"
else
  echo "  FAIL: CLAUDE.md missing Checkpoint Protocol section"
  ERRORS=$((ERRORS + 1))
fi

echo ""
if [ "$ERRORS" -eq 0 ]; then
  echo "All checks passed."
else
  echo "$ERRORS check(s) failed."
  exit 1
fi
```
