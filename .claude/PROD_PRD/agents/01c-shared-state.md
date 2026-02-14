# Phase 1c: Shared State — KG Cache & Beads Concurrency

## Purpose

Multiple agents running in parallel worktrees need to share state safely.
Three systems need attention: the Ownership KG cache, the Beads SQLite database,
and the MCP server configuration.

## Risks Mitigated

- Risk 4: KG cache is per-worktree, not shared — agents diverge (HIGH)
- Risk 14: KG cache concurrent write safety — no file locking (HIGH)
- Risk 15: Beads SQLite concurrent writes from parallel agents (MEDIUM-HIGH)

## Files to Modify

- `.claude/mcp/ownership_graph.py` — KG cache path + file locking
- `.mcp.json` — absolute paths for MCP server scripts

## Fix 1: KG Cache Shared Location (Risk 4)

### Problem

Each worktree has its own copy of `.claude/kg/agent_graph_cache.json` checked out from git.
When agent A calls `propose_ownership()`, it updates ITS worktree's copy. Agent B doesn't
see the update. KGs diverge during multi-agent sprints.

### Solution

The MCP server must read/write the KG cache from a FIXED ABSOLUTE PATH in the main repo,
NOT a relative path that resolves differently per worktree.

In `ownership_graph.py`, find where the cache file path is defined and change it:

```python
# WRONG (relative — resolves differently per worktree):
# CACHE_PATH = ".claude/kg/agent_graph_cache.json"

# CORRECT (absolute — all agents share the same file):
import subprocess

def get_main_repo_root():
    """Get the main repo root, even from a worktree."""
    try:
        git_common = subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        # git-common-dir returns the .git dir of the main repo
        if git_common.endswith("/.git"):
            return git_common[:-5]
        # If bare or just ".git", use toplevel
        return subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
    except subprocess.CalledProcessError:
        return os.getcwd()

MAIN_REPO = get_main_repo_root()
CACHE_PATH = os.path.join(MAIN_REPO, ".claude", "kg", "agent_graph_cache.json")
SEEDS_DIR = os.path.join(MAIN_REPO, ".claude", "kg", "seeds")
```

This way, ALL agents (in any worktree) read/write the SAME KG cache file in the main repo.

## Fix 2: File Locking on KG Writes (Risk 14)

### Problem

Two agents calling `propose_ownership()` simultaneously both read the JSON, modify it
in memory, and write it back. The second write overwrites the first agent's changes.

### Solution

Use `fcntl.flock()` for advisory file locking on all KG write operations:

```python
import fcntl
import json

LOCK_PATH = CACHE_PATH + ".lock"

def read_cache():
    """Read KG cache (shared read, no lock needed for reads)."""
    with open(CACHE_PATH, 'r') as f:
        return json.load(f)

def write_cache(data):
    """Write KG cache with exclusive file lock."""
    with open(LOCK_PATH, 'w') as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)  # Exclusive lock
        try:
            with open(CACHE_PATH, 'w') as f:
                json.dump(data, f, indent=2)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)  # Release

def propose_ownership(file_path, agent_name, evidence=""):
    """Register file ownership with safe concurrent writes."""
    with open(LOCK_PATH, 'w') as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            # Read current state INSIDE the lock
            data = read_cache()

            # Check exclusive ownership
            for node in data.get("nodes", []):
                if node.get("id") == file_path and node.get("type") == "file":
                    existing_owner = node.get("owner")
                    if existing_owner and existing_owner != agent_name:
                        return {"error": f"File already owned by {existing_owner}"}

            # Add or update file node
            # ... (existing logic)

            # Write back
            with open(CACHE_PATH, 'w') as f:
                json.dump(data, f, indent=2)

            return {"status": "registered", "file": file_path, "owner": agent_name}
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
```

Apply the same locking pattern to ANY function that writes to the cache file.

## Fix 3: Beads Concurrent Access (Risk 15)

### Problem

`.beads/` is symlinked from the main repo into each worktree (done by spawn.sh in 01a).
Multiple agents calling `bd close`, `bd create`, `bd update` simultaneously all hit
the same SQLite database. SQLite handles concurrent reads fine, but concurrent writes
can fail with "database is locked."

### Solution

Beads uses its own SQLite with WAL mode (which supports concurrent writes better).
Verify this is enabled:

```bash
# Check if beads SQLite uses WAL mode
sqlite3 .beads/beads.db "PRAGMA journal_mode;"
# Should return: wal

# If not, enable it:
sqlite3 .beads/beads.db "PRAGMA journal_mode=WAL;"
```

Additionally, set a busy timeout so bd commands retry instead of failing:

```bash
sqlite3 .beads/beads.db "PRAGMA busy_timeout = 5000;"  # Wait up to 5 seconds
```

If beads doesn't use SQLite directly (check its implementation), then the fix is at
the application level. The key insight: beads concurrent writes are less critical than
KG writes because each agent typically only writes to ITS OWN beads. Conflicts are rare.

Check how beads stores data:
```bash
ls -la .beads/
file .beads/*
```

If it's JSONL-based (append-only), concurrency is safe (appends are atomic on Linux for
small writes). If it's SQLite, ensure WAL mode. If it's a JSON file, it needs the same
fcntl.flock treatment as the KG cache.

## Fix 4: .mcp.json Absolute Paths

### Problem

`.mcp.json` may use relative paths for MCP server scripts. When an agent in a worktree
starts its MCP servers, relative paths resolve from the worktree directory (which has
the files via git checkout). But the KG cache is now at a FIXED path in the main repo.

### Solution

Read the current `.mcp.json` and ensure the MCP server commands work from any directory.
The MCP servers themselves will use `get_main_repo_root()` internally (from Fix 1), so
the .mcp.json command just needs to find the Python script.

If .mcp.json uses relative paths like `python3 .claude/mcp/ownership_graph.py`, this
works from worktrees because the script IS checked out there. The script itself then
resolves the KG cache to the main repo via `get_main_repo_root()`. So .mcp.json can
stay relative for the script path — only the KG cache inside the script needs to be absolute.

Verify this by reading .mcp.json:
```bash
cat .mcp.json
```

If it uses `bash .claude/mcp/run_mcp.sh`, verify that run_mcp.sh correctly resolves paths.

## Success Criteria

- [ ] ownership_graph.py uses `get_main_repo_root()` for KG cache path
- [ ] All KG writes use fcntl.flock() for exclusive locking
- [ ] propose_ownership() reads + writes INSIDE the lock (no TOCTOU race)
- [ ] Beads database uses WAL mode or equivalent concurrent-safe mode
- [ ] .mcp.json commands work from both main repo and worktree directories
- [ ] Two agents calling propose_ownership() simultaneously don't lose data

## Verification

```bash
# Test 1: KG path resolution from worktree
cd ~/agents/test-agent/  # (create a test worktree first)
python3 -c "
import subprocess
git_common = subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], text=True).strip()
print(f'Git common dir: {git_common}')
# Should point to main repo's .git, not worktree's
"

# Test 2: Concurrent KG writes
# Run two propose_ownership calls in parallel, verify both succeed
python3 -c "
import subprocess, threading

def register(name):
    subprocess.run(['python3', '.claude/mcp/ownership_graph.py', '--test-register', f'test_{name}.py', 'test-agent'])

t1 = threading.Thread(target=register, args=('file_a',))
t2 = threading.Thread(target=register, args=('file_b',))
t1.start(); t2.start()
t1.join(); t2.join()
print('Both registrations completed without error')
"
```
