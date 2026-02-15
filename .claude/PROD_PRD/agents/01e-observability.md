# Phase 1e: Observability — Logs, Monitoring, Status

## Purpose

Right now the orchestrator is blind to what agents are doing. It knows "alive or dead"
(heartbeat) and "bead open or closed" (bd list). It doesn't know what file an agent is
editing, whether it hit an error, or what it's thinking. If a tmux window closes,
everything that happened is gone — no logs, no record.

Production requires three things:
1. Persistent logs — every agent's output saved to disk
2. Real-time status — what each agent is doing right now
3. Aggregated monitoring — one command to see everything

## Risks Mitigated

- Risk 16: No log capture — agent output lost when tmux scrollback overflows or window closes
- Risk 17: No real-time visibility into what agents are doing
- Risk 18: No single-pane-of-glass monitoring for the orchestrator or human

## Files to Create

- `.claude/scripts/monitor.sh` — Aggregated status dashboard
- Agent log directory convention: `~/agents/{name}/agent.log`

## Files to Modify

- `.claude/scripts/spawn.sh` — Add log capture via `tee`, status file writing

---

## Fix 1: Log Capture in spawn.sh

### Problem

Agent output goes to tmux only. If the window closes or scrollback overflows, it's gone.
No post-mortem debugging possible.

### Solution

Pipe claude's output through `tee` to capture both tmux display AND a log file:

In spawn.sh, change the tmux launch command from:

```bash
tmux new-window -t "$TMUX_SESSION" -n "$NAME" "cd $WORKTREE && $CLAUDE_CMD"
```

To:

```bash
LOG_DIR="$WORKTREE"
LOG_FILE="$LOG_DIR/agent.log"

tmux new-window -t "$TMUX_SESSION" -n "$NAME" \
  "cd $WORKTREE && export AGENT_NAME=$NAME && export AGENT_LEVEL=$LEVEL && $CLAUDE_CMD 2>&1 | tee $LOG_FILE; echo 'Agent $NAME finished. Press Enter to close.'; read"
```

This way:
- Agent output appears in tmux window (real-time monitoring by human)
- Agent output is ALSO written to `~/agents/{name}/agent.log` (persistent)
- After agent finishes, log remains on disk even if tmux window is closed
- Orchestrator can `tail -f ~/agents/{name}/agent.log` to watch any agent

### Log rotation

For long-running agents, logs could get large. Add a size check:

```bash
# In heartbeat.sh, add log size monitoring
LOG_FILE="$AGENT_DIR/$AGENT_NAME/agent.log"
if [ -f "$LOG_FILE" ]; then
  LOG_SIZE=$(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
  # Warn if log > 50MB
  if [ "$LOG_SIZE" -gt 52428800 ]; then
    echo "WARNING: Agent $AGENT_NAME log exceeds 50MB"
  fi
fi
```

---

## Fix 2: Agent Status File

### Problem

The orchestrator wants to know "what is identity-agent doing RIGHT NOW?" without
attaching to tmux or tailing a log. A structured, machine-readable status.

### Solution

Each agent writes a status file at a known location. The file is updated at key moments.

Convention: `/tmp/baap-agent-status/{agent-name}.json`

```json
{
  "agent": "identity-agent",
  "level": 1,
  "bead": "baap-abc",
  "status": "working",
  "current_action": "Editing src/models/user.py",
  "started_at": "2026-02-14T10:30:00Z",
  "last_update": "2026-02-14T10:35:22Z",
  "files_modified": ["src/models/user.py", "src/models/auth.py"],
  "errors": 0
}
```

### How agents write status

Add to CLAUDE.md work protocol — agents should update their status file at key points.
But since we can't guarantee LLM compliance, we also capture it from the log.

In spawn.sh, create the status directory and initial status:

```bash
STATUS_DIR="/tmp/baap-agent-status"
mkdir -p "$STATUS_DIR"

cat > "$STATUS_DIR/$NAME.json" << STATUSEOF
{
  "agent": "$NAME",
  "level": $LEVEL,
  "status": "spawning",
  "started_at": "$(date -Iseconds)",
  "last_update": "$(date -Iseconds)",
  "worktree": "$WORKTREE",
  "log_file": "$WORKTREE/agent.log"
}
STATUSEOF
```

In heartbeat.sh, update the status file with latest info:

```bash
# Update status from heartbeat
STATUS_FILE="$STATUS_DIR/$AGENT_NAME.json"
if [ -f "$STATUS_FILE" ]; then
  # Update last_update timestamp
  python3 -c "
import json, datetime
with open('$STATUS_FILE', 'r') as f:
    s = json.load(f)
s['last_update'] = datetime.datetime.now().isoformat()
s['status'] = 'working'
# Try to get last log line for current_action
try:
    with open('$AGENT_DIR/$AGENT_NAME/agent.log', 'r') as log:
        lines = log.readlines()
        # Find last meaningful line (skip blank lines)
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith('─'):
                s['current_action'] = line[:200]
                break
except: pass
with open('$STATUS_FILE', 'w') as f:
    json.dump(s, f, indent=2)
" 2>/dev/null || true
fi
```

In kill-agent.sh, update status to "stopped":

```bash
STATUS_FILE="/tmp/baap-agent-status/$AGENT_NAME.json"
if [ -f "$STATUS_FILE" ]; then
  python3 -c "
import json, datetime
with open('$STATUS_FILE', 'r') as f:
    s = json.load(f)
s['status'] = 'stopped'
s['last_update'] = datetime.datetime.now().isoformat()
s['stop_reason'] = '$REASON'
with open('$STATUS_FILE', 'w') as f:
    json.dump(s, f, indent=2)
" 2>/dev/null || true
fi
```

---

## Fix 3: monitor.sh — Single-Pane Dashboard

### Purpose

One command that shows the full picture: all agents, their beads, their status,
their last heartbeat, their last log line.

### Implementation

```bash
#!/usr/bin/env bash
# monitor.sh — Aggregated agent monitoring dashboard
#
# Usage:
#   monitor.sh              # One-shot display
#   monitor.sh --watch      # Auto-refresh every 5 seconds
#   monitor.sh --agent NAME # Detail view for one agent
set -euo pipefail

STATUS_DIR="/tmp/baap-agent-status"
HEARTBEAT_DIR="/tmp/baap-heartbeats"
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
NOW=$(date +%s)

show_dashboard() {
  clear 2>/dev/null || true
  echo "╔══════════════════════════════════════════════════════════════════════════╗"
  echo "║                    BAAP AGENT MONITOR — $(date '+%H:%M:%S')                       ║"
  echo "╠══════════════════════════════════════════════════════════════════════════╣"

  # Active agents from status files
  if [ -d "$STATUS_DIR" ] && ls "$STATUS_DIR"/*.json &>/dev/null; then
    printf "║ %-20s %-8s %-10s %-10s %-18s ║\n" "AGENT" "LEVEL" "STATUS" "HEARTBEAT" "BEAD"
    echo "║──────────────────────────────────────────────────────────────────────────║"

    for status_file in "$STATUS_DIR"/*.json; do
      AGENT=$(python3 -c "import json; print(json.load(open('$status_file')).get('agent','?'))" 2>/dev/null || echo "?")
      LEVEL=$(python3 -c "import json; print('L'+str(json.load(open('$status_file')).get('level','?')))" 2>/dev/null || echo "?")
      STATUS=$(python3 -c "import json; print(json.load(open('$status_file')).get('status','?'))" 2>/dev/null || echo "?")
      BEAD=$(python3 -c "import json; print(json.load(open('$status_file')).get('bead','—'))" 2>/dev/null || echo "—")

      # Heartbeat check
      HB_FILE="$HEARTBEAT_DIR/$AGENT"
      if [ -f "$HB_FILE" ]; then
        LAST_HB=$(cat "$HB_FILE")
        HB_AGE=$(( NOW - LAST_HB ))
        if [ "$HB_AGE" -lt 120 ]; then
          HB_STATUS="${HB_AGE}s ago"
        else
          HB_STATUS="STALE!"
        fi
      else
        HB_STATUS="none"
      fi

      printf "║ %-20s %-8s %-10s %-10s %-18s ║\n" "$AGENT" "$LEVEL" "$STATUS" "$HB_STATUS" "$BEAD"
    done
  else
    echo "║ No active agents.                                                        ║"
  fi

  echo "╠══════════════════════════════════════════════════════════════════════════╣"

  # Beads summary
  if command -v bd &>/dev/null; then
    OPEN=$(bd list --status=open 2>/dev/null | wc -l || echo 0)
    IN_PROG=$(bd list --status=in_progress 2>/dev/null | wc -l || echo 0)
    BLOCKED=$(bd blocked 2>/dev/null | wc -l || echo 0)
    echo "║ Beads: $IN_PROG in-progress | $OPEN open | $BLOCKED blocked                         ║"
  fi

  # Worktrees
  WT_COUNT=$(git worktree list 2>/dev/null | grep -c agents || echo 0)
  echo "║ Worktrees: $WT_COUNT active                                                      ║"

  echo "╚══════════════════════════════════════════════════════════════════════════╝"
}

show_agent_detail() {
  local AGENT="$1"
  echo "=== Agent: $AGENT ==="

  # Status
  STATUS_FILE="$STATUS_DIR/$AGENT.json"
  if [ -f "$STATUS_FILE" ]; then
    python3 -c "import json; [print(f'  {k}: {v}') for k,v in json.load(open('$STATUS_FILE')).items()]"
  fi

  echo ""
  echo "=== Last 20 log lines ==="
  LOG_FILE="$AGENT_DIR/$AGENT/agent.log"
  if [ -f "$LOG_FILE" ]; then
    tail -20 "$LOG_FILE"
  else
    echo "  No log file found."
  fi

  echo ""
  echo "=== Beads ==="
  if command -v bd &>/dev/null; then
    bd list --status=in_progress 2>/dev/null | grep -i "$AGENT" || echo "  No in-progress beads for $AGENT"
  fi
}

# Parse args
case "${1:-}" in
  --watch)
    while true; do
      show_dashboard
      sleep 5
    done
    ;;
  --agent)
    show_agent_detail "${2:?Usage: monitor.sh --agent NAME}"
    ;;
  *)
    show_dashboard
    ;;
esac
```

### Usage

```bash
# Dashboard view (one-shot)
bash .claude/scripts/monitor.sh

# Auto-refreshing dashboard (like htop for agents)
bash .claude/scripts/monitor.sh --watch

# Detailed view of one agent
bash .claude/scripts/monitor.sh --agent identity-agent

# Tail an agent's log in real-time
tail -f ~/agents/identity-agent/agent.log
```

### The orchestrator uses it like this:

```bash
# In its monitoring loop:
bash .claude/scripts/monitor.sh  # Quick status check
# Or for a specific agent:
bash .claude/scripts/monitor.sh --agent identity-agent
# Or just tail the log:
tail -50 ~/agents/identity-agent/agent.log
```

---

## Fix 4: Cleanup Logging

When cleanup.sh runs (merge or discard), archive the agent log:

In cleanup.sh, before removing the worktree:

```bash
# Archive agent log before worktree removal
LOG_FILE="$WORKTREE/agent.log"
ARCHIVE_DIR="$PROJECT/.claude/logs"
if [ -f "$LOG_FILE" ]; then
  mkdir -p "$ARCHIVE_DIR"
  cp "$LOG_FILE" "$ARCHIVE_DIR/${NAME}_$(date +%Y%m%d_%H%M%S).log"
  echo "Archived agent log to $ARCHIVE_DIR/"
fi

# Clean up status file
rm -f "/tmp/baap-agent-status/$NAME.json"
```

Add `.claude/logs/` to .gitignore (logs are local, not committed):

```bash
echo ".claude/logs/" >> .gitignore
```

---

## CLAUDE.md Addition

Add to the orchestrator protocol section of CLAUDE.md:

```markdown
## Monitoring Agents

| Command | Purpose |
|---------|---------|
| `bash .claude/scripts/monitor.sh` | Dashboard: all agents, status, heartbeats |
| `bash .claude/scripts/monitor.sh --watch` | Auto-refreshing dashboard (every 5s) |
| `bash .claude/scripts/monitor.sh --agent NAME` | Detail view: status + last 20 log lines |
| `tail -f ~/agents/{name}/agent.log` | Real-time log stream for one agent |
| `tail -50 ~/agents/{name}/agent.log` | Last 50 lines of agent output |
```

---

## Success Criteria

- [ ] spawn.sh pipes output through `tee` to agent.log
- [ ] spawn.sh creates initial status JSON in /tmp/baap-agent-status/
- [ ] heartbeat.sh updates status JSON with last_update and current_action
- [ ] kill-agent.sh updates status to "stopped"
- [ ] cleanup.sh archives agent.log to .claude/logs/ before worktree removal
- [ ] monitor.sh shows aggregated dashboard with all agents
- [ ] monitor.sh --watch auto-refreshes every 5 seconds
- [ ] monitor.sh --agent NAME shows detailed view with log tail
- [ ] .claude/logs/ added to .gitignore

## Verification

```bash
# Spawn a test agent
bash .claude/scripts/spawn.sh reactive "echo hello world && sleep 30" ~/Projects/baap test-observe 2

sleep 5

# Check log exists
[ -f ~/agents/test-observe/agent.log ] && echo "PASS: Log file exists" || echo "FAIL: No log"

# Check status file exists
[ -f /tmp/baap-agent-status/test-observe.json ] && echo "PASS: Status file exists" || echo "FAIL: No status"

# Run monitor
bash .claude/scripts/monitor.sh
# Should show test-observe agent with status

# Run agent detail
bash .claude/scripts/monitor.sh --agent test-observe
# Should show status + log lines

# Cleanup
bash .claude/scripts/kill-agent.sh test-observe "testing observability"

# Check log archived
ls .claude/logs/test-observe_*.log && echo "PASS: Log archived" || echo "FAIL: Log not archived"
```
