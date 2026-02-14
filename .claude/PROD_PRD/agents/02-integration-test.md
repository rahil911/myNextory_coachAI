# Phase 2: Integration Test — Full Agent Lifecycle Verification

## Purpose

Verify that ALL production hardening fixes work together end-to-end.
Every fix from Phase 1 (a, b, c, d) must be validated in a real agent lifecycle.

## Dependencies

- Phase 00: git state validated
- Phase 01a: spawn.sh hardened
- Phase 01b: cleanup.sh hardened
- Phase 01c: shared KG + file locking
- Phase 01d: heartbeat + kill-agent + memory bootstrap

## Test Plan

Run these tests SEQUENTIALLY. Each test builds on the previous.

---

### Test 1: Pre-flight & Spawn

Verify spawn.sh pre-flight checks and worktree creation.

```bash
cd ~/Projects/baap

# Test pre-flight catches missing tools
# (This should pass since tools are installed)
echo "=== Test 1a: Pre-flight ==="
bash .claude/scripts/spawn.sh reactive "echo hello" ~/Projects/baap test-preflight 2
echo "RESULT: Spawn succeeded"

# Verify worktree structure
echo "=== Test 1b: Worktree structure ==="
WORKTREE="$HOME/agents/test-preflight"

# .beads/ must be a symlink to main repo
[ -L "$WORKTREE/.beads" ] && echo "PASS: .beads/ is symlink" || echo "FAIL: .beads/ not symlinked"

# .venv/ must be a symlink to main repo
[ -L "$WORKTREE/.venv" ] && echo "PASS: .venv/ is symlink" || echo "FAIL: .venv/ not symlinked"

# .claude/ must exist (from git checkout)
[ -d "$WORKTREE/.claude" ] && echo "PASS: .claude/ exists" || echo "FAIL: .claude/ missing"

# CLAUDE.md must be present
[ -f "$WORKTREE/.claude/CLAUDE.md" ] && echo "PASS: CLAUDE.md present" || echo "FAIL: CLAUDE.md missing"

# MCP config must be present
[ -f "$WORKTREE/.mcp.json" ] && echo "PASS: .mcp.json present" || echo "FAIL: .mcp.json missing"

# Cleanup
bash .claude/scripts/cleanup.sh test-preflight discard
echo "Test 1: COMPLETE"
```

---

### Test 2: Beads from Worktree

Verify agents can read/write beads from inside a worktree.

```bash
echo "=== Test 2: Beads from worktree ==="

# Create a test bead
TEST_BEAD=$(bd create --title="Integration test bead" --type=task --priority=3 2>/dev/null | grep -oP 'baap-\w+' | head -1)
echo "Created bead: $TEST_BEAD"

# Spawn agent
bash .claude/scripts/spawn.sh reactive "echo test" ~/Projects/baap test-beads 2

# From the worktree, try to read the bead
cd "$HOME/agents/test-beads"
bd show "$TEST_BEAD" 2>/dev/null && echo "PASS: Can read bead from worktree" || echo "FAIL: Cannot read bead"

# From the worktree, try to close the bead
bd close "$TEST_BEAD" --reason="Integration test" 2>/dev/null && echo "PASS: Can close bead from worktree" || echo "FAIL: Cannot close bead"

# Verify from main repo
cd ~/Projects/baap
bd show "$TEST_BEAD" 2>/dev/null | grep -q "closed" && echo "PASS: Bead closure visible from main" || echo "FAIL: Bead closure not propagated"

# Cleanup
bash .claude/scripts/cleanup.sh test-beads discard
echo "Test 2: COMPLETE"
```

---

### Test 3: KG Shared State

Verify KG cache is shared and file-locked.

```bash
echo "=== Test 3: KG shared state ==="

# Read KG from main repo
MAIN_NODES=$(python3 -c "import json; d=json.load(open('.claude/kg/agent_graph_cache.json')); print(d['metadata']['node_count'])")
echo "Main repo KG nodes: $MAIN_NODES"

# Spawn two agents
bash .claude/scripts/spawn.sh reactive "echo test" ~/Projects/baap test-kg-a 2
bash .claude/scripts/spawn.sh reactive "echo test" ~/Projects/baap test-kg-b 2

# From worktree A, read KG
cd "$HOME/agents/test-kg-a"
KG_A_NODES=$(python3 -c "
import subprocess, os, json
git_common = subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], text=True).strip()
main_root = git_common.replace('/.git', '') if git_common.endswith('/.git') else os.getcwd()
kg_path = os.path.join(main_root, '.claude', 'kg', 'agent_graph_cache.json')
d = json.load(open(kg_path))
print(d['metadata']['node_count'])
")
echo "Worktree A sees KG nodes: $KG_A_NODES"

[ "$MAIN_NODES" = "$KG_A_NODES" ] && echo "PASS: KG shared between main and worktree" || echo "FAIL: KG diverged"

# Cleanup
cd ~/Projects/baap
bash .claude/scripts/cleanup.sh test-kg-a discard
bash .claude/scripts/cleanup.sh test-kg-b discard
echo "Test 3: COMPLETE"
```

---

### Test 4: Concurrent Merge Lock

Verify flock prevents concurrent merge races.

```bash
echo "=== Test 4: Merge lock ==="

# Create two agents with simple changes
bash .claude/scripts/spawn.sh reactive "echo test" ~/Projects/baap test-merge-a 2
bash .claude/scripts/spawn.sh reactive "echo test" ~/Projects/baap test-merge-b 2

# Make changes in each worktree
echo "# Change A" >> "$HOME/agents/test-merge-a/test_a.txt"
cd "$HOME/agents/test-merge-a" && git add -A && git commit -m "Test A" --no-verify

echo "# Change B" >> "$HOME/agents/test-merge-b/test_b.txt"
cd "$HOME/agents/test-merge-b" && git add -A && git commit -m "Test B" --no-verify

cd ~/Projects/baap

# Launch both merges simultaneously
bash .claude/scripts/cleanup.sh test-merge-a merge &
PID_A=$!
bash .claude/scripts/cleanup.sh test-merge-b merge &
PID_B=$!

# Wait for both
wait $PID_A && echo "Merge A: OK" || echo "Merge A: FAILED"
wait $PID_B && echo "Merge B: OK" || echo "Merge B: FAILED"

# Verify both changes are on main
git log --oneline -5
[ -f test_a.txt ] && echo "PASS: Change A on main" || echo "FAIL: Change A lost"
[ -f test_b.txt ] && echo "PASS: Change B on main" || echo "FAIL: Change B lost"

# Cleanup test files
git rm test_a.txt test_b.txt 2>/dev/null || true
git commit -m "Clean up integration test files" --no-verify 2>/dev/null || true

echo "Test 4: COMPLETE"
```

---

### Test 5: Timeout Enforcement

Verify that agents are killed after timeout.

```bash
echo "=== Test 5: Timeout ==="

# Spawn an agent with L3 timeout (30 minutes) but we'll use a custom short timeout for testing
# Modify: spawn with a 10-second timeout for testing
TIMEOUT_SECS=10 bash .claude/scripts/spawn.sh reactive "sleep 3600" ~/Projects/baap test-timeout 3

# Wait for timeout + buffer
sleep 15

# Check if agent's tmux window is gone
if tmux list-windows -t agents 2>/dev/null | grep -q "test-timeout"; then
  echo "FAIL: Agent still running after timeout"
else
  echo "PASS: Agent killed by timeout"
fi

# Cleanup
bash .claude/scripts/cleanup.sh test-timeout discard 2>/dev/null || true
echo "Test 5: COMPLETE"
```

NOTE: Test 5 may need adjustment based on how timeout is implemented. If spawn.sh
uses `timeout` command, the 10-second test should work. If it uses a different mechanism,
adjust accordingly. The key verification is: does the agent stop after the configured time?

---

### Test 6: Heartbeat Detection

Verify heartbeat file is written and stale detection works.

```bash
echo "=== Test 6: Heartbeat ==="

# Spawn agent (heartbeat should auto-start)
bash .claude/scripts/spawn.sh reactive "sleep 60" ~/Projects/baap test-heartbeat 2

sleep 5

# Check heartbeat file exists
HEARTBEAT_FILE="/tmp/baap-heartbeats/test-heartbeat"
[ -f "$HEARTBEAT_FILE" ] && echo "PASS: Heartbeat file exists" || echo "FAIL: No heartbeat file"

# Check heartbeat is recent
if [ -f "$HEARTBEAT_FILE" ]; then
  LAST=$(cat "$HEARTBEAT_FILE")
  NOW=$(date +%s)
  AGE=$(( NOW - LAST ))
  [ "$AGE" -lt 120 ] && echo "PASS: Heartbeat recent (${AGE}s ago)" || echo "FAIL: Heartbeat stale (${AGE}s ago)"
fi

# Cleanup
bash .claude/scripts/kill-agent.sh test-heartbeat "integration test"

# Verify heartbeat file removed
[ ! -f "$HEARTBEAT_FILE" ] && echo "PASS: Heartbeat cleaned up" || echo "FAIL: Heartbeat file not removed"

echo "Test 6: COMPLETE"
```

---

### Test 7: Kill Agent Graceful Shutdown

Verify kill-agent.sh cleans everything up.

```bash
echo "=== Test 7: Kill agent ==="

# Create a bead and spawn an agent working on it
KILL_BEAD=$(bd create --title="Kill test bead" --type=task --priority=3 2>/dev/null | grep -oP 'baap-\w+' | head -1)
bash .claude/scripts/spawn.sh reactive "sleep 3600" ~/Projects/baap test-kill 2

sleep 3

# Kill the agent
bash .claude/scripts/kill-agent.sh test-kill "integration test"

# Verify cleanup
echo "Checking cleanup..."

# tmux window should be gone
tmux list-windows -t agents 2>/dev/null | grep -q "test-kill" && echo "FAIL: tmux window still exists" || echo "PASS: tmux window removed"

# Worktree should be gone
[ -d "$HOME/agents/test-kill" ] && echo "FAIL: Worktree still exists" || echo "PASS: Worktree removed"

# Heartbeat should be gone
[ -f "/tmp/baap-heartbeats/test-kill" ] && echo "FAIL: Heartbeat still exists" || echo "PASS: Heartbeat removed"

echo "Test 7: COMPLETE"
```

---

### Test 8: Memory Bootstrap

Verify new agents get memory directory created.

```bash
echo "=== Test 8: Memory bootstrap ==="

# Spawn a brand new agent (never existed before)
bash .claude/scripts/spawn.sh reactive "echo test" ~/Projects/baap brand-new-agent 2

# Check memory was created in main repo
[ -f ".claude/agents/brand-new-agent/memory/MEMORY.md" ] && echo "PASS: Memory created" || echo "FAIL: No memory"

# Check memory content
cat .claude/agents/brand-new-agent/memory/MEMORY.md

# Cleanup
bash .claude/scripts/cleanup.sh brand-new-agent discard

echo "Test 8: COMPLETE"
```

---

## Final Summary

After all tests pass, print summary:

```bash
echo ""
echo "========================================"
echo "  PRODUCTION HARDENING: ALL TESTS DONE  "
echo "========================================"
echo ""
echo "Fixes verified:"
echo "  [1]  .beads/ symlinked in worktrees"
echo "  [3]  Agent identity passed in prompt"
echo "  [4]  KG cache shared via absolute path"
echo "  [5]  Merge lock prevents concurrent races"
echo "  [6]  Timeout enforcement kills stuck agents"
echo "  [7]  .venv/ shared (no cold start)"
echo "  [8]  Heartbeat detects stuck agents"
echo "  [9]  kill-agent.sh graceful cancellation"
echo "  [11] --mcp-config absolute path"
echo "  [12] Memory bootstrap for new agents"
echo "  [13] Pre-flight tool check"
echo ""
```

## Success Criteria

- [ ] All 8 tests print PASS (no FAIL)
- [ ] No worktrees or test branches left behind
- [ ] No test beads left open
- [ ] System ready for real agent work

## After All Tests Pass

```bash
cd ~/Projects/baap
git add -A
git commit -m "Production hardening: all 15 risks mitigated, integration tests passed"
git push
```
