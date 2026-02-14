#!/usr/bin/env python3
"""
Baap Phase 1b: Relationship Mapper
Discovers explicit FKs and inferred relationships between tables in the baap database.
Outputs .claude/discovery/relationships.json
"""

import json
import subprocess
import re
import sys
from datetime import datetime, timezone
from collections import defaultdict

MAPPER_VERSION = "1.0"
DATABASE = "baap"


def run_query(sql):
    """Execute a MySQL query and return rows as list of dicts."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"Query error: {result.stderr}", file=sys.stderr)
        return []
    lines = result.stdout.strip().split("\n")
    if len(lines) < 2:
        return []
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        rows.append(dict(zip(headers, values)))
    return rows


def get_tables():
    """Get all table names."""
    rows = run_query("SHOW TABLES;")
    if not rows:
        return []
    key = list(rows[0].keys())[0]
    return [r[key] for r in rows]


def get_columns(table):
    """Get column metadata for a table."""
    rows = run_query(
        f"SELECT COLUMN_NAME, DATA_TYPE, COLUMN_KEY, IS_NULLABLE, COLUMN_TYPE "
        f"FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA = '{DATABASE}' AND TABLE_NAME = '{table}' "
        f"ORDER BY ORDINAL_POSITION;"
    )
    return rows


def get_explicit_fks():
    """Get explicit foreign key constraints from information_schema."""
    rows = run_query(
        "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME, "
        "CONSTRAINT_NAME "
        "FROM information_schema.KEY_COLUMN_USAGE "
        f"WHERE TABLE_SCHEMA = '{DATABASE}' AND REFERENCED_TABLE_NAME IS NOT NULL;"
    )
    return rows


def singularize(word):
    """Simple singularization: remove trailing s, es, ies->y."""
    if not word:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("ses") or word.endswith("xes") or word.endswith("zes") or word.endswith("ches") or word.endswith("shes"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def pluralize(word):
    """Simple pluralization."""
    if not word:
        return word
    if word.endswith("y") and not word.endswith("ey") and not word.endswith("ay") and not word.endswith("oy"):
        return word[:-1] + "ies"
    if word.endswith("s") or word.endswith("x") or word.endswith("z") or word.endswith("ch") or word.endswith("sh"):
        return word + "es"
    return word + "s"


def find_target_table(col_name, all_tables, source_table):
    """
    Given a column name, try to find the target table it references.
    Returns (target_table, target_column, confidence, pattern_name) or None.
    """
    all_tables_set = set(all_tables)
    all_tables_lower = {t.lower(): t for t in all_tables}

    # ---- Pattern: self-referencing parent_id ----
    if col_name == "parent_id":
        return (source_table, "id", 0.85, "self_reference_parent_id")

    # ---- Pattern: created_by / updated_by / hosting_by -> user tables ----
    if col_name in ("created_by", "updated_by", "hosting_by"):
        # In this DB, created_by is polymorphic (user_type column usually present)
        # We map to nx_users as the primary user table
        if "nx_users" in all_tables_set:
            return ("nx_users", "id", 0.60, "polymorphic_user_ref")

    # ---- Pattern: *_id columns ----
    if col_name.endswith("_id"):
        base = col_name[:-3]  # strip _id

        # ---- Pattern: nx_*_id -> nx_* tables ----
        if base.startswith("nx_"):
            # Try direct: nx_user_id -> nx_users
            # base = "nx_user", try plurals
            candidates = [
                base,                    # nx_user
                pluralize(base),         # nx_users
                base + "s",             # nx_users (simple)
            ]
            for c in candidates:
                if c.lower() in all_tables_lower:
                    return (all_tables_lower[c.lower()], "id", 0.95, "nx_prefix_id")

            # Try nx_*_details pattern: nx_chapter_detail_id -> nx_chapter_details
            if base.endswith("_detail"):
                detail_table = base + "s"
                if detail_table.lower() in all_tables_lower:
                    return (all_tables_lower[detail_table.lower()], "id", 0.95, "nx_detail_id")

        # ---- Pattern: *_detail_id -> *_details table OR lesson_details ----
        if base.endswith("_detail"):
            detail_table = base + "s"  # lesson_detail -> lesson_details
            if detail_table.lower() in all_tables_lower:
                return (all_tables_lower[detail_table.lower()], "id", 0.95, "detail_id_pattern")

        # ---- Pattern: *_slide_id -> *_slides table ----
        if base.endswith("_slide"):
            slide_table = base + "s"  # lesson_slide -> lesson_slides
            if slide_table.lower() in all_tables_lower:
                return (all_tables_lower[slide_table.lower()], "id", 0.95, "slide_id_pattern")

        # ---- Pattern: direct table match (singular -> plural) ----
        # e.g., client_id -> clients, coach_id -> coaches
        candidates = [
            base,                         # exact match
            pluralize(base),              # client -> clients
            base + "s",                   # simple plural
            base + "es",                 # coach -> coaches
        ]
        for c in candidates:
            if c.lower() in all_tables_lower:
                target = all_tables_lower[c.lower()]
                if target != source_table:
                    return (target, "id", 0.90, "standard_id_fk")
                else:
                    return (target, "id", 0.85, "self_reference_id")

        # ---- Pattern: compound prefix match ----
        # e.g., video_library_id -> video_libraries
        # Try replacing last word with plural forms
        parts = base.split("_")
        if len(parts) >= 2:
            last = parts[-1]
            prefix = "_".join(parts[:-1])
            plural_candidates = [
                prefix + "_" + pluralize(last),    # video_libraries
                prefix + "_" + last + "s",         # video_librarys (fallback)
                prefix + "_" + last + "es",        # fallback
            ]
            for c in plural_candidates:
                if c.lower() in all_tables_lower:
                    return (all_tables_lower[c.lower()], "id", 0.90, "compound_plural_id")

        # ---- Pattern: table_name prefix match ----
        # e.g., mail_communication_detail_id -> mail_communication_details
        # Already covered by detail_id_pattern above, but also try broader match
        for t in all_tables:
            t_singular = singularize(t)
            if t_singular.lower() == base.lower() and t != source_table:
                return (t, "id", 0.88, "singularized_table_match")

        # ---- Pattern: admin_id -> nx_admin_users ----
        if base == "admin":
            if "nx_admin_users" in all_tables_set:
                return ("nx_admin_users", "id", 0.80, "admin_to_nx_admin_users")

        # ---- Pattern: participant_id -> polymorphic (user_type column) ----
        if base == "participant":
            return ("nx_users", "id", 0.50, "polymorphic_participant")

        # ---- Pattern: subject_id, causer_id -> polymorphic (with _type column) ----
        if base in ("subject", "causer", "from"):
            return None  # Truly polymorphic, skip

        # ---- Pattern: old_lesson_id -> self-reference to nx_lessons ----
        if base.startswith("old_"):
            real_base = base[4:]  # strip "old_"
            candidates = [
                real_base,
                pluralize(real_base),
                real_base + "s",
            ]
            for c in candidates:
                if c.lower() in all_tables_lower:
                    return (all_tables_lower[c.lower()], "id", 0.75, "old_id_self_ref")

    return None


def discover_relationships(tables, all_columns_by_table):
    """Discover all relationships - both explicit FKs and inferred."""
    relationships = []
    naming_patterns = defaultdict(int)
    explicit_fk_count = 0
    inferred_count = 0

    # 1. Explicit FKs
    explicit_fks = get_explicit_fks()
    for fk in explicit_fks:
        relationships.append({
            "from_table": fk["TABLE_NAME"],
            "from_column": fk["COLUMN_NAME"],
            "to_table": fk["REFERENCED_TABLE_NAME"],
            "to_column": fk["REFERENCED_COLUMN_NAME"],
            "type": "explicit_fk",
            "confidence": 1.0,
            "constraint_name": fk.get("CONSTRAINT_NAME", ""),
            "pattern": "explicit_fk"
        })
        explicit_fk_count += 1
        naming_patterns["explicit_fk"] += 1

    # Track explicit FK pairs to avoid duplicates
    explicit_pairs = set()
    for r in relationships:
        explicit_pairs.add((r["from_table"], r["from_column"], r["to_table"], r["to_column"]))

    # 2. Inferred relationships from column naming patterns
    for table in tables:
        columns = all_columns_by_table.get(table, [])
        has_user_type = any(c["COLUMN_NAME"] == "user_type" for c in columns)
        has_from_type = any(c["COLUMN_NAME"] == "from_type" for c in columns)

        for col in columns:
            col_name = col["COLUMN_NAME"]
            data_type = col["DATA_TYPE"]

            # Skip non-integer columns for FK inference (except bigint)
            if data_type not in ("int", "bigint", "smallint", "tinyint", "mediumint"):
                continue

            # Skip primary keys
            if col["COLUMN_KEY"] == "PRI" and col_name == "id":
                continue

            # Skip columns that are clearly not FKs
            if col_name in ("status", "priority", "orders", "rating",
                           "no_of_lessons", "no_of_sublessons", "total_slides",
                           "message_when", "diff_minutes", "on_complete",
                           "is_recomended", "has_sublesson", "is_foundation",
                           "is_sublesson", "is_profile_done", "is_password_reset",
                           "verification_code", "slide_index", "is_chapter_completed",
                           "is_transfered", "is_email_sent", "future_months",
                           "is_global_chat", "no_of_days"):
                continue

            # Try to find target table
            result = find_target_table(col_name, tables, table)
            if result is None:
                continue

            to_table, to_col, confidence, pattern = result

            # Adjust confidence for polymorphic refs
            if has_user_type and col_name == "created_by":
                confidence = min(confidence, 0.60)
                pattern = "polymorphic_created_by"
            if has_from_type and col_name == "from_id":
                confidence = min(confidence, 0.55)
                pattern = "polymorphic_from_id"

            # Skip if already found as explicit FK
            if (table, col_name, to_table, to_col) in explicit_pairs:
                continue

            # Verify target table actually has the target column
            target_columns = all_columns_by_table.get(to_table, [])
            target_col_names = [c["COLUMN_NAME"] for c in target_columns]
            if to_col not in target_col_names:
                continue

            relationships.append({
                "from_table": table,
                "from_column": col_name,
                "to_table": to_table,
                "to_column": to_col,
                "type": "inferred_naming",
                "confidence": confidence,
                "pattern": pattern
            })
            inferred_count += 1
            naming_patterns[pattern] += 1

    return relationships, explicit_fk_count, inferred_count, dict(naming_patterns)


def find_orphan_tables(tables, relationships):
    """Tables with no relationships at all."""
    referenced = set()
    for r in relationships:
        referenced.add(r["from_table"])
        referenced.add(r["to_table"])
    return sorted(set(tables) - referenced)


def find_hub_tables(tables, relationships):
    """Tables with many references (both incoming and outgoing)."""
    incoming = defaultdict(int)
    outgoing = defaultdict(int)
    for r in relationships:
        outgoing[r["from_table"]] += 1
        incoming[r["to_table"]] += 1

    hubs = []
    for t in tables:
        inc = incoming.get(t, 0)
        out = outgoing.get(t, 0)
        total = inc + out
        if total > 0:
            hubs.append({
                "table": t,
                "incoming_references": inc,
                "outgoing_references": out,
                "total_references": total
            })
    hubs.sort(key=lambda x: x["total_references"], reverse=True)
    return hubs


def main():
    print("Phase 1b: Relationship Mapper v" + MAPPER_VERSION)
    print("=" * 60)

    # Get all tables
    tables = get_tables()
    print(f"Found {len(tables)} tables")

    if not tables:
        print("ERROR: No tables found in database!", file=sys.stderr)
        sys.exit(1)

    # Get all columns for all tables
    all_columns_by_table = {}
    all_cols = run_query(
        "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, COLUMN_KEY, IS_NULLABLE, COLUMN_TYPE "
        f"FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = '{DATABASE}' "
        "ORDER BY TABLE_NAME, ORDINAL_POSITION;"
    )
    for col in all_cols:
        table = col["TABLE_NAME"]
        if table not in all_columns_by_table:
            all_columns_by_table[table] = []
        all_columns_by_table[table].append(col)

    print(f"Loaded columns for {len(all_columns_by_table)} tables")

    # Discover relationships
    relationships, explicit_count, inferred_count, naming_patterns = discover_relationships(
        tables, all_columns_by_table
    )
    print(f"\nExplicit FKs: {explicit_count}")
    print(f"Inferred relationships: {inferred_count}")
    print(f"Total: {len(relationships)}")

    # Find orphans and hubs
    orphans = find_orphan_tables(tables, relationships)
    hubs = find_hub_tables(tables, relationships)

    print(f"\nOrphan tables (no relationships): {len(orphans)}")
    for o in orphans:
        print(f"  - {o}")

    print(f"\nTop hub tables:")
    for h in hubs[:10]:
        print(f"  - {h['table']}: {h['incoming_references']} in, {h['outgoing_references']} out")

    # Detect naming patterns
    detected_patterns = sorted(naming_patterns.keys())
    print(f"\nNaming patterns detected: {detected_patterns}")

    # Build output
    output = {
        "metadata": {
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "database": DATABASE,
            "table_count": len(tables),
            "explicit_fk_count": explicit_count,
            "inferred_count": inferred_count,
            "total_relationships": len(relationships),
            "naming_patterns_detected": detected_patterns,
            "mapper_version": MAPPER_VERSION
        },
        "relationships": relationships,
        "naming_patterns": naming_patterns,
        "orphan_tables": orphans,
        "hub_tables": hubs
    }

    # Write output
    output_path = "/home/rahil/Projects/baap/.claude/discovery/relationships.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nOutput written to: {output_path}")
    print(f"Total relationships: {len(relationships)}")

    # Validation
    assert len(relationships) > 0, "No relationships found - something is wrong"
    assert all("from_table" in r for r in relationships), "Missing from_table"
    assert all("to_table" in r for r in relationships), "Missing to_table"
    assert all("confidence" in r for r in relationships), "Missing confidence"
    assert all("type" in r for r in relationships), "Missing type"
    print("\nValidation passed!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
