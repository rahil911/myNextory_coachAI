#!/usr/bin/env python3
"""
Convert SQL Server dump to MariaDB-compatible SQL.

Handles:
- [dbo].[table] → `table` bracket notation
- IDENTITY(1,1) → AUTO_INCREMENT
- [nvarchar](max) → TEXT, [nvarchar](N) → VARCHAR(N)
- [datetime] → DATETIME, [bigint] → BIGINT, etc.
- GO statements → removed
- CLUSTERED/NONCLUSTERED indexes → simplified
- WITH (...) clauses on indexes → removed
- ON [PRIMARY] → removed
- SET ANSI_NULLS/QUOTED_IDENTIFIER → removed
- ALTER DATABASE → removed
- CREATE SCHEMA → removed
- INSERT [dbo].[table] → INSERT INTO `table`
- TEXTIMAGE_ON [PRIMARY] → removed
- CONSTRAINT [name] PRIMARY KEY → simplified
- N'string' → 'string' (Unicode prefix removed)
- CAST(N'...' AS ...) → simplified
"""

import re
import sys
from pathlib import Path


def convert_type(match):
    """Convert SQL Server types to MariaDB types."""
    full = match.group(0)
    type_name = match.group(1).lower()
    size = match.group(2) if match.lastindex >= 2 else None

    type_map = {
        'bigint': 'BIGINT',
        'int': 'INT',
        'smallint': 'SMALLINT',
        'tinyint': 'TINYINT',
        'bit': 'TINYINT(1)',
        'decimal': f'DECIMAL({size})' if size else 'DECIMAL',
        'numeric': f'DECIMAL({size})' if size else 'DECIMAL',
        'float': 'DOUBLE',
        'real': 'FLOAT',
        'money': 'DECIMAL(19,4)',
        'smallmoney': 'DECIMAL(10,4)',
        'datetime': 'DATETIME',
        'datetime2': 'DATETIME(6)',
        'date': 'DATE',
        'time': 'TIME',
        'datetimeoffset': 'DATETIME(6)',
        'smalldatetime': 'DATETIME',
        'timestamp': 'TIMESTAMP',
        'uniqueidentifier': 'CHAR(36)',
        'xml': 'LONGTEXT',
        'sql_variant': 'TEXT',
        'hierarchyid': 'VARCHAR(4000)',
        'geometry': 'GEOMETRY',
        'geography': 'LONGTEXT',
        'image': 'LONGBLOB',
        'binary': f'BINARY({size})' if size else 'BLOB',
        'varbinary': f'VARBINARY({size})' if size and size.lower() != 'max' else 'LONGBLOB',
    }

    if type_name == 'nvarchar':
        if size and size.lower() == 'max':
            return 'LONGTEXT'
        elif size:
            return f'VARCHAR({size})'
        return 'VARCHAR(255)'

    if type_name == 'varchar':
        if size and size.lower() == 'max':
            return 'LONGTEXT'
        elif size:
            return f'VARCHAR({size})'
        return 'VARCHAR(255)'

    if type_name == 'nchar':
        return f'CHAR({size})' if size else 'CHAR(255)'

    if type_name == 'char':
        return f'CHAR({size})' if size else 'CHAR(255)'

    if type_name == 'text':
        return 'LONGTEXT'

    if type_name == 'ntext':
        return 'LONGTEXT'

    if type_name in type_map:
        return type_map[type_name]

    return full


def convert_line(line):
    """Convert a single line from SQL Server to MariaDB syntax."""
    original = line
    stripped = line.strip()

    # Skip lines we don't need
    skip_patterns = [
        r'^SET ANSI_NULLS',
        r'^SET QUOTED_IDENTIFIER',
        r'^SET ANSI_PADDING',
        r'^SET ANSI_WARNINGS',
        r'^SET ARITHABORT',
        r'^ALTER DATABASE',
        r'^CREATE DATABASE',
        r'^CREATE SCHEMA',
        r'^--\s*ALTER DATABASE',
        r'^/\*\*\*\*\*\*\s*Object:\s*Database',
        r'^/\*\*\*\s*The scripts of database',
        r'^GO\s*$',
        r'^\s*$',
    ]

    for pattern in skip_patterns:
        if re.match(pattern, stripped, re.IGNORECASE):
            return None

    # Remove BOM
    line = line.lstrip('\ufeff')

    # Remove comment headers but keep table object comments for tracking
    if stripped.startswith('/****** Object:') and 'Table' not in stripped and 'Index' not in stripped:
        return None

    # Convert [dbo].[table_name] to `table_name`
    line = re.sub(r'\[dbo\]\.\[([^\]]+)\]', r'`\1`', line)

    # Convert remaining [name] brackets to `name` backticks
    line = re.sub(r'\[([^\]]+)\]', r'`\1`', line)

    # Remove IDENTITY(seed,increment) and add AUTO_INCREMENT
    line = re.sub(r'\s*IDENTITY\(\d+,\d+\)', '', line)

    # Convert data types with size: [type](size) or `type`(size)
    line = re.sub(r'`(nvarchar|varchar|nchar|char|varbinary|binary|decimal|numeric)`\((\w+(?:,\s*\w+)?)\)',
                  lambda m: convert_type(m), line, flags=re.IGNORECASE)

    # Convert data types without size
    line = re.sub(r'`(bigint|int|smallint|tinyint|bit|float|real|money|smallmoney|datetime|datetime2|date|time|datetimeoffset|smalldatetime|uniqueidentifier|xml|text|ntext|image|sql_variant|hierarchyid|geometry|geography)`',
                  lambda m: convert_type(m), line, flags=re.IGNORECASE)

    # Remove TEXTIMAGE_ON [PRIMARY]
    line = re.sub(r'\s*TEXTIMAGE_ON\s+`\w+`', '', line)

    # Remove ON [PRIMARY]
    line = re.sub(r'\s*ON\s+`PRIMARY`', '', line)

    # Remove WITH (...) clauses on index/constraint definitions
    line = re.sub(r'\s*WITH\s*\([^)]*\)', '', line)

    # Convert CLUSTERED/NONCLUSTERED index hints
    line = re.sub(r'\s*(CLUSTERED|NONCLUSTERED)\s*', ' ', line)

    # Convert CONSTRAINT [name] PRIMARY KEY
    line = re.sub(r'CONSTRAINT\s+`[^`]+`\s+PRIMARY\s+KEY', 'PRIMARY KEY', line, flags=re.IGNORECASE)

    # Convert INSERT [dbo].[table] to INSERT INTO `table`
    line = re.sub(r'INSERT\s+`([^`]+)`', r'INSERT INTO `\1`', line)

    # Remove N' prefix (Unicode string literal)
    line = re.sub(r"N'", "'", line)

    # Remove CAST(... AS ...) around string literals in VALUES (simplify)
    line = re.sub(r"CAST\('([^']*)'\s+AS\s+\w+(?:\([^)]*\))?\)", r"'\1'", line)

    # Handle SET IDENTITY_INSERT
    line = re.sub(r'SET\s+IDENTITY_INSERT\s+`([^`]+)`\s+ON', '', line, flags=re.IGNORECASE)
    line = re.sub(r'SET\s+IDENTITY_INSERT\s+`([^`]+)`\s+OFF', '', line, flags=re.IGNORECASE)

    # Remove ASC/DESC from PRIMARY KEY column lists
    line = re.sub(r'`(\w+)`\s+ASC', r'`\1`', line)
    line = re.sub(r'`(\w+)`\s+DESC', r'`\1`', line)

    # Clean up empty lines after conversions
    if not line.strip():
        return None

    return line


def add_auto_increment(create_block):
    """Add AUTO_INCREMENT to the identity column in a CREATE TABLE block."""
    # Find the identity column (the one that had IDENTITY removed)
    # In SQL Server, IDENTITY columns are typically the first column and are NOT NULL
    # We detect them by looking for the original pattern or by finding the PK column
    lines = create_block.split('\n')
    pk_column = None

    # Find the PRIMARY KEY column
    for line in lines:
        pk_match = re.search(r'PRIMARY\s+KEY\s*\(\s*`(\w+)`', line, re.IGNORECASE)
        if pk_match:
            pk_column = pk_match.group(1)
            break

    if not pk_column:
        return create_block

    # Check if this column is an integer type (likely identity)
    result_lines = []
    for line in lines:
        col_match = re.match(r'(\s*`' + re.escape(pk_column) + r'`\s+)(BIGINT|INT|SMALLINT|TINYINT)(\s.*)', line, re.IGNORECASE)
        if col_match:
            # Add AUTO_INCREMENT before NOT NULL or at end
            prefix = col_match.group(1)
            col_type = col_match.group(2)
            rest = col_match.group(3)
            if 'NOT NULL' in rest.upper():
                rest = re.sub(r'NOT\s+NULL', 'NOT NULL AUTO_INCREMENT', rest, flags=re.IGNORECASE)
            else:
                rest = rest.rstrip(',') + ' AUTO_INCREMENT,'
            line = prefix + col_type + rest
        result_lines.append(line)

    return '\n'.join(result_lines)


def process_create_table(block):
    """Process a complete CREATE TABLE block."""
    # Remove trailing commas before closing paren
    block = re.sub(r',\s*\n\s*\)', '\n)', block)

    # Add engine and charset
    block = re.sub(r'\)\s*$', ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;', block.rstrip())
    block = re.sub(r'\)\s*;?\s*$', ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;', block.rstrip())

    # Add AUTO_INCREMENT
    block = add_auto_increment(block)

    return block


def convert_file(input_path, output_path):
    """Convert the entire SQL Server dump file to MariaDB format."""
    print(f"Reading {input_path}...")

    with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # Remove BOM
    content = content.lstrip('\ufeff')

    # Remove carriage returns
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    # Split by GO statements
    blocks = re.split(r'\nGO\s*\n', content)

    output_lines = []
    output_lines.append("-- Converted from SQL Server to MariaDB")
    output_lines.append("SET NAMES utf8mb4;")
    output_lines.append("SET FOREIGN_KEY_CHECKS = 0;")
    output_lines.append("SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';")
    output_lines.append("")

    table_count = 0
    insert_count = 0

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Skip database-level operations
        if any(block.upper().startswith(s) for s in [
            'CREATE DATABASE', 'ALTER DATABASE', 'CREATE SCHEMA',
            'SET ANSI_NULLS', 'SET QUOTED_IDENTIFIER', 'SET ANSI_PADDING',
            'SET ANSI_WARNINGS', 'SET ARITHABORT',
        ]):
            continue

        # Skip comment-only blocks
        if block.startswith('/***') and 'CREATE TABLE' not in block:
            if 'Object:  Table' in block or 'Object:  Index' in block:
                # Keep as a marker comment
                table_comment = re.search(r'Object:\s+\w+\s+\[dbo\]\.\[(\w+)\]', block)
                if table_comment:
                    output_lines.append(f"\n-- Table: {table_comment.group(1)}")
            continue

        # Handle CREATE TABLE blocks
        if 'CREATE TABLE' in block.upper():
            # Convert line by line
            converted_lines = []
            for line in block.split('\n'):
                converted = convert_line(line)
                if converted is not None:
                    converted_lines.append(converted)

            if converted_lines:
                create_block = '\n'.join(converted_lines)
                create_block = process_create_table(create_block)
                output_lines.append(create_block)
                output_lines.append("")
                table_count += 1
                if table_count % 10 == 0:
                    print(f"  Converted {table_count} tables...")

        # Handle INSERT blocks
        elif block.upper().lstrip().startswith('INSERT'):
            # Convert each INSERT statement
            for line in block.split('\n'):
                line = line.strip()
                if not line or line.upper().startswith('SET IDENTITY') or line.upper().startswith('SET ANSI'):
                    continue
                if line.upper().startswith('INSERT'):
                    converted = convert_line(line)
                    if converted and converted.strip():
                        # Make sure it ends with semicolon
                        converted = converted.rstrip()
                        if not converted.endswith(';'):
                            converted += ';'
                        output_lines.append(converted)
                        insert_count += 1
                        if insert_count % 10000 == 0:
                            print(f"  Converted {insert_count} inserts...")

        # Handle SET IDENTITY_INSERT and other SET statements
        elif block.upper().startswith('SET IDENTITY'):
            continue

        # Handle CREATE INDEX blocks
        elif 'CREATE' in block.upper() and 'INDEX' in block.upper():
            converted = convert_line(block.replace('\n', ' '))
            if converted and converted.strip():
                # Simplify the index
                converted = re.sub(r'\s+', ' ', converted)
                converted = converted.rstrip()
                if not converted.endswith(';'):
                    converted += ';'
                output_lines.append(converted)

    output_lines.append("")
    output_lines.append("SET FOREIGN_KEY_CHECKS = 1;")

    print(f"\nWriting {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    print(f"Converted: {table_count} tables, {insert_count} inserts")
    return table_count, insert_count


if __name__ == '__main__':
    input_file = sys.argv[1] if len(sys.argv) > 1 else '/home/rahil/Projects/baap/app-mynextory-backup-utf8.sql'
    output_file = sys.argv[2] if len(sys.argv) > 2 else '/home/rahil/Projects/baap/app-mynextory-mariadb.sql'

    tables, inserts = convert_file(input_file, output_file)
    print(f"\nDone! {tables} tables, {inserts} inserts written to {output_file}")
