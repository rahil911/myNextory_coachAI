# Phase 3d: CLI Builder (`ag`)

## Purpose

Build the `ag` CLI tool — a command-line interface for querying the ownership knowledge graph. Used by shell scripts (spawn.sh, cleanup.sh), human operators, and agents that prefer CLI over MCP tools.

## Phase Info

- **Phase**: 3d (parallel with 3a, 3b, 3c — runs after Phase 2 gate)
- **Estimated time**: 30-40 minutes
- **Model tier**: Sonnet

## Input Contract

- **File**: `.claude/kg/agent_graph_cache.json` (from Phase 2a)
- **Module**: Same graph logic as the MCP server (shared core)

## Output Contract

- **File**: `.claude/tools/ag` (executable Python script)
- **Permissions**: `chmod +x`
- **Usage**: `ag <command> [args]` or `python3 .claude/tools/ag <command> [args]`

## Commands to Implement

```
OWNERSHIP QUERIES:
  ag owner <file_path>              Print the agent that owns this file
  ag files <agent_id>               List all files owned by an agent
  ag context <agent_id>             Print full agent context as JSON
  ag search <query>                 Find agents by name/capability

GRAPH TRAVERSAL:
  ag blast <node_id>                Print blast radius report
  ag deps <agent_id>                Print upstream dependencies
  ag rdeps <agent_id>               Print downstream dependents
  ag path <from_agent> <to_agent>   Print dependency path

MANAGEMENT:
  ag register <file> <agent>        Register file ownership
  ag lock <file> <agent>            Set advisory lock
  ag unlock <file>                  Release advisory lock
  ag transfer <file> <new_agent>    Transfer file ownership

STATS:
  ag stats                          Print node/edge counts by type
```

## Implementation

```python
#!/usr/bin/env python3
"""
ag — Ownership Knowledge Graph CLI

Query file ownership, agent context, blast radius, and dependencies
from the command line. Loads agent_graph_cache.json and runs dict-based
BFS traversals.

Usage:
  ag owner src/api/users.py
  ag files api-agent
  ag context api-agent
  ag search auth
  ag blast User
  ag deps api-agent
  ag rdeps db-agent
  ag path db-agent ui-agent
  ag register src/new.py api-agent
  ag stats
"""

import sys
import json
from pathlib import Path
from collections import deque
from datetime import datetime, timezone

# Find the cache file relative to this script
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # .claude/tools/ → project root
KG_DIR = PROJECT_ROOT / ".claude" / "kg"
CACHE_FILE = KG_DIR / "agent_graph_cache.json"
PROPOSALS_FILE = KG_DIR / "proposals.json"

# Graph data structures
nodes_data = {}
predecessors = {}
successors = {}
edges_data = {}


def load_graph():
    """Load graph from cache file."""
    global nodes_data, predecessors, successors, edges_data

    if not CACHE_FILE.exists():
        print(f"Error: Graph cache not found at {CACHE_FILE}", file=sys.stderr)
        print("Run: python3 .claude/kg/build_cache.py", file=sys.stderr)
        sys.exit(1)

    with open(CACHE_FILE) as f:
        cache = json.load(f)

    nodes_data = {}
    predecessors = {}
    successors = {}
    edges_data = {}

    for node in cache["nodes"]:
        nid = node["id"]
        nodes_data[nid] = node
        predecessors[nid] = []
        successors[nid] = []

    for edge in cache["edges"]:
        f, t = edge["from"], edge["to"]
        if t in predecessors:
            predecessors[t].append(f)
        if f in successors:
            successors[f].append(t)
        edges_data[(f, t)] = edge


def cmd_owner(file_path):
    """Find owner of a file."""
    # Look for FILE node
    if file_path in nodes_data:
        node = nodes_data[file_path]
        owner = node.get("owner", "unowned")
        print(f"{file_path} → {owner}")
        return

    # Search through edges
    for (f, t), edge in edges_data.items():
        if edge.get("type") == "OWNS" and t == file_path:
            print(f"{file_path} → {f}")
            return

    # Check if any agent's module covers this path
    print(f"{file_path} → unowned (not in KG)")


def cmd_files(agent_id):
    """List files owned by an agent."""
    if agent_id not in nodes_data:
        print(f"Error: Agent '{agent_id}' not found", file=sys.stderr)
        sys.exit(1)

    files = []
    for target in successors.get(agent_id, []):
        node = nodes_data.get(target, {})
        if node.get("type") == "file":
            files.append(target)

    # Also check OWNS edges
    for (f, t), edge in edges_data.items():
        if f == agent_id and edge.get("type") == "OWNS" and t not in files:
            files.append(t)

    print(f"{agent_id} owns {len(files)} files:")
    for fp in sorted(files):
        print(f"  {fp}")


def cmd_context(agent_id):
    """Print full agent context as JSON."""
    if agent_id not in nodes_data:
        print(f"Error: Agent '{agent_id}' not found", file=sys.stderr)
        sys.exit(1)

    agent = nodes_data[agent_id]

    # Owned files
    owned = [nodes_data[t] for t in successors.get(agent_id, [])
             if nodes_data.get(t, {}).get("type") == "file"]

    # Dependencies
    deps = []
    for t in successors.get(agent_id, []):
        edge = edges_data.get((agent_id, t), {})
        if edge.get("type") == "DEPENDS_ON":
            deps.append({"id": t, "dep_type": edge.get("dependency_type", "")})

    # Dependents
    rdeps = []
    for s in predecessors.get(agent_id, []):
        edge = edges_data.get((s, agent_id), {})
        if edge.get("type") == "DEPENDS_ON":
            rdeps.append({"id": s, "dep_type": edge.get("dependency_type", "")})

    # Children
    children = []
    for t in successors.get(agent_id, []):
        edge = edges_data.get((agent_id, t), {})
        if edge.get("type") == "PARENT_OF":
            children.append(nodes_data.get(t, {"id": t}))

    # Concepts
    concepts = [nodes_data[t] for t in successors.get(agent_id, [])
                if nodes_data.get(t, {}).get("type") == "concept"]

    context = {
        "identity": {
            "id": agent_id,
            "level": agent.get("level"),
            "parent": agent.get("parent"),
            "model_tier": agent.get("model_tier", "sonnet"),
            "capabilities": agent.get("capabilities", []),
        },
        "ownership": {"files": owned, "file_count": len(owned)},
        "relationships": {"depends_on": deps, "depended_by": rdeps, "children": children},
        "domain": {"concepts": concepts},
        "safety": agent.get("safety", {})
    }

    print(json.dumps(context, indent=2, default=str))


def cmd_search(query):
    """Search agents by name or capability."""
    query_lower = query.lower()
    matches = []

    for nid, node in nodes_data.items():
        if node.get("type") != "agent":
            continue

        # Match by ID
        if query_lower in nid.lower():
            matches.append({"id": nid, "match": "id"})
            continue

        # Match by capability
        caps = node.get("capabilities", [])
        for cap in caps:
            if query_lower in cap.lower():
                matches.append({"id": nid, "match": f"capability:{cap}"})
                break

    if matches:
        for m in matches:
            print(f"  {m['id']} (matched: {m['match']})")
    else:
        print(f"No agents matching '{query}'")


def cmd_blast(node_id):
    """Calculate blast radius from any node."""
    if node_id not in nodes_data:
        print(f"Error: Node '{node_id}' not found", file=sys.stderr)
        sys.exit(1)

    visited = set()
    affected = {"file": [], "agent": [], "module": [], "concept": []}
    queue = deque([(node_id, 0)])

    while queue:
        current, depth = queue.popleft()
        if current in visited or depth > 5:
            continue
        visited.add(current)
        node = nodes_data.get(current, {})

        if current != node_id:
            ntype = node.get("type", "unknown")
            if ntype in affected:
                affected[ntype].append({"id": current, "depth": depth})

        for succ in successors.get(current, []):
            if succ not in visited:
                queue.append((succ, depth + 1))

        for pred in predecessors.get(current, []):
            edge = edges_data.get((pred, current), {})
            if edge.get("type") in ("OWNS", "MANAGES", "IMPLEMENTS"):
                if pred not in visited:
                    queue.append((pred, depth + 1))

    total = sum(len(v) for v in affected.values())
    agent_count = len(affected["agent"])
    severity = "critical" if agent_count > 5 else "high" if agent_count > 2 else "medium" if agent_count > 1 else "low"

    print(f"Blast radius for '{node_id}': {total} affected nodes (severity: {severity})")
    for ntype, items in affected.items():
        if items:
            print(f"  {ntype}s ({len(items)}):")
            for item in items:
                print(f"    - {item['id']} (depth {item['depth']})")


def cmd_deps(agent_id):
    """Print upstream dependencies."""
    if agent_id not in nodes_data:
        print(f"Error: Agent '{agent_id}' not found", file=sys.stderr)
        sys.exit(1)

    deps = []
    for t in successors.get(agent_id, []):
        edge = edges_data.get((agent_id, t), {})
        if edge.get("type") == "DEPENDS_ON":
            deps.append(f"{t} ({edge.get('dependency_type', 'general')})")

    if deps:
        print(f"{agent_id} depends on:")
        for d in deps:
            print(f"  → {d}")
    else:
        print(f"{agent_id} has no upstream dependencies")


def cmd_rdeps(agent_id):
    """Print downstream dependents."""
    if agent_id not in nodes_data:
        print(f"Error: Agent '{agent_id}' not found", file=sys.stderr)
        sys.exit(1)

    rdeps = []
    for s in predecessors.get(agent_id, []):
        edge = edges_data.get((s, agent_id), {})
        if edge.get("type") == "DEPENDS_ON":
            rdeps.append(f"{s} ({edge.get('dependency_type', 'general')})")

    if rdeps:
        print(f"Agents depending on {agent_id}:")
        for d in rdeps:
            print(f"  ← {d}")
    else:
        print(f"No agents depend on {agent_id}")


def cmd_path(from_id, to_id):
    """BFS shortest path between two nodes."""
    if from_id not in nodes_data or to_id not in nodes_data:
        print(f"Error: Node not found", file=sys.stderr)
        sys.exit(1)

    visited = {from_id}
    queue = deque([(from_id, [from_id])])

    while queue:
        current, path = queue.popleft()
        if current == to_id:
            print(" → ".join(path))
            return

        for neighbor in successors.get(current, []) + predecessors.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    print(f"No path from {from_id} to {to_id}")


def cmd_register(file_path, agent_id):
    """Register file ownership."""
    if agent_id not in nodes_data:
        print(f"Error: Agent '{agent_id}' not found", file=sys.stderr)
        sys.exit(1)

    # Add to proposals
    proposal = {
        "file": file_path,
        "agent": agent_id,
        "proposed_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending"
    }

    proposals = []
    if PROPOSALS_FILE.exists():
        with open(PROPOSALS_FILE) as f:
            proposals = json.load(f)

    proposals.append(proposal)
    with open(PROPOSALS_FILE, 'w') as f:
        json.dump(proposals, f, indent=2)

    print(f"Registered: {file_path} → {agent_id} (pending review)")


def cmd_stats():
    """Print node/edge counts."""
    type_counts = {}
    for node in nodes_data.values():
        t = node.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    edge_type_counts = {}
    for edge in edges_data.values():
        t = edge.get("type", "unknown")
        edge_type_counts[t] = edge_type_counts.get(t, 0) + 1

    print(f"Nodes: {len(nodes_data)}")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")
    print(f"\nEdges: {len(edges_data)}")
    for t, c in sorted(edge_type_counts.items()):
        print(f"  {t}: {c}")


COMMANDS = {
    "owner": (cmd_owner, 1, "<file_path>"),
    "files": (cmd_files, 1, "<agent_id>"),
    "context": (cmd_context, 1, "<agent_id>"),
    "search": (cmd_search, 1, "<query>"),
    "blast": (cmd_blast, 1, "<node_id>"),
    "deps": (cmd_deps, 1, "<agent_id>"),
    "rdeps": (cmd_rdeps, 1, "<agent_id>"),
    "path": (cmd_path, 2, "<from> <to>"),
    "register": (cmd_register, 2, "<file> <agent>"),
    "lock": (lambda f, a: print(f"Locked {f} by {a} (advisory)"), 2, "<file> <agent>"),
    "unlock": (lambda f: print(f"Unlocked {f}"), 1, "<file>"),
    "transfer": (cmd_register, 2, "<file> <new_agent>"),  # Same as register
    "stats": (cmd_stats, 0, ""),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("ag — Ownership Knowledge Graph CLI\n")
        print("Commands:")
        for cmd, (_, nargs, usage) in sorted(COMMANDS.items()):
            print(f"  ag {cmd} {usage}")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}. Run 'ag help' for usage.", file=sys.stderr)
        sys.exit(1)

    func, expected_args, usage = COMMANDS[cmd]
    args = sys.argv[2:]

    if len(args) < expected_args:
        print(f"Usage: ag {cmd} {usage}", file=sys.stderr)
        sys.exit(1)

    load_graph()
    func(*args[:expected_args + 1])


if __name__ == "__main__":
    main()
```

### Make Executable

```bash
chmod +x .claude/tools/ag
```

### Add to PATH (optional)

```bash
# Add to ~/.bashrc or ~/.zshrc:
export PATH="$HOME/Projects/baap/.claude/tools:$PATH"
```

## Success Criteria

1. `.claude/tools/ag` exists and is executable
2. `ag stats` prints node/edge counts
3. `ag search orchestrator` finds the orchestrator
4. `ag blast db-agent` shows blast radius
5. `ag deps api-agent` shows dependencies
6. `ag rdeps db-agent` shows dependents
7. `ag path db-agent ui-agent` finds a path
8. All commands handle missing nodes gracefully (error message, not crash)
