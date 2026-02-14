#!/usr/bin/env python3
"""Build agent_graph_cache.json from seed CSV files.

Reads seed CSVs (agents.csv, modules.csv, files.csv, edges.csv, and
optionally concepts.csv from Phase 2b) and produces the unified
agent_graph_cache.json that the MCP server loads.

Usage:
    python3 .claude/kg/build_cache.py
"""

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
        level = int(a.get('level', 1))
        node = {
            "id": a['id'],
            "type": "agent",
            "level": level,
            "parent": a.get('parent') or None,
            "spec_path": a.get('spec_path', ''),
            "memory_path": a.get('memory_path', ''),
            "capabilities": capabilities,
            "model_tier": a.get('model_tier', 'sonnet'),
            "status": "idle",
            "module": a.get('module') or None,
            "safety": {
                "max_children": 10 if level == 0 else 5,
                "timeout_minutes": None if level == 0 else [None, 120, 60, 30][min(level, 3)],
                "can_spawn": True,
                "review_required": level >= 1
            }
        }
        nodes.append(node)

    # Load files
    files = load_csv("files.csv")
    for f in files:
        node = {
            "id": f['id'],
            "type": "file",
            "path": f.get('path', ''),
            "owner": f.get('owner', ''),
            "module": f.get('module') or None
        }
        nodes.append(node)

        # Auto-create OWNS edge
        if f.get('owner'):
            edges_list.append({
                "from": f['owner'],
                "to": f['id'],
                "type": "OWNS"
            })

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

    # Load concepts (if exists — produced by Phase 2b domain mapper)
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
