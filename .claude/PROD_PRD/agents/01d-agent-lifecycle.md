# Phase 1d: Agent Lifecycle — Heartbeat, Cancellation, Memory Bootstrap

## Purpose

Agents need monitoring, graceful shutdown, and guaranteed initial state.
Currently there's no way to detect stuck agents, no way to cleanly kill one,
and first-run agents may crash trying to read nonexistent memory files.

## Risks Mitigated

- Risk 8: No heartbeat / stuck-agent detection (MEDIUM-HIGH)
- Risk 9: No graceful agent cancellation (MEDIUM)
- Risk 12: Agent memory directory may not exist on first run (MEDIUM)

## Files to Create

- `.claude/scripts/heartbeat.sh` — Background heartbeat wrapper
- `.claude/scripts/kill-agent.sh` — Graceful agent cancellation

## Files to Modify

- `.claude/scripts/spawn.sh` — Launch heartbeat alongside agent, bootstrap memory

---

## Fix 1: heartbeat.sh (Risk 8)

### Problem

If an agent freezes (Claude Code session hangs, tmux window stuck), the orchestrator
has no way to detect it. `bd list --status=in_progress` shows the agent is "working"
but it might be dead. The orchestrator waits indefinitely.

### Solution

A background process that writes heartbeats to beads while the agent runs:

```bash
#!/usr/bin/env bash
# heartbeat.sh — Background heartbeat for agent liveness detection
#
# Usage: heartbeat.sh <agent_name> <interval_seconds>
#
# Runs in background, writes heartbeat every N seconds.
# Stops when the agent's tmux window disappears.
set -euo pipefail

AGENT_NAME="${1:?Usage: heartbeat.sh <agent_name> <interval>}"
INTERVAL="${2:-60}"
TMUX_SESSION="${TMUX_SESSION_NAME:-agents}"
HEARTBEAT_DIR="/tmp/baap-heartbeats"

mkdir -p "$HEARTBEAT_DIR"
HEARTBEAT_FILE="$HEARTBEAT_DIR/$AGENT_NAME"

echo "Heartbeat started for $AGENT_NAME (every ${INTERVAL}s)"

while true; do
  # Check if agent's tmux window still exists
  if ! tmux list-windows -t "$TMUX_SESSION" 2>/dev/null | grep -q "$AGENT_NAME"; then
    echo "Agent $AGENT_NAME tmux window gone. Stopping heartbeat."
    rm -f "$HEARTBEAT_FILE"
    exit 0
  fi

  # Write heartbeat timestamp
  date +%s > "$HEARTBEAT_FILE"

  # Also update beads if bd is available
  if command -v bd &>/dev/null; then
    bd agent heartbeat "$AGENT_NAME" 2>/dev/null || true
  fi

  sleep "$INTERVAL"
done
```

### How the orchestrator checks liveness:

```bash
# Check if agent is alive (heartbeat < 2 minutes old)
check_agent_alive() {
  local AGENT="$1"
  local HEARTBEAT_FILE="/tmp/baap-heartbeats/$AGENT"
  local NOW=$(date +%s)
  local MAX_AGE=120  # 2 minutes

  if [ ! -f "$HEARTBEAT_FILE" ]; then
    echo "UNKNOWN"  # No heartbeat file — agent may not have started
    return
  fi

  local LAST=$(cat "$HEARTBEAT_FILE")
  local AGE=$(( NOW - LAST ))

  if [ "$AGE" -gt "$MAX_AGE" ]; then
    echo "STUCK (last heartbeat ${AGE}s ago)"
  else
    echo "ALIVE (last heartbeat ${AGE}s ago)"
  fi
}
```

---

## Fix 2: kill-agent.sh (Risk 9)

### Problem

If an agent is doing something wrong, the only option is manually killing the tmux
window. That leaves:
- Beads in `in_progress` state (downstream agents stay blocked)
- Worktree uncleaned (disk space leak)
- KG possibly half-updated
- No record of what happened

### Solution

A graceful cancellation script that cleans up everything:

```bash
#!/usr/bin/env bash
# kill-agent.sh — Gracefully cancel a running agent
#
# Usage: kill-agent.sh <agent_name> [reason]
#
# What it does:
# 1. Kills the claude process in the agent's tmux window
# 2. Marks any in-progress beads as failed
# 3. Updates agent state to "stopped"
# 4. Runs cleanup.sh discard (removes worktree + branch)
# 5. Stops heartbeat
set -euo pipefail

AGENT_NAME="${1:?Usage: kill-agent.sh <agent_name> [reason]}"
REASON="${2:-Manually cancelled}"
TMUX_SESSION="${TMUX_SESSION_NAME:-agents}"

echo "Killing agent: $AGENT_NAME"
echo "Reason: $REASON"

# 1. Kill the claude process in tmux window
if tmux list-windows -t "$TMUX_SESSION" 2>/dev/null | grep -q "$AGENT_NAME"; then
  # Send Ctrl+C to interrupt, then wait briefly
  tmux send-keys -t "$TMUX_SESSION:$AGENT_NAME" C-c 2>/dev/null || true
  sleep 2

  # If still running, force kill
  PANE_PID=$(tmux list-panes -t "$TMUX_SESSION:$AGENT_NAME" -F '#{pane_pid}' 2>/dev/null || true)
  if [ -n "$PANE_PID" ]; then
    # Kill the process tree (claude + child processes)
    pkill -TERM -P "$PANE_PID" 2>/dev/null || true
    sleep 1
    pkill -KILL -P "$PANE_PID" 2>/dev/null || true
  fi

  # Close the tmux window
  tmux kill-window -t "$TMUX_SESSION:$AGENT_NAME" 2>/dev/null || true
  echo "Killed tmux window."
fi

# 2. Mark in-progress beads as failed
if command -v bd &>/dev/null; then
  # Find beads assigned to this agent that are in_progress
  OPEN_BEADS=$(bd list --status=in_progress --json 2>/dev/null | python3 -c "
import json, sys
try:
    beads = json.load(sys.stdin)
    agent = '$AGENT_NAME'
    open_ones = [b['id'] for b in beads if agent in str(b.get('assignee','')) or agent in str(b.get('title',''))]
    print(' '.join(open_ones))
except: pass
" 2>/dev/null || true)

  for BEAD_ID in $OPEN_BEADS; do
    bd close "$BEAD_ID" --reason="CANCELLED: $REASON" 2>/dev/null || true
    echo "Closed bead: $BEAD_ID (cancelled)"
  done

  # Update agent state
  bd agent state "$AGENT_NAME" stopped 2>/dev/null || true
fi

# 3. Stop heartbeat
rm -f "/tmp/baap-heartbeats/$AGENT_NAME"

# 4. Discard worktree and branch
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
if [ -d "$AGENT_DIR/$AGENT_NAME" ]; then
  bash "$(dirname "$0")/cleanup.sh" "$AGENT_NAME" discard
  echo "Worktree discarded."
else
  echo "No worktree found (already cleaned up)."
fi

echo "Agent $AGENT_NAME killed and cleaned up."
```

---

## Fix 3: Memory Bootstrap in spawn.sh (Risk 12)

### Problem

Agent specs reference `.claude/agents/{name}/memory/MEMORY.md`. If this is the first
time an agent runs, that file doesn't exist. The agent tries to read it, gets an error,
and may go off track.

### Solution

Add memory directory bootstrap to spawn.sh, right after creating the worktree:

```bash
# ── Bootstrap agent memory ──────────────────────────────────────────────────
MEMORY_DIR="$MAIN_REPO/.claude/agents/$AGENT_NAME/memory"
if [ ! -d "$MEMORY_DIR" ]; then
  mkdir -p "$MEMORY_DIR"
  cat > "$MEMORY_DIR/MEMORY.md" << MEMEOF
# $AGENT_NAME Memory

## Created
- $(date -Iseconds)
- First session, no prior knowledge

## My Ownership
- Check with: get_agent_files("$AGENT_NAME")

## Key Decisions
- (none yet)

## Recent Changes
- (none yet)
MEMEOF
  echo "Created memory directory for $AGENT_NAME"

  # Commit the new memory dir so worktrees can access it
  cd "$MAIN_REPO"
  git add ".claude/agents/$AGENT_NAME/memory/" 2>/dev/null || true
  git commit -m "Bootstrap memory for $AGENT_NAME" --no-verify 2>/dev/null || true
fi
```

Important: The memory directory is created in the MAIN REPO and committed to git,
so it appears in all worktrees.

---

## Fix 4: Integrate heartbeat into spawn.sh

Add heartbeat launch to spawn.sh, right after launching the agent in tmux:

```bash
# ── Launch heartbeat in background ──────────────────────────────────────────
nohup bash "$MAIN_REPO/.claude/scripts/heartbeat.sh" "$AGENT_NAME" 60 \
  > /tmp/baap-heartbeats/$AGENT_NAME.log 2>&1 &
echo "Heartbeat PID: $!"
```

---

## Success Criteria

- [ ] heartbeat.sh created and executable at .claude/scripts/heartbeat.sh
- [ ] kill-agent.sh created and executable at .claude/scripts/kill-agent.sh
- [ ] heartbeat.sh writes timestamp to /tmp/baap-heartbeats/<name> every 60s
- [ ] heartbeat.sh auto-stops when tmux window disappears
- [ ] kill-agent.sh kills claude process, closes beads, discards worktree
- [ ] spawn.sh bootstraps memory directory for new agents
- [ ] spawn.sh launches heartbeat alongside agent
- [ ] Memory MEMORY.md has sensible defaults for first-run agents

## Verification

```bash
# Test heartbeat
bash .claude/scripts/heartbeat.sh test-agent 5 &
sleep 12
cat /tmp/baap-heartbeats/test-agent  # Should have recent timestamp
kill %1  # Stop background heartbeat

# Test kill-agent (requires a running test agent)
bash .claude/scripts/spawn.sh reactive "sleep 3600" ~/Projects/baap test-kill-agent 2
sleep 5
bash .claude/scripts/kill-agent.sh test-kill-agent "testing cancellation"
# Verify: tmux window gone, worktree removed, no heartbeat file

# Test memory bootstrap
bash .claude/scripts/spawn.sh reactive "echo test" ~/Projects/baap new-agent 2
ls .claude/agents/new-agent/memory/MEMORY.md  # Should exist
bash .claude/scripts/cleanup.sh new-agent discard
```
