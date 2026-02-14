# Phase 1b: Relationship Mapper

## Purpose

Discover ALL relationships between tables in the `baap` database — both explicit (foreign keys) and implicit (naming conventions like `user_id` → `users.id`). Build a comprehensive relationship map that the KG builder uses to create edges.

## Phase Info

- **Phase**: 1b (parallel with 1a, 1c — runs after Phase 0 gate)
- **Estimated time**: 15-20 minutes
- **Model tier**: Sonnet

## Input Contract

- **Database**: `baap` in MariaDB (loaded by Phase 0)
- **Access**: `mysql baap -e "..."` (passwordless unix socket)
- **Prerequisite**: `~/Projects/baap/db_ready.flag` exists

## Output Contract

- **File**: `.claude/discovery/relationships.json`
- **Format**: JSON (schema defined below)

### Output Schema

```json
{
  "metadata": {
    "extracted_at": "2026-02-13T10:00:00Z",
    "database": "baap",
    "explicit_fk_count": 50,
    "inferred_count": 120,
    "total_relationships": 170,
    "naming_patterns_detected": ["snake_case_id", "table_id"],
    "mapper_version": "1.0"
  },
  "relationships": [
    {
      "from_table": "orders",
      "from_column": "user_id",
      "to_table": "users",
      "to_column": "id",
      "type": "explicit_fk",
      "constraint_name": "fk_orders_user",
      "on_delete": "CASCADE",
      "on_update": "NO ACTION",
      "confidence": 1.0
    },
    {
      "from_table": "order_items",
      "from_column": "product_id",
      "to_table": "products",
      "to_column": "id",
      "type": "inferred_naming",
      "pattern": "column 'product_id' matches table 'products' + '_id'",
      "confidence": 0.95
    }
  ],
  "naming_patterns": {
    "snake_case_id": {
      "pattern": "{table_singular}_id → {table}.id",
      "examples": ["user_id → users.id", "product_id → products.id"],
      "match_count": 80,
      "confidence": 0.95
    }
  },
  "orphan_tables": ["migrations", "cache", "sessions"],
  "hub_tables": [
    {
      "table": "users",
      "incoming_references": 25,
      "outgoing_references": 3
    }
  ]
}
```

## Step-by-Step Instructions

### 1. Create Output Directory

```bash
mkdir -p ~/Projects/baap/.claude/discovery
```

### 2. Write Relationship Discovery Script

Create a Python script that discovers both explicit and inferred relationships:

```python
#!/usr/bin/env python3
"""Discover all relationships between tables in the baap database."""

import json
import subprocess
import re
from datetime import datetime, timezone
from collections import defaultdict

def mysql_query(sql):
    """Run a MySQL query and return results as list of dicts."""
    result = subprocess.run(
        ["mysql", "baap", "--batch", "--raw", "-e", sql],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception(f"MySQL error: {result.stderr}")

    lines = result.stdout.strip().split('\n')
    if len(lines) < 2:
        return []

    headers = lines[0].split('\t')
    rows = []
    for line in lines[1:]:
        values = line.split('\t')
        rows.append(dict(zip(headers, values)))
    return rows


def get_all_tables():
    """Get all table names."""
    rows = mysql_query("SHOW TABLES")
    key = list(rows[0].keys())[0] if rows else "Tables_in_baap"
    return [r[key] for r in rows]


def get_explicit_fks():
    """Get all explicit foreign key constraints."""
    return mysql_query("""
        SELECT
            kcu.TABLE_NAME AS from_table,
            kcu.COLUMN_NAME AS from_column,
            kcu.REFERENCED_TABLE_NAME AS to_table,
            kcu.REFERENCED_COLUMN_NAME AS to_column,
            kcu.CONSTRAINT_NAME,
            rc.DELETE_RULE AS on_delete,
            rc.UPDATE_RULE AS on_update
        FROM information_schema.KEY_COLUMN_USAGE kcu
        JOIN information_schema.REFERENTIAL_CONSTRAINTS rc
            ON kcu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
            AND kcu.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA
        WHERE kcu.TABLE_SCHEMA = 'baap'
            AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY kcu.TABLE_NAME, kcu.COLUMN_NAME
    """)


def get_all_columns():
    """Get all columns for inference."""
    return mysql_query("""
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_KEY
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = 'baap'
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """)


def singularize(word):
    """Simple English singularization."""
    if word.endswith('ies'):
        return word[:-3] + 'y'
    if word.endswith('ses') or word.endswith('xes') or word.endswith('zes'):
        return word[:-2]
    if word.endswith('s') and not word.endswith('ss'):
        return word[:-1]
    return word


def infer_relationships(tables, columns, explicit_pairs):
    """Infer relationships from naming conventions."""
    table_set = set(tables)
    table_singular_map = {}
    for t in tables:
        singular = singularize(t)
        table_singular_map[singular] = t
        # Also map without common prefixes
        for prefix in ['wp_', 'app_', 'tbl_', 'mn_']:
            if t.startswith(prefix):
                stripped = t[len(prefix):]
                table_singular_map[singularize(stripped)] = t

    inferred = []
    patterns = defaultdict(lambda: {"examples": [], "match_count": 0})

    for col in columns:
        col_name = col['COLUMN_NAME']
        table_name = col['TABLE_NAME']

        # Skip if not an ID-like column
        if not col_name.endswith('_id') and col_name not in ('parent_id', 'created_by', 'updated_by', 'author_id'):
            continue

        # Already has explicit FK?
        pair = (table_name, col_name)
        if pair in explicit_pairs:
            continue

        # Try to match to a table
        target_table = None
        pattern_name = None

        if col_name.endswith('_id'):
            # user_id → users, product_id → products
            base = col_name[:-3]  # Remove _id

            # Try plural forms
            for candidate in [base + 's', base + 'es', base[:-1] + 'ies' if base.endswith('y') else None, base]:
                if candidate and candidate in table_set:
                    target_table = candidate
                    pattern_name = "snake_case_id"
                    break

            # Try singular map
            if not target_table and base in table_singular_map:
                target_table = table_singular_map[base]
                pattern_name = "singular_id"

            # Try with common prefixes
            if not target_table:
                for prefix in ['wp_', 'app_', 'tbl_', 'mn_']:
                    for candidate in [prefix + base + 's', prefix + base + 'es', prefix + base]:
                        if candidate in table_set:
                            target_table = candidate
                            pattern_name = "prefixed_id"
                            break
                    if target_table:
                        break

        # Special patterns
        if col_name == 'parent_id' and table_name in table_set:
            target_table = table_name  # Self-referencing
            pattern_name = "self_reference"

        if col_name in ('created_by', 'updated_by', 'author_id', 'modified_by'):
            for candidate in ['users', 'admins', 'admin_users']:
                if candidate in table_set:
                    target_table = candidate
                    pattern_name = "user_reference"
                    break

        if target_table and target_table != table_name or (target_table == table_name and col_name == 'parent_id'):
            confidence = 0.95 if pattern_name == "snake_case_id" else 0.85
            inferred.append({
                "from_table": table_name,
                "from_column": col_name,
                "to_table": target_table,
                "to_column": "id",
                "type": "inferred_naming",
                "pattern": f"column '{col_name}' matches table '{target_table}' via {pattern_name}",
                "confidence": confidence
            })

            example = f"{col_name} → {target_table}.id"
            patterns[pattern_name]["examples"].append(example)
            patterns[pattern_name]["match_count"] += 1

    return inferred, dict(patterns)


def find_hub_tables(relationships):
    """Find tables with the most references (hubs)."""
    incoming = defaultdict(int)
    outgoing = defaultdict(int)

    for rel in relationships:
        outgoing[rel['from_table']] += 1
        incoming[rel['to_table']] += 1

    # Combine and sort by total references
    all_tables = set(list(incoming.keys()) + list(outgoing.keys()))
    hubs = []
    for t in all_tables:
        total = incoming[t] + outgoing[t]
        if total >= 3:
            hubs.append({
                "table": t,
                "incoming_references": incoming[t],
                "outgoing_references": outgoing[t]
            })

    return sorted(hubs, key=lambda x: x['incoming_references'], reverse=True)


def find_orphan_tables(tables, relationships):
    """Find tables with no relationships."""
    referenced = set()
    for rel in relationships:
        referenced.add(rel['from_table'])
        referenced.add(rel['to_table'])

    return sorted(set(tables) - referenced)


def main():
    tables = get_all_tables()
    columns = get_all_columns()
    explicit_fks = get_explicit_fks()

    # Build explicit relationships
    relationships = []
    explicit_pairs = set()
    for fk in explicit_fks:
        explicit_pairs.add((fk['from_table'], fk['from_column']))
        relationships.append({
            "from_table": fk['from_table'],
            "from_column": fk['from_column'],
            "to_table": fk['to_table'],
            "to_column": fk['to_column'],
            "type": "explicit_fk",
            "constraint_name": fk['CONSTRAINT_NAME'],
            "on_delete": fk.get('on_delete', 'NO ACTION'),
            "on_update": fk.get('on_update', 'NO ACTION'),
            "confidence": 1.0
        })

    # Infer relationships from naming
    inferred, patterns = infer_relationships(tables, columns, explicit_pairs)
    relationships.extend(inferred)

    # Add pattern metadata
    for name, data in patterns.items():
        data["confidence"] = 0.95 if name == "snake_case_id" else 0.85
        data["pattern"] = {
            "snake_case_id": "{column_without_id} → {plural_table}.id",
            "singular_id": "{column_without_id} → singularize match",
            "prefixed_id": "prefix + {column_without_id} → {prefixed_table}.id",
            "self_reference": "parent_id → same_table.id",
            "user_reference": "created_by/updated_by → users.id"
        }.get(name, "custom pattern")

    # Find hubs and orphans
    hubs = find_hub_tables(relationships)
    orphans = find_orphan_tables(tables, relationships)

    output = {
        "metadata": {
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "database": "baap",
            "explicit_fk_count": len(explicit_fks),
            "inferred_count": len(inferred),
            "total_relationships": len(relationships),
            "naming_patterns_detected": list(patterns.keys()),
            "mapper_version": "1.0"
        },
        "relationships": relationships,
        "naming_patterns": patterns,
        "orphan_tables": orphans,
        "hub_tables": hubs
    }

    output_path = '.claude/discovery/relationships.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    m = output['metadata']
    print(f"Found {m['explicit_fk_count']} explicit FKs + {m['inferred_count']} inferred = {m['total_relationships']} total")
    print(f"Hub tables: {[h['table'] for h in hubs[:5]]}")
    print(f"Orphan tables: {len(orphans)}")
    print(f"Written to {output_path}")


if __name__ == '__main__':
    main()
```

### 3. Run and Validate

```bash
cd ~/Projects/baap
python3 .claude/discovery/map_relationships.py

python3 -c "
import json
d = json.load(open('.claude/discovery/relationships.json'))
m = d['metadata']
print(f'Total relationships: {m[\"total_relationships\"]}')
print(f'Explicit FKs: {m[\"explicit_fk_count\"]}')
print(f'Inferred: {m[\"inferred_count\"]}')
assert m['total_relationships'] > 0, 'No relationships found!'
print('Relationship mapping validated')
"
```

## Success Criteria

1. `.claude/discovery/relationships.json` exists and is valid JSON
2. `total_relationships` > 0
3. Both explicit FKs and inferred relationships are captured
4. Hub tables identified (highest incoming reference count)
5. Orphan tables listed (tables with no relationships)
6. Each relationship has `from_table`, `from_column`, `to_table`, `to_column`, `type`, `confidence`

## Edge Cases

- Tables with no foreign keys → rely entirely on naming inference
- Polymorphic associations (`commentable_type` + `commentable_id`) → skip these (too complex for Phase 1)
- Tables with non-standard naming (no `_id` suffix) → will appear as orphans
- Self-referencing tables (`parent_id` → same table) → capture as `self_reference`
- Composite foreign keys → capture all columns in the relationship
