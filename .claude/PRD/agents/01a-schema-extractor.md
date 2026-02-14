# Phase 1a: Schema Extractor

## Purpose

Extract the complete database schema from the `baap` MariaDB database: all tables, columns, types, indexes, constraints, and auto-increment values. Output a structured JSON file that downstream agents (KG builder, MCP builder) consume.

## Phase Info

- **Phase**: 1a (parallel with 1b, 1c — runs after Phase 0 gate)
- **Estimated time**: 10-15 minutes
- **Model tier**: Sonnet

## Input Contract

- **Database**: `baap` in MariaDB (loaded by Phase 0)
- **Access**: `mysql baap -e "..."` (passwordless unix socket)
- **Prerequisite**: `~/Projects/baap/db_ready.flag` exists

## Output Contract

- **File**: `.claude/discovery/schema.json`
- **Format**: JSON (schema defined below)

### Output Schema

```json
{
  "metadata": {
    "extracted_at": "2026-02-13T10:00:00Z",
    "database": "baap",
    "table_count": 200,
    "total_columns": 1500,
    "extractor_version": "1.0"
  },
  "tables": [
    {
      "name": "users",
      "engine": "InnoDB",
      "row_format": "Dynamic",
      "auto_increment": 50000,
      "create_time": "2024-01-15 10:30:00",
      "table_comment": "Application users",
      "columns": [
        {
          "name": "id",
          "type": "int(11)",
          "nullable": false,
          "default": null,
          "key": "PRI",
          "extra": "auto_increment",
          "comment": "",
          "ordinal_position": 1
        }
      ],
      "indexes": [
        {
          "name": "PRIMARY",
          "columns": ["id"],
          "unique": true,
          "type": "BTREE"
        }
      ],
      "constraints": [
        {
          "name": "fk_users_org",
          "type": "FOREIGN KEY",
          "columns": ["org_id"],
          "referenced_table": "organizations",
          "referenced_columns": ["id"],
          "on_delete": "CASCADE",
          "on_update": "NO ACTION"
        }
      ]
    }
  ]
}
```

## Step-by-Step Instructions

### 1. Create Output Directory

```bash
mkdir -p ~/Projects/baap/.claude/discovery
```

### 2. Write Extraction Script

Create a Python script that queries `information_schema` and generates the JSON:

```python
#!/usr/bin/env python3
"""Extract complete database schema from MariaDB baap database."""

import json
import subprocess
from datetime import datetime, timezone

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

def extract_schema():
    # Get all tables
    tables_raw = mysql_query("""
        SELECT TABLE_NAME, ENGINE, ROW_FORMAT, AUTO_INCREMENT,
               CREATE_TIME, TABLE_COMMENT
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = 'baap'
        ORDER BY TABLE_NAME
    """)

    tables = []
    for t in tables_raw:
        table_name = t['TABLE_NAME']

        # Get columns
        columns = mysql_query(f"""
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                   COLUMN_KEY, EXTRA, COLUMN_COMMENT, ORDINAL_POSITION
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME = '{table_name}'
            ORDER BY ORDINAL_POSITION
        """)

        # Get indexes
        indexes_raw = mysql_query(f"""
            SELECT INDEX_NAME, COLUMN_NAME, NON_UNIQUE, INDEX_TYPE
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME = '{table_name}'
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """)

        # Group index columns
        index_map = {}
        for idx in indexes_raw:
            name = idx['INDEX_NAME']
            if name not in index_map:
                index_map[name] = {
                    'name': name,
                    'columns': [],
                    'unique': idx['NON_UNIQUE'] == '0',
                    'type': idx['INDEX_TYPE']
                }
            index_map[name]['columns'].append(idx['COLUMN_NAME'])

        # Get foreign key constraints
        constraints = mysql_query(f"""
            SELECT CONSTRAINT_NAME, COLUMN_NAME,
                   REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME = '{table_name}'
            AND REFERENCED_TABLE_NAME IS NOT NULL
            ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION
        """)

        # Get ON DELETE / ON UPDATE rules
        fk_rules = mysql_query(f"""
            SELECT CONSTRAINT_NAME, DELETE_RULE, UPDATE_RULE
            FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = 'baap' AND TABLE_NAME = '{table_name}'
        """)
        fk_rules_map = {r['CONSTRAINT_NAME']: r for r in fk_rules}

        # Group constraint columns
        constraint_map = {}
        for c in constraints:
            name = c['CONSTRAINT_NAME']
            if name not in constraint_map:
                rules = fk_rules_map.get(name, {})
                constraint_map[name] = {
                    'name': name,
                    'type': 'FOREIGN KEY',
                    'columns': [],
                    'referenced_table': c['REFERENCED_TABLE_NAME'],
                    'referenced_columns': [],
                    'on_delete': rules.get('DELETE_RULE', 'NO ACTION'),
                    'on_update': rules.get('UPDATE_RULE', 'NO ACTION')
                }
            constraint_map[name]['columns'].append(c['COLUMN_NAME'])
            constraint_map[name]['referenced_columns'].append(c['REFERENCED_COLUMN_NAME'])

        tables.append({
            'name': table_name,
            'engine': t.get('ENGINE', 'InnoDB'),
            'row_format': t.get('ROW_FORMAT', ''),
            'auto_increment': int(t['AUTO_INCREMENT']) if t.get('AUTO_INCREMENT') and t['AUTO_INCREMENT'] != 'NULL' else None,
            'create_time': t.get('CREATE_TIME', ''),
            'table_comment': t.get('TABLE_COMMENT', ''),
            'columns': [
                {
                    'name': col['COLUMN_NAME'],
                    'type': col['COLUMN_TYPE'],
                    'nullable': col['IS_NULLABLE'] == 'YES',
                    'default': None if col.get('COLUMN_DEFAULT') in ('NULL', None, '') else col['COLUMN_DEFAULT'],
                    'key': col.get('COLUMN_KEY', ''),
                    'extra': col.get('EXTRA', ''),
                    'comment': col.get('COLUMN_COMMENT', ''),
                    'ordinal_position': int(col['ORDINAL_POSITION'])
                }
                for col in columns
            ],
            'indexes': list(index_map.values()),
            'constraints': list(constraint_map.values())
        })

    total_columns = sum(len(t['columns']) for t in tables)

    schema = {
        'metadata': {
            'extracted_at': datetime.now(timezone.utc).isoformat(),
            'database': 'baap',
            'table_count': len(tables),
            'total_columns': total_columns,
            'extractor_version': '1.0'
        },
        'tables': tables
    }

    return schema

if __name__ == '__main__':
    schema = extract_schema()
    output_path = '.claude/discovery/schema.json'
    with open(output_path, 'w') as f:
        json.dump(schema, f, indent=2, default=str)

    m = schema['metadata']
    print(f"Extracted {m['table_count']} tables with {m['total_columns']} total columns")
    print(f"Written to {output_path}")
```

### 3. Run the Script

```bash
cd ~/Projects/baap
python3 .claude/discovery/extract_schema.py
```

### 4. Validate Output

```bash
python3 -c "
import json
d = json.load(open('.claude/discovery/schema.json'))
m = d['metadata']
print(f'Tables: {m[\"table_count\"]}')
print(f'Columns: {m[\"total_columns\"]}')
print(f'Sample tables: {[t[\"name\"] for t in d[\"tables\"][:10]]}')
assert m['table_count'] > 0, 'No tables found!'
assert m['total_columns'] > 0, 'No columns found!'
print('Schema extraction validated successfully')
"
```

### 5. Clean Up

You can optionally delete the extraction script after running it, or keep it for re-extraction:

```bash
# Keep it — useful for future re-extraction
# rm .claude/discovery/extract_schema.py
```

## Success Criteria

1. `.claude/discovery/schema.json` exists
2. JSON is valid and parseable
3. `metadata.table_count` > 0
4. Every table has at least 1 column
5. Column types are properly extracted (not empty strings)
6. Indexes are grouped by name with correct column lists
7. Foreign key constraints include referenced table and columns

## Edge Cases

- Tables with no indexes → `indexes: []` (valid)
- Tables with no foreign keys → `constraints: []` (valid)
- Tables with composite primary keys → multiple columns in the PRIMARY index
- Views might appear in SHOW TABLES → filter by `TABLE_TYPE = 'BASE TABLE'` if needed
- Very long column types (e.g., `enum(...)`) → captured as-is in `type` field
- NULL values in `auto_increment` → set to `null` in JSON
- Special characters in table/column names → MySQL handles escaping via `information_schema`
