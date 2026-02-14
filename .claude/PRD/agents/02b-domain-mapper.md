# Phase 2b: Domain Mapper

## Purpose

Map database tables to business concepts (domain entities). This creates the CONCEPT nodes in the ownership KG — the semantic layer that lets agents reason about business entities rather than raw tables.

When the orchestrator hears "add user search," it queries `get_blast_radius("User")` and the KG returns all tables, files, and agents related to the User concept.

## Phase Info

- **Phase**: 2b (parallel with 2a — runs after Phase 1 gate)
- **Estimated time**: 20-30 minutes
- **Model tier**: Sonnet

## Input Contract

- **File**: `.claude/discovery/schema.json` (from Phase 1a)
- **File**: `.claude/discovery/relationships.json` (from Phase 1b)
- **File**: `.claude/discovery/profile.json` (from Phase 1c)

## Output Contract

- **File**: `.claude/kg/seeds/concepts.csv`
- **Format**: CSV with columns: `id,type,description,tables,domain,related_concepts,agents_involved`

### concepts.csv Schema

```csv
id,type,description,tables,domain,related_concepts,agents_involved
User,concept,"Customer/user entity in the application","users,user_profiles,user_sessions",identity,"Order,Auth,Session","db-agent,api-agent,ui-agent"
Order,concept,"Customer purchase order","orders,order_items,order_statuses",commerce,"User,Product,Payment","db-agent,api-agent,ui-agent"
Product,concept,"Catalog product/item","products,product_categories,product_images",catalog,"Order,Category,Inventory","db-agent,api-agent,ui-agent"
```

## Step-by-Step Instructions

### 1. Create Output Directory

```bash
mkdir -p ~/Projects/baap/.claude/kg/seeds
```

### 2. Analyze Table Groupings

Read the discovery data and identify business concepts by:

#### Strategy 1: Naming Convention Clustering

Tables with the same prefix belong to the same concept:
- `user_*` → User concept
- `order_*` → Order concept
- `product_*` → Product concept
- `payment_*` → Payment concept

#### Strategy 2: Relationship Clustering

Tables connected by foreign keys form concept groups:
- If `orders` → `users` and `order_items` → `orders`, then Orders and Users are related concepts
- Hub tables (from relationships.json `hub_tables`) are core concepts

#### Strategy 3: Domain Semantics

Group by business domain:
- **Identity**: users, roles, permissions, sessions, auth tokens
- **Commerce**: orders, carts, checkouts, payments, invoices
- **Catalog**: products, categories, variants, attributes, images
- **Inventory**: stock, warehouses, shipments, tracking
- **Communication**: emails, notifications, messages, logs
- **Content**: pages, posts, media, templates
- **Configuration**: settings, configs, features, flags

### 3. Write Domain Mapping Script

```python
#!/usr/bin/env python3
"""Map database tables to business concepts."""

import json
import csv
from pathlib import Path
from collections import defaultdict

def load_json(path):
    with open(path) as f:
        return json.load(f)

def extract_prefix(table_name):
    """Extract the conceptual prefix from a table name."""
    # Remove common prefixes
    name = table_name
    for prefix in ['wp_', 'app_', 'tbl_', 'mn_', 'sys_']:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break

    # Split on underscore and take the root word
    parts = name.split('_')
    return parts[0] if parts else name

def singularize(word):
    """Simple singularization."""
    if word.endswith('ies'):
        return word[:-3] + 'y'
    if word.endswith('ses') or word.endswith('xes'):
        return word[:-2]
    if word.endswith('s') and not word.endswith('ss'):
        return word[:-1]
    return word

def capitalize_concept(word):
    """Convert to PascalCase concept name."""
    return singularize(word).capitalize()

def main():
    schema = load_json('.claude/discovery/schema.json')
    relationships = load_json('.claude/discovery/relationships.json')
    profile = load_json('.claude/discovery/profile.json')

    # Build table → row_count map for importance
    row_counts = {}
    for t in profile.get('tables', []):
        row_counts[t['name']] = t.get('row_count', 0)

    # Group tables by prefix
    prefix_groups = defaultdict(list)
    for table in schema['tables']:
        prefix = extract_prefix(table['name'])
        prefix_groups[prefix].append(table['name'])

    # Build relationship graph for relatedness
    table_relations = defaultdict(set)
    for rel in relationships.get('relationships', []):
        table_relations[rel['from_table']].add(rel['to_table'])
        table_relations[rel['to_table']].add(rel['from_table'])

    # Create concepts from prefix groups
    concepts = []
    seen_tables = set()

    # Sort groups by total row count (most important first)
    sorted_groups = sorted(
        prefix_groups.items(),
        key=lambda x: sum(row_counts.get(t, 0) for t in x[1]),
        reverse=True
    )

    for prefix, tables in sorted_groups:
        if len(tables) == 0:
            continue

        # Skip very small groups of tiny tables (likely config/meta)
        total_rows = sum(row_counts.get(t, 0) for t in tables)

        concept_name = capitalize_concept(prefix)

        # Determine domain
        domain = "general"
        domain_keywords = {
            "identity": ["user", "role", "permission", "session", "auth", "token", "login", "password", "account"],
            "commerce": ["order", "cart", "checkout", "invoice", "payment", "transaction", "purchase", "sale"],
            "catalog": ["product", "category", "variant", "attribute", "catalog", "item", "sku"],
            "inventory": ["stock", "warehouse", "shipment", "tracking", "delivery", "shipping"],
            "communication": ["email", "notification", "message", "sms", "template", "newsletter"],
            "content": ["page", "post", "blog", "media", "image", "document", "file", "content"],
            "configuration": ["setting", "config", "option", "preference", "feature", "flag"],
            "analytics": ["log", "event", "metric", "report", "stat", "analytic"],
        }

        for d, keywords in domain_keywords.items():
            if prefix.lower() in keywords or any(prefix.lower().startswith(k) for k in keywords):
                domain = d
                break

        # Find related concepts via table relationships
        related_tables = set()
        for t in tables:
            related_tables.update(table_relations.get(t, set()))

        related_concepts = set()
        for rt in related_tables:
            rt_prefix = extract_prefix(rt)
            if rt_prefix != prefix:
                related_concepts.add(capitalize_concept(rt_prefix))

        # Determine which agents are involved (based on domain)
        agents = ["db-agent"]  # All concepts involve db-agent
        if domain in ("identity", "commerce", "catalog", "inventory"):
            agents.extend(["api-agent", "ui-agent"])
        elif domain in ("communication",):
            agents.append("api-agent")
        elif domain in ("analytics",):
            agents.append("api-agent")

        concept = {
            "id": concept_name,
            "type": "concept",
            "description": f"{concept_name} domain entity — {len(tables)} tables, {total_rows:,} total rows",
            "tables": ",".join(sorted(tables)),
            "domain": domain,
            "related_concepts": ",".join(sorted(related_concepts)[:10]),  # Cap at 10
            "agents_involved": ",".join(agents)
        }
        concepts.append(concept)
        seen_tables.update(tables)

    # Write concepts.csv
    output_path = Path('.claude/kg/seeds/concepts.csv')
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'id', 'type', 'description', 'tables', 'domain',
            'related_concepts', 'agents_involved'
        ])
        writer.writeheader()
        writer.writerows(concepts)

    # Summary
    domains = defaultdict(int)
    for c in concepts:
        domains[c['domain']] += 1

    print(f"Created {len(concepts)} concepts from {len(seen_tables)} tables")
    print(f"Domains: {dict(domains)}")
    print(f"Orphan tables (no concept): {len(set(t['name'] for t in schema['tables']) - seen_tables)}")
    print(f"Written to {output_path}")

if __name__ == '__main__':
    main()
```

### 3. Run and Validate

```bash
cd ~/Projects/baap
python3 .claude/discovery/map_domains.py

# Check output
head -20 .claude/kg/seeds/concepts.csv
wc -l .claude/kg/seeds/concepts.csv
```

### 4. After Phase 2a Creates build_cache.py

Once the KG builder (Phase 2a) creates `build_cache.py`, re-run it to incorporate concepts:

```bash
python3 .claude/kg/build_cache.py
```

This is a coordination point: either agent can run build_cache.py after both complete, or the build orchestrator runs it during the Phase 2 gate validation.

## Success Criteria

1. `.claude/kg/seeds/concepts.csv` exists and is valid CSV
2. At least 10 concepts identified
3. Each concept has at least 1 table
4. Domains are properly classified (not all "general")
5. Related concepts cross-reference each other
6. Hub tables (from relationships.json) are covered as core concepts

## Edge Cases

- Tables with no clear prefix → group as "Misc" concept
- Very large prefix groups (>20 tables) → may need sub-concepts
- Tables that belong to multiple concepts → assign to primary concept
- Empty tables → still include in concepts (they're part of the schema)
- Laravel/framework tables (migrations, jobs, cache) → group as "Framework" concept with "configuration" domain
