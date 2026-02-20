#!/usr/bin/env python3
"""Bulk interpret learner profiles from EPP assessment data.

Replicates the deterministic logic from tory_engine.py:_tool_interpret_profile
for all users who have EPP scores but no tory_learner_profiles entry yet.

Two-phase approach to avoid mysql --batch tab-delimiter corruption on large JSON:
  Phase 1: Get list of (onboarding_id, nx_user_id) pairs needing processing
  Phase 2: Fetch each onboarding record individually via mysql --xml for safe parsing

Usage:
    python3 bulk_profile_interpret.py              # Process all unprocessed users
    python3 bulk_profile_interpret.py --limit 5    # Process first 5 only
    python3 bulk_profile_interpret.py --dry-run    # Show what would be inserted, no writes
"""

import json
import subprocess
import sys
import argparse
import xml.etree.ElementTree as ET
from datetime import datetime

DATABASE = "baap"
QUERY_TIMEOUT = 30

# EPP dimension names from Criteria Corp
EPP_PERSONALITY_DIMS = [
    "Achievement", "Motivation", "Competitiveness", "Managerial",
    "Assertiveness", "Extroversion", "Cooperativeness", "Patience",
    "SelfConfidence", "Conscientiousness", "Openness", "Stability",
    "StressTolerance",
]

EPP_JOBFIT_DIMS = [
    "Accounting", "AdminAsst", "Analyst", "BankTeller", "Collections",
    "CustomerService", "FrontDesk", "Manager", "MedicalAsst",
    "Production", "Programmer", "Sales",
]

EPP_SKIP_FIELDS = {"EPPPercentMatch", "EPPInconsistency", "EPPInvalid", "RankingScore"}

TRAIT_LABELS = {
    "Achievement": "achievement drive", "Motivation": "intrinsic motivation",
    "Competitiveness": "competitiveness", "Managerial": "managerial ability",
    "Assertiveness": "assertiveness", "Extroversion": "extroversion",
    "Cooperativeness": "cooperativeness", "Patience": "patience",
    "SelfConfidence": "self-confidence", "Conscientiousness": "conscientiousness",
    "Openness": "openness to new ideas", "Stability": "emotional stability",
    "StressTolerance": "stress tolerance",
}

STYLE_DESC = {
    "active": "You learn best through hands-on activities and interactive exercises.",
    "reflective": "You learn best when given time to reflect and process information deeply.",
    "theoretical": "You thrive with structured, methodical content and clear frameworks.",
    "blended": "You adapt well across different learning formats and approaches.",
}


def mysql_query_batch(sql):
    """Execute a read query with --batch, return (headers, rows). Safe for simple columns."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL query error: {result.stderr.strip()}")
    lines = result.stdout.strip().split("\n")
    if not lines:
        return [], []
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        row = {}
        for i, h in enumerate(headers):
            row[h] = values[i] if i < len(values) else None
        rows.append(row)
    return headers, rows


def mysql_query_xml(sql):
    """Execute a read query with --xml, return list of dicts. Safe for JSON columns."""
    result = subprocess.run(
        ["mysql", DATABASE, "--xml", "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL XML query error: {result.stderr.strip()}")
    if not result.stdout.strip():
        return []
    root = ET.fromstring(result.stdout)
    rows = []
    for row_elem in root.findall("row"):
        row = {}
        for field in row_elem.findall("field"):
            name = field.get("name")
            # xsi:nil="true" means NULL
            if field.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                row[name] = None
            else:
                row[name] = field.text
        rows.append(row)
    return rows


def mysql_write(sql):
    """Execute a write query."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL write error: {result.stderr.strip()}")


def escape_sql(value):
    """Escape a string value for safe SQL insertion."""
    if value is None:
        return "NULL"
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r")
    escaped = escaped.replace("\x00", "").replace("\x1a", "")
    return f"'{escaped}'"


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_epp_scores(assessment_result):
    """Parse EPP scores from assessment_result JSON."""
    if not assessment_result or assessment_result == "NULL":
        return {}
    try:
        data = json.loads(assessment_result)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    raw_scores = data.get("scores", data)
    if not isinstance(raw_scores, dict):
        return {}
    scores = {}
    for key, value in raw_scores.items():
        if key in EPP_SKIP_FIELDS:
            continue
        try:
            score = float(value)
        except (ValueError, TypeError):
            continue
        if key.startswith("EPP"):
            scores[key[3:]] = score
        elif key in EPP_JOBFIT_DIMS:
            scores[f"{key}_JobFit"] = score
        else:
            scores[key] = score
    return scores


def parse_qa_answers(onboarding):
    """Extract Q&A answers from onboarding record."""
    qa_fields = [
        "why_did_you_come", "own_reason", "in_first_professional_job",
        "call_yourself", "advance_your_career", "imp_thing_career_plan",
        "best_boss", "success_look_like", "stay_longer", "future_months",
    ]
    answers = {}
    for field in qa_fields:
        val = onboarding.get(field)
        if val and val != "NULL":
            try:
                answers[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                answers[field] = val
    return answers


def label_trait(t):
    """Human-readable trait name."""
    if t.endswith("_JobFit"):
        return t.replace("_JobFit", "").lower() + " aptitude"
    return TRAIT_LABELS.get(t, t.lower())


def build_profile(onboarding):
    """Build a complete profile dict from onboarding data."""
    epp_scores = parse_epp_scores(onboarding.get("assesment_result", ""))
    if not epp_scores:
        return None

    qa_answers = parse_qa_answers(onboarding)

    sorted_traits = sorted(epp_scores.items(), key=lambda x: x[1], reverse=True)
    strengths = []
    gaps = []
    for trait, score in sorted_traits:
        if score >= 60:
            strengths.append({"trait": trait, "score": score, "type": "strength"})
        elif score <= 40:
            gaps.append({"trait": trait, "score": score, "type": "gap"})

    motivation_drivers = []
    for field in ("advance_your_career", "imp_thing_career_plan", "success_look_like"):
        val = qa_answers.get(field)
        if not val:
            continue
        if isinstance(val, list):
            motivation_drivers.extend(str(v) for v in val)
        else:
            motivation_drivers.append(str(val))

    learning_style = "blended"
    if epp_scores.get("Extroversion", 50) > 70:
        learning_style = "active"
    elif epp_scores.get("Openness", 50) > 70:
        learning_style = "reflective"
    elif epp_scores.get("Conscientiousness", 50) > 70:
        learning_style = "theoretical"

    top_strengths = [s["trait"] for s in strengths[:3]]
    top_gaps = [g["trait"] for g in gaps[:2]]
    str_labels = [label_trait(t) for t in top_strengths]
    gap_labels = [label_trait(t) for t in top_gaps]

    parts = []
    if str_labels:
        if len(str_labels) >= 3:
            parts.append(f"You show strong {str_labels[0]}, {str_labels[1]}, and {str_labels[2]}.")
        else:
            parts.append(f"You show strong {' and '.join(str_labels)}.")
        parts.append(
            "These strengths suggest you tend to excel in roles that value "
            "collaboration, reliability, and initiative."
        )
    if gap_labels:
        parts.append(
            f"Your growth areas include {' and '.join(gap_labels)}, "
            "which your learning path will focus on developing."
        )
    parts.append(STYLE_DESC.get(learning_style, STYLE_DESC["blended"]))
    if motivation_drivers:
        clean_drivers = [d.strip().rstrip(".").lower() for d in motivation_drivers[:2]]
        parts.append(f"You are driven by {' and '.join(clean_drivers)}.")

    narrative = " ".join(parts[:5])

    confidence = 50
    if qa_answers:
        confidence += 10
    if len(epp_scores) >= 20:
        confidence += 15

    return {
        "epp_scores": epp_scores,
        "motivation_drivers": motivation_drivers,
        "strengths": strengths,
        "gaps": gaps,
        "learning_style": learning_style,
        "narrative": narrative,
        "confidence": confidence,
    }


def get_unprocessed_ids(limit=None):
    """Get (onboarding_id, nx_user_id) pairs for users needing profiles.

    Uses simple columns only to avoid tab-delimiter corruption.
    """
    sql = (
        "SELECT nuo.id, nuo.nx_user_id "
        "FROM nx_user_onboardings nuo "
        "WHERE nuo.assesment_result IS NOT NULL "
        "AND nuo.assesment_result != '' "
        "AND nuo.nx_user_id NOT IN (SELECT nx_user_id FROM tory_learner_profiles) "
        "ORDER BY nuo.nx_user_id"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    _, rows = mysql_query_batch(sql)
    return [(int(r["id"]), int(r["nx_user_id"])) for r in rows]


def fetch_onboarding(onboarding_id):
    """Fetch a single onboarding record using XML output for safe JSON parsing."""
    rows = mysql_query_xml(
        f"SELECT * FROM nx_user_onboardings WHERE id = {int(onboarding_id)} LIMIT 1"
    )
    return rows[0] if rows else None


def insert_profile(nx_user_id, onboarding_id, profile):
    """Insert a profile into tory_learner_profiles."""
    now = now_str()
    epp_json = escape_sql(json.dumps(profile["epp_scores"]))
    motivation_json = escape_sql(json.dumps(profile["motivation_drivers"]))
    strengths_json = escape_sql(json.dumps(profile["strengths"]))
    gaps_json = escape_sql(json.dumps(profile["gaps"]))
    narrative_esc = escape_sql(profile["narrative"])

    sql = (
        "INSERT INTO tory_learner_profiles "
        "(nx_user_id, onboarding_id, epp_summary, motivation_cluster, "
        "strengths, gaps, learning_style, profile_narrative, confidence, "
        "version, source, feedback_flags, created_at, updated_at) "
        f"VALUES ({int(nx_user_id)}, {int(onboarding_id)}, {epp_json}, {motivation_json}, "
        f"{strengths_json}, {gaps_json}, '{profile['learning_style']}', {narrative_esc}, "
        f"{profile['confidence']}, 1, 'epp_qa', 0, '{now}', '{now}')"
    )
    mysql_write(sql)


def main():
    parser = argparse.ArgumentParser(description="Bulk interpret learner profiles from EPP data")
    parser.add_argument("--limit", type=int, help="Max users to process")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing")
    args = parser.parse_args()

    print(f"[{now_str()}] Phase 1: Getting unprocessed user IDs...")
    id_pairs = get_unprocessed_ids(args.limit)
    total = len(id_pairs)
    print(f"[{now_str()}] Found {total} users needing profiles")

    if total == 0:
        print("Nothing to do.")
        return

    success = 0
    skipped = 0
    errors = 0

    for i, (onboarding_id, nx_user_id) in enumerate(id_pairs, 1):
        try:
            onboarding = fetch_onboarding(onboarding_id)
            if not onboarding:
                print(f"  [{i}/{total}] SKIP user {nx_user_id} (onb={onboarding_id}) — record not found")
                skipped += 1
                continue

            profile = build_profile(onboarding)
            if profile is None:
                print(f"  [{i}/{total}] SKIP user {nx_user_id} (onb={onboarding_id}) — no parseable EPP")
                skipped += 1
                continue

            if args.dry_run:
                print(
                    f"  [{i}/{total}] DRY-RUN user {nx_user_id}: "
                    f"{len(profile['epp_scores'])} dims, {len(profile['strengths'])}S/{len(profile['gaps'])}G, "
                    f"style={profile['learning_style']}, conf={profile['confidence']}"
                )
            else:
                insert_profile(nx_user_id, onboarding_id, profile)
                print(
                    f"  [{i}/{total}] OK user {nx_user_id}: "
                    f"{len(profile['strengths'])}S/{len(profile['gaps'])}G, "
                    f"style={profile['learning_style']}, conf={profile['confidence']}"
                )
            success += 1

        except Exception as e:
            print(f"  [{i}/{total}] ERROR user {nx_user_id} (onb={onboarding_id}): {e}")
            errors += 1

        # Progress checkpoint every 50
        if i % 50 == 0:
            print(f"  --- Progress: {i}/{total} ({success} ok, {skipped} skip, {errors} err) ---")

    print(f"\n[{now_str()}] Done: {success} created, {skipped} skipped, {errors} errors (of {total} total)")


if __name__ == "__main__":
    main()
