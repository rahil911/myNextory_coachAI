# Phase 5: First Swarm (End-to-End Demo)

## Purpose

Validate the entire system by running a REAL multi-agent task: the orchestrator creates a bead, the beads orchestrator dispatches it to a domain agent, the agent does work, closes the bead, merges its code, and notifies dependents.

This proves the full lifecycle works: human → orchestrator → KG query → bead creation → agent spawn → work → merge → notification.

## Phase Info

- **Phase**: 5 (sequential — runs after Phase 4 gate)
- **Estimated time**: 30-60 minutes
- **Model tier**: Sonnet (for the orchestration); Haiku (for the spawned agent)
- **Optional**: This phase is a demo/validation. The system is functional after Phase 4.

## Input Contract

- **All Phase 4 outputs**: .mcp.json, .beads/, all MCP servers working, all agent specs
- **Integration test passing**: `integration_passed.flag` exists

## Output Contract

- **Git merge commit**: Agent's work merged to main branch
- **Bead closed**: The task bead is marked complete
- **Memory updated**: The agent's memory reflects what it did
- **Notification bead created**: Dependent agents were notified

## The Task: "Add a database status summary view"

A simple, self-contained task for `db-agent`:
- Create a SQL view `v_database_summary` that shows table names, row counts, and sizes
- This is low-risk (it's a view, not a table mutation)
- It exercises: KG query, bead lifecycle, agent spawn, SQL execution, merge, notification

## Step-by-Step Instructions

### 1. Orchestrator Creates the Task

```bash
cd ~/Projects/baap

# Step 1a: Query blast radius
python3 .claude/tools/ag blast db-agent
# Shows: db-agent affects api-agent, test-agent (via DEPENDS_ON)

# Step 1b: Create epic
EPIC_ID=$(bd create --title="EPIC: Add database summary view" --type=epic --priority=2 2>&1 | grep -oE '[a-zA-Z]+-[a-f0-9]+' | head -1)
echo "Epic: $EPIC_ID"

# Step 1c: Create task bead with full spec
TASK_ID=$(bd create --title="Create v_database_summary view" --type=task --priority=2 \
  --description="## Spec
Create a SQL view named v_database_summary in the baap database.

## View Definition
SELECT
  TABLE_NAME as table_name,
  TABLE_ROWS as row_count,
  ROUND(DATA_LENGTH / 1048576, 2) as data_size_mb,
  ROUND(INDEX_LENGTH / 1048576, 2) as index_size_mb,
  ENGINE as engine
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'baap'
ORDER BY TABLE_ROWS DESC;

## Acceptance Criteria
- View exists: SHOW CREATE VIEW v_database_summary
- Returns rows: SELECT * FROM v_database_summary LIMIT 5
- Row count matches table count

## Assigned to: db-agent" 2>&1 | grep -oE '[a-zA-Z]+-[a-f0-9]+' | head -1)
echo "Task: $TASK_ID"

# Step 1d: Create notification task (blocked by main task)
NOTIFY_ID=$(bd create --title="[NOTIFY] Database summary view created" --type=task --priority=3 \
  --description="db-agent created v_database_summary view. Update your code if you query database metadata." 2>&1 | grep -oE '[a-zA-Z]+-[a-f0-9]+' | head -1)
echo "Notify: $NOTIFY_ID"

# Step 1e: Set dependencies
bd dep add $NOTIFY_ID $TASK_ID  # Notification blocked by task completion

echo "Beads created. Ready for dispatch."
bd list --status=open
```

### 2. Spawn the Agent

Use the agent-infra spawn script to create an isolated environment:

```bash
# Option A: Use spawn.sh if it exists
if [ -f .claude/scripts/spawn.sh ]; then
    bash .claude/scripts/spawn.sh reactive "bd show $TASK_ID && work on it" ~/agents/db-agent-001
fi

# Option B: Manual spawn (if spawn.sh not ready)
cd ~/Projects/baap

# Create worktree
git worktree add ~/agents/db-agent-001 -b agent/db-agent-001

# Start agent in tmux
tmux new-session -d -s baap-agents -n db-agent-001 2>/dev/null || true
tmux new-window -t baap-agents -n db-agent-001 2>/dev/null || true

tmux send-keys -t baap-agents:db-agent-001 "cd ~/agents/db-agent-001 && claude --dangerously-skip-permissions --mcp-config .mcp.json -p '
You are db-agent. Read your spec at .claude/agents/db-agent/agent.md.

Your task bead is $TASK_ID. Run: bd show $TASK_ID

Follow the work protocol:
1. Read the bead spec
2. Execute the SQL to create the view
3. Verify it works
4. Update your memory at .claude/agents/db-agent/memory/MEMORY.md
5. Close the bead: bd close $TASK_ID --reason=\"View created and verified\"
6. Commit your changes
'" Enter
```

### 3. Monitor the Agent

```bash
# Watch in tmux
tmux attach -t baap-agents

# Or check bead status
bd list --status=in_progress
bd show $TASK_ID
```

### 4. After Agent Completes

The agent should:
1. Create the view: `CREATE VIEW v_database_summary AS SELECT ...`
2. Verify: `SELECT * FROM v_database_summary LIMIT 5`
3. Update memory
4. Close bead
5. Commit changes

### 5. Merge Agent's Work

```bash
# Option A: Use cleanup.sh
bash .claude/scripts/cleanup.sh db-agent-001 merge

# Option B: Manual merge
cd ~/Projects/baap
git merge agent/db-agent-001 --no-ff -m "Merge db-agent-001: Create v_database_summary view"
git worktree remove ~/agents/db-agent-001
git branch -d agent/db-agent-001
```

### 6. Verify the Full Lifecycle

```bash
echo "=== First Swarm Verification ==="

# 1. View exists
mysql baap -e "SHOW CREATE VIEW v_database_summary" && echo "  View exists: PASS" || echo "  View exists: FAIL"

# 2. View returns data
mysql baap -e "SELECT * FROM v_database_summary LIMIT 5" && echo "  View data: PASS" || echo "  View data: FAIL"

# 3. Bead is closed
bd show $TASK_ID 2>&1 | grep -q "closed\|completed" && echo "  Bead closed: PASS" || echo "  Bead closed: CHECK MANUALLY"

# 4. Memory updated
grep -q "database_summary\|v_database" .claude/agents/db-agent/memory/MEMORY.md 2>/dev/null && echo "  Memory updated: PASS" || echo "  Memory updated: CHECK MANUALLY"

# 5. Git shows merge commit
git log --oneline -5 | grep -q "db-agent\|database_summary" && echo "  Git merge: PASS" || echo "  Git merge: CHECK MANUALLY"

# 6. Notification bead unblocked
bd show $NOTIFY_ID 2>&1 | grep -q "ready\|open" && echo "  Notification unblocked: PASS" || echo "  Notification: CHECK MANUALLY"

echo "=== Verification Complete ==="
```

### 7. Handle the Notification Bead

The notification bead ($NOTIFY_ID) should now be unblocked (since the task bead is closed). In a full system, the beads orchestrator would:

1. Detect `$NOTIFY_ID` is ready via `bd ready`
2. Query KG: who depends on db-agent? → api-agent, test-agent
3. Spawn those agents with the notification
4. They update their memory and close the notification bead

For this demo, we can simply close it manually:

```bash
bd close $NOTIFY_ID --reason="First swarm demo — notification acknowledged"
bd close $EPIC_ID --reason="First swarm demo complete — full lifecycle validated"
```

### 8. Final Sync

```bash
bd sync
git push 2>/dev/null || echo "No remote configured (OK for local demo)"
```

## Success Criteria

1. `v_database_summary` view exists and returns data
2. Task bead is closed with reason
3. Agent memory file contains record of the change
4. Git log shows merge commit from agent branch
5. Notification bead was created and is ready/closed
6. No merge conflicts occurred
7. Worktree was cleaned up after merge

## What This Proves

- **KG queries work**: Orchestrator queried blast radius before creating tasks
- **Bead lifecycle works**: Create → assign → in_progress → close
- **Agent spawn works**: Isolated worktree, tmux session, headless Claude
- **Work protocol works**: Agent read spec, did work, updated memory, closed bead
- **Merge works**: Agent's branch merged cleanly to main
- **Notification works**: Dependent bead unblocked when task completed
- **The system is operational**: Ready for real feature development

## What's Next

After Phase 5 succeeds, the system is ready. To use it:

```bash
cd ~/Projects/baap
claude --dangerously-skip-permissions --mcp-config .mcp.json

# You are now talking to the orchestrator.
# Try: "Add a customer search feature"
# The orchestrator will:
#   1. Query blast radius
#   2. Create beads for each affected agent
#   3. Report back what it created
#   4. The beads orchestrator dispatches the work
```
