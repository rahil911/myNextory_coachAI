# Phase 1f: Agent Retry & Recovery

## Purpose

Agents fail. Claude Code sessions run out of context, hit errors, timeout, or produce
wrong code. Right now there's no automatic recovery — a failed agent leaves a dirty
bead, an abandoned worktree, and blocked downstream work. The orchestrator has to
manually diagnose and re-dispatch.

This spec adds structured failure handling so the system self-heals where possible
and escalates cleanly where it can't.

## Risks Mitigated

- Risk 19: No automatic retry for transient failures (timeout, context exhaustion)
- Risk 20: Failed agent leaves dirty state (beads stuck, worktrees abandoned)
- Risk 21: Orchestrator has no structured failure information to act on

## Files to Create

- `.claude/scripts/retry-agent.sh` — Re-dispatch a failed agent's bead to a fresh session

## Files to Modify

- `.claude/scripts/spawn.sh` — Capture exit code, write failure record
- `.claude/scripts/cleanup.sh` — Handle failed agent cleanup path

---

## Fix 1: Exit Code Capture in spawn.sh

### Problem

When claude's session ends (success, timeout, error), spawn.sh doesn't capture the
exit code. There's no record of whether the agent succeeded or failed.

### Solution

Capture the exit code and write it to the status file:

In spawn.sh, change the tmux launch command to capture exit status:

```bash
tmux new-window -t "$TMUX_SESSION" -n "$NAME" \
  "cd $WORKTREE && export AGENT_NAME=$NAME && export AGENT_LEVEL=$LEVEL && \
   $CLAUDE_CMD 2>&1 | tee $LOG_FILE; \
   EXIT_CODE=\$?; \
   python3 -c \"
import json, datetime
status_file = '/tmp/baap-agent-status/$NAME.json'
try:
    with open(status_file, 'r') as f:
        s = json.load(f)
except:
    s = {}
s['status'] = 'completed' if \$EXIT_CODE == 0 else 'failed'
s['exit_code'] = \$EXIT_CODE
s['finished_at'] = datetime.datetime.now().isoformat()
if \$EXIT_CODE == 124:
    s['failure_reason'] = 'timeout'
elif \$EXIT_CODE != 0:
    s['failure_reason'] = 'error'
with open(status_file, 'w') as f:
    json.dump(s, f, indent=2)
\" 2>/dev/null; \
   echo 'Agent $NAME finished (exit \$EXIT_CODE). Press Enter.'; read"
```

Exit codes to handle:
- 0: Success — agent finished normally
- 124: Timeout — `timeout` command killed it (transient, retry-safe)
- 1: Error — Claude Code hit an error (may or may not be retry-safe)
- 137: SIGKILL — killed by kill-agent.sh (intentional, no retry)

---

## Fix 2: retry-agent.sh

### Purpose

Re-dispatch a failed agent's bead to a fresh Claude Code session.
The old worktree is discarded, a new one is created, and the agent starts over.

### Implementation

```bash
#!/usr/bin/env bash
# retry-agent.sh — Retry a failed agent's work
#
# Usage: retry-agent.sh <agent_name> [max_retries]
#
# What it does:
# 1. Reads the agent's status to find its bead
# 2. Discards the failed worktree
# 3. Re-opens the bead (if it was auto-closed)
# 4. Spawns a fresh agent session with the same bead
# 5. Tracks retry count to prevent infinite loops
set -euo pipefail

AGENT_NAME="${1:?Usage: retry-agent.sh <agent_name> [max_retries]}"
MAX_RETRIES="${2:-3}"

STATUS_DIR="/tmp/baap-agent-status"
STATUS_FILE="$STATUS_DIR/$AGENT_NAME.json"
RETRY_FILE="$STATUS_DIR/$AGENT_NAME.retries"

# ── Check retry count ────────────────────────────────────────────────────────
RETRY_COUNT=0
if [ -f "$RETRY_FILE" ]; then
  RETRY_COUNT=$(cat "$RETRY_FILE")
fi

if [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
  echo "ERROR: Agent $AGENT_NAME has been retried $RETRY_COUNT times (max: $MAX_RETRIES)" >&2
  echo "Escalating to human. Bead remains open for manual intervention." >&2
  exit 1
fi

# ── Read failure info ────────────────────────────────────────────────────────
BEAD_ID=""
LEVEL="1"
if [ -f "$STATUS_FILE" ]; then
  BEAD_ID=$(python3 -c "import json; print(json.load(open('$STATUS_FILE')).get('bead',''))" 2>/dev/null || true)
  LEVEL=$(python3 -c "import json; print(json.load(open('$STATUS_FILE')).get('level',1))" 2>/dev/null || true)
  FAILURE=$(python3 -c "import json; print(json.load(open('$STATUS_FILE')).get('failure_reason','unknown'))" 2>/dev/null || true)
  echo "Retrying $AGENT_NAME (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)"
  echo "Last failure: $FAILURE"
  echo "Bead: $BEAD_ID"
fi

# ── Cleanup old worktree ────────────────────────────────────────────────────
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
if [ -d "$AGENT_DIR/$AGENT_NAME" ]; then
  bash "$(dirname "$0")/cleanup.sh" "$AGENT_NAME" discard
fi

# ── Re-open bead if it was auto-closed ──────────────────────────────────────
if [ -n "$BEAD_ID" ] && command -v bd &>/dev/null; then
  # Check if bead was auto-closed by cleanup.sh
  BEAD_STATUS=$(bd show "$BEAD_ID" --json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)
  if [ "$BEAD_STATUS" = "closed" ]; then
    bd update "$BEAD_ID" --status=open 2>/dev/null || true
    echo "Re-opened bead $BEAD_ID"
  fi
fi

# ── Increment retry count ───────────────────────────────────────────────────
echo "$((RETRY_COUNT + 1))" > "$RETRY_FILE"

# ── Build prompt with retry context ─────────────────────────────────────────
RETRY_PROMPT="bd show $BEAD_ID && work on it"
if [ "$RETRY_COUNT" -gt 0 ]; then
  RETRY_PROMPT="This is retry attempt $((RETRY_COUNT + 1)). Previous attempt failed ($FAILURE). Check the bead notes for context. $RETRY_PROMPT"
fi

# ── Re-spawn ────────────────────────────────────────────────────────────────
MAIN_REPO="$(cd "${AGENT_DIR%/agents}" && git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/Projects/baap")"
bash "$(dirname "$0")/spawn.sh" reactive "$RETRY_PROMPT" "$MAIN_REPO" "$AGENT_NAME" "$LEVEL"

echo "Agent $AGENT_NAME re-spawned (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)"
```

### Usage by orchestrator

```bash
# Agent timed out — retry it
bash .claude/scripts/retry-agent.sh identity-agent

# Agent failed twice, try one more time with higher limit
bash .claude/scripts/retry-agent.sh identity-agent 5

# Check retry status
cat /tmp/baap-agent-status/identity-agent.retries
```

---

## Fix 3: Auto-retry for Timeout in spawn.sh

For timeout exits (exit code 124), spawn.sh can auto-retry once without orchestrator
intervention. This handles the most common transient failure.

Add to spawn.sh, after the tmux launch command:

Actually, this is complex because tmux launches asynchronously. Instead, the orchestrator
should check agent status and call retry-agent.sh when it detects a timeout failure.

Add to the orchestrator's monitoring loop (in CLAUDE.md):

```markdown
### After spawning agents, monitor with:

1. `bash .claude/scripts/monitor.sh` — check status
2. For any agent showing status "failed":
   - If failure_reason is "timeout": `bash .claude/scripts/retry-agent.sh <name>`
   - If failure_reason is "error": review the log first: `tail -50 ~/agents/<name>/agent.log`
   - If retry count >= 3: escalate to human
```

---

## Fix 4: Failure Record in Bead

When an agent fails, add a note to its bead with failure details:

In kill-agent.sh and in the exit code capture (spawn.sh), add:

```bash
if [ -n "$BEAD_ID" ] && command -v bd &>/dev/null; then
  bd update "$BEAD_ID" --notes="FAILED: exit_code=$EXIT_CODE, reason=$FAILURE_REASON, log=~/agents/$NAME/agent.log, retry_count=$RETRY_COUNT" 2>/dev/null || true
fi
```

This gives the orchestrator (or the retried agent) context about what went wrong.

---

## Success Criteria

- [ ] spawn.sh captures exit code and writes to status file
- [ ] Exit code 124 (timeout) identified as "timeout" failure
- [ ] Exit code 0 identified as "completed" success
- [ ] retry-agent.sh created and executable
- [ ] retry-agent.sh discards old worktree, re-opens bead, re-spawns
- [ ] Retry count tracked, max retries enforced (default 3)
- [ ] Exceeded max retries = escalation (not infinite loop)
- [ ] Failure details recorded in bead notes

## Verification

```bash
# Test retry mechanism
# Spawn an agent that will fail quickly
bash .claude/scripts/spawn.sh reactive "exit 1" ~/Projects/baap test-retry 2

sleep 10

# Check status shows failed
cat /tmp/baap-agent-status/test-retry.json | python3 -c "import json,sys; print(json.load(sys.stdin).get('status'))"
# Should print: failed

# Retry it
bash .claude/scripts/retry-agent.sh test-retry

# Check retry count
cat /tmp/baap-agent-status/test-retry.retries
# Should print: 1

# Cleanup
bash .claude/scripts/kill-agent.sh test-retry "test complete"
```
