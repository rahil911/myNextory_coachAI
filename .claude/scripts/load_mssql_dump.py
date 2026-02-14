#!/usr/bin/env python3
"""
Load SQL Server dump into MariaDB.
Converts T-SQL to MySQL on the fly and loads table by table.
"""

import re
import subprocess
import sys
import os


def mysql_exec(sql, database="baap"):
    """Execute SQL via mysql client."""
    result = subprocess.run(
        ["mysql", database, "-e", sql],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, result.stdout.strip()


def mysql_load_file(filepath, database="baap"):
    """Load a SQL file via mysql client."""
    with open(filepath) as f:
        result = subprocess.run(
            ["mysql", "--force", "--binary-mode", database],
            stdin=f, capture_output=True, text=True, timeout=600
        )
    err_lines = [l for l in result.stderr.strip().split('\n') if l.strip()] if result.stderr.strip() else []
    return len(err_lines)


def parse_create_table(block):
    """Convert a SQL Server CREATE TABLE block to MariaDB."""
    # Remove [dbo]. prefix
    block = re.sub(r'\[dbo\]\.\[([^\]]+)\]', r'`\1`', block)
    # Remove remaining brackets
    block = re.sub(r'\[([^\]]+)\]', r'`\1`', block)

    # Remove IDENTITY
    has_identity = bool(re.search(r'IDENTITY\(\d+,\d+\)', block))
    block = re.sub(r'\s*IDENTITY\(\d+,\d+\)', '', block)

    # Type conversions
    type_map = {
        r'`nvarchar`\(max\)': 'LONGTEXT',
        r'`nvarchar`\((\d+)\)': r'VARCHAR(\1)',
        r'`varchar`\(max\)': 'LONGTEXT',
        r'`varchar`\((\d+)\)': r'VARCHAR(\1)',
        r'`nchar`\((\d+)\)': r'CHAR(\1)',
        r'`char`\((\d+)\)': r'CHAR(\1)',
        r'`ntext`': 'LONGTEXT',
        r'`text`': 'LONGTEXT',
        r'`bigint`': 'BIGINT',
        r'`int`': 'INT',
        r'`smallint`': 'SMALLINT',
        r'`tinyint`': 'TINYINT',
        r'`bit`': 'TINYINT(1)',
        r'`float`': 'DOUBLE',
        r'`real`': 'FLOAT',
        r'`money`': 'DECIMAL(19,4)',
        r'`decimal`\((\d+),\s*(\d+)\)': r'DECIMAL(\1,\2)',
        r'`numeric`\((\d+),\s*(\d+)\)': r'DECIMAL(\1,\2)',
        r'`datetime2`\((\d+)\)': r'DATETIME(\1)',
        r'`datetime2`': 'DATETIME(6)',
        r'`datetime`': 'DATETIME',
        r'`datetimeoffset`\((\d+)\)': r'DATETIME(\1)',
        r'`datetimeoffset`': 'DATETIME(6)',
        r'`date`': 'DATE',
        r'`time`\((\d+)\)': r'TIME(\1)',
        r'`time`': 'TIME',
        r'`uniqueidentifier`': 'CHAR(36)',
        r'`image`': 'LONGBLOB',
        r'`varbinary`\(max\)': 'LONGBLOB',
        r'`varbinary`\((\d+)\)': r'VARBINARY(\1)',
        r'`xml`': 'LONGTEXT',
        r'`sql_variant`': 'TEXT',
        r'`hierarchyid`': 'VARCHAR(4000)',
    }

    for pattern, replacement in type_map.items():
        block = re.sub(pattern, replacement, block, flags=re.IGNORECASE)

    # Fix TIME/DATETIME precision > 6
    block = re.sub(r'TIME\(7\)', 'TIME(6)', block)
    block = re.sub(r'DATETIME\(7\)', 'DATETIME(6)', block)

    # Remove SQL Server specific clauses
    block = re.sub(r'\s*TEXTIMAGE_ON\s+`\w+`', '', block)
    block = re.sub(r'\s*ON\s+`PRIMARY`', '', block)
    block = re.sub(r'\s*WITH\s*\([^)]*\)', '', block)
    block = re.sub(r'\s*(CLUSTERED|NONCLUSTERED)\s*', ' ', block)
    block = re.sub(r'CONSTRAINT\s+`[^`]+`\s+PRIMARY\s+KEY', 'PRIMARY KEY', block, flags=re.IGNORECASE)
    block = re.sub(r'`(\w+)`\s+ASC', r'`\1`', block)
    block = re.sub(r'`(\w+)`\s+DESC', r'`\1`', block)

    # Find PK column
    pk_match = re.search(r'PRIMARY\s+KEY\s*\(\s*`(\w+)`', block, re.IGNORECASE | re.DOTALL)
    pk_col = pk_match.group(1) if pk_match else None

    # Add AUTO_INCREMENT if identity column
    if has_identity and pk_col:
        pattern = re.compile(r'(`' + re.escape(pk_col) + r'`\s+(?:BIGINT|INT|SMALLINT|TINYINT)\s+NOT\s+NULL)', re.IGNORECASE)
        block = pattern.sub(r'\1 AUTO_INCREMENT', block)
    elif has_identity:
        # Add AUTO_INCREMENT to the first integer NOT NULL column
        block = re.sub(
            r'(`\w+`\s+(?:BIGINT|INT)\s+NOT\s+NULL)(?!\s+AUTO_INCREMENT)',
            r'\1 AUTO_INCREMENT',
            block,
            count=1,
            flags=re.IGNORECASE
        )
        # Also add PRIMARY KEY if missing
        if 'PRIMARY KEY' not in block.upper():
            id_match = re.search(r'`(\w+)`\s+(?:BIGINT|INT)\s+NOT\s+NULL\s+AUTO_INCREMENT', block, re.IGNORECASE)
            if id_match:
                pk_col = id_match.group(1)
                block = re.sub(r'\)\s*$', f',\nPRIMARY KEY (`{pk_col}`)\n)', block)

    # Remove trailing comma before closing paren
    block = re.sub(r',\s*\n(\s*\))', r'\n\1', block)
    block = re.sub(r',\s*\n(\s*PRIMARY)', r',\n\1', block)  # Keep comma before PRIMARY KEY

    # Add ENGINE
    block = block.rstrip().rstrip(';')
    block += ' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n'

    return block


def convert_insert(line):
    """Convert a SQL Server INSERT to MariaDB."""
    # [dbo].[table] → `table`
    line = re.sub(r'\[dbo\]\.\[([^\]]+)\]', r'`\1`', line)

    # INSERT [table] → INSERT INTO `table`
    line = re.sub(r'^INSERT\s+\[([^\]]+)\]', r'INSERT INTO `\1`', line)
    line = re.sub(r'^INSERT\s+`([^`]+)`', r'INSERT INTO `\1`', line)

    # Handle column names in parentheses after table name - convert [col] to `col`
    # But be careful not to convert data in VALUES(...)

    # Split into column part and values part
    values_idx = line.upper().find(' VALUES ')
    if values_idx == -1:
        values_idx = line.upper().find(' VALUES(')

    if values_idx != -1:
        col_part = line[:values_idx]
        val_part = line[values_idx:]

        # Convert column brackets
        col_part = re.sub(r'\[([^\]]+)\]', r'`\1`', col_part)

        # In VALUES, remove N' prefix and CAST wrappers
        val_part = re.sub(r"N'", "'", val_part)
        val_part = re.sub(r"CAST\('([^']*)'\s+AS\s+\w+(?:\([^)]*\))?\)", r"'\1'", val_part)

        line = col_part + val_part
    else:
        line = re.sub(r'\[([^\]]+)\]', r'`\1`', line)

    # Ensure ends with semicolon
    line = line.rstrip()
    if not line.endswith(';'):
        line += ';'

    return line


def main():
    input_file = '/home/rahil/Projects/baap/app-mynextory-backup-utf8.sql'

    print(f"Reading {input_file}...")
    with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # Remove BOM and normalize line endings
    content = content.lstrip('\ufeff')
    content = content.replace('\r\n', '\n')

    # Split by GO
    blocks = re.split(r'\nGO\s*\n', content)

    # Collect CREATE TABLEs and INSERTs
    create_tables = []
    inserts_by_table = {}

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if 'CREATE TABLE' in block and '[dbo]' in block:
            # Extract just the CREATE TABLE part (skip SET statements)
            ct_match = re.search(r'(CREATE TABLE.*)', block, re.DOTALL)
            if ct_match:
                create_tables.append(ct_match.group(1))

        elif block.upper().lstrip().startswith('INSERT'):
            for line in block.split('\n'):
                line = line.strip()
                if not line or line.upper().startswith('SET ') or line.startswith('--'):
                    continue
                if line.upper().startswith('INSERT'):
                    # Extract table name
                    m = re.search(r'INSERT\s+\[dbo\]\.\[(\w+)\]', line) or re.search(r'INSERT\s+\[(\w+)\]', line)
                    if m:
                        table = m.group(1)
                        if table not in inserts_by_table:
                            inserts_by_table[table] = []
                        inserts_by_table[table].append(line)

    print(f"Found {len(create_tables)} CREATE TABLE blocks")
    print(f"Found {len(inserts_by_table)} tables with INSERT data")
    print(f"Total INSERT statements: {sum(len(v) for v in inserts_by_table.values())}")

    # Step 1: Recreate database
    print("\nRecreating database...")
    subprocess.run(['mysql', '-e', 'DROP DATABASE IF EXISTS baap; CREATE DATABASE baap CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'], check=True)

    # Step 2: Create tables
    print("Creating tables...")
    schema_sql = "SET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS = 0;\nSET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';\n\n"

    for ct in create_tables:
        converted = parse_create_table(ct)
        schema_sql += converted + '\n'

    schema_sql += "\nSET FOREIGN_KEY_CHECKS = 1;\n"

    with open('/tmp/baap_schema.sql', 'w') as f:
        f.write(schema_sql)

    result = subprocess.run(['mysql', 'baap'], input=schema_sql, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Schema errors:\n{result.stderr[:1000]}")
        # Try with --force
        err_count = mysql_load_file('/tmp/baap_schema.sql')
        print(f"  Retried with --force, {err_count} errors")

    # Verify tables
    ok, out = mysql_exec("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='baap'")
    table_count = out.split('\n')[-1] if ok else "0"
    print(f"Tables created: {table_count}")

    # Step 3: Load data table by table
    print("\nLoading data...")
    total_rows = 0
    total_errors = 0

    for table in sorted(inserts_by_table.keys()):
        insert_lines = inserts_by_table[table]

        # Convert inserts
        converted = []
        for line in insert_lines:
            try:
                c = convert_insert(line)
                converted.append(c)
            except Exception as e:
                total_errors += 1

        # Write to temp file
        tmpfile = f'/tmp/baap_{table}.sql'
        with open(tmpfile, 'w') as f:
            f.write("SET FOREIGN_KEY_CHECKS=0;\n")
            f.write("SET SQL_MODE='NO_AUTO_VALUE_ON_ZERO';\n")
            for c in converted:
                f.write(c + '\n')

        # Load
        err_count = mysql_load_file(tmpfile)
        total_errors += err_count

        # Check count
        ok, out = mysql_exec(f"SELECT COUNT(*) FROM `{table}`")
        count = int(out.split('\n')[-1]) if ok and out.split('\n')[-1].isdigit() else 0
        total_rows += count

        if count > 0 or err_count > 0:
            status = f"{count}/{len(insert_lines)} rows" + (f", {err_count} errors" if err_count else "")
            print(f"  {table}: {status}")

        os.remove(tmpfile)

    print(f"\nDone! {total_rows:,} total rows, {total_errors} total errors")

    # Final verification
    print("\nFinal table summary:")
    ok, out = mysql_exec("SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.tables WHERE table_schema='baap' ORDER BY TABLE_ROWS DESC")
    print(out)


if __name__ == '__main__':
    main()
