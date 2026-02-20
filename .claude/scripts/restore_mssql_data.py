#!/usr/bin/env python3
"""
MSSQL to MariaDB data restorer for baap database.

Reads INSERT statements from the MSSQL backup (app-mynextory-backup-utf8.sql),
converts them to MariaDB-compatible SQL using a state-machine parser,
and executes them against the local MariaDB database.

Features:
- State-machine parser for MSSQL INSERT VALUES (handles nested quotes, CAST, NULL)
- Per-table processing in FK dependency order
- INSERT IGNORE for merge tables (never overwrites existing rows)
- NO_BACKSLASH_ESCAPES mode for safe JSON/Unicode passthrough
- Row count validation after each table
- Detailed logging (zero silent data drops)
"""

import re
import sys
import os
import subprocess
import logging
import tempfile
from pathlib import Path

# --- Configuration ---
MSSQL_FILE = '/home/rahil/Projects/baap/app-mynextory-backup-utf8.sql'
DB_NAME = 'baap'
WORK_DIR = Path(__file__).parent
LOG_FILE = WORK_DIR / 'restore_mssql_data.log'

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('restore')

# FK-ordered restoration tiers
# (table_name, mode, expected_mssql_source_count)
# mode='full': table should be empty, insert all rows
# mode='merge': table has existing data, INSERT IGNORE only
RESTORE_ORDER = [
    # Tier 1: No FK dependencies (parent tables)
    ('nx_journey_details', 'full', 16),
    ('clients', 'full', 37),
    ('coaches', 'full', 5),
    ('coach_profiles', 'full', 4),
    ('nx_admin_users', 'full', 1),

    # Tier 2: Depends on Tier 1
    ('nx_chapter_details', 'full', 46),
    ('departments', 'full', 97),
    ('coach_availabilities', 'full', 9),
    ('nx_users', 'merge', 1563),

    # Tier 3: Depends on Tier 2
    ('nx_lessons', 'full', 90),
    ('employees', 'merge', 1566),
    ('nx_user_onboardings', 'merge', 571),

    # Tier 4: Depends on Tier 3
    ('lesson_details', 'full', 86),
    ('video_libraries', 'merge', 158),

    # Tier 5: Depends on Tier 4
    ('lesson_slides', 'merge', 620),

    # Tier 6: Leaf tables
    ('backpacks', 'merge', 11951),
    ('tasks', 'merge', 2928),
    ('nx_user_ratings', 'merge', 3356),
    ('old_ratings', 'merge', 499),
    ('nx_journal_details', 'merge', 112),
    ('sms_details', 'merge', 5744),
    ('documents', 'merge', 144),
    ('chatbot_documents', 'merge', 106),
    ('chatbot_histories', 'merge', 291),
    ('notification_histories', 'full', 94),
    ('dynamic_sms_details', 'full', 53),
    ('mail_communication_details', 'full', 45),
    ('sms_schedules', 'full', 12),
    ('nx_password_resets', 'full', 19),
]


# ============================================================
# Core Parser: State-machine MSSQL → MariaDB value converter
# ============================================================

def parse_cast_expression(s, start):
    """Parse CAST(N'value' AS Type) starting at position `start`.

    Returns (converted_string, chars_consumed) or (None, 0).

    Handles DateTime, DateTime2, Date, Time types.
    Converts T separator to space, truncates fractional seconds.
    """
    i = start + 5  # skip 'CAST('
    n = len(s)

    # Skip whitespace
    while i < n and s[i] in (' ', '\t'):
        i += 1

    # Skip optional N prefix
    if i < n and s[i] == 'N':
        i += 1

    # Expect opening quote
    if i >= n or s[i] != "'":
        return None, 0

    i += 1  # skip opening quote

    # Read string content (handle '' escaping)
    value_chars = []
    while i < n:
        if s[i] == "'":
            if i + 1 < n and s[i + 1] == "'":
                value_chars.append("'")
                i += 2
            else:
                i += 1  # skip closing quote
                break
        else:
            value_chars.append(s[i])
            i += 1

    value = ''.join(value_chars)

    # Skip ' AS Type)' or ' AS Type(precision))'
    remaining = s[i:]
    as_match = re.match(r'\s+AS\s+\w+(?:\([^)]*\))?\s*\)', remaining, re.IGNORECASE)
    if not as_match:
        return None, 0

    i += as_match.end()

    # Convert datetime: T → space, truncate fractional seconds
    value = value.replace('T', ' ')
    value = re.sub(r'(\d{2}:\d{2}:\d{2})\.\d+', r'\1', value)

    return f"'{value}'", i - start


def convert_values_section(s):
    """Convert the VALUES (...) section from MSSQL to MariaDB format.

    State machine with two states:
    - NORMAL: outside any string literal
    - IN_STRING: inside a single-quoted string literal

    In NORMAL state:
    - CAST(... AS Type) → unwrapped datetime string
    - N' → ' (remove Unicode prefix, enter IN_STRING)
    - ' → ' (enter IN_STRING)
    - Everything else passes through

    In IN_STRING state:
    - '' → '' (escaped quote, stay in string)
    - ' (not followed by ') → end of string, return to NORMAL
    - Everything else passes through
    """
    result = []
    i = 0
    n = len(s)
    in_string = False

    while i < n:
        if in_string:
            if s[i] == "'":
                if i + 1 < n and s[i + 1] == "'":
                    # Escaped quote inside string — preserve both
                    result.append("''")
                    i += 2
                else:
                    # End of string
                    result.append("'")
                    in_string = False
                    i += 1
            else:
                result.append(s[i])
                i += 1
        else:
            # NORMAL state — outside any string

            # Check for CAST( pattern
            if s[i:i + 5].upper() == 'CAST(':
                cast_result, consumed = parse_cast_expression(s, i)
                if cast_result is not None:
                    result.append(cast_result)
                    i += consumed
                    continue

            # Check for N' (Unicode string prefix)
            if s[i] == 'N' and i + 1 < n and s[i + 1] == "'":
                result.append("'")  # open string without N prefix
                in_string = True
                i += 2
                continue

            # Check for plain string start
            if s[i] == "'":
                result.append("'")
                in_string = True
                i += 1
                continue

            # Everything else passes through
            result.append(s[i])
            i += 1

    return ''.join(result)


def convert_insert_statement(stmt):
    """Convert an MSSQL INSERT statement (possibly multi-line) to MariaDB SQL.

    Input:  INSERT [dbo].[table] ([col1], [col2]) VALUES (val1, val2)
    Output: INSERT IGNORE INTO `table` (`col1`, `col2`) VALUES ('val1', 'val2');

    Handles multi-line statements where string values contain embedded newlines.
    """
    # Extract table name
    prefix_match = re.match(r"INSERT\s+\[dbo\]\.\[(\w+)\]\s*\(", stmt)
    if not prefix_match:
        return None

    table_name = prefix_match.group(1)

    # Find column list boundary and VALUES
    col_start = stmt.index('(')
    values_match = re.search(r'\)\s*VALUES\s*\(', stmt)
    if not values_match:
        return None

    col_section = stmt[col_start + 1:values_match.start()]
    values_section = stmt[values_match.end() - 1:]  # include opening ( of VALUES

    # Convert column names: [col_name] → `col_name`
    columns = re.sub(r'\[(\w+)\]', r'`\1`', col_section)

    # Convert VALUES section using state machine
    converted_values = convert_values_section(values_section)

    return f"INSERT IGNORE INTO `{table_name}` ({columns}) VALUES {converted_values};"  # nosec: table_name from hardcoded dict


def is_insert_complete(text):
    """Check if an INSERT statement is complete (all strings closed).

    Walks through the text tracking quote state.
    Returns True if all strings are closed and text ends with ')'.
    """
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        if in_string:
            if text[i] == "'":
                if i + 1 < n and text[i + 1] == "'":
                    i += 2  # escaped quote ''
                else:
                    in_string = False
                    i += 1
            else:
                i += 1
        else:
            if text[i] == 'N' and i + 1 < n and text[i + 1] == "'":
                in_string = True
                i += 2
            elif text[i] == "'":
                in_string = True
                i += 1
            else:
                i += 1
    if in_string:
        return False
    return text.rstrip().endswith(')')


def extract_inserts(filepath, target_tables):
    """Single-pass extraction of INSERT statements for target tables.

    Handles multi-line INSERT statements (string values with embedded newlines).
    Returns dict of table_name → list of complete INSERT statement strings.
    """
    prefixes = {f"INSERT [dbo].[{t}]": t for t in target_tables}  # nosec: table names from hardcoded dict
    result = {t: [] for t in target_tables}

    current_table = None
    current_stmt = None

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            raw = line.rstrip('\n').rstrip('\r')

            if current_stmt is not None:
                # Continuation of a multi-line INSERT
                current_stmt += '\n' + raw
                if is_insert_complete(current_stmt):
                    result[current_table].append(current_stmt)
                    current_stmt = None
                    current_table = None
                continue

            # Check if this is an INSERT for a target table
            for prefix, table in prefixes.items():
                if raw.startswith(prefix):
                    if is_insert_complete(raw):
                        # Single-line INSERT
                        result[table].append(raw)
                    else:
                        # Multi-line — start accumulating
                        current_table = table
                        current_stmt = raw
                    break

    # Warn about unclosed statements
    if current_stmt is not None:
        log.warning(f"Unclosed INSERT at end of file for {current_table}")

    return result


# ============================================================
# Database helpers
# ============================================================

def run_sql(sql, timeout=60):
    """Execute SQL against MariaDB, return (success, stdout, stderr)."""
    result = subprocess.run(
        ['mysql', DB_NAME, '-N', '-e', sql],
        capture_output=True, text=True, timeout=timeout
    )
    return result.returncode == 0, result.stdout.strip(), result.stderr.strip()


def get_row_count(table):
    """Get current row count for a table."""
    ok, out, err = run_sql(f'SELECT COUNT(*) FROM `{table}`')  # nosec: table from hardcoded dict
    if not ok:
        log.error(f"Failed to count {table}: {err}")
        return -1
    return int(out)


def execute_sql_file(filepath, timeout=600):
    """Execute a SQL file against MariaDB."""
    with open(filepath, 'r', encoding='utf-8') as f:
        result = subprocess.run(
            ['mysql', DB_NAME],
            stdin=f,
            capture_output=True, text=True, timeout=timeout
        )
    if result.returncode != 0:
        log.error(f"MySQL error: {result.stderr[:500]}")
        return False
    if result.stderr:
        # Warnings are on stderr but aren't fatal
        warnings = result.stderr.strip()
        if warnings:
            log.warning(f"MySQL warnings: {warnings[:300]}")
    return True


# ============================================================
# Phase 1: Cleanup dummy data
# ============================================================

def phase1_cleanup():
    """Delete dummy data created by the old broken converter."""
    log.info("\n" + "=" * 60)
    log.info("PHASE 1: CLEANING UP DUMMY DATA")
    log.info("=" * 60)

    # Check what dummy data exists
    before = {}
    for tbl in ['tory_content_tags', 'tory_recommendations', 'lesson_slides',
                'nx_lessons', 'nx_chapter_details', 'nx_journey_details']:
        before[tbl] = get_row_count(tbl)

    cleanup_sql = """
SET FOREIGN_KEY_CHECKS = 0;

-- Clean up tory_content_tags referencing dummy lessons
DELETE FROM tory_content_tags WHERE nx_lesson_id IS NOT NULL
    AND nx_lesson_id IN (SELECT id FROM nx_lessons WHERE id <= 25);

-- Clean up tory_content_tags with orphaned lesson_detail_ids
DELETE FROM tory_content_tags WHERE lesson_detail_id IS NOT NULL
    AND lesson_detail_id NOT IN (SELECT id FROM lesson_details);

-- Clean up tory_recommendations referencing dummy lessons
DELETE FROM tory_recommendations WHERE nx_lesson_id IS NOT NULL
    AND nx_lesson_id <= 25;

-- Clean up tory_roadmap_items referencing dummy content
DELETE FROM tory_roadmap_items WHERE nx_lesson_id IS NOT NULL
    AND nx_lesson_id <= 25;

-- Delete dummy lessons
DELETE FROM nx_lessons WHERE id <= 25;

-- Delete dummy chapter details
DELETE FROM nx_chapter_details WHERE id <= 8;

-- Delete dummy journey details
DELETE FROM nx_journey_details WHERE id <= 4;

SET FOREIGN_KEY_CHECKS = 1;
"""
    sql_file = WORK_DIR / '_cleanup_dummy.sql'
    with open(sql_file, 'w') as f:
        f.write(cleanup_sql)

    ok = execute_sql_file(sql_file)
    sql_file.unlink()

    if not ok:
        log.error("Phase 1 cleanup FAILED!")
        return False

    # Report what was cleaned
    after = {}
    for tbl in ['tory_content_tags', 'tory_recommendations', 'lesson_slides',
                'nx_lessons', 'nx_chapter_details', 'nx_journey_details']:
        after[tbl] = get_row_count(tbl)
        deleted = before[tbl] - after[tbl]
        if deleted > 0:
            log.info(f"  Cleaned {tbl}: {before[tbl]} → {after[tbl]} ({deleted} deleted)")
        else:
            log.info(f"  {tbl}: unchanged ({after[tbl]} rows)")

    return True


# ============================================================
# Phase 2+3: Extract, convert, restore per table
# ============================================================

def restore_table(table_name, mode, expected_source_count, statements):
    """Restore a single table from MSSQL to MariaDB.

    Args:
        table_name: table to restore
        mode: 'full' or 'merge'
        expected_source_count: expected number of INSERT statements from MSSQL
        statements: list of raw MSSQL INSERT statements (pre-extracted)
    """
    log.info(f"\n{'─' * 60}")
    log.info(f"RESTORING: {table_name} (mode={mode})")
    log.info(f"{'─' * 60}")

    before_count = get_row_count(table_name)
    log.info(f"  MariaDB before: {before_count} rows")

    source_count = len(statements)
    log.info(f"  MSSQL source: {source_count} rows")

    if source_count != expected_source_count:
        log.warning(f"  Source count {source_count} != expected {expected_source_count}")

    # Convert each statement
    converted_lines = []
    failed_count = 0

    for i, stmt in enumerate(statements):
        converted = convert_insert_statement(stmt)
        if converted:
            converted_lines.append(converted)
        else:
            failed_count += 1
            log.warning(f"  FAILED stmt #{i+1}: {stmt[:100]}...")

    log.info(f"  Converted: {len(converted_lines)}, Failed: {failed_count}")

    if failed_count > 0:
        log.error(f"  {failed_count} rows FAILED conversion!")

    if not converted_lines:
        log.warning(f"  No rows to insert for {table_name}")
        return True

    # Write temp SQL file
    sql_file = WORK_DIR / f'_restore_{table_name}.sql'
    with open(sql_file, 'w', encoding='utf-8') as f:
        f.write("SET NAMES utf8mb4;\n")
        f.write("SET FOREIGN_KEY_CHECKS = 0;\n")
        f.write("SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO,NO_BACKSLASH_ESCAPES';\n")
        f.write("SET UNIQUE_CHECKS = 0;\n\n")
        for line in converted_lines:
            f.write(line + '\n')
        f.write("\nSET FOREIGN_KEY_CHECKS = 1;\n")
        f.write("SET UNIQUE_CHECKS = 1;\n")

    # Execute
    log.info(f"  Loading into MariaDB...")
    ok = execute_sql_file(sql_file, timeout=600)
    sql_file.unlink()

    if not ok:
        log.error(f"  LOAD FAILED for {table_name}!")
        return False

    # Validate
    after_count = get_row_count(table_name)
    inserted = after_count - before_count
    log.info(f"  MariaDB after: {after_count} rows (+{inserted} inserted)")

    if mode == 'full':
        if after_count == source_count:
            log.info(f"  PASS: {after_count} rows matches source")
        elif after_count >= expected_source_count:
            log.info(f"  OK: {after_count} rows (expected {expected_source_count})")
        else:
            log.warning(f"  MISMATCH: {after_count} rows, expected {expected_source_count}, source had {source_count}")
    else:
        log.info(f"  Merge result: {before_count} existing + {inserted} new = {after_count}")

    return True


# ============================================================
# Phase 4: Validation
# ============================================================

def phase4_validate():
    """Validate FK integrity and row counts after restoration."""
    log.info("\n" + "=" * 60)
    log.info("PHASE 4: VALIDATION")
    log.info("=" * 60)

    issues = []

    # Critical check: lesson_details must have data
    ld_count = get_row_count('lesson_details')
    if ld_count >= 86:
        log.info(f"  PASS: lesson_details has {ld_count} rows (>= 86)")
    else:
        msg = f"CRITICAL: lesson_details has only {ld_count} rows (expected >= 86)"
        log.error(f"  {msg}")
        issues.append(msg)

    # Critical check: video_libraries
    vl_count = get_row_count('video_libraries')
    if vl_count >= 155:
        log.info(f"  PASS: video_libraries has {vl_count} rows (>= 155)")
    else:
        msg = f"video_libraries has only {vl_count} rows (expected >= 155)"
        log.warning(f"  {msg}")
        issues.append(msg)

    # Check lesson_slides FK integrity
    ok, out, _ = run_sql("""
        SELECT COUNT(*) FROM lesson_slides ls
        WHERE ls.lesson_detail_id IS NOT NULL
        AND ls.lesson_detail_id NOT IN (SELECT id FROM lesson_details)
    """)
    if ok and int(out or 0) > 0:
        msg = f"lesson_slides has {out} orphaned lesson_detail_id references"
        log.warning(f"  {msg}")
        issues.append(msg)
    else:
        log.info("  PASS: lesson_slides FK integrity (lesson_detail_id)")

    # Check lesson_slides → video_libraries FK
    ok, out, _ = run_sql("""
        SELECT COUNT(*) FROM lesson_slides ls
        WHERE ls.video_library_id IS NOT NULL
        AND ls.video_library_id NOT IN (SELECT id FROM video_libraries)
    """)
    if ok and int(out or 0) > 0:
        msg = f"lesson_slides has {out} orphaned video_library_id references"
        log.warning(f"  {msg}")
        issues.append(msg)
    else:
        log.info("  PASS: lesson_slides FK integrity (video_library_id)")

    # Check lesson_details → nx_lessons FK
    ok, out, _ = run_sql("""
        SELECT COUNT(*) FROM lesson_details ld
        WHERE ld.nx_lesson_id IS NOT NULL
        AND ld.nx_lesson_id NOT IN (SELECT id FROM nx_lessons)
    """)
    if ok and int(out or 0) > 0:
        msg = f"lesson_details has {out} orphaned nx_lesson_id references"
        log.warning(f"  {msg}")
        issues.append(msg)
    else:
        log.info("  PASS: lesson_details FK integrity (nx_lesson_id)")

    # Check lesson_details → nx_chapter_details FK
    ok, out, _ = run_sql("""
        SELECT COUNT(*) FROM lesson_details ld
        WHERE ld.nx_chapter_detail_id IS NOT NULL
        AND ld.nx_chapter_detail_id NOT IN (SELECT id FROM nx_chapter_details)
    """)
    if ok and int(out or 0) > 0:
        msg = f"lesson_details has {out} orphaned nx_chapter_detail_id references"
        log.warning(f"  {msg}")
        issues.append(msg)
    else:
        log.info("  PASS: lesson_details FK integrity (nx_chapter_detail_id)")

    # Check lesson_details → nx_journey_details FK
    ok, out, _ = run_sql("""
        SELECT COUNT(*) FROM lesson_details ld
        WHERE ld.nx_journey_detail_id IS NOT NULL
        AND ld.nx_journey_detail_id NOT IN (SELECT id FROM nx_journey_details)
    """)
    if ok and int(out or 0) > 0:
        msg = f"lesson_details has {out} orphaned nx_journey_detail_id references"
        log.warning(f"  {msg}")
        issues.append(msg)
    else:
        log.info("  PASS: lesson_details FK integrity (nx_journey_detail_id)")

    # Spot check: lesson_details content
    ok, out, _ = run_sql("SELECT id, nx_journey_detail_id, nx_lesson_id, status FROM lesson_details LIMIT 5")
    if ok:
        log.info(f"  Spot check lesson_details: {out}")

    # Summary row counts for all 29 tables
    log.info("\n  Final row counts:")
    for table, mode, expected in RESTORE_ORDER:
        count = get_row_count(table)
        marker = "  "
        if expected and count < expected:
            marker = "!!"
        log.info(f"  {marker} {table}: {count} rows (source: {expected})")

    if issues:
        log.warning(f"\n  {len(issues)} validation issues found:")
        for issue in issues:
            log.warning(f"    - {issue}")
    else:
        log.info("\n  ALL VALIDATIONS PASSED")

    return len(issues) == 0


# ============================================================
# Phase 5: Re-dump
# ============================================================

def phase5_redump():
    """Re-dump baap database to baap.sql.gz."""
    log.info("\n" + "=" * 60)
    log.info("PHASE 5: RE-DUMP DATABASE")
    log.info("=" * 60)

    dump_dir = WORK_DIR.parent / 'db'
    dump_file = dump_dir / 'baap.sql.gz'
    backup_file = dump_dir / 'baap.sql.gz.bak'

    # Backup existing dump
    if dump_file.exists():
        import shutil
        shutil.copy2(dump_file, backup_file)
        log.info(f"  Backed up existing dump to {backup_file.name}")

    # Dump with mysqldump
    log.info("  Running mysqldump...")
    result = subprocess.run(
        f'mysqldump --single-transaction --routines --triggers '
        f'--default-character-set=utf8mb4 {DB_NAME} | gzip > {dump_file}',
        shell=True, capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        log.error(f"  mysqldump FAILED: {result.stderr}")
        return False

    size_mb = dump_file.stat().st_size / (1024 * 1024)
    log.info(f"  Dump created: {dump_file} ({size_mb:.1f} MB)")

    return True


# ============================================================
# Main
# ============================================================

def main():
    log.info("=" * 60)
    log.info("MSSQL → MariaDB Data Restorer")
    log.info("=" * 60)
    log.info(f"Source: {MSSQL_FILE}")
    log.info(f"Target: MariaDB/{DB_NAME}")
    log.info(f"Tables: {len(RESTORE_ORDER)}")

    # Check source file exists
    if not os.path.exists(MSSQL_FILE):
        log.error(f"MSSQL backup not found: {MSSQL_FILE}")
        sys.exit(1)

    # Allow running individual phases via CLI args
    phases = sys.argv[1:] if len(sys.argv) > 1 else ['1', '2', '3', '4', '5']

    if '1' in phases:
        if not phase1_cleanup():
            log.error("Phase 1 failed — aborting")
            sys.exit(1)

    if '2' in phases or '3' in phases:
        # Single-pass extraction of all target tables
        target_tables = [t for t, _, _ in RESTORE_ORDER]
        log.info(f"\nExtracting INSERT statements for {len(target_tables)} tables (single pass)...")
        all_inserts = extract_inserts(MSSQL_FILE, target_tables)
        for t in target_tables:
            log.info(f"  {t}: {len(all_inserts[t])} statements extracted")

        # Phase 3: restore tables in FK order
        results = {}
        for table, mode, expected in RESTORE_ORDER:
            success = restore_table(table, mode, expected, all_inserts[table])
            results[table] = success
            if not success:
                log.error(f"Failed to restore {table} — continuing with remaining tables")

        ok_count = sum(1 for v in results.values() if v)
        fail_count = sum(1 for v in results.values() if not v)
        log.info(f"\nPhase 3 complete: {ok_count} OK, {fail_count} failed")

    if '4' in phases:
        phase4_validate()

    if '5' in phases:
        phase5_redump()

    log.info("\n" + "=" * 60)
    log.info("RESTORATION COMPLETE")
    log.info("=" * 60)


if __name__ == '__main__':
    main()
