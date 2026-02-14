#!/usr/bin/env python3
"""
Ownership Knowledge Graph MCP Server

Self-contained MCP server for querying the ownership graph.
Loads graph from agent_graph_cache.json - no external dependencies.

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


# Load graph on startup
CACHE_FILE = Path(__file__).parent.parent / "kg" / "agent_graph_cache.json"
PROPOSALS_FILE = Path(__file__).parent.parent / "kg" / "proposals.json"

# Simple graph structure (avoiding NetworkX for Python 3.14 compatibility)
nodes_data: dict = {}
predecessors: dict = {}  # node -> list of upstream nodes
successors: dict = {}    # node -> list of downstream nodes
edges_data: dict = {}    # (from, to) -> edge data


def load_graph():
    """Load graph from cache file into simple dict structure."""
    global nodes_data, predecessors, successors, edges_data

    if not CACHE_FILE.exists():
        raise FileNotFoundError(f"Graph cache not found: {CACHE_FILE}")

    with open(CACHE_FILE, "r") as f:
        cache = json.load(f)

    # Clear and rebuild
    nodes_data = {}
    predecessors = {}
    successors = {}
    edges_data = {}

    # Add nodes
    for node in cache["nodes"]:
        node_id = node["id"]
        nodes_data[node_id] = node
        predecessors[node_id] = []
        successors[node_id] = []

    # Add edges
    for edge in cache["edges"]:
        from_node = edge["from"]
        to_node = edge["to"]

        # Ensure nodes exist in adjacency lists
        if from_node not in predecessors:
            predecessors[from_node] = []
        if from_node not in successors:
            successors[from_node] = []
        if to_node not in predecessors:
            predecessors[to_node] = []
        if to_node not in successors:
            successors[to_node] = []

        predecessors[to_node].append(from_node)
        successors[from_node].append(to_node)

        edges_data[(from_node, to_node)] = {
            "type": edge.get("type", "RELATES_TO"),
            "dependency_type": edge.get("dependency_type", ""),
            "inferred_from": edge.get("inferred_from", ""),
        }

    return cache["metadata"]


def get_node_info(node_id: str) -> dict:
    """Get node info dict."""
    if node_id not in nodes_data:
        return {"id": node_id, "type": "unknown"}
    return dict(nodes_data[node_id])


def get_agent_module(agent_id: str) -> str | None:
    """Get the module an agent manages."""
    if agent_id not in nodes_data:
        return None
    node = nodes_data[agent_id]
    if node.get("type") != "agent":
        return None
    return node.get("module")


def get_module_for_file(file_path: str) -> str | None:
    """Try to infer which module a file belongs to based on path patterns.

    This is a heuristic: check if any module name (without '-module' suffix)
    appears in the file path.
    """
    path_lower = file_path.lower()
    for nid, node in nodes_data.items():
        if node.get("type") == "module":
            # Extract the domain name from the module id (e.g., 'identity' from 'identity-module')
            domain = nid.replace("-module", "")
            if domain in path_lower:
                return nid
    return None


def bfs_blast_radius(start: str, max_depth: int = 5) -> dict:
    """BFS from a node following BOTH successors AND predecessors for
    OWNS/MANAGES/IMPLEMENTS edges, and successors for all edge types.
    Returns categorized affected nodes."""
    if start not in nodes_data and start not in edges_data:
        return {"affected_files": [], "affected_agents": [], "affected_modules": [], "affected_concepts": []}

    visited = set()
    affected = {"file": [], "agent": [], "module": [], "concept": []}
    queue = deque([(start, 0)])

    while queue:
        node, depth = queue.popleft()
        if node in visited or depth > max_depth:
            continue
        visited.add(node)

        if node != start and node in nodes_data:
            node_type = nodes_data[node].get("type", "unknown")
            info = {"id": node, "depth": depth, "type": node_type}
            if node_type in affected:
                affected[node_type].append(info)

        if depth < max_depth:
            # Follow successors (all edges)
            for succ in successors.get(node, []):
                if succ not in visited:
                    queue.append((succ, depth + 1))

            # Follow predecessors for ownership/structural edges
            # (if something OWNS/MANAGES/IMPLEMENTS this node, it's affected)
            for pred in predecessors.get(node, []):
                if pred not in visited:
                    edge = edges_data.get((pred, node), {})
                    etype = edge.get("type", "")
                    if etype in ("OWNS", "MANAGES", "IMPLEMENTS", "DEPENDS_ON", "PARENT_OF"):
                        queue.append((pred, depth + 1))

    return {
        "affected_files": affected["file"],
        "affected_agents": affected["agent"],
        "affected_modules": affected["module"],
        "affected_concepts": affected["concept"],
    }


def bfs_shortest_path(start: str, end: str) -> list:
    """BFS to find shortest path between two nodes (following all edges bidirectionally)."""
    if start not in nodes_data or end not in nodes_data:
        return []
    if start == end:
        return [start]

    visited = {start}
    queue = deque([(start, [start])])

    while queue:
        node, path = queue.popleft()

        # Check successors
        for succ in successors.get(node, []):
            if succ == end:
                return path + [succ]
            if succ not in visited:
                visited.add(succ)
                queue.append((succ, path + [succ]))

        # Check predecessors (bidirectional search)
        for pred in predecessors.get(node, []):
            if pred == end:
                return path + [pred]
            if pred not in visited:
                visited.add(pred)
                queue.append((pred, path + [pred]))

    return []


def save_cache():
    """Persist the current in-memory graph back to agent_graph_cache.json."""
    nodes_list = list(nodes_data.values())
    edges_list = []
    for (f, t), edata in edges_data.items():
        edge = {"from": f, "to": t, "type": edata.get("type", "RELATES_TO")}
        if edata.get("dependency_type"):
            edge["dependency_type"] = edata["dependency_type"]
        if edata.get("inferred_from"):
            edge["inferred_from"] = edata["inferred_from"]
        edges_list.append(edge)

    cache = {
        "metadata": {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
            "agent_count": sum(1 for n in nodes_data.values() if n.get("type") == "agent"),
            "module_count": sum(1 for n in nodes_data.values() if n.get("type") == "module"),
            "concept_count": sum(1 for n in nodes_data.values() if n.get("type") == "concept"),
            "builder_version": "1.0",
        },
        "nodes": nodes_list,
        "edges": edges_list,
    }

    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


# Create MCP server
server = Server("ownership-graph")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_file_owner",
            description="Get the agent that owns a file. Use to check ownership before editing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (e.g., 'src/api/users.py')"},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="get_agent_files",
            description="Get all files owned by an agent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent ID (e.g., 'identity-agent')"},
                },
                "required": ["agent"],
            },
        ),
        Tool(
            name="get_agent_context",
            description="Full agent context: identity, ownership, relationships, domain, safety. THE most important tool - call this first when an agent wakes up.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent ID (e.g., 'identity-agent')"},
                },
                "required": ["agent"],
            },
        ),
        Tool(
            name="search_agents",
            description="Search agents by name, capability, or module.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term (e.g., 'auth', 'sms', 'content')"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_blast_radius",
            description="Calculate impact - what agents, files, modules, concepts are affected by changing this node.",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "Any node ID - agent, module, concept, or file path"},
                    "max_depth": {"type": "integer", "description": "Max BFS depth (1-10)", "default": 5},
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="get_dependencies",
            description="Get upstream agents this agent depends on.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent ID"},
                },
                "required": ["agent"],
            },
        ),
        Tool(
            name="get_dependents",
            description="Get downstream agents that depend on this agent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent ID"},
                },
                "required": ["agent"],
            },
        ),
        Tool(
            name="get_dependency_path",
            description="Find the shortest path between two agents. Uses BFS over all edge types.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_agent": {"type": "string", "description": "Source agent ID"},
                    "to_agent": {"type": "string", "description": "Target agent ID"},
                },
                "required": ["from_agent", "to_agent"],
            },
        ),
        Tool(
            name="get_module_decomposition",
            description="Get all files and sub-modules within a module.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "Module ID (e.g., 'identity-module')"},
                },
                "required": ["module"],
            },
        ),
        Tool(
            name="propose_ownership",
            description="Propose that an agent owns a file. Does HOT UPDATE to in-memory graph and persists to disk. Auto-approves if file is in agent's module.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "File path to register ownership for"},
                    "agent": {"type": "string", "description": "Agent ID that should own the file"},
                    "evidence": {"type": "string", "description": "Why this agent should own this file"},
                },
                "required": ["file", "agent", "evidence"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "get_file_owner":
            return _get_file_owner(arguments)
        elif name == "get_agent_files":
            return _get_agent_files(arguments)
        elif name == "get_agent_context":
            return _get_agent_context(arguments)
        elif name == "search_agents":
            return _search_agents(arguments)
        elif name == "get_blast_radius":
            return _get_blast_radius(arguments)
        elif name == "get_dependencies":
            return _get_dependencies(arguments)
        elif name == "get_dependents":
            return _get_dependents(arguments)
        elif name == "get_dependency_path":
            return _get_dependency_path(arguments)
        elif name == "get_module_decomposition":
            return _get_module_decomposition(arguments)
        elif name == "propose_ownership":
            return _propose_ownership(arguments)
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


# ── Tool Implementations ────────────────────────────────────────────────────


def _get_file_owner(arguments: dict) -> list[TextContent]:
    """Find which agent owns a given file path."""
    path = arguments["path"]

    # Check if file exists as a node in the graph
    if path in nodes_data:
        node = nodes_data[path]
        # Find who OWNS this file (predecessor with OWNS edge)
        owner = None
        module = None
        locked_by = node.get("locked_by")
        for pred in predecessors.get(path, []):
            edge = edges_data.get((pred, path), {})
            if edge.get("type") == "OWNS":
                owner_node = nodes_data.get(pred, {})
                if owner_node.get("type") == "agent":
                    owner = pred
                    module = owner_node.get("module")
                    break

        if owner:
            result = {
                "file": path,
                "owner": owner,
                "level": nodes_data.get(owner, {}).get("level"),
                "module": module,
                "spec_path": nodes_data.get(owner, {}).get("spec_path"),
                "locked_by": locked_by,
            }
        else:
            result = {
                "file": path,
                "owner": None,
                "message": "File exists in graph but has no owner",
            }
    else:
        # File not in graph yet - try to infer owner from path patterns
        inferred_module = get_module_for_file(path)
        if inferred_module:
            # Find the agent that manages this module
            managing_agent = None
            for pred in predecessors.get(inferred_module, []):
                edge = edges_data.get((pred, inferred_module), {})
                if edge.get("type") == "MANAGES":
                    managing_agent = pred
                    break
            result = {
                "file": path,
                "owner": None,
                "inferred_module": inferred_module,
                "suggested_agent": managing_agent,
                "message": f"File not registered. Suggested owner: {managing_agent} (manages {inferred_module}). Use propose_ownership() to register.",
            }
        else:
            result = {
                "file": path,
                "owner": None,
                "message": "File not found in ownership graph. Use propose_ownership() to register it.",
            }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _get_agent_files(arguments: dict) -> list[TextContent]:
    """Get all files owned by an agent."""
    agent = arguments["agent"]

    if agent not in nodes_data:
        return [TextContent(type="text", text=json.dumps({"error": f"Agent '{agent}' not found in graph"}))]

    if nodes_data[agent].get("type") != "agent":
        return [TextContent(type="text", text=json.dumps({"error": f"'{agent}' is not an agent (type: {nodes_data[agent].get('type')})"}))]

    files = []
    for succ in successors.get(agent, []):
        edge = edges_data.get((agent, succ), {})
        if edge.get("type") == "OWNS":
            node = nodes_data.get(succ, {})
            files.append({
                "id": succ,
                "language": node.get("language", ""),
                "module": get_agent_module(agent),
            })

    result = {
        "agent": agent,
        "file_count": len(files),
        "files": files,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _get_agent_context(arguments: dict) -> list[TextContent]:
    """THE most important tool. Returns everything an agent needs to start working."""
    agent = arguments["agent"]

    if agent not in nodes_data:
        return [TextContent(type="text", text=json.dumps({"error": f"Agent '{agent}' not found in graph"}))]

    node = nodes_data[agent]
    if node.get("type") != "agent":
        return [TextContent(type="text", text=json.dumps({"error": f"'{agent}' is not an agent (type: {node.get('type')})"}))]

    # ── Identity ──
    identity = {
        "id": agent,
        "level": node.get("level"),
        "parent": node.get("parent"),
        "model_tier": node.get("model_tier"),
        "spec_path": node.get("spec_path"),
        "memory_path": node.get("memory_path"),
        "capabilities": node.get("capabilities", []),
        "status": node.get("status", "idle"),
    }

    # ── Ownership ──
    owned_files = []
    for succ in successors.get(agent, []):
        edge = edges_data.get((agent, succ), {})
        if edge.get("type") == "OWNS":
            owned_files.append({"id": succ, "type": nodes_data.get(succ, {}).get("type", "file")})

    module = node.get("module")
    ownership = {
        "files": owned_files,
        "file_count": len(owned_files),
        "module": module,
    }

    # ── Relationships ──
    # depends_on: agents this agent DEPENDS_ON (outgoing DEPENDS_ON edges)
    depends_on = []
    for succ in successors.get(agent, []):
        edge = edges_data.get((agent, succ), {})
        if edge.get("type") == "DEPENDS_ON":
            depends_on.append({
                "id": succ,
                "dependency_type": edge.get("dependency_type", ""),
                "inferred_from": edge.get("inferred_from", ""),
            })

    # depended_by: agents that DEPEND_ON this agent (incoming DEPENDS_ON edges)
    depended_by = []
    for pred in predecessors.get(agent, []):
        edge = edges_data.get((pred, agent), {})
        if edge.get("type") == "DEPENDS_ON":
            depended_by.append({
                "id": pred,
                "dependency_type": edge.get("dependency_type", ""),
                "inferred_from": edge.get("inferred_from", ""),
            })

    # children: agents this agent is PARENT_OF
    children = []
    for succ in successors.get(agent, []):
        edge = edges_data.get((agent, succ), {})
        if edge.get("type") == "PARENT_OF":
            child_node = nodes_data.get(succ, {})
            children.append({
                "id": succ,
                "level": child_node.get("level"),
                "module": child_node.get("module"),
                "status": child_node.get("status", "idle"),
            })

    relationships = {
        "depends_on": depends_on,
        "depended_by": depended_by,
        "children": children,
    }

    # ── Domain (concepts this agent IMPLEMENTS) ──
    concepts = []
    for succ in successors.get(agent, []):
        edge = edges_data.get((agent, succ), {})
        if edge.get("type") == "IMPLEMENTS":
            concept_node = nodes_data.get(succ, {})
            if concept_node.get("type") == "concept":
                concepts.append({
                    "id": succ,
                    "description": concept_node.get("description", ""),
                    "tables": concept_node.get("tables", []),
                    "domain": concept_node.get("domain", ""),
                })

    domain = {
        "concepts": concepts,
    }

    # ── Safety ──
    safety = node.get("safety", {
        "max_children": 5,
        "timeout_minutes": 120,
        "can_spawn": True,
        "review_required": True,
    })

    result = {
        "identity": identity,
        "ownership": ownership,
        "relationships": relationships,
        "domain": domain,
        "safety": safety,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _search_agents(arguments: dict) -> list[TextContent]:
    """Search agents by name, capability, or module."""
    query = arguments["query"].lower()

    matches = []
    for nid, node in nodes_data.items():
        if node.get("type") != "agent":
            continue

        # Match by agent ID
        if query in nid.lower():
            matches.append({"id": nid, "match_field": "id", "match_value": nid})
            continue

        # Match by capabilities
        capabilities = node.get("capabilities", [])
        for cap in capabilities:
            if query in cap.lower():
                matches.append({"id": nid, "match_field": "capabilities", "match_value": cap})
                break
        else:
            # Match by module name
            module = node.get("module", "")
            if module and query in module.lower():
                matches.append({"id": nid, "match_field": "module", "match_value": module})

    result = {
        "query": arguments["query"],
        "matches": matches,
        "count": len(matches),
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _get_blast_radius(arguments: dict) -> list[TextContent]:
    """BFS blast radius from any node type."""
    node_id = arguments["node_id"]
    max_depth = min(arguments.get("max_depth", 5), 10)

    if node_id not in nodes_data:
        return [TextContent(type="text", text=json.dumps({"error": f"Node '{node_id}' not found in graph"}))]

    affected = bfs_blast_radius(node_id, max_depth)

    total = (
        len(affected["affected_files"])
        + len(affected["affected_agents"])
        + len(affected["affected_modules"])
        + len(affected["affected_concepts"])
    )

    # Severity based on number of agents affected
    agent_count = len(affected["affected_agents"])
    if agent_count >= 4:
        severity = "critical"
    elif agent_count >= 2:
        severity = "high"
    elif agent_count >= 1:
        severity = "medium"
    else:
        severity = "low"

    result = {
        "source": node_id,
        "source_type": nodes_data[node_id].get("type", "unknown"),
        "affected_files": affected["affected_files"],
        "affected_agents": affected["affected_agents"],
        "affected_modules": affected["affected_modules"],
        "affected_concepts": affected["affected_concepts"],
        "total_affected": total,
        "severity": severity,
        "recommended_review": agent_count >= 2 or total >= 5,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _get_dependencies(arguments: dict) -> list[TextContent]:
    """Get upstream agents this agent depends on."""
    agent = arguments["agent"]

    if agent not in nodes_data:
        return [TextContent(type="text", text=json.dumps({"error": f"Agent '{agent}' not found in graph"}))]

    if nodes_data[agent].get("type") != "agent":
        return [TextContent(type="text", text=json.dumps({"error": f"'{agent}' is not an agent"}))]

    depends_on = []
    for succ in successors.get(agent, []):
        edge = edges_data.get((agent, succ), {})
        if edge.get("type") == "DEPENDS_ON":
            depends_on.append({
                "id": succ,
                "dependency_type": edge.get("dependency_type", ""),
                "inferred_from": edge.get("inferred_from", ""),
            })

    result = {
        "agent": agent,
        "depends_on": depends_on,
        "count": len(depends_on),
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _get_dependents(arguments: dict) -> list[TextContent]:
    """Get downstream agents that depend on this agent."""
    agent = arguments["agent"]

    if agent not in nodes_data:
        return [TextContent(type="text", text=json.dumps({"error": f"Agent '{agent}' not found in graph"}))]

    if nodes_data[agent].get("type") != "agent":
        return [TextContent(type="text", text=json.dumps({"error": f"'{agent}' is not an agent"}))]

    depended_by = []
    for pred in predecessors.get(agent, []):
        edge = edges_data.get((pred, agent), {})
        if edge.get("type") == "DEPENDS_ON":
            depended_by.append({
                "id": pred,
                "dependency_type": edge.get("dependency_type", ""),
                "inferred_from": edge.get("inferred_from", ""),
            })

    result = {
        "agent": agent,
        "depended_by": depended_by,
        "count": len(depended_by),
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _get_dependency_path(arguments: dict) -> list[TextContent]:
    """BFS shortest path between two agents."""
    from_agent = arguments["from_agent"]
    to_agent = arguments["to_agent"]

    if from_agent not in nodes_data:
        return [TextContent(type="text", text=json.dumps({"error": f"Agent '{from_agent}' not found in graph"}))]
    if to_agent not in nodes_data:
        return [TextContent(type="text", text=json.dumps({"error": f"Agent '{to_agent}' not found in graph"}))]

    path = bfs_shortest_path(from_agent, to_agent)

    if path:
        # Build edge info for each step
        edges = []
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            # Check both directions for the edge
            edge = edges_data.get((a, b))
            if edge:
                edges.append({"from": a, "to": b, "type": edge.get("type", "UNKNOWN")})
            else:
                edge = edges_data.get((b, a))
                if edge:
                    edges.append({"from": b, "to": a, "type": edge.get("type", "UNKNOWN"), "traversed_reverse": True})
                else:
                    edges.append({"from": a, "to": b, "type": "UNKNOWN"})

        result = {
            "from": from_agent,
            "to": to_agent,
            "path_exists": True,
            "path": path,
            "edges": edges,
            "path_length": len(path) - 1,
        }
    else:
        result = {
            "from": from_agent,
            "to": to_agent,
            "path_exists": False,
            "path": [],
            "edges": [],
            "path_length": 0,
        }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _get_module_decomposition(arguments: dict) -> list[TextContent]:
    """Get all files and sub-modules within a module."""
    module = arguments["module"]

    if module not in nodes_data:
        return [TextContent(type="text", text=json.dumps({"error": f"Module '{module}' not found in graph"}))]

    node = nodes_data[module]
    if node.get("type") != "module":
        return [TextContent(type="text", text=json.dumps({"error": f"'{module}' is not a module (type: {node.get('type')})"}))]

    # Find managing agent (predecessor with MANAGES edge)
    managed_by = None
    for pred in predecessors.get(module, []):
        edge = edges_data.get((pred, module), {})
        if edge.get("type") == "MANAGES":
            managed_by = pred
            break

    # Alternative: check the managed_by field on the node
    if not managed_by:
        managed_by = node.get("managed_by")

    # Find files owned by the managing agent (those are the module's files)
    files = []
    if managed_by:
        for succ in successors.get(managed_by, []):
            edge = edges_data.get((managed_by, succ), {})
            if edge.get("type") == "OWNS":
                file_node = nodes_data.get(succ, {})
                files.append({
                    "id": succ,
                    "language": file_node.get("language", ""),
                })

    # Concepts associated with this module's agent
    concepts = []
    if managed_by:
        for succ in successors.get(managed_by, []):
            edge = edges_data.get((managed_by, succ), {})
            if edge.get("type") == "IMPLEMENTS":
                concept_node = nodes_data.get(succ, {})
                if concept_node.get("type") == "concept":
                    concepts.append({
                        "id": succ,
                        "description": concept_node.get("description", ""),
                        "tables": concept_node.get("tables", []),
                    })

    result = {
        "module": module,
        "managed_by": managed_by,
        "description": node.get("description", ""),
        "files": files,
        "concepts": concepts,
        "sub_modules": node.get("sub_modules", []),
        "total_files": len(files),
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _propose_ownership(arguments: dict) -> list[TextContent]:
    """Propose that an agent owns a file. HOT UPDATE + persist."""
    global nodes_data, predecessors, successors, edges_data

    file_path = arguments["file"]
    agent = arguments["agent"]
    evidence = arguments.get("evidence", "")

    # Validate agent exists
    if agent not in nodes_data:
        return [TextContent(type="text", text=json.dumps({"error": f"Agent '{agent}' not found in graph"}))]
    if nodes_data[agent].get("type") != "agent":
        return [TextContent(type="text", text=json.dumps({"error": f"'{agent}' is not an agent"}))]

    # Check if file already has an owner
    if file_path in nodes_data:
        for pred in predecessors.get(file_path, []):
            edge = edges_data.get((pred, file_path), {})
            if edge.get("type") == "OWNS":
                return [TextContent(type="text", text=json.dumps({
                    "error": f"File '{file_path}' is already owned by '{pred}'. Use transfer instead.",
                    "current_owner": pred,
                }))]

    # Determine if auto-approve: file is in agent's module
    agent_module = get_agent_module(agent)
    file_module = get_module_for_file(file_path)
    auto_approved = agent_module is not None and agent_module == file_module

    # Build proposal record
    proposal = {
        "id": f"prop-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "file": file_path,
        "agent": agent,
        "evidence": evidence,
        "proposed_at": datetime.now(timezone.utc).isoformat(),
        "status": "approved" if auto_approved else "pending",
        "auto_approved": auto_approved,
        "reason": f"File is within agent's module ({agent_module})" if auto_approved else "Requires human review (file not in agent's module)",
    }

    # Save to proposals.json
    proposals = []
    if PROPOSALS_FILE.exists():
        with open(PROPOSALS_FILE, "r") as f:
            try:
                proposals = json.load(f)
            except json.JSONDecodeError:
                proposals = []

    proposals.append(proposal)

    with open(PROPOSALS_FILE, "w") as f:
        json.dump(proposals, f, indent=2)

    # HOT UPDATE: add file node and OWNS edge to in-memory graph
    # Always do the hot update (even for pending) so the agent can work immediately
    if file_path not in nodes_data:
        nodes_data[file_path] = {
            "id": file_path,
            "type": "file",
            "language": _infer_language(file_path),
            "module": agent_module,
            "locked_by": None,
        }
        predecessors[file_path] = []
        successors[file_path] = []

    # Add OWNS edge
    predecessors[file_path].append(agent)
    successors[agent].append(file_path)
    edges_data[(agent, file_path)] = {
        "type": "OWNS",
        "dependency_type": "",
        "inferred_from": evidence,
    }

    # Persist updated graph to cache file
    save_cache()

    result = {
        "status": "approved" if auto_approved else "pending",
        "file": file_path,
        "agent": agent,
        "auto_approved": auto_approved,
        "reason": proposal["reason"],
        "proposal_id": proposal["id"],
        "hot_updated": True,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def _infer_language(file_path: str) -> str:
    """Infer programming language from file extension."""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".php": "php",
        ".rb": "ruby",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".sh": "bash",
        ".sql": "sql",
        ".md": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".vue": "vue",
        ".css": "css",
        ".html": "html",
    }
    for ext, lang in ext_map.items():
        if file_path.endswith(ext):
            return lang
    return ""


async def main():
    import sys
    metadata = load_graph()
    print(
        f"Loaded ownership graph: {metadata['node_count']} nodes, "
        f"{metadata['edge_count']} edges, "
        f"{metadata['agent_count']} agents, "
        f"{metadata['module_count']} modules, "
        f"{metadata['concept_count']} concepts",
        file=sys.stderr,
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
