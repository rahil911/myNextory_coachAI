# Phase 3a: Ownership Graph MCP Server Builder

## Purpose

Build the `ownership_graph.py` MCP server — the PRIMARY tool every agent uses to understand the codebase. This server provides 10 tools for querying file ownership, agent context, blast radius, dependencies, and proposals.

**CRITICAL**: Mirror the causal-graph MCP server pattern EXACTLY. Same data structures (dict-based, no NetworkX), same BFS traversal, same TextContent JSON responses.

## Phase Info

- **Phase**: 3a (parallel with 3b, 3c, 3d — runs after Phase 2 gate)
- **Estimated time**: 45-60 minutes
- **Model tier**: Sonnet

## Input Contract

- **File**: `.claude/kg/agent_graph_cache.json` (from Phase 2a)
- **Reference**: `~/Projects/decision-canvas-os/.claude/mcp/causal_graph.py` (MUST read this)

## Output Contract

- **File**: `.claude/mcp/ownership_graph.py`
- **Tools**: 10 MCP tools (listed below)
- **Protocol**: MCP stdio transport

## Reference Architecture

**CRITICAL**: Before writing any code, READ the reference implementation:

```bash
cat ~/Projects/decision-canvas-os/.claude/mcp/causal_graph.py
```

Your server MUST follow the same patterns:
- `mcp.server.Server` with `stdio_server`
- Dict-based graph: `nodes_data`, `predecessors`, `successors`, `edges_data`
- `load_graph()` from JSON cache file
- BFS with `deque` from `collections`
- `TextContent` with JSON for all responses
- `@server.list_tools()` and `@server.call_tool()` handlers

## Tools to Implement (10 total)

### 1. get_file_owner(path: str)
Returns the agent that owns this file.

```json
// Input: {"path": "src/api/users.py"}
// Output:
{
  "file": "src/api/users.py",
  "owner": "api-agent",
  "level": 1,
  "module": "api-module",
  "spec_path": ".claude/agents/api-agent/agent.md",
  "locked_by": null
}
```

### 2. get_agent_files(agent: str)
Returns all files owned by an agent.

```json
// Input: {"agent": "api-agent"}
// Output:
{
  "agent": "api-agent",
  "file_count": 15,
  "files": [
    {"id": "src/api/users.py", "language": "python", "module": "api-module"}
  ]
}
```

### 3. get_agent_context(agent: str)
**THE MOST IMPORTANT TOOL.** Returns everything an agent needs to start working.

```json
// Input: {"agent": "api-agent"}
// Output:
{
  "identity": {
    "id": "api-agent",
    "level": 1,
    "parent": "orchestrator",
    "model_tier": "sonnet",
    "spec_path": ".claude/agents/api-agent/agent.md",
    "memory_path": ".claude/agents/api-agent/memory/",
    "capabilities": ["fastapi", "crud", "auth"]
  },
  "ownership": {
    "files": [...],
    "file_count": 15,
    "module": "api-module"
  },
  "relationships": {
    "depends_on": [{"id": "db-agent", "dep_type": "schema"}],
    "depended_by": [{"id": "ui-agent", "dep_type": "api"}],
    "children": []
  },
  "domain": {
    "concepts": [{"id": "User", "tables": [...]}]
  },
  "safety": {
    "max_children": 5,
    "timeout_minutes": 120,
    "can_spawn": true,
    "review_required": true
  }
}
```

### 4. search_agents(query: str)
Search agents by name, capability, or module.

```json
// Input: {"query": "auth"}
// Output:
{
  "query": "auth",
  "matches": [
    {"id": "api-agent", "match_field": "capabilities", "match_value": "auth"},
    {"id": "auth-handler", "match_field": "id", "match_value": "auth-handler"}
  ]
}
```

### 5. get_blast_radius(node_id: str, max_depth: int = 5)
BFS from any node type. Returns everything affected by changing this node.

```json
// Input: {"node_id": "User", "max_depth": 3}
// Output:
{
  "source": "User",
  "affected_files": [...],
  "affected_agents": [...],
  "affected_modules": [...],
  "affected_concepts": [...],
  "total_affected": 12,
  "severity": "high",
  "recommended_review": true
}
```

### 6. get_dependencies(agent: str)
Returns upstream agents this agent depends on.

```json
// Input: {"agent": "api-agent"}
// Output:
{
  "agent": "api-agent",
  "depends_on": [
    {"id": "db-agent", "dependency_type": "schema", "inferred_from": "..."}
  ]
}
```

### 7. get_dependents(agent: str)
Returns downstream agents that depend on this agent.

```json
// Input: {"agent": "db-agent"}
// Output:
{
  "agent": "db-agent",
  "depended_by": [
    {"id": "api-agent", "dependency_type": "schema"},
    {"id": "test-agent", "dependency_type": "testing"}
  ]
}
```

### 8. get_dependency_path(from_agent: str, to_agent: str)
BFS to find the shortest path between two agents.

```json
// Input: {"from_agent": "db-agent", "to_agent": "ui-agent"}
// Output:
{
  "from": "db-agent",
  "to": "ui-agent",
  "path": ["db-agent", "api-agent", "ui-agent"],
  "edges": [
    {"from": "db-agent", "to": "api-agent", "type": "DEPENDS_ON"},
    {"from": "api-agent", "to": "ui-agent", "type": "DEPENDS_ON"}
  ],
  "path_length": 2
}
```

### 9. get_module_decomposition(module: str)
Returns all files and sub-modules within a module.

```json
// Input: {"module": "api-module"}
// Output:
{
  "module": "api-module",
  "managed_by": "api-agent",
  "description": "HTTP API layer",
  "files": [...],
  "sub_modules": [...],
  "total_files": 15
}
```

### 10. propose_ownership(file: str, agent: str, evidence: str)
Propose that an agent owns a file. Does a HOT UPDATE to the in-memory graph AND appends to proposals.json.

```json
// Input: {"file": "src/api/new_endpoint.py", "agent": "api-agent", "evidence": "New file in api module"}
// Output:
{
  "status": "approved",
  "file": "src/api/new_endpoint.py",
  "agent": "api-agent",
  "auto_approved": true,
  "reason": "File is within agent's module (api-module)"
}
```

Auto-approve if the file is within the agent's module. Otherwise, write to proposals.json for human review.

## Implementation Template

```python
#!/usr/bin/env python3
"""
Ownership Knowledge Graph MCP Server

Self-contained MCP server for querying the ownership graph.
Loads graph from agent_graph_cache.json — no external dependencies.

Tools:
- get_file_owner: Who owns this file?
- get_agent_files: What files does an agent own?
- get_agent_context: Full agent context (THE key tool)
- search_agents: Find agents by capability/name
- get_blast_radius: Impact analysis for any node
- get_dependencies: Upstream agents
- get_dependents: Downstream agents
- get_dependency_path: Path between agents
- get_module_decomposition: Module breakdown
- propose_ownership: Register new file ownership

NOTE: Uses simple dict-based graph instead of NetworkX for Python 3.14 compatibility.
"""

import asyncio
import json
from pathlib import Path
from collections import deque
from datetime import datetime, timezone

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


CACHE_FILE = Path(__file__).parent.parent / "kg" / "agent_graph_cache.json"
PROPOSALS_FILE = Path(__file__).parent.parent / "kg" / "proposals.json"

nodes_data: dict = {}
predecessors: dict = {}
successors: dict = {}
edges_data: dict = {}


def load_graph():
    """Load graph from cache file into dict structure."""
    global nodes_data, predecessors, successors, edges_data

    if not CACHE_FILE.exists():
        raise FileNotFoundError(f"Graph cache not found: {CACHE_FILE}")

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


# ... implement all 10 tools following the causal_graph.py pattern ...
# ... BFS traversal for blast_radius and dependency_path ...
# ... Hot updates for propose_ownership ...


server = Server("ownership-graph")

@server.list_tools()
async def list_tools():
    return [
        Tool(name="get_file_owner", description="Get the agent that owns a file", inputSchema={...}),
        Tool(name="get_agent_files", description="Get all files owned by an agent", inputSchema={...}),
        # ... all 10 tools ...
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    # ... dispatch to implementation functions ...
    pass


async def main():
    load_graph()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
```

## Implementation Notes

- **BFS for blast_radius**: Follow BOTH forward (successors) AND reverse (predecessors for OWNS/MANAGES/IMPLEMENTS edges). Same algorithm as the plan.
- **get_agent_context**: Must return ALL relationship types — depends_on, depended_by, children, concepts, owned files. This is the tool agents call FIRST when waking up.
- **propose_ownership HOT UPDATE**: Modify `nodes_data`, `predecessors`, `successors`, `edges_data` in-memory immediately. ALSO append to cache file so the update persists across restarts.
- **Error handling**: If a node/agent doesn't exist, return an error message in TextContent, don't crash.
- **All responses**: Return `[TextContent(type="text", text=json.dumps(result, indent=2))]`

## Success Criteria

1. `.claude/mcp/ownership_graph.py` exists
2. Server starts without errors: `python3 .claude/mcp/ownership_graph.py` (then Ctrl+C)
3. All 10 tools registered in `list_tools()`
4. `get_agent_context("orchestrator")` returns complete context
5. `get_blast_radius("db-agent")` returns affected agents
6. `propose_ownership("new/file.py", "api-agent", "test")` does hot update
7. No NetworkX dependency — pure dict-based graph
8. All responses are TextContent with JSON
