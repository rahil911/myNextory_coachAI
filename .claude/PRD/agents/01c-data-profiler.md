# Phase 1c: Data Profiler

## Purpose

Profile every table in the `baap` database: row counts, sample data, null rates, cardinality, data type distributions, and storage sizes. This gives the KG builder and domain mapper the quantitative understanding needed to assign importance and group tables into concepts.

## Phase Info

- **Phase**: 1c (parallel with 1a, 1b — runs after Phase 0 gate)
- **Estimated time**: 15-25 minutes (depends on table count)
- **Model tier**: Sonnet

## Input Contract

- **Database**: `baap` in MariaDB (loaded by Phase 0)
- **Access**: `mysql baap -e "..."` (passwordless unix socket)
- **Prerequisite**: `~/Projects/baap/db_ready.flag` exists

## Output Contract

- **File**: `.claude/discovery/profile.json`
- **Format**: JSON (schema defined below)

### Output Schema

```json
{
  "metadata": {
    "profiled_at": "2026-02-13T10:00:00Z",
    "database": "baap",
    "tables_profiled": 200,
    "total_rows": 5000000,
    "total_size_mb": 450.5,
    "profiler_version": "1.0"
  },
  "tables": [
    {
      "name": "users",
      "row_count": 50000,
      "data_size_mb": 12.5,
      "index_size_mb": 3.2,
      "avg_row_length": 250,
      "is_empty": false,
      "has_timestamps": true,
      "timestamp_columns": ["created_at", "updated_at"],
      "columns": [
        {
          "name": "email",
          "null_count": 120,
          "null_rate": 0.0024,
          "distinct_count": 49800,
          "cardinality_ratio": 0.996,
          "sample_values": ["alice@example.com", "bob@test.org", "carol@mail.net"],
          "min_length": 5,
          "max_length": 120,
          "avg_length": 25.3
        }
      ],
      "sample_rows": [
        {"id": 1, "name": "Alice", "email": "alice@example.com"}
      ]
    }
  ],
  "size_distribution": {
    "empty_tables": 15,
    "small_tables": 80,
    "medium_tables": 60,
    "large_tables": 30,
    "huge_tables": 5
  },
  "top_tables_by_rows": [
    {"name": "order_items", "row_count": 2000000},
    {"name": "log_entries", "row_count": 1500000}
  ]
}
```

Size categories: empty (0 rows), small (<1000), medium (1000-100000), large (100000-1M), huge (>1M).

## Step-by-Step Instructions

### 1. Create Output Directory

```bash
mkdir -p ~/Projects/baap/.claude/discovery
```

### 2. Write Profiling Script

Create a Python script that profiles each table:

```python
#!/usr/bin/env python3
"""Profile all tables in the baap database."""

import json
import subprocess
from datetime import datetime, timezone

def mysql_query(sql):
    """Run a MySQL query and return results as list of dicts."""
    result = subprocess.run(
        ["mysql", "baap", "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        return []

    lines = result.stdout.strip().split('\n')
    if len(lines) < 2:
        return []

    headers = lines[0].split('\t')
    rows = []
    for line in lines[1:]:
        values = line.split('\t')
        rows.append(dict(zip(headers, values)))
    return rows


def safe_int(val, default=0):
    try:
        return int(val) if val and val != 'NULL' else default
    except (ValueError, TypeError):
        return default


def safe_float(val, default=0.0):
    try:
        return float(val) if val and val != 'NULL' else default
    except (ValueError, TypeError):
        return default


def profile_table(table_name, columns_info):
    """Profile a single table."""
    # Get row count and sizes from information_schema (fast, no table scan)
    info = mysql_query(f"""
        SELECT TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH, AVG_ROW_LENGTH
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = 'baap' AND TABLE_NAME = '{table_name}'
    """)

    if not info:
        return None

    row_count = safe_int(info[0].get('TABLE_ROWS'))
    data_size_bytes = safe_int(info[0].get('DATA_LENGTH'))
    index_size_bytes = safe_int(info[0].get('INDEX_LENGTH'))
    avg_row_length = safe_int(info[0].get('AVG_ROW_LENGTH'))

    # Get exact row count for smaller tables (information_schema estimates for InnoDB)
    if row_count < 100000:
        exact = mysql_query(f"SELECT COUNT(*) AS cnt FROM `{table_name}`")
        if exact:
            row_count = safe_int(exact[0].get('cnt'))

    is_empty = row_count == 0

    # Detect timestamp columns
    timestamp_cols = [
        c['COLUMN_NAME'] for c in columns_info
        if c['COLUMN_TYPE'] in ('timestamp', 'datetime')
        or c['COLUMN_NAME'] in ('created_at', 'updated_at', 'deleted_at', 'created', 'modified')
    ]

    # Profile columns (skip for empty tables)
    column_profiles = []
    if not is_empty and row_count > 0:
        for col in columns_info:
            col_name = col['COLUMN_NAME']
            col_type = col['COLUMN_TYPE']

            try:
                # Null count and distinct count
                stats = mysql_query(f"""
                    SELECT
                        COUNT(*) - COUNT(`{col_name}`) AS null_count,
                        COUNT(DISTINCT `{col_name}`) AS distinct_count
                    FROM `{table_name}`
                """)

                null_count = safe_int(stats[0].get('null_count')) if stats else 0
                distinct_count = safe_int(stats[0].get('distinct_count')) if stats else 0
                null_rate = round(null_count / row_count, 4) if row_count > 0 else 0
                cardinality_ratio = round(distinct_count / row_count, 4) if row_count > 0 else 0

                # Sample values (up to 3)
                samples = mysql_query(f"""
                    SELECT DISTINCT CAST(`{col_name}` AS CHAR) AS val
                    FROM `{table_name}`
                    WHERE `{col_name}` IS NOT NULL
                    LIMIT 3
                """)
                sample_values = [s['val'] for s in samples if s.get('val')]

                # String length stats for text columns
                length_stats = {}
                if 'char' in col_type or 'text' in col_type or 'varchar' in col_type:
                    lens = mysql_query(f"""
                        SELECT
                            MIN(CHAR_LENGTH(`{col_name}`)) AS min_len,
                            MAX(CHAR_LENGTH(`{col_name}`)) AS max_len,
                            AVG(CHAR_LENGTH(`{col_name}`)) AS avg_len
                        FROM `{table_name}`
                        WHERE `{col_name}` IS NOT NULL
                    """)
                    if lens:
                        length_stats = {
                            'min_length': safe_int(lens[0].get('min_len')),
                            'max_length': safe_int(lens[0].get('max_len')),
                            'avg_length': round(safe_float(lens[0].get('avg_len')), 1)
                        }

                profile = {
                    'name': col_name,
                    'null_count': null_count,
                    'null_rate': null_rate,
                    'distinct_count': distinct_count,
                    'cardinality_ratio': cardinality_ratio,
                    'sample_values': sample_values[:3]
                }
                profile.update(length_stats)
                column_profiles.append(profile)

            except Exception as e:
                column_profiles.append({
                    'name': col_name,
                    'error': str(e)
                })

    # Get sample rows (up to 3)
    sample_rows = []
    if not is_empty:
        try:
            samples = mysql_query(f"SELECT * FROM `{table_name}` LIMIT 3")
            sample_rows = samples[:3]
        except Exception:
            pass

    return {
        'name': table_name,
        'row_count': row_count,
        'data_size_mb': round(data_size_bytes / (1024 * 1024), 2),
        'index_size_mb': round(index_size_bytes / (1024 * 1024), 2),
        'avg_row_length': avg_row_length,
        'is_empty': is_empty,
        'has_timestamps': len(timestamp_cols) > 0,
        'timestamp_columns': timestamp_cols,
        'columns': column_profiles,
        'sample_rows': sample_rows
    }


def categorize_size(row_count):
    if row_count == 0: return 'empty_tables'
    if row_count < 1000: return 'small_tables'
    if row_count < 100000: return 'medium_tables'
    if row_count < 1000000: return 'large_tables'
    return 'huge_tables'


def main():
    # Get all tables
    tables_raw = mysql_query("SHOW TABLES")
    key = list(tables_raw[0].keys())[0]
    table_names = [r[key] for r in tables_raw]

    # Get all columns grouped by table
    all_columns = mysql_query("""
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = 'baap'
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """)

    columns_by_table = {}
    for col in all_columns:
        t = col['TABLE_NAME']
        if t not in columns_by_table:
            columns_by_table[t] = []
        columns_by_table[t].append(col)

    # Profile each table
    tables = []
    total_rows = 0
    total_size = 0
    size_dist = {'empty_tables': 0, 'small_tables': 0, 'medium_tables': 0, 'large_tables': 0, 'huge_tables': 0}

    for i, table_name in enumerate(table_names):
        print(f"  Profiling {i+1}/{len(table_names)}: {table_name}...", flush=True)
        profile = profile_table(table_name, columns_by_table.get(table_name, []))
        if profile:
            tables.append(profile)
            total_rows += profile['row_count']
            total_size += profile['data_size_mb']
            size_dist[categorize_size(profile['row_count'])] += 1

    # Top tables by rows
    top_by_rows = sorted(tables, key=lambda t: t['row_count'], reverse=True)[:20]
    top_by_rows_summary = [{'name': t['name'], 'row_count': t['row_count']} for t in top_by_rows]

    output = {
        'metadata': {
            'profiled_at': datetime.now(timezone.utc).isoformat(),
            'database': 'baap',
            'tables_profiled': len(tables),
            'total_rows': total_rows,
            'total_size_mb': round(total_size, 2),
            'profiler_version': '1.0'
        },
        'tables': tables,
        'size_distribution': size_dist,
        'top_tables_by_rows': top_by_rows_summary
    }

    output_path = '.claude/discovery/profile.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    m = output['metadata']
    print(f"\nProfiled {m['tables_profiled']} tables")
    print(f"Total rows: {m['total_rows']:,}")
    print(f"Total size: {m['total_size_mb']} MB")
    print(f"Distribution: {size_dist}")
    print(f"Written to {output_path}")


if __name__ == '__main__':
    main()
```

### 3. Run and Validate

```bash
cd ~/Projects/baap
python3 .claude/discovery/profile_data.py

python3 -c "
import json
d = json.load(open('.claude/discovery/profile.json'))
m = d['metadata']
print(f'Tables profiled: {m[\"tables_profiled\"]}')
print(f'Total rows: {m[\"total_rows\"]:,}')
print(f'Top 5 by rows: {[t[\"name\"] for t in d[\"top_tables_by_rows\"][:5]]}')
assert m['tables_profiled'] > 0, 'No tables profiled!'
print('Data profiling validated')
"
```

## Success Criteria

1. `.claude/discovery/profile.json` exists and is valid JSON
2. `tables_profiled` matches the actual table count (or close — some views may be skipped)
3. Non-empty tables have column profiles with null_rate and cardinality
4. Sample rows captured for non-empty tables
5. Size distribution categorizes all tables
6. Top tables by rows sorted correctly

## Edge Cases

- Very large tables (>1M rows) → use `information_schema.TABLE_ROWS` (estimate, not exact COUNT)
- Tables with binary/blob columns → skip length stats, sample values may be truncated
- Tables with special characters in names → use backtick quoting
- Timeout on large column profiling → catch and record error per column
- Empty tables → `is_empty: true`, no column profiles, no samples
