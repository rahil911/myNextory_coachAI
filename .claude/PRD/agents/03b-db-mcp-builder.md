# Phase 3b: Database Tools MCP Server Builder

## Purpose

Build the `db_tools.py` MCP server that gives agents access to the application database. Agents use this to understand the data they're building features for — table schemas, sample data, entity context.

## Phase Info

- **Phase**: 3b (parallel with 3a, 3c, 3d — runs after Phase 2 gate)
- **Estimated time**: 30-45 minutes
- **Model tier**: Sonnet

## Input Contract

- **Database**: `baap` in MariaDB (passwordless unix socket)
- **Reference**: `~/Projects/decision-canvas-os/.claude/mcp/causal_graph.py` (for MCP server pattern)
- **File**: `.claude/discovery/schema.json` (for entity context enrichment)

## Output Contract

- **File**: `.claude/mcp/db_tools.py`
- **Tools**: 5 MCP tools (listed below)
- **Protocol**: MCP stdio transport

## Tools to Implement (5 total)

### 1. list_tables()
Returns all tables with row counts and sizes.

```json
// No input required
// Output:
{
  "database": "baap",
  "table_count": 200,
  "tables": [
    {
      "name": "users",
      "engine": "InnoDB",
      "row_count": 50000,
      "data_size_mb": 12.5,
      "has_primary_key": true
    }
  ]
}
```

### 2. describe_table(name: str)
Returns full table schema: columns, types, indexes, constraints.

```json
// Input: {"name": "users"}
// Output:
{
  "table": "users",
  "engine": "InnoDB",
  "row_count": 50000,
  "columns": [
    {
      "name": "id",
      "type": "int(11)",
      "nullable": false,
      "key": "PRI",
      "extra": "auto_increment"
    }
  ],
  "indexes": [
    {"name": "PRIMARY", "columns": ["id"], "unique": true}
  ],
  "foreign_keys": [
    {"column": "org_id", "references": "organizations.id", "on_delete": "CASCADE"}
  ],
  "sample_rows": [
    {"id": 1, "name": "Alice", "email": "alice@example.com"}
  ]
}
```

### 3. run_query(sql: str)
Execute a READ-ONLY SQL query. **CRITICAL SAFETY**: Only allow SELECT statements. Reject INSERT/UPDATE/DELETE/ALTER/DROP/CREATE.

```json
// Input: {"sql": "SELECT id, name, email FROM users LIMIT 5"}
// Output:
{
  "query": "SELECT id, name, email FROM users LIMIT 5",
  "row_count": 5,
  "columns": ["id", "name", "email"],
  "rows": [
    {"id": 1, "name": "Alice", "email": "alice@example.com"}
  ],
  "truncated": false
}
```

Safety: Add `LIMIT 1000` if no LIMIT clause present. Max result size 10MB.

### 4. search_tables(keyword: str)
Find tables by name keyword (partial match).

```json
// Input: {"keyword": "user"}
// Output:
{
  "keyword": "user",
  "matches": [
    {"name": "users", "row_count": 50000},
    {"name": "user_profiles", "row_count": 48000},
    {"name": "user_sessions", "row_count": 120000}
  ]
}
```

### 5. get_entity_context(entity: str)
Get comprehensive context for a business entity: related tables, sample data, key relationships. Combines KG data (if available) with live database queries.

```json
// Input: {"entity": "User"}
// Output:
{
  "entity": "User",
  "primary_table": "users",
  "related_tables": ["user_profiles", "user_sessions", "orders"],
  "row_count": 50000,
  "key_columns": ["id", "name", "email"],
  "relationships": [
    {"table": "orders", "via": "user_id", "count": 120000}
  ],
  "sample_data": [
    {"id": 1, "name": "Alice", "email": "alice@example.com"}
  ]
}
```

## Implementation

```python
#!/usr/bin/env python3
"""
Database Tools MCP Server

Provides read-only access to the baap MariaDB database.
Agents use this to understand application data structure and content.

Tools:
- list_tables: Show all tables with stats
- describe_table: Full schema for a table
- run_query: Execute read-only SQL
- search_tables: Find tables by keyword
- get_entity_context: Business entity context

SAFETY: All queries are READ-ONLY. Write operations are rejected.
"""

import asyncio
import json
import subprocess
import re
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


DATABASE = "baap"
MAX_ROWS = 1000
MAX_RESULT_SIZE = 10 * 1024 * 1024  # 10MB


def mysql_query(sql, database=DATABASE):
    """Execute a MySQL query and return results."""
    result = subprocess.run(
        ["mysql", database, "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise Exception(f"MySQL error: {result.stderr.strip()}")

    lines = result.stdout.strip().split('\n')
    if len(lines) < 2:
        return [], []

    headers = lines[0].split('\t')
    rows = []
    for line in lines[1:]:
        values = line.split('\t')
        row = {}
        for i, h in enumerate(headers):
            row[h] = values[i] if i < len(values) else None
        rows.append(row)

    return headers, rows


def is_read_only(sql):
    """Check if SQL is read-only (SELECT, SHOW, DESCRIBE, EXPLAIN only)."""
    cleaned = sql.strip().upper()
    # Remove comments
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'--.*$', '', cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    allowed = ('SELECT', 'SHOW', 'DESCRIBE', 'DESC', 'EXPLAIN')
    return any(cleaned.startswith(prefix) for prefix in allowed)


def ensure_limit(sql, max_rows=MAX_ROWS):
    """Add LIMIT if not present."""
    upper = sql.upper().strip()
    if 'LIMIT' not in upper and upper.startswith('SELECT'):
        sql = sql.rstrip(';') + f' LIMIT {max_rows}'
    return sql


# Implement all 5 tools...
# Follow the pattern from causal_graph.py for server setup


server = Server("db-tools")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="list_tables",
            description="List all tables in the database with row counts and sizes",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="describe_table",
            description="Get full schema for a table: columns, types, indexes, foreign keys, sample data",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Table name"}},
                "required": ["name"]
            }
        ),
        Tool(
            name="run_query",
            description="Execute a read-only SQL query (SELECT only). Auto-limited to 1000 rows.",
            inputSchema={
                "type": "object",
                "properties": {"sql": {"type": "string", "description": "SQL SELECT query"}},
                "required": ["sql"]
            }
        ),
        Tool(
            name="search_tables",
            description="Find tables by keyword in table name",
            inputSchema={
                "type": "object",
                "properties": {"keyword": {"type": "string", "description": "Search keyword"}},
                "required": ["keyword"]
            }
        ),
        Tool(
            name="get_entity_context",
            description="Get comprehensive context for a business entity: tables, relationships, sample data",
            inputSchema={
                "type": "object",
                "properties": {"entity": {"type": "string", "description": "Entity name (e.g., 'User', 'Order')"}},
                "required": ["entity"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        if name == "list_tables":
            _, rows = mysql_query("""
                SELECT TABLE_NAME, ENGINE, TABLE_ROWS,
                       ROUND(DATA_LENGTH/1048576, 2) AS data_mb,
                       CASE WHEN INDEX_LENGTH > 0 THEN 'yes' ELSE 'no' END AS has_pk
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = 'baap' AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_ROWS DESC
            """, database="information_schema")

            tables = [{
                "name": r["TABLE_NAME"],
                "engine": r.get("ENGINE", ""),
                "row_count": int(r.get("TABLE_ROWS", 0) or 0),
                "data_size_mb": float(r.get("data_mb", 0) or 0),
                "has_primary_key": r.get("has_pk") == "yes"
            } for r in rows]

            result = {"database": DATABASE, "table_count": len(tables), "tables": tables}

        elif name == "describe_table":
            table = arguments["name"]
            # Columns
            _, cols = mysql_query(f"""
                SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, EXTRA
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME = '{table}'
                ORDER BY ORDINAL_POSITION
            """, database="information_schema")

            # Row count
            _, cnt = mysql_query(f"SELECT COUNT(*) AS c FROM `{table}`")
            row_count = int(cnt[0]["c"]) if cnt else 0

            # Sample rows
            _, samples = mysql_query(f"SELECT * FROM `{table}` LIMIT 3")

            # Indexes
            _, idxs = mysql_query(f"SHOW INDEX FROM `{table}`")

            # Foreign keys
            _, fks = mysql_query(f"""
                SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME = '{table}'
                AND REFERENCED_TABLE_NAME IS NOT NULL
            """, database="information_schema")

            result = {
                "table": table,
                "row_count": row_count,
                "columns": [{
                    "name": c["COLUMN_NAME"],
                    "type": c["COLUMN_TYPE"],
                    "nullable": c["IS_NULLABLE"] == "YES",
                    "key": c.get("COLUMN_KEY", ""),
                    "extra": c.get("EXTRA", "")
                } for c in cols],
                "indexes": [{
                    "name": i.get("Key_name", ""),
                    "column": i.get("Column_name", ""),
                    "unique": i.get("Non_unique", "1") == "0"
                } for i in idxs],
                "foreign_keys": [{
                    "column": f["COLUMN_NAME"],
                    "references": f"{f['REFERENCED_TABLE_NAME']}.{f['REFERENCED_COLUMN_NAME']}"
                } for f in fks],
                "sample_rows": samples[:3]
            }

        elif name == "run_query":
            sql = arguments["sql"]
            if not is_read_only(sql):
                return [TextContent(type="text", text=json.dumps({
                    "error": "Only SELECT/SHOW/DESCRIBE queries are allowed. Write operations are rejected for safety."
                }))]

            sql = ensure_limit(sql)
            headers, rows = mysql_query(sql)
            result = {
                "query": sql,
                "row_count": len(rows),
                "columns": headers,
                "rows": rows,
                "truncated": len(rows) >= MAX_ROWS
            }

        elif name == "search_tables":
            keyword = arguments["keyword"].lower()
            _, rows = mysql_query(f"""
                SELECT TABLE_NAME, TABLE_ROWS
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = 'baap' AND TABLE_TYPE = 'BASE TABLE'
                AND LOWER(TABLE_NAME) LIKE '%{keyword}%'
                ORDER BY TABLE_ROWS DESC
            """, database="information_schema")

            result = {
                "keyword": keyword,
                "matches": [{"name": r["TABLE_NAME"], "row_count": int(r.get("TABLE_ROWS", 0) or 0)} for r in rows]
            }

        elif name == "get_entity_context":
            entity = arguments["entity"].lower()
            # Find matching tables
            _, tables = mysql_query(f"""
                SELECT TABLE_NAME, TABLE_ROWS
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = 'baap' AND TABLE_TYPE = 'BASE TABLE'
                AND LOWER(TABLE_NAME) LIKE '%{entity}%'
                ORDER BY TABLE_ROWS DESC
            """, database="information_schema")

            primary = tables[0]["TABLE_NAME"] if tables else None

            related = []
            if primary:
                _, fks = mysql_query(f"""
                    SELECT DISTINCT REFERENCED_TABLE_NAME AS ref_table
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME = '{primary}'
                    AND REFERENCED_TABLE_NAME IS NOT NULL
                    UNION
                    SELECT DISTINCT TABLE_NAME AS ref_table
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = 'baap' AND REFERENCED_TABLE_NAME = '{primary}'
                """, database="information_schema")
                related = [r["ref_table"] for r in fks]

                _, samples = mysql_query(f"SELECT * FROM `{primary}` LIMIT 3")
            else:
                samples = []

            result = {
                "entity": entity,
                "primary_table": primary,
                "related_tables": [t["TABLE_NAME"] for t in tables[1:]] + related,
                "row_count": int(tables[0].get("TABLE_ROWS", 0)) if tables else 0,
                "sample_data": samples[:3]
            }

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
```

## Success Criteria

1. `.claude/mcp/db_tools.py` exists
2. Server starts without errors
3. All 5 tools registered
4. `list_tables()` returns all tables
5. `describe_table("users")` returns schema (or whatever the main user table is called)
6. `run_query("SELECT 1")` works
7. `run_query("DROP TABLE users")` is REJECTED
8. `search_tables("user")` finds matching tables
9. SQL injection prevented (parameterized queries or strict validation)

## Security Notes

- **READ-ONLY ONLY**: `is_read_only()` must catch ALL write patterns
- **SQL injection**: The `keyword` parameter in `search_tables` uses `LIKE`. Sanitize by rejecting keywords with single quotes, semicolons, or comment markers.
- **Timeout**: All queries timeout after 30 seconds
- **Result size**: Limit to 1000 rows and 10MB total
- **No information_schema mutations**: Even through crafted SELECT subqueries
