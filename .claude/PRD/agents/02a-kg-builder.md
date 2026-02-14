# Phase 2a: Knowledge Graph Builder

## Purpose

Build the Ownership Knowledge Graph from Phase 1 discovery data. Create the core graph structure with AGENT, FILE, MODULE nodes and all relationship edges. Output seed CSVs and the `agent_graph_cache.json` that the MCP server loads.

This is the MOST CRITICAL component of the entire system. The KG is what makes agents intelligent — it gives every agent full context in a single query.

## Phase Info

- **Phase**: 2a (parallel with 2b — runs after Phase 1 gate)
- **Estimated time**: 30-45 minutes
- **Model tier**: Sonnet

## Input Contract

- **File**: `.claude/discovery/schema.json` (from Phase 1a)
- **File**: `.claude/discovery/relationships.json` (from Phase 1b)
- **File**: `.claude/discovery/profile.json` (from Phase 1c)

## Output Contract

- **File**: `.claude/kg/agent_graph_cache.json`
- **Files**: `.claude/kg/seeds/agents.csv`, `files.csv`, `modules.csv`, `edges.csv`
- **File**: `.claude/kg/proposals.json` (empty initial)
- **Script**: `.claude/kg/build_cache.py` (rebuilds cache from seeds)

### agent_graph_cache.json Schema

```json
{
  "metadata": {
    "built_at": "2026-02-13T10:00:00Z",
    "node_count": 300,
    "edge_count": 500,
    "agent_count": 8,
    "file_count": 0,
    "module_count": 10,
    "concept_count": 0,
    "builder_version": "1.0"
  },
  "nodes": [
    {
      "id": "orchestrator",
      "type": "agent",
      "level": 0,
      "parent": null,
      "spec_path": ".claude/agents/orchestrator/agent.md",
      "memory_path": ".claude/agents/orchestrator/memory/",
      "capabilities": ["planning", "blast-radius", "dispatch", "monitoring"],
      "model_tier": "opus",
      "status": "idle",
      "module": null,
      "safety": {
        "max_children": 10,
        "timeout_minutes": null,
        "can_spawn": true,
        "review_required": false
      }
    },
    {
      "id": "db-module",
      "type": "module",
      "description": "Database layer — models, migrations, seeds",
      "managed_by": "db-agent",
      "file_count": 0,
      "sub_modules": []
    }
  ],
  "edges": [
    {
      "from": "api-agent",
      "to": "db-agent",
      "type": "DEPENDS_ON",
      "dependency_type": "schema",
      "inferred_from": "api-module imports from db-module"
    },
    {
      "from": "orchestrator",
      "to": "db-agent",
      "type": "PARENT_OF"
    }
  ]
}
```

## Step-by-Step Instructions

### 1. Create Directory Structure

```bash
mkdir -p ~/Projects/baap/.claude/kg/seeds
```

### 2. Analyze Discovery Data to Determine Module Decomposition

Read the schema and profile data to identify natural module boundaries. Group tables by:

- **Naming prefix**: `user_*`, `order_*`, `product_*` → separate modules
- **Relationship clusters**: Tables connected by FKs form modules
- **Domain semantics**: Auth tables, payment tables, inventory tables, etc.

A good rule of thumb: **5-8 modules** for a 200-table database. Each module gets one L1 agent.

### 3. Define Agent Architecture

Based on the modules discovered, create these agents:

```
REQUIRED AGENTS:
  orchestrator   (L0) — human-facing, creates beads, monitors
  db-agent       (L1) — owns database models, migrations, seeds
  api-agent      (L1) — owns API endpoints
  ui-agent       (L1) — owns frontend components
  test-agent     (L1) — owns test files
  kg-agent       (L1) — owns KG infrastructure (.claude/kg/, .claude/mcp/)
  review-agent   (L1) — reviews code before merge (Opus tier)

DYNAMIC AGENTS (based on discovery):
  Based on table groupings, you may add domain-specific L1 agents:
  e.g., auth-agent, payments-agent, inventory-agent, etc.

  Keep total L1 agents between 5-10 for manageability.
```

### 4. Create Seed CSVs

#### agents.csv
```csv
id,type,level,parent,spec_path,memory_path,capabilities,model_tier,module
orchestrator,agent,0,,".claude/agents/orchestrator/agent.md",".claude/agents/orchestrator/memory/","planning,blast-radius,dispatch,monitoring",opus,
db-agent,agent,1,orchestrator,".claude/agents/db-agent/agent.md",".claude/agents/db-agent/memory/","mariadb,sql,migrations,models",sonnet,db-module
api-agent,agent,1,orchestrator,".claude/agents/api-agent/agent.md",".claude/agents/api-agent/memory/","fastapi,rest,crud,auth",sonnet,api-module
ui-agent,agent,1,orchestrator,".claude/agents/ui-agent/agent.md",".claude/agents/ui-agent/memory/","react,nextjs,components,pages",sonnet,ui-module
test-agent,agent,1,orchestrator,".claude/agents/test-agent/agent.md",".claude/agents/test-agent/memory/","pytest,testing,fixtures",sonnet,test-module
kg-agent,agent,1,orchestrator,".claude/agents/kg-agent/agent.md",".claude/agents/kg-agent/memory/","knowledge-graph,mcp,cli",sonnet,kg-module
review-agent,agent,1,orchestrator,".claude/agents/review-agent/agent.md",".claude/agents/review-agent/memory/","code-review,security,quality",opus,
```

#### modules.csv
```csv
id,type,description,managed_by
db-module,module,"Database layer — models, migrations, seeds, schema",db-agent
api-module,module,"HTTP API layer — FastAPI endpoints, middleware, auth",api-agent
ui-module,module,"Frontend — React/Next.js components, pages, styles",ui-agent
test-module,module,"Test suite — unit, integration, e2e tests",test-agent
kg-module,module,"Knowledge graph infrastructure — MCP servers, CLI, seeds",kg-agent
```

Add additional modules based on discovery (e.g., `auth-module`, `payments-module`).

#### edges.csv
```csv
from,to,type,dependency_type,inferred_from
orchestrator,db-agent,PARENT_OF,,
orchestrator,api-agent,PARENT_OF,,
orchestrator,ui-agent,PARENT_OF,,
orchestrator,test-agent,PARENT_OF,,
orchestrator,kg-agent,PARENT_OF,,
orchestrator,review-agent,PARENT_OF,,
api-agent,db-agent,DEPENDS_ON,schema,"api-module imports from db-module"
ui-agent,api-agent,DEPENDS_ON,api,"ui-module calls api-module endpoints"
test-agent,api-agent,DEPENDS_ON,testing,"test-module tests api-module"
test-agent,db-agent,DEPENDS_ON,testing,"test-module tests db-module"
```

Add edges based on relationships.json — if tables in module A reference tables in module B, then agent A DEPENDS_ON agent B.

### 5. Write build_cache.py

This script reads seed CSVs and produces `agent_graph_cache.json`. Pattern: same as `build_cache.py` in decision-canvas-os.

```python
#!/usr/bin/env python3
"""Build agent_graph_cache.json from seed CSV files."""

import csv
import json
from pathlib import Path
from datetime import datetime, timezone

KG_DIR = Path(__file__).parent
SEEDS_DIR = KG_DIR / "seeds"
CACHE_FILE = KG_DIR / "agent_graph_cache.json"


def load_csv(filename):
    """Load a CSV file and return list of dicts."""
    filepath = SEEDS_DIR / filename
    if not filepath.exists():
        print(f"Warning: {filepath} not found, skipping")
        return []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        return list(reader)


def build_cache():
    nodes = []
    edges_list = []

    # Load agents
    agents = load_csv("agents.csv")
    for a in agents:
        capabilities = [c.strip() for c in a.get('capabilities', '').split(',') if c.strip()]
        node = {
            "id": a['id'],
            "type": "agent",
            "level": int(a.get('level', 1)),
            "parent": a.get('parent') or None,
            "spec_path": a.get('spec_path', ''),
            "memory_path": a.get('memory_path', ''),
            "capabilities": capabilities,
            "model_tier": a.get('model_tier', 'sonnet'),
            "status": "idle",
            "module": a.get('module') or None,
            "safety": {
                "max_children": 10 if int(a.get('level', 1)) == 0 else 5,
                "timeout_minutes": None if int(a.get('level', 1)) == 0 else [None, 120, 60, 30][min(int(a.get('level', 1)), 3)],
                "can_spawn": True,
                "review_required": int(a.get('level', 1)) >= 1
            }
        }
        nodes.append(node)

    # Load modules
    modules = load_csv("modules.csv")
    for m in modules:
        node = {
            "id": m['id'],
            "type": "module",
            "description": m.get('description', ''),
            "managed_by": m.get('managed_by', ''),
            "file_count": 0,
            "sub_modules": []
        }
        nodes.append(node)

        # Auto-create MANAGES edge
        if m.get('managed_by'):
            edges_list.append({
                "from": m['managed_by'],
                "to": m['id'],
                "type": "MANAGES"
            })

    # Load concepts (if exists)
    concepts = load_csv("concepts.csv")
    for c in concepts:
        tables = [t.strip() for t in c.get('tables', '').split(',') if t.strip()]
        related = [r.strip() for r in c.get('related_concepts', '').split(',') if r.strip()]
        agents_involved = [a.strip() for a in c.get('agents_involved', '').split(',') if a.strip()]
        node = {
            "id": c['id'],
            "type": "concept",
            "description": c.get('description', ''),
            "tables": tables,
            "domain": c.get('domain', ''),
            "related_concepts": related,
            "agents_involved": agents_involved
        }
        nodes.append(node)

        # Auto-create IMPLEMENTS edges
        for agent_id in agents_involved:
            edges_list.append({
                "from": agent_id,
                "to": c['id'],
                "type": "IMPLEMENTS"
            })

        # Auto-create RELATES_TO edges
        for related_id in related:
            edges_list.append({
                "from": c['id'],
                "to": related_id,
                "type": "RELATES_TO"
            })

    # Load explicit edges
    explicit_edges = load_csv("edges.csv")
    for e in explicit_edges:
        edge = {
            "from": e['from'],
            "to": e['to'],
            "type": e.get('type', 'DEPENDS_ON')
        }
        if e.get('dependency_type'):
            edge['dependency_type'] = e['dependency_type']
        if e.get('inferred_from'):
            edge['inferred_from'] = e['inferred_from']
        edges_list.append(edge)

    # Deduplicate edges
    seen = set()
    unique_edges = []
    for e in edges_list:
        key = (e['from'], e['to'], e['type'])
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)

    # Count by type
    type_counts = {}
    for n in nodes:
        t = n['type']
        type_counts[t] = type_counts.get(t, 0) + 1

    cache = {
        "metadata": {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "node_count": len(nodes),
            "edge_count": len(unique_edges),
            **{f"{k}_count": v for k, v in type_counts.items()},
            "builder_version": "1.0"
        },
        "nodes": nodes,
        "edges": unique_edges
    }

    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)

    m = cache['metadata']
    print(f"Built KG: {m['node_count']} nodes, {m['edge_count']} edges")
    for k, v in type_counts.items():
        print(f"  {k}: {v}")
    print(f"Written to {CACHE_FILE}")


if __name__ == '__main__':
    build_cache()
```

### 6. Run Build and Validate

```bash
cd ~/Projects/baap
python3 .claude/kg/build_cache.py

python3 -c "
import json
d = json.load(open('.claude/kg/agent_graph_cache.json'))
m = d['metadata']
print(f'Nodes: {m[\"node_count\"]}')
print(f'Edges: {m[\"edge_count\"]}')
assert m['node_count'] > 0, 'No nodes!'
assert m['edge_count'] > 0, 'No edges!'
print('KG cache validated')
"
```

### 7. Initialize Empty Proposals File

```bash
echo '[]' > ~/Projects/baap/.claude/kg/proposals.json
```

## Success Criteria

1. `.claude/kg/agent_graph_cache.json` exists and is valid JSON
2. `metadata.node_count` > 0
3. `metadata.edge_count` > 0
4. At least 5 agent nodes (orchestrator + domain agents)
5. At least 3 module nodes
6. PARENT_OF edges from orchestrator to all L1 agents
7. DEPENDS_ON edges reflecting module dependencies
8. MANAGES edges from agents to their modules
9. `build_cache.py` can be re-run to rebuild the cache from seeds
10. `proposals.json` initialized as empty array

## Key Design Decisions

- **Node IDs are lowercase, kebab-case**: `db-agent`, `api-module`, not `DB_Agent`
- **Agent capabilities are lowercase, comma-separated**: `"fastapi,crud,auth"`
- **Module descriptions are human-readable**: used by agents to understand scope
- **Edge types are UPPERCASE**: `DEPENDS_ON`, `PARENT_OF`, `OWNS`, `MANAGES`
- **Safety limits baked into agent nodes**: timeouts, max_children, review gates

## Reference

Study the causal-graph MCP server at `~/Projects/decision-canvas-os/.claude/mcp/causal_graph.py` for the exact dict-based graph pattern to mirror. The ownership KG uses the same data structure (nodes_data, predecessors, successors, edges_data).
