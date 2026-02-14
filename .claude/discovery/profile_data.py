#!/usr/bin/env python3
"""
Baap Database Profiler — Phase 1c
Profiles every table in the `baap` MariaDB database and outputs profile.json.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATABASE = "baap"
OUTPUT_FILE = "/home/rahil/Projects/baap/.claude/discovery/profile.json"
MAX_SAMPLE_VALUES = 3
MAX_SAMPLE_ROWS = 3
SUBPROCESS_TIMEOUT = 120  # seconds
EXACT_COUNT_THRESHOLD = 100_000  # use COUNT(*) for tables below this estimate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run_sql(sql: str, timeout: int = SUBPROCESS_TIMEOUT) -> str:
    """Run a SQL query via the mysql CLI and return raw stdout."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"mysql error: {result.stderr.strip()}")
    return result.stdout


def parse_rows(output: str) -> list[dict]:
    """Parse mysql --batch output into a list of dicts."""
    lines = output.strip().split("\n")
    if len(lines) < 2:
        return []
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        rows.append(dict(zip(headers, values)))
    return rows


def safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Step 1 — Gather table-level metadata from information_schema (fast)
# ---------------------------------------------------------------------------
def get_table_metadata() -> list[dict]:
    """Return table-level stats from information_schema."""
    sql = """
    SELECT
        TABLE_NAME,
        TABLE_ROWS,
        DATA_LENGTH,
        INDEX_LENGTH,
        AVG_ROW_LENGTH
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = 'baap'
      AND TABLE_TYPE = 'BASE TABLE'
    ORDER BY TABLE_NAME;
    """
    rows = parse_rows(run_sql(sql))
    result = []
    for r in rows:
        result.append({
            "name": r["TABLE_NAME"],
            "estimated_rows": safe_int(r["TABLE_ROWS"]),
            "data_bytes": safe_int(r["DATA_LENGTH"]),
            "index_bytes": safe_int(r["INDEX_LENGTH"]),
            "avg_row_length": safe_int(r["AVG_ROW_LENGTH"]),
        })
    return result


# ---------------------------------------------------------------------------
# Step 2 — Get columns for a table
# ---------------------------------------------------------------------------
def get_columns(table_name: str) -> list[dict]:
    """Return column metadata for a table."""
    sql = f"""
    SELECT
        COLUMN_NAME,
        DATA_TYPE,
        IS_NULLABLE,
        COLUMN_KEY,
        COLUMN_DEFAULT,
        EXTRA
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'baap'
      AND TABLE_NAME = '{table_name}'
    ORDER BY ORDINAL_POSITION;
    """
    return parse_rows(run_sql(sql))


# ---------------------------------------------------------------------------
# Step 3 — Profile columns of a non-empty table
# ---------------------------------------------------------------------------
TIMESTAMP_TYPES = {"timestamp", "datetime", "date"}
TIMESTAMP_NAME_HINTS = {"created_at", "updated_at", "deleted_at", "created", "updated",
                        "modified_at", "date", "timestamp", "logged_at", "sent_at",
                        "scheduled_at", "completed_at", "start_time", "end_time"}


def profile_column(table_name: str, col_name: str, row_count: int) -> dict:
    """Profile a single column: null_count, distinct_count, sample_values."""
    # Backtick-escape identifiers
    t = f"`{table_name}`"
    c = f"`{col_name}`"

    try:
        sql = f"""
        SELECT
            SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END) AS null_count,
            COUNT(DISTINCT {c}) AS distinct_count
        FROM {t};
        """
        stats = parse_rows(run_sql(sql))
        if not stats:
            return {"name": col_name, "error": "no stats returned"}
        null_count = safe_int(stats[0].get("null_count", 0))
        distinct_count = safe_int(stats[0].get("distinct_count", 0))
    except Exception as e:
        return {
            "name": col_name,
            "null_count": None,
            "null_rate": None,
            "distinct_count": None,
            "cardinality_ratio": None,
            "sample_values": [],
            "error": str(e),
        }

    # Sample values (up to 3 non-null distinct values)
    sample_values = []
    try:
        sample_sql = f"""
        SELECT DISTINCT {c} AS val FROM {t}
        WHERE {c} IS NOT NULL
        LIMIT {MAX_SAMPLE_VALUES};
        """
        sample_rows = parse_rows(run_sql(sample_sql))
        sample_values = [r["val"] for r in sample_rows]
        # Truncate very long values for readability
        sample_values = [v[:200] if len(v) > 200 else v for v in sample_values]
    except Exception:
        pass

    null_rate = round(null_count / row_count, 4) if row_count > 0 else 0.0
    cardinality_ratio = round(distinct_count / row_count, 4) if row_count > 0 else 0.0

    return {
        "name": col_name,
        "null_count": null_count,
        "null_rate": null_rate,
        "distinct_count": distinct_count,
        "cardinality_ratio": cardinality_ratio,
        "sample_values": sample_values,
    }


# ---------------------------------------------------------------------------
# Step 4 — Get sample rows
# ---------------------------------------------------------------------------
def get_sample_rows(table_name: str, columns: list[str]) -> list[dict]:
    """Return up to MAX_SAMPLE_ROWS from the table."""
    t = f"`{table_name}`"
    try:
        sql = f"SELECT * FROM {t} LIMIT {MAX_SAMPLE_ROWS};"
        rows = parse_rows(run_sql(sql))
        # Truncate long cell values
        for row in rows:
            for k, v in row.items():
                if isinstance(v, str) and len(v) > 300:
                    row[k] = v[:300] + "...(truncated)"
        return rows
    except Exception as e:
        return [{"error": str(e)}]


# ---------------------------------------------------------------------------
# Step 5 — Exact row count
# ---------------------------------------------------------------------------
def exact_row_count(table_name: str) -> int:
    """Get exact row count via COUNT(*)."""
    t = f"`{table_name}`"
    sql = f"SELECT COUNT(*) AS cnt FROM {t};"
    rows = parse_rows(run_sql(sql))
    return safe_int(rows[0]["cnt"]) if rows else 0


# ---------------------------------------------------------------------------
# Main profiler
# ---------------------------------------------------------------------------
def classify_size(row_count: int) -> str:
    if row_count == 0:
        return "empty"
    elif row_count < 1000:
        return "small"
    elif row_count <= 100_000:
        return "medium"
    elif row_count <= 1_000_000:
        return "large"
    else:
        return "huge"


def main():
    start_time = datetime.now(timezone.utc)
    print(f"[profiler] Starting at {start_time.isoformat()}")
    print(f"[profiler] Database: {DATABASE}")

    # ------ Table metadata --------------------------------------------------
    tables_meta = get_table_metadata()
    total_tables = len(tables_meta)
    print(f"[profiler] Found {total_tables} tables")

    # ------ Profile each table ----------------------------------------------
    profiled_tables = []
    total_rows = 0
    total_size_mb = 0.0

    size_dist = {"empty_tables": 0, "small_tables": 0, "medium_tables": 0,
                 "large_tables": 0, "huge_tables": 0}

    for idx, tmeta in enumerate(tables_meta, 1):
        tname = tmeta["name"]
        est_rows = tmeta["estimated_rows"]
        data_mb = round(tmeta["data_bytes"] / (1024 * 1024), 4)
        index_mb = round(tmeta["index_bytes"] / (1024 * 1024), 4)
        total_size_mb += data_mb + index_mb

        print(f"[profiler] Profiling {idx}/{total_tables}: {tname} "
              f"(est. {est_rows} rows, {data_mb:.2f} MB) ...", flush=True)

        # Get exact count for tables under the threshold
        if est_rows < EXACT_COUNT_THRESHOLD:
            row_count = exact_row_count(tname)
        else:
            row_count = est_rows

        total_rows += row_count
        is_empty = row_count == 0

        # Classify
        cat = classify_size(row_count)
        size_dist[f"{cat}_tables"] += 1

        # Column metadata
        raw_columns = get_columns(tname)
        col_names = [c["COLUMN_NAME"] for c in raw_columns]
        col_types = {c["COLUMN_NAME"]: c["DATA_TYPE"] for c in raw_columns}

        # Detect timestamp columns
        timestamp_cols = []
        for c in raw_columns:
            cname_lower = c["COLUMN_NAME"].lower()
            ctype_lower = c["DATA_TYPE"].lower()
            if ctype_lower in TIMESTAMP_TYPES:
                timestamp_cols.append(c["COLUMN_NAME"])
            elif cname_lower in TIMESTAMP_NAME_HINTS:
                timestamp_cols.append(c["COLUMN_NAME"])
        has_timestamps = len(timestamp_cols) > 0

        # Column profiling (skip for empty tables)
        columns_profile = []
        if not is_empty:
            for cname in col_names:
                cp = profile_column(tname, cname, row_count)
                columns_profile.append(cp)
        else:
            # For empty tables, just list column names with no stats
            for cname in col_names:
                columns_profile.append({
                    "name": cname,
                    "null_count": 0,
                    "null_rate": 0.0,
                    "distinct_count": 0,
                    "cardinality_ratio": 0.0,
                    "sample_values": [],
                })

        # Sample rows
        sample_rows = []
        if not is_empty:
            sample_rows = get_sample_rows(tname, col_names)

        profiled_tables.append({
            "name": tname,
            "row_count": row_count,
            "data_size_mb": data_mb,
            "index_size_mb": index_mb,
            "avg_row_length": tmeta["avg_row_length"],
            "is_empty": is_empty,
            "has_timestamps": has_timestamps,
            "timestamp_columns": timestamp_cols,
            "columns": columns_profile,
            "sample_rows": sample_rows,
        })

        print(f"           -> {row_count} rows, {len(col_names)} columns, "
              f"{'EMPTY' if is_empty else f'{len(columns_profile)} profiled'}")

    # ------ Summary ---------------------------------------------------------
    total_size_mb = round(total_size_mb, 4)
    top_tables = sorted(profiled_tables, key=lambda t: t["row_count"], reverse=True)[:10]
    top_by_rows = [{"name": t["name"], "row_count": t["row_count"]} for t in top_tables]

    profile = {
        "metadata": {
            "profiled_at": datetime.now(timezone.utc).isoformat(),
            "database": DATABASE,
            "tables_profiled": total_tables,
            "total_rows": total_rows,
            "total_size_mb": total_size_mb,
            "profiler_version": "1.0",
        },
        "tables": profiled_tables,
        "size_distribution": size_dist,
        "top_tables_by_rows": top_by_rows,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(profile, f, indent=2, default=str)

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    print(f"\n[profiler] Done in {elapsed:.1f}s")
    print(f"[profiler] Output: {OUTPUT_FILE}")
    print(f"[profiler] Tables: {total_tables}, Rows: {total_rows}, "
          f"Size: {total_size_mb:.2f} MB")
    print(f"[profiler] Distribution: {size_dist}")


if __name__ == "__main__":
    main()
