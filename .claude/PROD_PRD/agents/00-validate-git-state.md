# Phase 0: Validate Git State & Tool Availability

## Purpose

Before ANY production hardening, verify that the build phase output is properly committed
to git and all required tools are available. Worktrees checkout from git — if .claude/
isn't committed, every spawned agent gets an empty shell.

## Risk Mitigated

- Risk 2: .claude/ directory not committed to git (SHOWSTOPPER)

## Steps

### Step 1: Check what's committed vs uncommitted

```bash
cd ~/Projects/baap
git status
```

Expected: `.claude/` files should be tracked. If they show as untracked or modified, they
need to be committed.

### Step 2: Verify critical files exist in git

Check that ALL of these are tracked by git (not just on disk):

```bash
git ls-files .claude/CLAUDE.md
git ls-files .claude/mcp/ownership_graph.py
git ls-files .claude/mcp/db_tools.py
git ls-files .claude/mcp/run_mcp.sh
git ls-files .claude/kg/agent_graph_cache.json
git ls-files .claude/kg/seeds/
git ls-files .claude/tools/ag
git ls-files .claude/scripts/spawn.sh
git ls-files .claude/scripts/cleanup.sh
git ls-files .claude/agents/
git ls-files .claude/references/claude-code-patterns.md
git ls-files .mcp.json
```

If ANY of these return empty (not tracked), add and commit them.

### Step 3: Commit if needed

```bash
# Add all .claude/ infrastructure files
git add .claude/ .mcp.json

# DO NOT add:
# - .beads/ (gitignored, runtime state)
# - agents/ (gitignored, worktree directory)
# - *.sql (gitignored, database dumps)
# - .venv/ (gitignored, virtual environment)

git commit -m "Track all infrastructure files for worktree availability"
```

### Step 4: Verify .gitignore

```bash
cat .gitignore
```

Must contain:
```
app-mynextory-backup.sql
app-mynextory-backup-utf8.sql
app-mynextory-mariadb.sql
.venv/
__pycache__/
*.pyc
/agents/
.beads/
*.flag
*.tmp
```

If missing entries, add them.

### Step 5: Verify tools in PATH

```bash
which claude    || echo "MISSING: claude CLI"
which bd        || echo "MISSING: beads CLI"
which python3   || echo "MISSING: python3"
which git       || echo "MISSING: git"
which tmux      || echo "MISSING: tmux"
which flock     || echo "MISSING: flock (needed for merge locking)"
```

For `ag` (may be a script, not in PATH):
```bash
test -x .claude/tools/ag && echo "ag: OK" || echo "MISSING: ag CLI"
```

For `flock`: If missing on the system, install it:
```bash
# Ubuntu/Debian
sudo apt-get install -y util-linux
# It's usually already there on Linux
```

### Step 6: Verify worktree checkout works

```bash
# Create a test worktree to verify .claude/ files appear
git worktree add /tmp/baap-worktree-test test-worktree-branch 2>/dev/null
ls /tmp/baap-worktree-test/.claude/CLAUDE.md && echo "CLAUDE.md: OK" || echo "FAIL: CLAUDE.md not in worktree"
ls /tmp/baap-worktree-test/.claude/mcp/ownership_graph.py && echo "MCP: OK" || echo "FAIL: MCP not in worktree"
ls /tmp/baap-worktree-test/.mcp.json && echo ".mcp.json: OK" || echo "FAIL: .mcp.json not in worktree"

# Cleanup test worktree
git worktree remove /tmp/baap-worktree-test --force
git branch -D test-worktree-branch
```

## Success Criteria

- [ ] All .claude/ infrastructure files are tracked by git
- [ ] .gitignore covers runtime artifacts (SQL, .beads/, agents/, .venv/)
- [ ] claude, bd, python3, git, tmux are all in PATH
- [ ] ag CLI is executable at .claude/tools/ag
- [ ] Test worktree checkout contains all .claude/ files
- [ ] flock is available (or installed)

## Output

Print "Phase 0: PASSED" if all checks pass, or list specific failures.
