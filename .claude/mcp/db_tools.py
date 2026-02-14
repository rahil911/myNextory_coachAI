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
Connection: passwordless unix socket via mysql CLI.
"""

import asyncio
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATABASE = "baap"
MAX_ROWS = 1000
MAX_RESULT_SIZE = 10 * 1024 * 1024  # 10 MB
QUERY_TIMEOUT = 30  # seconds

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONCEPTS_CSV = PROJECT_ROOT / ".claude" / "kg" / "seeds" / "concepts.csv"
RELATIONSHIPS_JSON = PROJECT_ROOT / ".claude" / "discovery" / "relationships.json"

# ---------------------------------------------------------------------------
# Concept & relationship caches (loaded once at startup)
# ---------------------------------------------------------------------------

_concepts: list[dict] = []          # rows from concepts.csv
_relationships: list[dict] = []     # rows from relationships.json


def _load_concepts() -> None:
    """Load concepts.csv into memory."""
    global _concepts
    if not CONCEPTS_CSV.exists():
        print(f"[db-tools] concepts.csv not found at {CONCEPTS_CSV}", file=sys.stderr)
        return
    with open(CONCEPTS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        _concepts = list(reader)
    print(f"[db-tools] Loaded {len(_concepts)} concepts from {CONCEPTS_CSV}", file=sys.stderr)


def _load_relationships() -> None:
    """Load relationships.json into memory."""
    global _relationships
    if not RELATIONSHIPS_JSON.exists():
        print(f"[db-tools] relationships.json not found at {RELATIONSHIPS_JSON}", file=sys.stderr)
        return
    with open(RELATIONSHIPS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    _relationships = data.get("relationships", [])
    print(f"[db-tools] Loaded {len(_relationships)} relationships from {RELATIONSHIPS_JSON}", file=sys.stderr)


# ---------------------------------------------------------------------------
# MySQL helpers
# ---------------------------------------------------------------------------

def mysql_query(sql: str, database: str = DATABASE) -> tuple[list[str], list[dict]]:
    """Execute a MySQL query via CLI and return (headers, rows).

    Uses passwordless unix socket authentication.
    """
    result = subprocess.run(
        ["mysql", database, "--batch", "--raw", "-e", sql],
        capture_output=True,
        text=True,
        timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL error: {result.stderr.strip()}")

    output = result.stdout
    # Enforce max result size
    if len(output.encode("utf-8", errors="replace")) > MAX_RESULT_SIZE:
        raise Exception(
            f"Result exceeds {MAX_RESULT_SIZE // (1024 * 1024)}MB limit. "
            "Add a tighter LIMIT or WHERE clause."
        )

    lines = output.strip().split("\n")
    if not lines or len(lines) < 1:
        return [], []

    headers = lines[0].split("\t")
    if len(lines) < 2:
        return headers, []

    rows: list[dict] = []
    for line in lines[1:]:
        values = line.split("\t")
        row: dict = {}
        for i, h in enumerate(headers):
            row[h] = values[i] if i < len(values) else None
        rows.append(row)

    return headers, rows


# ---------------------------------------------------------------------------
# Safety functions
# ---------------------------------------------------------------------------

# Patterns that indicate write/DDL/DCL operations.
_WRITE_PATTERNS = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|RENAME|"
    r"GRANT|REVOKE|LOCK|UNLOCK|CALL|LOAD|SET|START|BEGIN|COMMIT|ROLLBACK|"
    r"FLUSH|RESET|PURGE|HANDLER|DO|PREPARE|EXECUTE|DEALLOCATE|"
    r"INTO\s+OUTFILE|INTO\s+DUMPFILE)",
    re.IGNORECASE | re.MULTILINE,
)

# Allowed statement prefixes (after stripping comments).
_ALLOWED_PREFIXES = ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN")


def is_read_only(sql: str) -> bool:
    """Return True only if the SQL is a safe read-only statement.

    Guards:
    1. Strip block comments (/* ... */) and line comments (-- ...)
    2. Reject if any write keyword is found at statement start
    3. Reject multi-statement queries (semicolons before the final one)
    4. Only allow statements starting with SELECT / SHOW / DESCRIBE / EXPLAIN
    5. Reject SELECT ... INTO OUTFILE / INTO DUMPFILE
    """
    # Remove block comments
    cleaned = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Remove line comments
    cleaned = re.sub(r"--[^\n]*", " ", cleaned)
    # Remove # comments (MySQL-specific)
    cleaned = re.sub(r"#[^\n]*", " ", cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        return False

    # Reject multi-statement (semicolons in the middle)
    # Allow trailing semicolon only
    body = cleaned.rstrip(";").strip()
    if ";" in body:
        return False

    # Check allowed prefix
    upper = cleaned.upper().lstrip()
    if not any(upper.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        return False

    # Reject SELECT ... INTO OUTFILE / INTO DUMPFILE
    if re.search(r"\bINTO\s+(OUTFILE|DUMPFILE)\b", upper):
        return False

    # Extra: reject write keywords even when embedded (e.g., subquery tricks)
    if _WRITE_PATTERNS.search(upper) and not upper.startswith("SELECT"):
        return False

    return True


def ensure_limit(sql: str, max_rows: int = MAX_ROWS) -> str:
    """Add LIMIT clause if the query is a SELECT without one."""
    upper = sql.upper().strip()
    if upper.startswith("SELECT") and "LIMIT" not in upper:
        sql = sql.rstrip().rstrip(";") + f" LIMIT {max_rows}"
    return sql


def sanitize_keyword(keyword: str) -> str:
    """Sanitize a keyword for use in SQL LIKE patterns.

    Rejects dangerous characters to prevent SQL injection.
    """
    # Strip whitespace
    keyword = keyword.strip()

    # Reject empty
    if not keyword:
        raise ValueError("Keyword must not be empty")

    # Reject if contains dangerous characters
    dangerous = {"'", '"', ";", "\\", "--", "/*", "*/", "#", "\x00"}
    for char in dangerous:
        if char in keyword:
            raise ValueError(
                f"Keyword contains forbidden character: {repr(char)}. "
                "Use only alphanumeric characters and underscores."
            )

    # Only allow alphanumeric, underscore, hyphen, space, percent, dot
    if not re.match(r"^[a-zA-Z0-9_ \-%.]+$", keyword):
        raise ValueError(
            "Keyword contains invalid characters. "
            "Use only alphanumeric characters, underscores, hyphens, and spaces."
        )

    return keyword


def sanitize_table_name(name: str) -> str:
    """Validate and sanitize a table name.

    Only allows alphanumeric and underscores -- rejects anything that
    could be used for SQL injection.
    """
    name = name.strip()
    if not name:
        raise ValueError("Table name must not be empty")
    if not re.match(r"^[a-zA-Z0-9_]+$", name):
        raise ValueError(
            f"Invalid table name: {repr(name)}. "
            "Only alphanumeric characters and underscores are allowed."
        )
    return name


# ---------------------------------------------------------------------------
# Entity context helpers
# ---------------------------------------------------------------------------

def _find_concept(entity: str) -> dict | None:
    """Find a concept from concepts.csv matching the entity name (case-insensitive)."""
    entity_lower = entity.lower()
    for concept in _concepts:
        if concept.get("id", "").lower() == entity_lower:
            return concept
    # Fuzzy: partial match on id or description
    for concept in _concepts:
        cid = concept.get("id", "").lower()
        desc = concept.get("description", "").lower()
        if entity_lower in cid or entity_lower in desc:
            return concept
    return None


def _get_relationships_for_table(table_name: str) -> list[dict]:
    """Get all relationships involving a specific table from relationships.json."""
    results = []
    for rel in _relationships:
        if rel.get("from_table") == table_name or rel.get("to_table") == table_name:
            results.append(rel)
    return results


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

server = Server("db-tools")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_tables",
            description=(
                "List all tables in the baap database with row counts, sizes, and engine type. "
                "No input required."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="describe_table",
            description=(
                "Get full schema for a table: columns with types, indexes, foreign keys, "
                "row count, and 3 sample rows."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Table name (e.g., 'nx_users', 'clients')",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="run_query",
            description=(
                "Execute a read-only SQL query (SELECT, SHOW, DESCRIBE, EXPLAIN only). "
                "Write operations are rejected. Auto-limited to 1000 rows if no LIMIT clause."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "SQL query (SELECT only). Example: SELECT * FROM nx_users LIMIT 5",
                    },
                },
                "required": ["sql"],
            },
        ),
        Tool(
            name="search_tables",
            description=(
                "Find tables by keyword in table name (partial match, case-insensitive). "
                "Returns matching table names with row counts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Search keyword (e.g., 'user', 'coach', 'lesson')",
                    },
                },
                "required": ["keyword"],
            },
        ),
        Tool(
            name="get_entity_context",
            description=(
                "Get comprehensive context for a business entity: primary table, related tables, "
                "relationships, sample data, and concept metadata from the knowledge graph. "
                "Entity names match concept IDs (e.g., 'User', 'Coach', 'Journey', 'Lesson')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "Entity name (e.g., 'User', 'Coach', 'Journey', 'Client')",
                    },
                },
                "required": ["entity"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "list_tables":
            result = _tool_list_tables()

        elif name == "describe_table":
            result = _tool_describe_table(arguments["name"])

        elif name == "run_query":
            result = _tool_run_query(arguments["sql"])

        elif name == "search_tables":
            result = _tool_search_tables(arguments["keyword"])

        elif name == "get_entity_context":
            result = _tool_get_entity_context(arguments["entity"])

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except ValueError as e:
        return [TextContent(type="text", text=json.dumps({"error": f"Validation error: {e}"}, default=str))]
    except subprocess.TimeoutExpired:
        return [TextContent(type="text", text=json.dumps({"error": f"Query timed out after {QUERY_TIMEOUT} seconds. Simplify the query or add a tighter LIMIT."}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, default=str))]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _tool_list_tables() -> dict:
    """list_tables: Returns all tables with row counts and sizes."""
    _, rows = mysql_query(
        """
        SELECT TABLE_NAME, ENGINE, TABLE_ROWS,
               ROUND(DATA_LENGTH / 1048576, 2) AS data_mb,
               ROUND(INDEX_LENGTH / 1048576, 2) AS index_mb,
               CASE WHEN TABLE_ROWS IS NOT NULL THEN 'yes' ELSE 'no' END AS has_data
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = 'baap' AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_ROWS DESC
        """,
        database="information_schema",
    )

    # Determine primary key presence per table
    _, pk_rows = mysql_query(
        """
        SELECT TABLE_NAME
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = 'baap' AND CONSTRAINT_TYPE = 'PRIMARY KEY'
        """,
        database="information_schema",
    )
    pk_tables = {r["TABLE_NAME"] for r in pk_rows}

    tables = [
        {
            "name": r["TABLE_NAME"],
            "engine": r.get("ENGINE", ""),
            "row_count": int(r.get("TABLE_ROWS", 0) or 0),
            "data_size_mb": float(r.get("data_mb", 0) or 0),
            "index_size_mb": float(r.get("index_mb", 0) or 0),
            "has_primary_key": r["TABLE_NAME"] in pk_tables,
        }
        for r in rows
    ]

    return {
        "database": DATABASE,
        "table_count": len(tables),
        "tables": tables,
    }


def _tool_describe_table(name: str) -> dict:
    """describe_table: Returns full schema, indexes, foreign keys, sample rows."""
    table = sanitize_table_name(name)

    # 1. Columns
    _, cols = mysql_query(
        f"""
        SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT, EXTRA
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME = '{table}'
        ORDER BY ORDINAL_POSITION
        """,
        database="information_schema",
    )
    if not cols:
        return {"error": f"Table '{table}' not found in database 'baap'"}

    # 2. Engine + row count from information_schema
    _, meta = mysql_query(
        f"""
        SELECT ENGINE, TABLE_ROWS
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME = '{table}'
        """,
        database="information_schema",
    )
    engine = meta[0].get("ENGINE", "") if meta else ""

    # 3. Exact row count
    _, cnt = mysql_query(f"SELECT COUNT(*) AS c FROM `{table}`")
    row_count = int(cnt[0]["c"]) if cnt else 0

    # 4. Indexes
    _, idxs = mysql_query(f"SHOW INDEX FROM `{table}`")
    # Group index columns by index name
    index_map: dict[str, dict] = {}
    for idx in idxs:
        idx_name = idx.get("Key_name", "")
        if idx_name not in index_map:
            index_map[idx_name] = {
                "name": idx_name,
                "columns": [],
                "unique": idx.get("Non_unique", "1") == "0",
            }
        index_map[idx_name]["columns"].append(idx.get("Column_name", ""))

    # 5. Foreign keys (explicit)
    _, fks = mysql_query(
        f"""
        SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME = '{table}'
        AND REFERENCED_TABLE_NAME IS NOT NULL
        """,
        database="information_schema",
    )

    # 5b. Inferred relationships from relationships.json
    inferred_rels = _get_relationships_for_table(table)
    inferred_fks = []
    for rel in inferred_rels:
        if rel["from_table"] == table:
            inferred_fks.append({
                "column": rel["from_column"],
                "references": f"{rel['to_table']}.{rel['to_column']}",
                "type": "inferred",
                "confidence": rel.get("confidence", 0),
                "pattern": rel.get("pattern", ""),
            })

    # 6. Sample rows
    _, samples = mysql_query(f"SELECT * FROM `{table}` LIMIT 3")

    return {
        "table": table,
        "engine": engine,
        "row_count": row_count,
        "columns": [
            {
                "name": c["COLUMN_NAME"],
                "type": c["COLUMN_TYPE"],
                "nullable": c["IS_NULLABLE"] == "YES",
                "key": c.get("COLUMN_KEY", ""),
                "default": c.get("COLUMN_DEFAULT"),
                "extra": c.get("EXTRA", ""),
            }
            for c in cols
        ],
        "indexes": list(index_map.values()),
        "foreign_keys": [
            {
                "column": f["COLUMN_NAME"],
                "references": f"{f['REFERENCED_TABLE_NAME']}.{f['REFERENCED_COLUMN_NAME']}",
                "type": "explicit",
            }
            for f in fks
        ],
        "inferred_relationships": inferred_fks,
        "sample_rows": samples[:3],
    }


def _tool_run_query(sql: str) -> dict:
    """run_query: Execute a read-only SQL query."""
    if not is_read_only(sql):
        return {
            "error": (
                "REJECTED: Only SELECT, SHOW, DESCRIBE, and EXPLAIN queries are allowed. "
                "Write operations (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, etc.) "
                "are forbidden for safety."
            ),
            "query": sql,
        }

    sql = ensure_limit(sql)
    headers, rows = mysql_query(sql)

    # Check result size
    result_json = json.dumps(rows, default=str)
    if len(result_json.encode("utf-8", errors="replace")) > MAX_RESULT_SIZE:
        return {
            "error": f"Result exceeds {MAX_RESULT_SIZE // (1024 * 1024)}MB. Add a tighter LIMIT or WHERE clause.",
            "query": sql,
        }

    return {
        "query": sql,
        "row_count": len(rows),
        "columns": headers,
        "rows": rows,
        "truncated": len(rows) >= MAX_ROWS,
    }


def _tool_search_tables(keyword: str) -> dict:
    """search_tables: Find tables by keyword in table name."""
    keyword = sanitize_keyword(keyword).lower()

    _, rows = mysql_query(
        f"""
        SELECT TABLE_NAME, ENGINE, TABLE_ROWS,
               ROUND(DATA_LENGTH / 1048576, 2) AS data_mb
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = 'baap' AND TABLE_TYPE = 'BASE TABLE'
        AND LOWER(TABLE_NAME) LIKE '%{keyword}%'
        ORDER BY TABLE_ROWS DESC
        """,
        database="information_schema",
    )

    # Also search columns for tables containing columns with the keyword
    _, col_matches = mysql_query(
        f"""
        SELECT DISTINCT TABLE_NAME, COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = 'baap'
        AND LOWER(COLUMN_NAME) LIKE '%{keyword}%'
        ORDER BY TABLE_NAME
        """,
        database="information_schema",
    )

    # Deduplicate table names already found by name
    name_match_tables = {r["TABLE_NAME"] for r in rows}
    column_matches = [
        {"table": c["TABLE_NAME"], "matching_column": c["COLUMN_NAME"]}
        for c in col_matches
        if c["TABLE_NAME"] not in name_match_tables
    ]

    return {
        "keyword": keyword,
        "matches": [
            {
                "name": r["TABLE_NAME"],
                "engine": r.get("ENGINE", ""),
                "row_count": int(r.get("TABLE_ROWS", 0) or 0),
                "data_size_mb": float(r.get("data_mb", 0) or 0),
            }
            for r in rows
        ],
        "tables_with_matching_columns": column_matches[:20],  # Cap to avoid noise
    }


def _tool_get_entity_context(entity: str) -> dict:
    """get_entity_context: Comprehensive entity context from KG + live DB."""
    # 1. Look up concept in concepts.csv
    concept = _find_concept(entity)

    if concept:
        # Use concept data to find tables
        tables_str = concept.get("tables", "")
        concept_tables = [t.strip() for t in tables_str.split(",") if t.strip()]

        # Pick the primary table as the one with the most rows (the "hub")
        primary_table = None
        if concept_tables:
            if len(concept_tables) == 1:
                primary_table = concept_tables[0]
            else:
                # Query row counts to find the biggest table
                try:
                    safe_names = [sanitize_table_name(t) for t in concept_tables]
                    in_clause = ", ".join(f"'{n}'" for n in safe_names)
                    _, tbl_rows = mysql_query(
                        f"""
                        SELECT TABLE_NAME, TABLE_ROWS
                        FROM information_schema.TABLES
                        WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME IN ({in_clause})
                        ORDER BY TABLE_ROWS DESC
                        """,
                        database="information_schema",
                    )
                    primary_table = tbl_rows[0]["TABLE_NAME"] if tbl_rows else concept_tables[0]
                except Exception:
                    primary_table = concept_tables[0]

        # Related concepts
        related_str = concept.get("related_concepts", "")
        related_concepts = [r.strip() for r in related_str.split(",") if r.strip()]

        # Domain
        domain = concept.get("domain", "")
        description = concept.get("description", "")

        # Agents involved
        agents_str = concept.get("agents_involved", "")
        agents = [a.strip() for a in agents_str.split(",") if a.strip()]
    else:
        # Fallback: search tables by entity name
        concept_tables = []
        primary_table = None
        related_concepts = []
        domain = ""
        description = ""
        agents = []

        entity_sanitized = sanitize_keyword(entity).lower()
        _, found = mysql_query(
            f"""
            SELECT TABLE_NAME, TABLE_ROWS
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = 'baap' AND TABLE_TYPE = 'BASE TABLE'
            AND LOWER(TABLE_NAME) LIKE '%{entity_sanitized}%'
            ORDER BY TABLE_ROWS DESC
            """,
            database="information_schema",
        )
        concept_tables = [r["TABLE_NAME"] for r in found]
        primary_table = concept_tables[0] if concept_tables else None

    # 2. Get row count and sample data from primary table
    row_count = 0
    sample_data: list[dict] = []
    key_columns: list[str] = []

    if primary_table:
        try:
            safe_table = sanitize_table_name(primary_table)

            # Row count
            _, cnt = mysql_query(f"SELECT COUNT(*) AS c FROM `{safe_table}`")
            row_count = int(cnt[0]["c"]) if cnt else 0

            # Sample data
            _, sample_data = mysql_query(f"SELECT * FROM `{safe_table}` LIMIT 3")

            # Key columns (PRI, UNI, MUL)
            _, col_info = mysql_query(
                f"""
                SELECT COLUMN_NAME, COLUMN_KEY
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME = '{safe_table}'
                AND COLUMN_KEY != ''
                ORDER BY ORDINAL_POSITION
                """,
                database="information_schema",
            )
            key_columns = [c["COLUMN_NAME"] for c in col_info]
        except Exception as e:
            sample_data = [{"error": str(e)}]

    # 3. Get relationships from relationships.json for all concept tables
    relationships = []
    seen_rels = set()
    for tbl in concept_tables:
        for rel in _get_relationships_for_table(tbl):
            # Build a unique key to avoid duplicates
            rel_key = (rel["from_table"], rel["from_column"], rel["to_table"], rel["to_column"])
            if rel_key not in seen_rels:
                seen_rels.add(rel_key)
                # Determine direction relative to this entity
                if rel["from_table"] in concept_tables:
                    direction = "outgoing"
                    target_table = rel["to_table"]
                else:
                    direction = "incoming"
                    target_table = rel["from_table"]

                relationships.append({
                    "from_table": rel["from_table"],
                    "from_column": rel["from_column"],
                    "to_table": rel["to_table"],
                    "to_column": rel["to_column"],
                    "direction": direction,
                    "confidence": rel.get("confidence", 0),
                    "pattern": rel.get("pattern", ""),
                })

    # 4. Find related tables (unique set from relationships)
    related_tables = list(set(
        [r["to_table"] for r in relationships if r["to_table"] not in concept_tables]
        + [r["from_table"] for r in relationships if r["from_table"] not in concept_tables]
    ))

    # 5. Get row counts for related tables
    related_table_info = []
    if related_tables:
        # Build a safe IN clause
        safe_names = [sanitize_table_name(t) for t in related_tables[:20]]
        in_clause = ", ".join(f"'{n}'" for n in safe_names)
        _, rel_info = mysql_query(
            f"""
            SELECT TABLE_NAME, TABLE_ROWS
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME IN ({in_clause})
            """,
            database="information_schema",
        )
        related_table_info = [
            {"name": r["TABLE_NAME"], "row_count": int(r.get("TABLE_ROWS", 0) or 0)}
            for r in rel_info
        ]

    result = {
        "entity": entity,
        "concept_found": concept is not None,
        "domain": domain,
        "description": description,
        "primary_table": primary_table,
        "all_entity_tables": concept_tables,
        "row_count": row_count,
        "key_columns": key_columns,
        "related_concepts": related_concepts,
        "related_tables": related_table_info,
        "relationships": relationships,
        "agents_involved": agents,
        "sample_data": sample_data[:3],
    }

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    # Load static data
    _load_concepts()
    _load_relationships()

    # Verify DB connection
    try:
        _, rows = mysql_query("SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA = 'baap'")
        table_count = rows[0]["n"] if rows else "?"
        print(f"[db-tools] Connected to MariaDB. Database '{DATABASE}' has {table_count} tables.", file=sys.stderr)
    except Exception as e:
        print(f"[db-tools] WARNING: Could not connect to MariaDB: {e}", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
