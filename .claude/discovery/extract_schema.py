#!/usr/bin/env python3
"""
Baap Schema Extractor v1.0
Extracts complete database schema from MariaDB and outputs schema.json.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def query(sql: str) -> list[dict]:
    """Run a SQL query via mysql CLI and return list of dicts."""
    result = subprocess.run(
        ["mysql", "baap", "--batch", "--raw", "-e", sql],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"SQL error: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    lines = result.stdout.strip().split("\n")
    if len(lines) < 1:
        return []

    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        row = {}
        for i, h in enumerate(headers):
            val = values[i] if i < len(values) else None
            # Handle NULL values from --batch --raw mode
            if val == "NULL":
                val = None
            row[h] = val
        rows.append(row)
    return rows


def to_bool(val: str | None) -> bool:
    """Convert YES/NO string to bool."""
    return val == "YES"


def to_int_or_none(val: str | None) -> int | None:
    """Convert string to int, or None."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def extract_tables() -> list[dict]:
    """Extract table-level metadata."""
    sql = """
    SELECT
        TABLE_NAME,
        ENGINE,
        ROW_FORMAT,
        AUTO_INCREMENT,
        CREATE_TIME,
        TABLE_COMMENT
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = 'baap'
      AND TABLE_TYPE = 'BASE TABLE'
    ORDER BY TABLE_NAME;
    """
    rows = query(sql)
    tables = []
    for r in rows:
        tables.append({
            "name": r["TABLE_NAME"],
            "engine": r["ENGINE"],
            "row_format": r["ROW_FORMAT"],
            "auto_increment": to_int_or_none(r["AUTO_INCREMENT"]),
            "create_time": r["CREATE_TIME"],
            "table_comment": r["TABLE_COMMENT"] or "",
        })
    return tables


def extract_columns(table_name: str) -> list[dict]:
    """Extract columns for a given table."""
    sql = f"""
    SELECT
        COLUMN_NAME,
        COLUMN_TYPE,
        IS_NULLABLE,
        COLUMN_DEFAULT,
        COLUMN_KEY,
        EXTRA,
        COLUMN_COMMENT,
        ORDINAL_POSITION
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'baap'
      AND TABLE_NAME = '{table_name}'
    ORDER BY ORDINAL_POSITION;
    """
    rows = query(sql)
    columns = []
    for r in rows:
        columns.append({
            "name": r["COLUMN_NAME"],
            "type": r["COLUMN_TYPE"],
            "nullable": to_bool(r["IS_NULLABLE"]),
            "default": r["COLUMN_DEFAULT"],
            "key": r["COLUMN_KEY"] or "",
            "extra": r["EXTRA"] or "",
            "comment": r["COLUMN_COMMENT"] or "",
            "ordinal_position": to_int_or_none(r["ORDINAL_POSITION"]),
        })
    return columns


def extract_indexes(table_name: str) -> list[dict]:
    """Extract indexes for a given table."""
    sql = f"""
    SELECT
        INDEX_NAME,
        COLUMN_NAME,
        NON_UNIQUE,
        INDEX_TYPE,
        SEQ_IN_INDEX
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = 'baap'
      AND TABLE_NAME = '{table_name}'
    ORDER BY INDEX_NAME, SEQ_IN_INDEX;
    """
    rows = query(sql)

    # Group columns by index name
    index_map: dict[str, dict] = {}
    for r in rows:
        idx_name = r["INDEX_NAME"]
        if idx_name not in index_map:
            index_map[idx_name] = {
                "name": idx_name,
                "columns": [],
                "unique": r["NON_UNIQUE"] == "0",
                "type": r["INDEX_TYPE"] or "BTREE",
            }
        index_map[idx_name]["columns"].append(r["COLUMN_NAME"])

    return list(index_map.values())


def extract_constraints(table_name: str) -> list[dict]:
    """Extract foreign key constraints for a given table."""
    sql = f"""
    SELECT
        kcu.CONSTRAINT_NAME,
        kcu.COLUMN_NAME,
        kcu.REFERENCED_TABLE_NAME,
        kcu.REFERENCED_COLUMN_NAME,
        kcu.ORDINAL_POSITION,
        rc.UPDATE_RULE,
        rc.DELETE_RULE
    FROM information_schema.KEY_COLUMN_USAGE kcu
    JOIN information_schema.REFERENTIAL_CONSTRAINTS rc
      ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
      AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
      AND rc.TABLE_NAME = kcu.TABLE_NAME
    WHERE kcu.TABLE_SCHEMA = 'baap'
      AND kcu.TABLE_NAME = '{table_name}'
      AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
    ORDER BY kcu.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
    """
    rows = query(sql)

    # Group columns by constraint name (composite FKs)
    fk_map: dict[str, dict] = {}
    for r in rows:
        cname = r["CONSTRAINT_NAME"]
        if cname not in fk_map:
            fk_map[cname] = {
                "name": cname,
                "type": "FOREIGN KEY",
                "columns": [],
                "referenced_table": r["REFERENCED_TABLE_NAME"],
                "referenced_columns": [],
                "on_delete": r["DELETE_RULE"] or "NO ACTION",
                "on_update": r["UPDATE_RULE"] or "NO ACTION",
            }
        fk_map[cname]["columns"].append(r["COLUMN_NAME"])
        fk_map[cname]["referenced_columns"].append(r["REFERENCED_COLUMN_NAME"])

    return list(fk_map.values())


def main():
    output_path = Path(__file__).parent / "schema.json"

    print("Extracting tables...")
    tables = extract_tables()
    print(f"  Found {len(tables)} tables")

    total_columns = 0
    for i, table in enumerate(tables):
        tname = table["name"]
        print(f"  [{i+1}/{len(tables)}] {tname}...", end=" ")

        columns = extract_columns(tname)
        indexes = extract_indexes(tname)
        constraints = extract_constraints(tname)

        table["columns"] = columns
        table["indexes"] = indexes
        table["constraints"] = constraints

        total_columns += len(columns)
        print(f"{len(columns)} cols, {len(indexes)} idx, {len(constraints)} fk")

    schema = {
        "metadata": {
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "database": "baap",
            "table_count": len(tables),
            "total_columns": total_columns,
            "extractor_version": "1.0",
        },
        "tables": tables,
    }

    output_path.write_text(json.dumps(schema, indent=2, default=str))
    print(f"\nSchema written to {output_path}")
    print(f"  Tables: {len(tables)}")
    print(f"  Total columns: {total_columns}")


if __name__ == "__main__":
    main()
