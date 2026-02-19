#!/usr/bin/env python3
"""
Tory Engine MCP Server — Personalized Learning Path Intelligence

The brain of the Tory system. Provides tools for:
1. Content tagging (multi-pass Claude Opus analysis)
2. Learner profile interpretation (EPP + Q&A → structured profile)
3. Content similarity scoring (cosine similarity against trait tags)
4. Roadmap generation (discovery phase → full adaptive path)
5. Reassessment evaluation (mini + full EPP → profile update + path adaptation)
6. Coach compatibility checking (EPP heuristic → traffic light signal)

ARCHITECTURE: MCP Agent (Intelligence Layer) — invoked by orchestrator or
background worker. Reads from existing baap tables, writes to tory_* tables.

CONNECTION: MariaDB via subprocess mysql CLI (matches db_tools.py pattern).
AI CALLS: Anthropic Claude API for interpretation and generation.
"""

import asyncio
import json
import math
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATABASE = "baap"
MAX_ROWS = 1000
QUERY_TIMEOUT = 30  # seconds

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# EPP dimension names from actual Criteria Corp data
# Personality dimensions (EPP prefix in raw data)
EPP_PERSONALITY_DIMS = [
    "Achievement", "Motivation", "Competitiveness", "Managerial",
    "Assertiveness", "Extroversion", "Cooperativeness", "Patience",
    "SelfConfidence", "Conscientiousness", "Openness", "Stability",
    "StressTolerance",
]

# Job-fit dimensions (no prefix in raw data)
EPP_JOBFIT_DIMS = [
    "Accounting", "AdminAsst", "Analyst", "BankTeller", "Collections",
    "CustomerService", "FrontDesk", "Manager", "MedicalAsst",
    "Production", "Programmer", "Sales",
]

# Meta fields to skip
EPP_SKIP_FIELDS = {"EPPPercentMatch", "EPPInconsistency", "EPPInvalid", "RankingScore"}

# Discovery phase config
DISCOVERY_LESSON_COUNT = 5

# Confidence thresholds
CONFIDENCE_AUTO_APPROVE = 75  # Above this, tags are auto-approved
CONFIDENCE_NEEDS_REVIEW = 50  # Below this, tags need human review

# Reassessment config
REASSESSMENT_QUARTERLY_DAYS = 90  # Quarterly EPP retake interval
REASSESSMENT_MINI_QUESTION_COUNT = (3, 5)  # Min/max questions for mini-assessment
BACKPACK_SIGNAL_THRESHOLD = 10  # Number of new interactions to trigger reassessment
DRIFT_THRESHOLD_PCT = 15  # Profile drift % to trigger path re-ranking
CRITERIA_CORP_MAX_RETRIES = 3
CRITERIA_CORP_BASE_DELAY = 1.0  # seconds, for exponential backoff

# ---------------------------------------------------------------------------
# MySQL helpers (mirrors db_tools.py pattern)
# ---------------------------------------------------------------------------


def mysql_query(sql: str) -> tuple[list[str], list[dict]]:
    """Execute a MySQL query via CLI and return (headers, rows)."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True,
        text=True,
        timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL error: {result.stderr.strip()}")

    output = result.stdout.strip()
    if not output:
        return [], []

    lines = output.split("\n")
    headers = lines[0].split("\t")
    if len(lines) < 2:
        return headers, []

    rows: list[dict] = []
    for line in lines[1:]:
        values = line.split("\t")
        row = {}
        for i, h in enumerate(headers):
            row[h] = values[i] if i < len(values) else None
        rows.append(row)

    return headers, rows


def mysql_write(sql: str) -> int:
    """Execute a write query. Returns number of affected rows."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True,
        text=True,
        timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL write error: {result.stderr.strip()}")
    # Try to extract affected rows from output
    return 0


def escape_sql(value: str) -> str:
    """Escape a string value for safe SQL insertion."""
    if value is None:
        return "NULL"
    # Escape single quotes, backslashes, and other dangerous chars
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r")
    escaped = escaped.replace("\x00", "").replace("\x1a", "")
    return f"'{escaped}'"


def now_str() -> str:
    """Current datetime as MySQL-compatible string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Vector math for cosine similarity
# ---------------------------------------------------------------------------


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(vec_a) != len(vec_b):
        # Pad shorter vector with zeros
        max_len = max(len(vec_a), len(vec_b))
        vec_a = vec_a + [0.0] * (max_len - len(vec_a))
        vec_b = vec_b + [0.0] * (max_len - len(vec_b))

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot / (mag_a * mag_b)


def normalize_vector(vec: list[float]) -> list[float]:
    """Normalize vector to 0-1 range."""
    if not vec:
        return vec
    min_v = min(vec)
    max_v = max(vec)
    if max_v == min_v:
        return [0.5] * len(vec)
    return [(v - min_v) / (max_v - min_v) for v in vec]


# ---------------------------------------------------------------------------
# Data access layer
# ---------------------------------------------------------------------------


def get_user_onboarding(nx_user_id: int) -> dict | None:
    """Fetch onboarding data (EPP + Q&A) for a user."""
    _, rows = mysql_query(
        f"SELECT * FROM nx_user_onboardings WHERE nx_user_id = {int(nx_user_id)} LIMIT 1"
    )
    return rows[0] if rows else None


def get_user_info(nx_user_id: int) -> dict | None:
    """Fetch basic user info."""
    _, rows = mysql_query(
        f"SELECT * FROM nx_users WHERE id = {int(nx_user_id)} LIMIT 1"
    )
    return rows[0] if rows else None


def get_client_pedagogy(client_id: int) -> dict | None:
    """Fetch pedagogy config for a client company."""
    _, rows = mysql_query(
        f"SELECT * FROM tory_pedagogy_config WHERE client_id = {int(client_id)} "
        f"AND deleted_at IS NULL ORDER BY id DESC LIMIT 1"
    )
    return rows[0] if rows else None


def get_current_profile(nx_user_id: int) -> dict | None:
    """Fetch the latest learner profile."""
    _, rows = mysql_query(
        f"SELECT * FROM tory_learner_profiles WHERE nx_user_id = {int(nx_user_id)} "
        f"AND deleted_at IS NULL ORDER BY version DESC LIMIT 1"
    )
    return rows[0] if rows else None


def get_current_roadmap(nx_user_id: int) -> dict | None:
    """Fetch the current active roadmap."""
    _, rows = mysql_query(
        f"SELECT * FROM tory_roadmaps WHERE nx_user_id = {int(nx_user_id)} "
        f"AND is_current = 1 AND deleted_at IS NULL ORDER BY id DESC LIMIT 1"
    )
    return rows[0] if rows else None


def get_roadmap_items(roadmap_id: int) -> list[dict]:
    """Fetch all items in a roadmap, ordered by sequence."""
    _, rows = mysql_query(
        f"SELECT * FROM tory_roadmap_items WHERE roadmap_id = {int(roadmap_id)} "
        f"AND deleted_at IS NULL ORDER BY sequence ASC"
    )
    return rows


def get_content_tags(
    nx_lesson_id: int | None = None,
    confidence_threshold: int = 70,
) -> list[dict]:
    """Fetch content tags, optionally for a specific lesson.

    Filters to confidence >= threshold OR review_status = 'approved'.
    This implements the bead requirement: exclude tags with confidence
    below 0.7 (70) unless manually reviewed/approved.
    """
    where = (
        "WHERE deleted_at IS NULL AND review_status != 'rejected' "
        f"AND (confidence >= {int(confidence_threshold)} OR review_status = 'approved')"
    )
    if nx_lesson_id is not None:
        where += f" AND nx_lesson_id = {int(nx_lesson_id)}"
    _, rows = mysql_query(
        f"SELECT * FROM tory_content_tags {where} ORDER BY nx_lesson_id ASC"
    )
    return rows


def get_content_tags_unfiltered(nx_lesson_id: int | None = None) -> list[dict]:
    """Fetch all content tags without confidence filtering (for listing/review)."""
    where = "WHERE deleted_at IS NULL AND review_status != 'rejected'"
    if nx_lesson_id is not None:
        where += f" AND nx_lesson_id = {int(nx_lesson_id)}"
    _, rows = mysql_query(
        f"SELECT * FROM tory_content_tags {where} ORDER BY nx_lesson_id ASC"
    )
    return rows


def get_all_lessons() -> list[dict]:
    """Fetch all lessons with their content hierarchy info."""
    _, rows = mysql_query(
        "SELECT l.id, l.lesson, l.description, l.nx_journey_detail_id, "
        "l.nx_chapter_detail_id, l.is_foundation, l.priority "
        "FROM nx_lessons l WHERE l.deleted_at IS NULL ORDER BY l.id ASC"
    )
    return rows


def get_lesson_journey_map() -> dict[int, int]:
    """Build a mapping of lesson_id -> journey_id for diversity rules."""
    _, rows = mysql_query(
        "SELECT id, nx_journey_detail_id FROM nx_lessons WHERE deleted_at IS NULL"
    )
    return {int(r["id"]): int(r["nx_journey_detail_id"] or 0) for r in rows}


def get_user_coach(nx_user_id: int) -> dict | None:
    """Fetch the coach assigned to a user (if any)."""
    _, rows = mysql_query(
        f"SELECT c.id as coach_id FROM coaches c "
        f"JOIN coach_users cu ON cu.coach_id = c.id "
        f"WHERE cu.nx_user_id = {int(nx_user_id)} "
        f"AND cu.deleted_at IS NULL AND c.deleted_at IS NULL "
        f"LIMIT 1"
    )
    return rows[0] if rows else None


def get_lesson_slides(nx_lesson_id: int) -> list[dict]:
    """Fetch slides for a lesson (for content tagging)."""
    _, rows = mysql_query(
        f"SELECT ls.id, ls.slide_content, ls.type, ls.priority "
        f"FROM lesson_slides ls "
        f"JOIN lesson_details ld ON ls.lesson_detail_id = ld.id "
        f"WHERE ld.nx_lesson_id = {int(nx_lesson_id)} "
        f"AND ls.deleted_at IS NULL "
        f"ORDER BY ls.priority ASC"
    )
    return rows


def get_user_backpacks(nx_user_id: int) -> list[dict]:
    """Fetch backpack (interaction) data for a user."""
    _, rows = mysql_query(
        f"SELECT * FROM backpacks WHERE created_by = {int(nx_user_id)} "
        f"AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 100"
    )
    return rows


def get_user_ratings(nx_user_id: int) -> list[dict]:
    """Fetch ratings for a user."""
    _, rows = mysql_query(
        f"SELECT * FROM nx_user_ratings WHERE created_by = {int(nx_user_id)} "
        f"AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 100"
    )
    return rows


def get_user_tasks(nx_user_id: int) -> list[dict]:
    """Fetch tasks for a user."""
    _, rows = mysql_query(
        f"SELECT * FROM tasks WHERE created_by = {int(nx_user_id)} "
        f"AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 100"
    )
    return rows


def get_reassessment_history(nx_user_id: int) -> list[dict]:
    """Fetch reassessment history for a user."""
    _, rows = mysql_query(
        f"SELECT * FROM tory_reassessments WHERE nx_user_id = {int(nx_user_id)} "
        f"AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 20"
    )
    return rows


def get_coach_overrides(roadmap_id: int) -> list[dict]:
    """Fetch coach overrides for a roadmap."""
    _, rows = mysql_query(
        f"SELECT * FROM tory_coach_overrides WHERE roadmap_id = {int(roadmap_id)} "
        f"AND deleted_at IS NULL ORDER BY created_at DESC"
    )
    return rows


def get_locked_recommendations(nx_user_id: int) -> list[dict]:
    """Fetch coach-locked recommendations that must be preserved through re-ranking."""
    _, rows = mysql_query(
        f"SELECT * FROM tory_recommendations WHERE nx_user_id = {int(nx_user_id)} "
        f"AND locked_by_coach = 1 AND deleted_at IS NULL ORDER BY sequence ASC"
    )
    return rows


def get_last_reassessment(nx_user_id: int, reassessment_type: str | None = None) -> dict | None:
    """Fetch the most recent completed reassessment for a user."""
    where = (
        f"WHERE nx_user_id = {int(nx_user_id)} AND status = 'completed' "
        f"AND deleted_at IS NULL"
    )
    if reassessment_type:
        where += f" AND type = '{reassessment_type}'"
    _, rows = mysql_query(
        f"SELECT * FROM tory_reassessments {where} ORDER BY completed_at DESC LIMIT 1"
    )
    return rows[0] if rows else None


def count_new_interactions_since(nx_user_id: int, since: str) -> dict:
    """Count new backpack saves, ratings, and task completions since a datetime."""
    counts = {}
    for table, col in [("backpacks", "created_by"), ("nx_user_ratings", "created_by"), ("tasks", "created_by")]:
        _, rows = mysql_query(
            f"SELECT COUNT(*) as cnt FROM {table} "
            f"WHERE {col} = {int(nx_user_id)} AND created_at > '{since}' "
            f"AND deleted_at IS NULL"
        )
        counts[table] = int(rows[0]["cnt"]) if rows else 0
    return counts


# ---------------------------------------------------------------------------
# Criteria Corp API Client (with retry + fallback)
# ---------------------------------------------------------------------------


def _load_criteria_credentials() -> dict | None:
    """Load Criteria Corp API credentials from integration config."""
    cred_path = PROJECT_ROOT / ".claude" / "integrations" / "criteria-corp" / "credentials.json"
    if not cred_path.exists():
        return None
    try:
        return json.loads(cred_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def criteria_corp_fetch_scores(
    order_id: str,
    credentials: dict | None = None,
) -> dict | None:
    """Fetch updated EPP scores from Criteria Corp API.

    Implements retry with exponential backoff (3 retries, 1s/2s/4s delays).
    Returns parsed scores dict or None on failure.
    """
    import time
    import urllib.request
    import urllib.error

    if credentials is None:
        credentials = _load_criteria_credentials()
    if not credentials:
        return None

    api_url = credentials.get("api_url", "https://api.criteriacorp.com/v1")
    api_key = credentials.get("api_key", "")
    if not api_key:
        return None

    url = f"{api_url}/orders/{order_id}/scores"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(CRITERIA_CORP_MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                return data
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as e:
            last_error = e
            if attempt < CRITERIA_CORP_MAX_RETRIES - 1:
                delay = CRITERIA_CORP_BASE_DELAY * (2 ** attempt)
                time.sleep(delay)

    # All retries failed
    print(
        f"[tory-engine] Criteria Corp API failed after {CRITERIA_CORP_MAX_RETRIES} retries: {last_error}",
        file=sys.stderr,
    )
    return None


# ---------------------------------------------------------------------------
# Reassessment Engine
# ---------------------------------------------------------------------------


def compute_profile_drift(old_scores: dict, new_scores: dict) -> dict:
    """Compare two EPP score sets and compute drift metrics.

    Returns {drift_pct, changed_traits, delta_map}.
    """
    all_traits = set(old_scores.keys()) | set(new_scores.keys())
    if not all_traits:
        return {"drift_pct": 0, "changed_traits": [], "delta_map": {}}

    delta_map = {}
    total_delta = 0.0

    for trait in all_traits:
        old_val = old_scores.get(trait, 50.0)
        new_val = new_scores.get(trait, 50.0)
        delta = new_val - old_val
        delta_map[trait] = round(delta, 2)
        total_delta += abs(delta)

    avg_delta = total_delta / len(all_traits) if all_traits else 0
    drift_pct = round(avg_delta, 2)

    changed_traits = [
        {"trait": t, "old": old_scores.get(t, 50.0), "new": new_scores.get(t, 50.0), "delta": d}
        for t, d in delta_map.items()
        if abs(d) >= 5  # Only report meaningful changes (5+ points)
    ]
    changed_traits.sort(key=lambda x: abs(x["delta"]), reverse=True)

    return {
        "drift_pct": drift_pct,
        "changed_traits": changed_traits,
        "delta_map": delta_map,
    }


def update_profile_from_scores(
    nx_user_id: int,
    new_epp_scores: dict,
    source: str = "reassessment",
) -> dict:
    """Create a new profile version with updated EPP scores.

    Returns the new profile record.
    """
    existing = get_current_profile(nx_user_id)
    if not existing:
        raise ValueError(f"No existing profile for user {nx_user_id}")

    # Re-classify strengths and gaps from new scores
    sorted_traits = sorted(new_epp_scores.items(), key=lambda x: x[1], reverse=True)
    strengths = [{"trait": t, "score": s, "type": "strength"} for t, s in sorted_traits if s >= 60]
    gaps = [{"trait": t, "score": s, "type": "gap"} for t, s in sorted_traits if s <= 40]

    # Preserve learning style and motivation from existing profile
    learning_style = existing.get("learning_style", "blended")
    try:
        motivation = existing.get("motivation_cluster", "[]")
        if isinstance(motivation, str):
            motivation = json.loads(motivation)
    except (json.JSONDecodeError, TypeError):
        motivation = []

    # Build updated narrative
    top_str = [s["trait"] for s in strengths[:3]]
    top_gap = [g["trait"] for g in gaps[:2]]
    parts = []
    if top_str:
        labels = [_humanize_trait(t) for t in top_str]
        parts.append(f"You show strong {', '.join(labels[:3])}.")
    if top_gap:
        labels = [_humanize_trait(t) for t in top_gap]
        parts.append(f"Your growth areas include {' and '.join(labels)}.")
    parts.append(f"Updated from {source} reassessment.")
    narrative = " ".join(parts)

    new_version = int(existing["version"]) + 1
    confidence = min(95, int(existing.get("confidence", 50)) + 5)
    now = now_str()

    epp_json = escape_sql(json.dumps(new_epp_scores))
    motivation_json = escape_sql(json.dumps(motivation))
    strengths_json = escape_sql(json.dumps(strengths))
    gaps_json = escape_sql(json.dumps(gaps))
    narrative_esc = escape_sql(narrative)
    onboarding_id = existing.get("onboarding_id") or "NULL"

    sql = (
        f"INSERT INTO tory_learner_profiles "
        f"(nx_user_id, onboarding_id, epp_summary, motivation_cluster, "
        f"strengths, gaps, learning_style, profile_narrative, confidence, "
        f"version, source, feedback_flags, created_at, updated_at) "
        f"VALUES ({int(nx_user_id)}, {onboarding_id}, {epp_json}, {motivation_json}, "
        f"{strengths_json}, {gaps_json}, '{learning_style}', {narrative_esc}, "
        f"{confidence}, {new_version}, '{source}', 0, '{now}', '{now}')"
    )
    mysql_write(sql)

    return get_current_profile(nx_user_id)


def write_reassessment(
    nx_user_id: int,
    profile_id: int | None,
    reassessment_type: str,
    trigger_reason: str,
    status: str = "pending",
    assessment_data: dict | None = None,
    previous_scores: dict | None = None,
    new_scores: dict | None = None,
    result_delta: dict | None = None,
    drift_detected: bool = False,
    path_action: str | None = None,
    criteria_order_id: str | None = None,
) -> int:
    """Write a reassessment record to tory_reassessments. Returns the new row ID."""
    now = now_str()

    def _js(val):
        return escape_sql(json.dumps(val)) if val else "NULL"

    sql = (
        f"INSERT INTO tory_reassessments "
        f"(nx_user_id, profile_id, type, trigger_reason, status, "
        f"assessment_data, previous_scores, new_scores, result_delta, "
        f"drift_detected, path_action, criteria_order_id, "
        f"created_at, updated_at) "
        f"VALUES ({int(nx_user_id)}, {int(profile_id) if profile_id else 'NULL'}, "
        f"'{reassessment_type}', '{trigger_reason}', '{status}', "
        f"{_js(assessment_data)}, {_js(previous_scores)}, {_js(new_scores)}, "
        f"{_js(result_delta)}, {1 if drift_detected else 0}, "
        f"{escape_sql(path_action) if path_action else 'NULL'}, "
        f"{escape_sql(criteria_order_id) if criteria_order_id else 'NULL'}, "
        f"'{now}', '{now}')"
    )
    mysql_write(sql)

    # Get the new ID
    _, rows = mysql_query(
        f"SELECT id FROM tory_reassessments WHERE nx_user_id = {int(nx_user_id)} "
        f"ORDER BY id DESC LIMIT 1"
    )
    return int(rows[0]["id"]) if rows else 0


def complete_reassessment(reassessment_id: int, updates: dict) -> None:
    """Mark a reassessment as completed with result data."""
    now = now_str()
    set_parts = [f"status = 'completed'", f"completed_at = '{now}'", f"updated_at = '{now}'"]

    for field in ("new_scores", "result_delta", "assessment_data"):
        if field in updates:
            set_parts.append(f"{field} = {escape_sql(json.dumps(updates[field]))}")
    if "drift_detected" in updates:
        set_parts.append(f"drift_detected = {1 if updates['drift_detected'] else 0}")
    if "path_action" in updates:
        set_parts.append(f"path_action = {escape_sql(updates['path_action'])}")
    if "profile_id" in updates:
        set_parts.append(f"profile_id = {int(updates['profile_id'])}")

    mysql_write(
        f"UPDATE tory_reassessments SET {', '.join(set_parts)} WHERE id = {int(reassessment_id)}"
    )


def write_path_event(
    nx_user_id: int,
    coach_id: int,
    event_type: str,
    reason: str,
    details: dict | None = None,
    recommendation_ids: list[int] | None = None,
) -> int:
    """Write a path event to tory_path_events. Returns the new row ID."""
    now = now_str()
    details_sql = escape_sql(json.dumps(details)) if details else "NULL"
    rec_ids_sql = escape_sql(json.dumps(recommendation_ids)) if recommendation_ids else "NULL"
    reason_esc = escape_sql(reason)

    sql = (
        f"INSERT INTO tory_path_events "
        f"(nx_user_id, coach_id, event_type, reason, details, "
        f"recommendation_ids, created_at, updated_at) "
        f"VALUES ({int(nx_user_id)}, {int(coach_id)}, '{event_type}', "
        f"{reason_esc}, {details_sql}, {rec_ids_sql}, '{now}', '{now}')"
    )
    mysql_write(sql)

    _, rows = mysql_query(
        f"SELECT id FROM tory_path_events WHERE nx_user_id = {int(nx_user_id)} "
        f"ORDER BY id DESC LIMIT 1"
    )
    return int(rows[0]["id"]) if rows else 0


def rerank_recommendations(
    nx_user_id: int,
    new_profile: dict,
    reassessment_id: int,
    trigger_reason: str,
) -> dict:
    """Re-run the scoring engine against an updated profile, preserving coach-locked items.

    This is the core adaptive re-ranking worker. Steps:
    1. Load locked recommendations (preserved through re-ranking)
    2. Load current profile traits
    3. Re-score all content against updated profile
    4. Merge: locked items keep their positions, unlocked items re-ranked
    5. Write new recommendations with new batch_id
    6. Record path event with type=reassessed
    7. Return summary of changes

    Returns dict with old_recs, new_recs, changes, path_event_id.
    """
    import uuid

    profile_id = int(new_profile["id"])

    # 1. Load locked recommendations
    locked = get_locked_recommendations(nx_user_id)
    locked_lesson_ids = {int(r["nx_lesson_id"]) for r in locked}

    # 2. Load profile traits
    try:
        strengths = json.loads(new_profile.get("strengths", "[]"))
        gaps = json.loads(new_profile.get("gaps", "[]"))
    except (json.JSONDecodeError, TypeError):
        strengths, gaps = [], []
    learner_traits = gaps + strengths

    # 3. Load pedagogy config
    user = get_user_info(nx_user_id)
    client_id = user.get("client_id") if user else None
    pedagogy = get_client_pedagogy(int(client_id)) if client_id else None

    mode = pedagogy["mode"] if pedagogy else "balanced"
    gap_ratio = int(pedagogy["gap_ratio"]) if pedagogy else 50
    strength_ratio = int(pedagogy["strength_ratio"]) if pedagogy else 50
    if mode == "gap_fill":
        gap_ratio, strength_ratio = 70, 30
    elif mode == "strength_lead":
        gap_ratio, strength_ratio = 30, 70

    pedagogy_info = {"mode": mode, "gap_ratio": gap_ratio, "strength_ratio": strength_ratio}

    # 4. Fetch content tags and re-score
    content_tags = get_content_tags(confidence_threshold=70)
    scored = score_content_for_learner(
        learner_traits, content_tags, mode, gap_ratio, strength_ratio
    )

    # Enrich with content_tag_id
    tag_by_lesson = {int(t["nx_lesson_id"]): t for t in content_tags}
    for lesson in scored:
        lid = int(lesson["nx_lesson_id"])
        if lid in tag_by_lesson:
            lesson["content_tag_id"] = int(tag_by_lesson[lid]["id"])

    # Apply sequencing (excluding locked lessons from re-ordering)
    unlocked_scored = [s for s in scored if int(s["nx_lesson_id"]) not in locked_lesson_ids]
    lesson_journey_map = get_lesson_journey_map()
    sequenced = apply_sequencing(unlocked_scored, lesson_journey_map=lesson_journey_map, max_lessons=20)

    # 5. Merge: locked items at their original positions, unlocked fill the rest
    # Generate rationale for unlocked
    for lesson in sequenced:
        lesson["is_discovery"] = False
        lesson["match_rationale"] = generate_rationale(lesson, is_discovery=False)

    # Build final list: locked items first (at their sequence), then unlocked
    final_recs = []
    seq = 1

    # Insert locked at their positions
    locked_by_seq = {int(r.get("sequence", 0)): r for r in locked}

    # Interleave: place locked items at their original positions
    unlocked_iter = iter(sequenced)
    max_seq = max(len(sequenced) + len(locked), 20)

    for pos in range(1, max_seq + 1):
        if pos in locked_by_seq:
            rec = locked_by_seq[pos]
            final_recs.append({
                "nx_lesson_id": int(rec["nx_lesson_id"]),
                "content_tag_id": rec.get("content_tag_id"),
                "score": float(rec.get("match_score", 0)),
                "adjusted_score": float(rec.get("adjusted_score", rec.get("match_score", 0))),
                "gap_contribution": float(rec.get("gap_contribution", 0)),
                "strength_contribution": float(rec.get("strength_contribution", 0)),
                "matching_traits": json.loads(rec.get("matching_traits", "[]")) if isinstance(rec.get("matching_traits"), str) else rec.get("matching_traits", []),
                "match_rationale": rec.get("match_rationale", "Coach-locked recommendation."),
                "is_discovery": False,
                "locked_by_coach": True,
                "confidence": int(rec.get("confidence", 0) or 0),
                "sequence": seq,
                "nx_journey_detail_id": rec.get("nx_journey_detail_id"),
            })
        else:
            try:
                unlocked = next(unlocked_iter)
                final_recs.append({
                    **unlocked,
                    "locked_by_coach": False,
                    "sequence": seq,
                })
            except StopIteration:
                break
        seq += 1

    # Cap at 20
    final_recs = final_recs[:20]
    for i, rec in enumerate(final_recs):
        rec["sequence"] = i + 1

    # 6. Soft-delete old recommendations and write new ones
    batch_id = f"rerank-{nx_user_id}-{uuid.uuid4().hex[:8]}"
    now = now_str()
    mysql_write(
        f"UPDATE tory_recommendations SET deleted_at = '{now}' "
        f"WHERE nx_user_id = {int(nx_user_id)} AND deleted_at IS NULL"
    )

    rec_count = write_recommendations(nx_user_id, profile_id, final_recs, pedagogy_info, batch_id)

    # Re-lock the coach-locked items in the new batch
    for rec in final_recs:
        if rec.get("locked_by_coach"):
            mysql_write(
                f"UPDATE tory_recommendations SET locked_by_coach = 1 "
                f"WHERE nx_user_id = {int(nx_user_id)} AND batch_id = '{batch_id}' "
                f"AND nx_lesson_id = {int(rec['nx_lesson_id'])} AND deleted_at IS NULL"
            )

    # 7. Record path event
    coach_info = get_user_coach(nx_user_id)
    coach_id = int(coach_info["coach_id"]) if coach_info else 0

    # Build human-readable reason
    new_rec_ids = []
    _, new_recs_db = mysql_query(
        f"SELECT id FROM tory_recommendations WHERE batch_id = '{batch_id}' "
        f"AND deleted_at IS NULL ORDER BY sequence ASC"
    )
    new_rec_ids = [int(r["id"]) for r in new_recs_db]

    reason = (
        f"Path reassessed due to {trigger_reason}. "
        f"Reassessment #{reassessment_id}. "
        f"{len(locked)} coach-locked items preserved. "
        f"{rec_count} total recommendations generated."
    )

    event_id = write_path_event(
        nx_user_id=nx_user_id,
        coach_id=coach_id,
        event_type="reassessed",
        reason=reason,
        details={
            "reassessment_id": reassessment_id,
            "trigger": trigger_reason,
            "locked_count": len(locked),
            "new_batch_id": batch_id,
            "profile_version": int(new_profile.get("version", 0)),
        },
        recommendation_ids=new_rec_ids,
    )

    return {
        "batch_id": batch_id,
        "recommendations_written": rec_count,
        "locked_preserved": len(locked),
        "path_event_id": event_id,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# EPP Score Parser
# ---------------------------------------------------------------------------


def parse_epp_scores(assessment_result: str) -> dict[str, float]:
    """Parse EPP scores from the assessment_result JSON field.

    Actual structure from Criteria Corp:
    {
      "orderId": "...",
      "candidate": {...},
      "scores": {
        "EPPAchievement": 14,
        "EPPMotivation": 64,
        ...
        "Manager": 81,      // Job-fit scores (no EPP prefix)
        "Sales": 57,
        ...
      },
      "reportUrl": "...",
      ...
    }

    Returns normalized dict: {"Achievement": 14, "Motivation": 64, "Manager_JobFit": 81, ...}
    """
    if not assessment_result or assessment_result == "NULL":
        return {}

    try:
        data = json.loads(assessment_result)
    except (json.JSONDecodeError, TypeError):
        return {}

    if not isinstance(data, dict):
        return {}

    # Scores are nested under "scores" key
    raw_scores = data.get("scores", data)
    if not isinstance(raw_scores, dict):
        return {}

    scores = {}
    for key, value in raw_scores.items():
        # Skip meta fields
        if key in EPP_SKIP_FIELDS:
            continue

        # Try to convert to float
        try:
            score = float(value)
        except (ValueError, TypeError):
            continue

        # Normalize key: strip "EPP" prefix for personality dims
        if key.startswith("EPP"):
            clean_key = key[3:]  # Remove "EPP" prefix
            scores[clean_key] = score
        elif key in EPP_JOBFIT_DIMS:
            # Job-fit dimensions: add suffix for clarity
            scores[f"{key}_JobFit"] = score
        else:
            scores[key] = score

    return scores


def parse_qa_answers(onboarding: dict) -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Scoring Engine
# ---------------------------------------------------------------------------


def score_content_for_learner(
    learner_gaps: list[dict],
    content_tags: list[dict],
    pedagogy_mode: str = "balanced",
    gap_ratio: int = 50,
    strength_ratio: int = 50,
) -> list[dict]:
    """Score all tagged lessons against a learner's profile.

    Returns sorted list of {lesson_id, score, rationale_hint} by match quality.
    """
    # Build learner gap vector
    gap_traits = {}
    strength_traits = {}

    for item in learner_gaps:
        trait = item.get("trait", "")
        score = float(item.get("score", 0))
        if item.get("type") == "gap":
            gap_traits[trait] = score
        else:
            strength_traits[trait] = score

    scored_lessons = []

    for tag in content_tags:
        lesson_id = tag.get("nx_lesson_id")
        try:
            trait_tags = json.loads(tag.get("trait_tags", "[]"))
        except (json.JSONDecodeError, TypeError):
            trait_tags = []

        if not trait_tags:
            continue

        # Score this lesson's relevance
        gap_score = 0.0
        strength_score = 0.0
        matching_traits = []

        for tt in trait_tags:
            trait_name = tt.get("trait", "")
            relevance = float(tt.get("relevance_score", 0))
            direction = tt.get("direction", "builds")

            if trait_name in gap_traits:
                gap_score += relevance * gap_traits[trait_name] / 100.0
                matching_traits.append(
                    {"trait": trait_name, "type": "gap", "direction": direction}
                )
            if trait_name in strength_traits:
                strength_score += relevance * strength_traits[trait_name] / 100.0
                matching_traits.append(
                    {"trait": trait_name, "type": "strength", "direction": direction}
                )

        # Apply pedagogy weighting
        gap_w = gap_ratio / 100.0
        strength_w = strength_ratio / 100.0
        total_score = (gap_score * gap_w + strength_score * strength_w)

        # Normalize to 0-100
        total_score = min(100, max(0, total_score * 100))

        scored_lessons.append({
            "nx_lesson_id": lesson_id,
            "score": round(total_score, 2),
            "gap_contribution": round(gap_score, 4),
            "strength_contribution": round(strength_score, 4),
            "matching_traits": matching_traits,
            "confidence": int(tag.get("confidence", 0)),
        })

    # Sort by score descending
    scored_lessons.sort(key=lambda x: x["score"], reverse=True)
    return scored_lessons


def apply_sequencing(
    scored_lessons: list[dict],
    lesson_journey_map: dict[int, int] | None = None,
    max_lessons: int = 20,
    max_consecutive_same_journey: int = 3,
    diminishing_factor: float = 0.7,
) -> list[dict]:
    """Apply sequencing logic to scored lessons.

    Rules (from bead spec):
    - Limit to max_lessons (default 20)
    - No more than max_consecutive_same_journey (3) from same journey in a row
    - Apply diminishing returns for same-trait stacking
    - Mix strength-building and growth-area lessons
    - Ensure diversity of targeted traits
    """
    if not scored_lessons:
        return []

    if lesson_journey_map is None:
        lesson_journey_map = {}

    # Phase 1: Score adjustment with diminishing returns
    candidates = []
    trait_counts: dict[str, int] = {}

    for lesson in scored_lessons:
        adjusted_score = lesson["score"]
        for mt in lesson.get("matching_traits", []):
            trait = mt["trait"]
            count = trait_counts.get(trait, 0)
            if count > 0:
                adjusted_score *= diminishing_factor ** count

        lesson_copy = dict(lesson)
        lesson_copy["adjusted_score"] = round(adjusted_score, 2)
        candidates.append(lesson_copy)

        for mt in lesson.get("matching_traits", []):
            trait = mt["trait"]
            trait_counts[trait] = trait_counts.get(trait, 0) + 1

    # Sort by adjusted score
    candidates.sort(key=lambda x: x["adjusted_score"], reverse=True)

    # Phase 2: Journey diversity — no more than 3 consecutive from same journey
    selected: list[dict] = []
    deferred: list[dict] = []

    for lesson in candidates:
        if len(selected) >= max_lessons:
            break

        lesson_id = int(lesson["nx_lesson_id"])
        journey_id = lesson_journey_map.get(lesson_id, lesson.get("nx_journey_detail_id", 0))

        # Check consecutive same-journey count
        consecutive = 0
        for prev in reversed(selected):
            prev_lid = int(prev["nx_lesson_id"])
            prev_jid = lesson_journey_map.get(prev_lid, prev.get("nx_journey_detail_id", 0))
            if prev_jid == journey_id and journey_id != 0:
                consecutive += 1
            else:
                break

        if consecutive >= max_consecutive_same_journey:
            deferred.append(lesson)
        else:
            lesson["nx_journey_detail_id"] = journey_id
            selected.append(lesson)

    # Phase 3: Fill remaining slots from deferred (at positions where they don't violate)
    for lesson in deferred:
        if len(selected) >= max_lessons:
            break
        lesson["nx_journey_detail_id"] = lesson_journey_map.get(
            int(lesson["nx_lesson_id"]), 0
        )
        selected.append(lesson)

    # Phase 4: Interleave gap and strength lessons for variety
    gap_lessons = [l for l in selected if any(
        m.get("type") == "gap" for m in l.get("matching_traits", [])
    )]
    strength_lessons = [l for l in selected if l not in gap_lessons]

    interleaved: list[dict] = []
    gi, si = 0, 0
    streak_type = None
    streak_count = 0

    while gi < len(gap_lessons) or si < len(strength_lessons):
        # Alternate: prefer gap, but don't let either type run more than 3 in a row
        pick_gap = True
        if gi >= len(gap_lessons):
            pick_gap = False
        elif si >= len(strength_lessons):
            pick_gap = True
        elif streak_type == "gap" and streak_count >= 3:
            pick_gap = False
        elif streak_type == "strength" and streak_count >= 3:
            pick_gap = True
        else:
            # Pick whichever has higher adjusted_score
            pick_gap = gap_lessons[gi]["adjusted_score"] >= strength_lessons[si]["adjusted_score"]

        if pick_gap:
            interleaved.append(gap_lessons[gi])
            gi += 1
            if streak_type == "gap":
                streak_count += 1
            else:
                streak_type = "gap"
                streak_count = 1
        else:
            interleaved.append(strength_lessons[si])
            si += 1
            if streak_type == "strength":
                streak_count += 1
            else:
                streak_type = "strength"
                streak_count = 1

    # Assign final sequence numbers
    for i, lesson in enumerate(interleaved):
        lesson["sequence"] = i + 1

    return interleaved[:max_lessons]


def check_coach_compatibility(
    learner_epp: dict[str, float],
    coach_id: int,
) -> dict:
    """Basic heuristic check for coach-learner compatibility.

    Returns a traffic light signal based on EPP trait analysis.
    In V1, coaches don't have EPP — so this uses basic heuristic rules.
    """
    # V1 heuristic: Check if learner has extreme scores that need
    # specific coaching attention
    warnings = []

    low_threshold = 30
    high_threshold = 80

    # Check for extreme scores
    low_traits = [t for t, s in learner_epp.items() if s < low_threshold]
    high_traits = [t for t, s in learner_epp.items() if s > high_threshold]

    if len(low_traits) > 5:
        warnings.append(f"Learner has {len(low_traits)} traits below {low_threshold}")
    if "Stress_Tolerance" in low_traits:
        warnings.append("Low stress tolerance — needs supportive coaching style")
    if "Assertiveness" in low_traits and "Motivation" in high_traits:
        warnings.append("High motivation but low assertiveness — needs encouragement not pressure")

    # Determine signal
    if len(warnings) >= 3:
        signal = "red"
        message = "Potential mismatch — review recommended"
    elif len(warnings) >= 1:
        signal = "yellow"
        message = "Some considerations for coaching approach"
    else:
        signal = "green"
        message = "No compatibility concerns detected"

    return {
        "signal": signal,
        "message": message,
        "warnings": warnings,
        "learner_low_traits": low_traits,
        "learner_high_traits": high_traits,
    }


# ---------------------------------------------------------------------------
# Rationale generation (EPP-dimension-aware)
# ---------------------------------------------------------------------------


def generate_rationale(
    lesson: dict,
    is_discovery: bool = False,
) -> str:
    """Generate a human-readable match rationale referencing EPP dimensions.

    Cost-optimized: uses template-based generation (no Claude API call)
    with EPP dimension names for specificity.
    """
    matching = lesson.get("matching_traits", [])
    gap_traits = [m["trait"] for m in matching if m.get("type") == "gap"]
    str_traits = [m["trait"] for m in matching if m.get("type") == "strength"]
    score = lesson.get("adjusted_score", lesson.get("score", 0))

    parts = []

    if is_discovery:
        # Discovery-phase framing: exploratory, low-commitment language
        parts.append(
            "Discovery lesson: This is an exploratory recommendation to help "
            "us understand your learning preferences early in your journey."
        )
        if gap_traits:
            trait_names = ", ".join(_humanize_trait(t) for t in gap_traits[:2])
            parts.append(
                f"It gently introduces growth areas in {trait_names}, "
                f"allowing you to explore at your own pace."
            )
        if str_traits:
            trait_names = ", ".join(_humanize_trait(t) for t in str_traits[:2])
            parts.append(
                f"It also connects to your existing strengths in {trait_names}."
            )
    else:
        # Full-path framing: specific EPP dimension references
        if gap_traits:
            trait_names = ", ".join(_humanize_trait(t) for t in gap_traits[:3])
            parts.append(
                f"This lesson targets your growth areas in {trait_names}."
            )
        if str_traits:
            trait_names = ", ".join(_humanize_trait(t) for t in str_traits[:3])
            parts.append(
                f"It leverages your strong {trait_names} scores "
                f"to build confidence while stretching new skills."
            )
        if score > 70:
            parts.append("High-confidence match based on your EPP profile.")
        elif score > 40:
            parts.append("Moderate match — selected for balanced skill development.")

    if not parts:
        parts.append("Selected to broaden your learning experience across multiple dimensions.")

    return " ".join(parts)


def _humanize_trait(trait: str) -> str:
    """Convert EPP trait keys to human-readable names."""
    replacements = {
        "SelfConfidence": "Self-Confidence",
        "StressTolerance": "Stress Tolerance",
        "Accounting_JobFit": "Accounting aptitude",
        "AdminAsst_JobFit": "Administrative aptitude",
        "Analyst_JobFit": "Analytical aptitude",
        "BankTeller_JobFit": "Detail-oriented service",
        "Collections_JobFit": "Collections aptitude",
        "CustomerService_JobFit": "Customer Service aptitude",
        "FrontDesk_JobFit": "Front Desk aptitude",
        "Manager_JobFit": "Management aptitude",
        "MedicalAsst_JobFit": "Medical assistance aptitude",
        "Production_JobFit": "Production aptitude",
        "Programmer_JobFit": "Programming aptitude",
        "Sales_JobFit": "Sales aptitude",
    }
    return replacements.get(trait, trait)


def write_recommendations(
    nx_user_id: int,
    profile_id: int,
    lessons: list[dict],
    pedagogy: dict,
    batch_id: str,
) -> int:
    """Write scored recommendations to tory_recommendations table.

    Returns count of rows written.
    """
    now = now_str()
    count = 0

    for lesson in lessons:
        is_disc = 1 if lesson.get("is_discovery") else 0
        score = lesson.get("adjusted_score", lesson.get("score", 0))
        rationale = lesson.get("match_rationale", "")
        traits_json = escape_sql(json.dumps(lesson.get("matching_traits", [])))
        rationale_esc = escape_sql(rationale)
        journey_id = lesson.get("nx_journey_detail_id") or "NULL"
        tag_id = lesson.get("content_tag_id") or "NULL"
        conf = lesson.get("confidence", 0) or "NULL"

        sql = (
            f"INSERT INTO tory_recommendations "
            f"(nx_user_id, profile_id, nx_lesson_id, content_tag_id, "
            f"nx_journey_detail_id, match_score, gap_contribution, "
            f"strength_contribution, adjusted_score, sequence, "
            f"match_rationale, matching_traits, is_discovery, "
            f"pedagogy_mode, pedagogy_ratio, confidence, batch_id, "
            f"created_at, updated_at) "
            f"VALUES ({int(nx_user_id)}, {int(profile_id)}, "
            f"{int(lesson['nx_lesson_id'])}, {tag_id}, "
            f"{journey_id}, {score}, "
            f"{lesson.get('gap_contribution', 0)}, "
            f"{lesson.get('strength_contribution', 0)}, "
            f"{lesson.get('adjusted_score', score)}, "
            f"{lesson.get('sequence', 0)}, "
            f"{rationale_esc}, {traits_json}, {is_disc}, "
            f"'{pedagogy.get('mode', 'balanced')}', "
            f"'{pedagogy.get('gap_ratio', 50)}/{pedagogy.get('strength_ratio', 50)}', "
            f"{conf}, '{batch_id}', '{now}', '{now}')"
        )
        mysql_write(sql)
        count += 1

    return count


def write_coach_flags(
    nx_user_id: int,
    coach_id: int,
    profile_id: int,
    compat: dict,
) -> None:
    """Write coach compatibility flags to tory_coach_flags table."""
    now = now_str()
    warnings_json = escape_sql(json.dumps(compat.get("warnings", [])))
    low_json = escape_sql(json.dumps(compat.get("learner_low_traits", [])))
    high_json = escape_sql(json.dumps(compat.get("learner_high_traits", [])))
    msg = escape_sql(compat.get("message", ""))

    # Soft-delete previous flags for this user-coach pair
    mysql_write(
        f"UPDATE tory_coach_flags SET deleted_at = '{now}' "
        f"WHERE nx_user_id = {int(nx_user_id)} AND coach_id = {int(coach_id)} "
        f"AND deleted_at IS NULL"
    )

    sql = (
        f"INSERT INTO tory_coach_flags "
        f"(nx_user_id, coach_id, profile_id, compat_signal, compat_message, "
        f"warnings, learner_low_traits, learner_high_traits, "
        f"created_at, updated_at) "
        f"VALUES ({int(nx_user_id)}, {int(coach_id)}, {int(profile_id)}, "
        f"'{compat['signal']}', {msg}, "
        f"{warnings_json}, {low_json}, {high_json}, "
        f"'{now}', '{now}')"
    )
    mysql_write(sql)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

server = Server("tory-engine")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all Tory Engine tools."""
    return [
        Tool(
            name="tory_get_learner_data",
            description=(
                "Fetch all available data for a learner: user info, onboarding Q&A, "
                "EPP scores, existing profile, current roadmap, backpack interactions, "
                "ratings, and tasks. Returns a comprehensive data package for analysis."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                },
                "required": ["nx_user_id"],
            },
        ),
        Tool(
            name="tory_interpret_profile",
            description=(
                "Parse EPP scores and Q&A answers for a learner and produce a "
                "structured profile with trait vector, motivation cluster, strengths, "
                "gaps, and profile narrative. Stores result in tory_learner_profiles. "
                "This is the first step in the Tory pipeline."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                },
                "required": ["nx_user_id"],
            },
        ),
        Tool(
            name="tory_score_content",
            description=(
                "Score all tagged lessons against a learner's profile. Returns ranked "
                "list of lessons with match scores and trait explanations. Requires "
                "content tags and learner profile to exist first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                    "max_lessons": {
                        "type": "integer",
                        "description": "Maximum lessons to include in scored list (default 30)",
                        "default": 30,
                    },
                },
                "required": ["nx_user_id"],
            },
        ),
        Tool(
            name="tory_generate_roadmap",
            description=(
                "Generate a personalized learning roadmap for a learner. Creates "
                "discovery phase (3-5 exploratory lessons for cold-start) or full "
                "path (post-discovery). Stores in tory_roadmaps + tory_roadmap_items."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                    "mode": {
                        "type": "string",
                        "description": "discovery (cold start) or full (post-discovery)",
                        "enum": ["discovery", "full"],
                        "default": "discovery",
                    },
                },
                "required": ["nx_user_id"],
            },
        ),
        Tool(
            name="tory_check_coach_compatibility",
            description=(
                "Check compatibility between a learner and a manually-assigned coach. "
                "Returns a traffic light signal (green/yellow/red) based on EPP heuristics."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                    "coach_id": {
                        "type": "integer",
                        "description": "The coaches.id of the assigned coach",
                    },
                },
                "required": ["nx_user_id", "coach_id"],
            },
        ),
        Tool(
            name="tory_get_roadmap",
            description=(
                "Fetch the current roadmap and all items for a learner. "
                "Returns the roadmap with items, completion status, and any coach overrides."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                },
                "required": ["nx_user_id"],
            },
        ),
        Tool(
            name="tory_get_progress",
            description=(
                "Get progress summary for a learner: completion percentage, "
                "engagement score, path changes, coach overrides, and recommendations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                },
                "required": ["nx_user_id"],
            },
        ),
        Tool(
            name="tory_list_content_tags",
            description=(
                "List all content tags or tags for a specific lesson. "
                "Shows trait tags, confidence, review status, and pass agreement."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_lesson_id": {
                        "type": "integer",
                        "description": "Optional: specific lesson to get tags for",
                    },
                    "review_status": {
                        "type": "string",
                        "description": "Filter by review status (pending/approved/rejected/needs_review)",
                        "enum": ["pending", "approved", "rejected", "needs_review"],
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="tory_set_pedagogy",
            description=(
                "Set the pedagogy configuration for a client company. "
                "Options: A (gap_fill, 70/30), B (strength_lead, 30/70), "
                "C (balanced, custom ratio)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "client_id": {
                        "type": "integer",
                        "description": "The clients.id of the company",
                    },
                    "mode": {
                        "type": "string",
                        "description": "Pedagogy mode: gap_fill (A), strength_lead (B), or balanced (C)",
                        "enum": ["gap_fill", "strength_lead", "balanced"],
                    },
                    "gap_ratio": {
                        "type": "integer",
                        "description": "Gap-fill ratio 0-100 (only for balanced mode, default 50)",
                        "default": 50,
                    },
                    "strength_ratio": {
                        "type": "integer",
                        "description": "Strength-lead ratio 0-100 (only for balanced mode, default 50)",
                        "default": 50,
                    },
                },
                "required": ["client_id", "mode"],
            },
        ),
        Tool(
            name="tory_generate_path",
            description=(
                "Generate a complete personalized learning path for a learner. "
                "This is the main entry point (POST /api/tory/generate/:learnerId). "
                "Loads learner profile, scores content via cosine similarity against EPP "
                "dimensions, applies diversity rules (max 3 consecutive from same journey, "
                "mix gap/strength lessons), generates top-N recommendations (default 20) "
                "with EPP-referencing rationale, marks first 3-5 as discovery phase, "
                "computes coach compatibility flags, and writes everything to "
                "tory_recommendations + tory_coach_flags tables."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                    "max_recommendations": {
                        "type": "integer",
                        "description": "Number of recommendations to generate (default 20)",
                        "default": 20,
                    },
                    "coach_id": {
                        "type": "integer",
                        "description": "Optional: coaches.id to check compatibility for",
                    },
                },
                "required": ["nx_user_id"],
            },
        ),
        Tool(
            name="tory_dashboard_snapshot",
            description=(
                "Generate a progress snapshot for the HR dashboard. "
                "Can generate for a single user or aggregate for a department/client."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "Specific user (optional — omit for aggregate)",
                    },
                    "client_id": {
                        "type": "integer",
                        "description": "Client company for aggregate view (optional)",
                    },
                    "department_id": {
                        "type": "integer",
                        "description": "Department for aggregate view (optional)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="tory_schedule_quarterly_epp",
            description=(
                "Schedule a quarterly EPP retake for a learner via Criteria Corp API. "
                "Creates a pending reassessment record. When the API returns updated scores, "
                "computes profile drift, updates the learner profile, and triggers path "
                "re-ranking. Falls back to mini-assessment data if API fails after 3 retries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                },
                "required": ["nx_user_id"],
            },
        ),
        Tool(
            name="tory_mini_assessment",
            description=(
                "Process a mini-assessment submitted mid-lesson (POST /api/tory/mini-assessment). "
                "Accepts 3-5 question responses, stores as type=mini reassessment, computes "
                "profile adjustments, and triggers path re-ranking if drift exceeds threshold."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                    "responses": {
                        "type": "array",
                        "description": "Array of {question_id, trait, response_value (0-100)} objects",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question_id": {"type": "string"},
                                "trait": {"type": "string"},
                                "response_value": {"type": "number"},
                            },
                            "required": ["question_id", "trait", "response_value"],
                        },
                    },
                },
                "required": ["nx_user_id", "responses"],
            },
        ),
        Tool(
            name="tory_check_passive_signals",
            description=(
                "Check if a learner's passive engagement signals (backpack saves, ratings, "
                "task completions) have crossed the threshold for triggering a reassessment. "
                "If threshold is met, aggregates signals as type=backpack_derived reassessment "
                "and triggers path re-ranking."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                },
                "required": ["nx_user_id"],
            },
        ),
        Tool(
            name="tory_reassessment_status",
            description=(
                "Get the reassessment history and scheduling status for a learner. "
                "Shows completed, pending, and upcoming reassessments with drift data."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nx_user_id": {
                        "type": "integer",
                        "description": "The nx_users.id of the learner",
                    },
                },
                "required": ["nx_user_id"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _tool_get_learner_data(nx_user_id: int) -> str:
    """Comprehensive learner data fetch."""
    user = get_user_info(nx_user_id)
    if not user:
        return json.dumps({"error": f"User {nx_user_id} not found"})

    onboarding = get_user_onboarding(nx_user_id)
    epp_scores = {}
    qa_answers = {}
    if onboarding:
        epp_scores = parse_epp_scores(onboarding.get("assesment_result", ""))
        qa_answers = parse_qa_answers(onboarding)

    profile = get_current_profile(nx_user_id)
    roadmap = get_current_roadmap(nx_user_id)
    roadmap_items = get_roadmap_items(int(roadmap["id"])) if roadmap else []
    backpacks = get_user_backpacks(nx_user_id)
    ratings = get_user_ratings(nx_user_id)
    tasks = get_user_tasks(nx_user_id)
    reassessments = get_reassessment_history(nx_user_id)

    return json.dumps({
        "user": user,
        "onboarding": {
            "raw_id": onboarding.get("id") if onboarding else None,
            "has_epp": len(epp_scores) > 0,
            "epp_dimension_count": len(epp_scores),
            "epp_scores": epp_scores,
            "qa_answers": qa_answers,
        },
        "profile": profile,
        "roadmap": {
            "current": roadmap,
            "items": roadmap_items,
            "item_count": len(roadmap_items),
        },
        "interactions": {
            "backpack_count": len(backpacks),
            "rating_count": len(ratings),
            "task_count": len(tasks),
        },
        "reassessment_count": len(reassessments),
    }, indent=2, default=str)


async def _tool_interpret_profile(nx_user_id: int) -> str:
    """Interpret EPP + Q&A into a structured learner profile."""
    onboarding = get_user_onboarding(nx_user_id)
    if not onboarding:
        return json.dumps({"error": f"No onboarding data for user {nx_user_id}"})

    epp_scores = parse_epp_scores(onboarding.get("assesment_result", ""))
    if not epp_scores:
        return json.dumps({"error": f"No EPP scores found for user {nx_user_id}"})

    qa_answers = parse_qa_answers(onboarding)

    # Build structured profile from EPP scores
    # Classify traits into strengths and gaps
    sorted_traits = sorted(epp_scores.items(), key=lambda x: x[1], reverse=True)

    strengths = []
    gaps = []

    for trait, score in sorted_traits:
        if score >= 60:
            strengths.append({"trait": trait, "score": score, "type": "strength"})
        elif score <= 40:
            gaps.append({"trait": trait, "score": score, "type": "gap"})

    # Determine motivation cluster from Q&A
    motivation_drivers = []
    for field in ("advance_your_career", "imp_thing_career_plan", "success_look_like"):
        val = qa_answers.get(field)
        if not val:
            continue
        if isinstance(val, list):
            motivation_drivers.extend(str(v) for v in val)
        else:
            motivation_drivers.append(str(val))

    # Determine learning style (heuristic based on EPP)
    learning_style = "blended"
    if epp_scores.get("Extroversion", 50) > 70:
        learning_style = "active"
    elif epp_scores.get("Openness", 50) > 70:
        learning_style = "reflective"
    elif epp_scores.get("Conscientiousness", 50) > 70:
        learning_style = "theoretical"

    # Build narrative (second person, 3-5 sentences, top 3 strengths + 2 growth areas)
    top_strengths = [s["trait"] for s in strengths[:3]]
    top_gaps = [g["trait"] for g in gaps[:2]]

    # Human-readable trait names
    trait_labels = {
        "Achievement": "achievement drive", "Motivation": "intrinsic motivation",
        "Competitiveness": "competitiveness", "Managerial": "managerial ability",
        "Assertiveness": "assertiveness", "Extroversion": "extroversion",
        "Cooperativeness": "cooperativeness", "Patience": "patience",
        "SelfConfidence": "self-confidence", "Conscientiousness": "conscientiousness",
        "Openness": "openness to new ideas", "Stability": "emotional stability",
        "StressTolerance": "stress tolerance",
    }
    def label(t):
        if t.endswith("_JobFit"):
            return t.replace("_JobFit", "").lower() + " aptitude"
        return trait_labels.get(t, t.lower())

    str_labels = [label(t) for t in top_strengths]
    gap_labels = [label(t) for t in top_gaps]

    style_desc = {
        "active": "You learn best through hands-on activities and interactive exercises.",
        "reflective": "You learn best when given time to reflect and process information deeply.",
        "theoretical": "You thrive with structured, methodical content and clear frameworks.",
        "blended": "You adapt well across different learning formats and approaches.",
    }

    parts = []
    if str_labels:
        parts.append(
            f"You show strong {str_labels[0]}, {str_labels[1]}, and {str_labels[2]}."
            if len(str_labels) >= 3
            else f"You show strong {' and '.join(str_labels)}."
        )
        parts.append(
            f"These strengths suggest you tend to excel in roles that value "
            f"collaboration, reliability, and initiative."
        )
    if gap_labels:
        parts.append(
            f"Your growth areas include {' and '.join(gap_labels)}, "
            f"which your learning path will focus on developing."
        )
    parts.append(style_desc.get(learning_style, style_desc["blended"]))
    if motivation_drivers:
        clean_drivers = [d.strip().rstrip(".").lower() for d in motivation_drivers[:2]]
        parts.append(
            f"You are driven by {' and '.join(clean_drivers)}."
        )

    narrative = " ".join(parts[:5])

    # Determine confidence
    confidence = 50  # Base confidence from EPP alone
    if qa_answers:
        confidence += 10  # Q&A adds context
    if len(epp_scores) >= 20:
        confidence += 15  # Full EPP is more reliable

    # Store in database
    epp_json = escape_sql(json.dumps(epp_scores))
    motivation_json = escape_sql(json.dumps(motivation_drivers))
    strengths_json = escape_sql(json.dumps(strengths))
    gaps_json = escape_sql(json.dumps(gaps))
    narrative_esc = escape_sql(narrative)
    onboarding_id = int(onboarding["id"])
    now = now_str()

    # Check if profile already exists
    existing = get_current_profile(nx_user_id)
    new_version = int(existing["version"]) + 1 if existing else 1

    sql = (
        f"INSERT INTO tory_learner_profiles "
        f"(nx_user_id, onboarding_id, epp_summary, motivation_cluster, "
        f"strengths, gaps, learning_style, profile_narrative, confidence, "
        f"version, source, feedback_flags, created_at, updated_at) "
        f"VALUES ({int(nx_user_id)}, {onboarding_id}, {epp_json}, {motivation_json}, "
        f"{strengths_json}, {gaps_json}, '{learning_style}', {narrative_esc}, "
        f"{confidence}, {new_version}, 'epp_qa', 0, '{now}', '{now}')"
    )
    mysql_write(sql)

    # Fetch the newly created profile
    profile = get_current_profile(nx_user_id)

    return json.dumps({
        "status": "profile_created",
        "user_id": nx_user_id,
        "version": new_version,
        "epp_dimensions": len(epp_scores),
        "strengths_count": len(strengths),
        "gaps_count": len(gaps),
        "learning_style": learning_style,
        "confidence": confidence,
        "narrative": narrative,
        "profile_id": profile["id"] if profile else None,
    }, indent=2, default=str)


async def _tool_score_content(nx_user_id: int, max_lessons: int = 30) -> str:
    """Score content against learner profile."""
    profile = get_current_profile(nx_user_id)
    if not profile:
        return json.dumps({"error": f"No profile found for user {nx_user_id}. Run tory_interpret_profile first."})

    # Get pedagogy settings
    user = get_user_info(nx_user_id)
    client_id = user.get("client_id") if user else None
    pedagogy = get_client_pedagogy(int(client_id)) if client_id else None

    mode = pedagogy["mode"] if pedagogy else "balanced"
    gap_ratio = int(pedagogy["gap_ratio"]) if pedagogy else 50
    strength_ratio = int(pedagogy["strength_ratio"]) if pedagogy else 50

    if mode == "gap_fill":
        gap_ratio, strength_ratio = 70, 30
    elif mode == "strength_lead":
        gap_ratio, strength_ratio = 30, 70

    # Combine strengths + gaps into learner trait list
    try:
        strengths = json.loads(profile.get("strengths", "[]"))
        gaps = json.loads(profile.get("gaps", "[]"))
    except (json.JSONDecodeError, TypeError):
        strengths, gaps = [], []

    learner_traits = gaps + strengths

    # Get all tagged content (confidence >= 70 or approved)
    content_tags = get_content_tags(confidence_threshold=70)
    if not content_tags:
        return json.dumps({
            "error": "No content tags found. Run content tagging pipeline first.",
            "tagged_lesson_count": 0,
        })

    # Score
    scored = score_content_for_learner(
        learner_traits, content_tags, mode, gap_ratio, strength_ratio
    )

    # Apply sequencing
    sequenced = apply_sequencing(scored, max_lessons=max_lessons)

    return json.dumps({
        "status": "scored",
        "user_id": nx_user_id,
        "pedagogy": {"mode": mode, "gap_ratio": gap_ratio, "strength_ratio": strength_ratio},
        "total_tagged_lessons": len(content_tags),
        "scored_lessons": len(scored),
        "selected_lessons": len(sequenced),
        "lessons": sequenced,
    }, indent=2, default=str)


async def _tool_generate_roadmap(nx_user_id: int, mode: str = "discovery") -> str:
    """Generate a learning roadmap."""
    profile = get_current_profile(nx_user_id)
    if not profile:
        return json.dumps({"error": f"No profile for user {nx_user_id}. Run tory_interpret_profile first."})

    # Score content
    scored_json = await _tool_score_content(nx_user_id, max_lessons=50)
    scored_data = json.loads(scored_json)

    if "error" in scored_data:
        return json.dumps(scored_data)

    lessons = scored_data.get("lessons", [])
    if not lessons:
        return json.dumps({"error": "No scored lessons available for roadmap generation."})

    now = now_str()
    profile_id = int(profile["id"])
    pedagogy = scored_data.get("pedagogy", {})

    # Determine how many lessons for this roadmap
    if mode == "discovery":
        roadmap_lessons = lessons[:DISCOVERY_LESSON_COUNT]
        status = "discovery"
        trigger = "onboarding"
        rationale = (
            f"Discovery phase: {len(roadmap_lessons)} exploratory lessons selected "
            f"to understand your learning style before generating your full personalized path."
        )
    else:
        roadmap_lessons = lessons
        status = "active"
        trigger = "discovery_complete"
        rationale = (
            f"Full personalized learning path with {len(roadmap_lessons)} lessons, "
            f"tailored to your profile using {pedagogy.get('mode', 'balanced')} pedagogy "
            f"({pedagogy.get('gap_ratio', 50)}/{pedagogy.get('strength_ratio', 50)} ratio)."
        )

    # Deactivate any existing current roadmap
    mysql_write(
        f"UPDATE tory_roadmaps SET is_current = 0, updated_at = '{now}' "
        f"WHERE nx_user_id = {int(nx_user_id)} AND is_current = 1"
    )

    # Check version
    existing = get_current_roadmap(nx_user_id)
    new_version = int(existing["version"]) + 1 if existing else 1

    # Insert roadmap
    rationale_esc = escape_sql(rationale)
    sql = (
        f"INSERT INTO tory_roadmaps "
        f"(nx_user_id, profile_id, pedagogy_mode, pedagogy_ratio, version, "
        f"status, total_lessons, completed_lessons, completion_pct, "
        f"generation_rationale, trigger_source, is_current, "
        f"created_user_type, created_at, updated_at) "
        f"VALUES ({int(nx_user_id)}, {profile_id}, "
        f"'{pedagogy.get('mode', 'balanced')}', "
        f"'{pedagogy.get('gap_ratio', 50)}/{pedagogy.get('strength_ratio', 50)}', "
        f"{new_version}, '{status}', {len(roadmap_lessons)}, 0, 0, "
        f"{rationale_esc}, '{trigger}', 1, 'system', '{now}', '{now}')"
    )
    mysql_write(sql)

    # Get the new roadmap ID
    roadmap = get_current_roadmap(nx_user_id)
    if not roadmap:
        return json.dumps({"error": "Failed to create roadmap"})

    roadmap_id = int(roadmap["id"])

    # Insert roadmap items
    for lesson in roadmap_lessons:
        is_discovery = 1 if mode == "discovery" else 0
        is_critical = 1 if lesson.get("score", 0) > 70 else 0
        score = int(lesson.get("score", 0))
        traits_json = escape_sql(json.dumps(lesson.get("matching_traits", [])))
        seq = lesson.get("sequence", 0)
        lesson_id = int(lesson["nx_lesson_id"])

        # Generate rationale hint
        matching = lesson.get("matching_traits", [])
        gap_traits = [m["trait"] for m in matching if m.get("type") == "gap"]
        str_traits = [m["trait"] for m in matching if m.get("type") == "strength"]
        rationale_parts = []
        if gap_traits:
            rationale_parts.append(f"Builds growth area: {', '.join(gap_traits[:2])}")
        if str_traits:
            rationale_parts.append(f"Leverages strength: {', '.join(str_traits[:2])}")
        match_rationale = ". ".join(rationale_parts) if rationale_parts else "Selected for exploration"
        match_rationale_esc = escape_sql(match_rationale)

        item_sql = (
            f"INSERT INTO tory_roadmap_items "
            f"(roadmap_id, nx_lesson_id, sequence, status, is_critical, "
            f"is_discovery, match_score, match_rationale, trait_targets, "
            f"original_sequence, created_at, updated_at) "
            f"VALUES ({roadmap_id}, {lesson_id}, {seq}, 'pending', {is_critical}, "
            f"{is_discovery}, {score}, {match_rationale_esc}, {traits_json}, "
            f"{seq}, '{now}', '{now}')"
        )
        mysql_write(item_sql)

    # Fetch created items
    items = get_roadmap_items(roadmap_id)

    return json.dumps({
        "status": "roadmap_created",
        "user_id": nx_user_id,
        "roadmap_id": roadmap_id,
        "mode": mode,
        "version": new_version,
        "total_lessons": len(items),
        "critical_lessons": sum(1 for i in items if i.get("is_critical") == "1"),
        "discovery_lessons": sum(1 for i in items if i.get("is_discovery") == "1"),
        "rationale": rationale,
        "items": items,
    }, indent=2, default=str)


async def _tool_check_coach_compatibility(nx_user_id: int, coach_id: int) -> str:
    """Check coach-learner compatibility."""
    onboarding = get_user_onboarding(nx_user_id)
    if not onboarding:
        return json.dumps({"error": f"No onboarding data for user {nx_user_id}"})

    epp_scores = parse_epp_scores(onboarding.get("assesment_result", ""))
    if not epp_scores:
        return json.dumps({"error": f"No EPP scores for user {nx_user_id}"})

    result = check_coach_compatibility(epp_scores, coach_id)
    result["user_id"] = nx_user_id
    result["coach_id"] = coach_id

    return json.dumps(result, indent=2, default=str)


async def _tool_generate_path(
    nx_user_id: int,
    max_recommendations: int = 20,
    coach_id: int | None = None,
) -> str:
    """Generate a complete personalized learning path.

    This is the main entry point implementing POST /api/tory/generate/:learnerId.

    Pipeline:
    1. Load learner profile from tory_learner_profiles
    2. Load pedagogy config from tory_pedagogy_config (via client_id)
    3. Fetch content tags (confidence >= 70 or approved)
    4. Score lessons via weighted dot product against learner trait vector
    5. Apply sequencing: journey diversity (max 3 consecutive), trait mixing
    6. Generate rationale for each recommendation referencing EPP dimensions
    7. Mark first 3-5 as discovery phase with exploratory framing
    8. Write to tory_recommendations
    9. Check coach compatibility and write to tory_coach_flags
    10. Return full result
    """
    import uuid

    # Step 1: Load profile
    profile = get_current_profile(nx_user_id)
    if not profile:
        return json.dumps({
            "error": f"No profile for user {nx_user_id}. Run tory_interpret_profile first.",
        })

    profile_id = int(profile["id"])

    # Step 2: Load pedagogy config
    user = get_user_info(nx_user_id)
    if not user:
        return json.dumps({"error": f"User {nx_user_id} not found"})

    client_id = user.get("client_id")
    pedagogy = get_client_pedagogy(int(client_id)) if client_id else None

    mode = pedagogy["mode"] if pedagogy else "balanced"
    gap_ratio = int(pedagogy["gap_ratio"]) if pedagogy else 50
    strength_ratio = int(pedagogy["strength_ratio"]) if pedagogy else 50

    if mode == "gap_fill":
        gap_ratio, strength_ratio = 70, 30
    elif mode == "strength_lead":
        gap_ratio, strength_ratio = 30, 70

    pedagogy_info = {
        "mode": mode,
        "gap_ratio": gap_ratio,
        "strength_ratio": strength_ratio,
    }

    # Step 3: Load learner traits
    try:
        strengths = json.loads(profile.get("strengths", "[]"))
        gaps = json.loads(profile.get("gaps", "[]"))
    except (json.JSONDecodeError, TypeError):
        strengths, gaps = [], []

    learner_traits = gaps + strengths

    # Step 4: Fetch content tags (confidence >= 70 or approved)
    content_tags = get_content_tags(confidence_threshold=70)
    if not content_tags:
        return json.dumps({
            "error": "No eligible content tags found. Need tags with confidence >= 70 or status=approved.",
            "tagged_lesson_count": 0,
        })

    # Step 5: Score lessons
    scored = score_content_for_learner(
        learner_traits, content_tags, mode, gap_ratio, strength_ratio
    )

    if not scored:
        return json.dumps({
            "error": "No lessons scored above zero. Check content tags and learner profile alignment.",
        })

    # Enrich scored lessons with content_tag_id
    tag_by_lesson = {int(t["nx_lesson_id"]): t for t in content_tags}
    for lesson in scored:
        lid = int(lesson["nx_lesson_id"])
        if lid in tag_by_lesson:
            lesson["content_tag_id"] = int(tag_by_lesson[lid]["id"])

    # Step 6: Apply sequencing with journey diversity
    lesson_journey_map = get_lesson_journey_map()
    sequenced = apply_sequencing(
        scored,
        lesson_journey_map=lesson_journey_map,
        max_lessons=max_recommendations,
        max_consecutive_same_journey=3,
    )

    # Step 7: Generate rationale and mark discovery phase
    discovery_count = min(DISCOVERY_LESSON_COUNT, len(sequenced))
    for i, lesson in enumerate(sequenced):
        is_discovery = i < discovery_count
        lesson["is_discovery"] = is_discovery
        lesson["match_rationale"] = generate_rationale(lesson, is_discovery=is_discovery)

    # Step 8: Write to tory_recommendations
    batch_id = f"gen-{nx_user_id}-{uuid.uuid4().hex[:8]}"

    # Soft-delete previous recommendations for this user
    now = now_str()
    mysql_write(
        f"UPDATE tory_recommendations SET deleted_at = '{now}' "
        f"WHERE nx_user_id = {int(nx_user_id)} AND deleted_at IS NULL"
    )

    rec_count = write_recommendations(
        nx_user_id, profile_id, sequenced, pedagogy_info, batch_id
    )

    # Step 9: Coach compatibility
    coach_result = None
    if coach_id is None:
        # Try to find assigned coach
        coach_info = get_user_coach(nx_user_id)
        if coach_info:
            coach_id = int(coach_info["coach_id"])

    if coach_id:
        onboarding = get_user_onboarding(nx_user_id)
        epp_scores = {}
        if onboarding:
            epp_scores = parse_epp_scores(onboarding.get("assesment_result", ""))

        if epp_scores:
            compat = check_coach_compatibility(epp_scores, coach_id)
            write_coach_flags(nx_user_id, coach_id, profile_id, compat)
            coach_result = {
                "coach_id": coach_id,
                "signal": compat["signal"],
                "message": compat["message"],
                "warning_count": len(compat.get("warnings", [])),
            }

    # Step 10: Build response
    discovery_lessons = [l for l in sequenced if l.get("is_discovery")]
    non_discovery = [l for l in sequenced if not l.get("is_discovery")]

    # Verify consecutive journey constraint
    journey_violations = 0
    for i in range(3, len(sequenced)):
        jids = [
            lesson_journey_map.get(int(sequenced[j]["nx_lesson_id"]), 0)
            for j in range(i - 2, i + 1)
        ]
        if jids[0] == jids[1] == jids[2] != 0:
            # Check if the item before the window is also the same
            if i >= 3:
                prev_jid = lesson_journey_map.get(int(sequenced[i - 3]["nx_lesson_id"]), 0)
                if prev_jid == jids[0]:
                    journey_violations += 1

    return json.dumps({
        "status": "path_generated",
        "user_id": nx_user_id,
        "profile_id": profile_id,
        "batch_id": batch_id,
        "pedagogy": pedagogy_info,
        "total_eligible_tags": len(content_tags),
        "total_scored": len(scored),
        "total_recommendations": len(sequenced),
        "recommendations_written": rec_count,
        "discovery_count": len(discovery_lessons),
        "non_discovery_count": len(non_discovery),
        "journey_diversity_violations": journey_violations,
        "coach_compatibility": coach_result,
        "recommendations": [
            {
                "sequence": l["sequence"],
                "nx_lesson_id": l["nx_lesson_id"],
                "match_score": l.get("adjusted_score", l.get("score", 0)),
                "is_discovery": l.get("is_discovery", False),
                "match_rationale": l.get("match_rationale", ""),
                "matching_traits": l.get("matching_traits", []),
            }
            for l in sequenced
        ],
    }, indent=2, default=str)


async def _tool_get_roadmap(nx_user_id: int) -> str:
    """Get current roadmap with items and overrides."""
    roadmap = get_current_roadmap(nx_user_id)
    if not roadmap:
        return json.dumps({"error": f"No active roadmap for user {nx_user_id}"})

    roadmap_id = int(roadmap["id"])
    items = get_roadmap_items(roadmap_id)
    overrides = get_coach_overrides(roadmap_id)

    return json.dumps({
        "roadmap": roadmap,
        "items": items,
        "coach_overrides": overrides,
        "stats": {
            "total": len(items),
            "completed": sum(1 for i in items if i.get("status") == "completed"),
            "pending": sum(1 for i in items if i.get("status") == "pending"),
            "active": sum(1 for i in items if i.get("status") == "active"),
            "skipped": sum(1 for i in items if i.get("status") == "skipped"),
            "critical": sum(1 for i in items if i.get("is_critical") == "1"),
            "override_count": len(overrides),
        },
    }, indent=2, default=str)


async def _tool_get_progress(nx_user_id: int) -> str:
    """Get progress summary for a learner."""
    profile = get_current_profile(nx_user_id)
    roadmap = get_current_roadmap(nx_user_id)
    backpacks = get_user_backpacks(nx_user_id)
    ratings = get_user_ratings(nx_user_id)
    tasks = get_user_tasks(nx_user_id)
    reassessments = get_reassessment_history(nx_user_id)

    items = get_roadmap_items(int(roadmap["id"])) if roadmap else []
    completed = sum(1 for i in items if i.get("status") == "completed")
    total = len(items)

    completion_pct = round(completed / total * 100, 1) if total > 0 else 0

    # Engagement score heuristic (0-100)
    engagement = min(100, (
        min(50, len(backpacks) * 2) +  # Recent interactions
        min(25, len(ratings) * 5) +     # Ratings given
        min(25, len(tasks) * 3)          # Tasks completed
    ))

    # Check for stall
    stalled = False
    if roadmap and items:
        active_items = [i for i in items if i.get("status") == "active"]
        if not active_items and completed < total:
            stalled = True

    return json.dumps({
        "user_id": nx_user_id,
        "profile_version": profile.get("version") if profile else None,
        "profile_confidence": profile.get("confidence") if profile else None,
        "roadmap_status": roadmap.get("status") if roadmap else None,
        "completion_pct": completion_pct,
        "completed_lessons": completed,
        "total_lessons": total,
        "engagement_score": engagement,
        "interaction_counts": {
            "backpacks": len(backpacks),
            "ratings": len(ratings),
            "tasks": len(tasks),
        },
        "reassessments_completed": sum(
            1 for r in reassessments if r.get("status") == "completed"
        ),
        "is_stalled": stalled,
        "needs_reassessment": len(reassessments) == 0 and completed > 3,
    }, indent=2, default=str)


async def _tool_list_content_tags(
    nx_lesson_id: int | None = None,
    review_status: str | None = None,
) -> str:
    """List content tags with optional filters."""
    where_parts = ["deleted_at IS NULL"]
    if nx_lesson_id is not None:
        where_parts.append(f"nx_lesson_id = {int(nx_lesson_id)}")
    if review_status:
        where_parts.append(f"review_status = '{review_status}'")

    where = " AND ".join(where_parts)
    _, rows = mysql_query(
        f"SELECT id, nx_lesson_id, confidence, review_status, pass_agreement, "
        f"difficulty, learning_style, created_at "
        f"FROM tory_content_tags WHERE {where} "
        f"ORDER BY nx_lesson_id ASC LIMIT 100"
    )

    return json.dumps({
        "count": len(rows),
        "tags": rows,
    }, indent=2, default=str)


async def _tool_set_pedagogy(
    client_id: int,
    mode: str,
    gap_ratio: int = 50,
    strength_ratio: int = 50,
) -> str:
    """Set pedagogy config for a client company."""
    # Validate mode
    if mode not in ("gap_fill", "strength_lead", "balanced"):
        return json.dumps({"error": f"Invalid mode: {mode}"})

    # Set defaults for non-balanced modes
    if mode == "gap_fill":
        gap_ratio, strength_ratio = 70, 30
    elif mode == "strength_lead":
        gap_ratio, strength_ratio = 30, 70

    # Validate ratios
    if gap_ratio + strength_ratio != 100:
        return json.dumps({"error": f"Ratios must sum to 100 (got {gap_ratio} + {strength_ratio})"})

    now = now_str()

    # Soft-delete existing config
    mysql_write(
        f"UPDATE tory_pedagogy_config SET deleted_at = '{now}' "
        f"WHERE client_id = {int(client_id)} AND deleted_at IS NULL"
    )

    # Insert new config
    sql = (
        f"INSERT INTO tory_pedagogy_config "
        f"(client_id, mode, gap_ratio, strength_ratio, "
        f"configured_user_type, created_at, updated_at) "
        f"VALUES ({int(client_id)}, '{mode}', {gap_ratio}, {strength_ratio}, "
        f"'admin', '{now}', '{now}')"
    )
    mysql_write(sql)

    return json.dumps({
        "status": "pedagogy_set",
        "client_id": client_id,
        "mode": mode,
        "gap_ratio": gap_ratio,
        "strength_ratio": strength_ratio,
    }, indent=2, default=str)


async def _tool_dashboard_snapshot(
    nx_user_id: int | None = None,
    client_id: int | None = None,
    department_id: int | None = None,
) -> str:
    """Generate dashboard snapshot data."""
    if nx_user_id:
        # Individual snapshot
        progress_json = await _tool_get_progress(nx_user_id)
        progress = json.loads(progress_json)

        roadmap = get_current_roadmap(nx_user_id)
        overrides = get_coach_overrides(int(roadmap["id"])) if roadmap else []

        now = now_str()
        today = datetime.now().strftime("%Y-%m-%d")

        # Store snapshot
        sql = (
            f"INSERT INTO tory_progress_snapshots "
            f"(nx_user_id, roadmap_id, snapshot_date, completion_pct, "
            f"engagement_score, lessons_completed, lessons_total, "
            f"path_changes, coach_overrides, profile_confidence, "
            f"created_at, updated_at) "
            f"VALUES ({int(nx_user_id)}, "
            f"{int(roadmap['id']) if roadmap else 'NULL'}, "
            f"'{today}', {progress.get('completion_pct', 0)}, "
            f"{progress.get('engagement_score', 0)}, "
            f"{progress.get('completed_lessons', 0)}, "
            f"{progress.get('total_lessons', 0)}, "
            f"0, {len(overrides)}, "
            f"{progress.get('profile_confidence', 0) or 0}, "
            f"'{now}', '{now}')"
        )
        mysql_write(sql)

        return json.dumps({
            "type": "individual",
            "user_id": nx_user_id,
            "snapshot": progress,
        }, indent=2, default=str)

    elif client_id or department_id:
        # Aggregate snapshot
        where = "WHERE s.deleted_at IS NULL"
        if client_id:
            where += f" AND s.client_id = {int(client_id)}"
        if department_id:
            where += f" AND s.department_id = {int(department_id)}"

        _, rows = mysql_query(
            f"SELECT COUNT(*) as learner_count, "
            f"AVG(s.completion_pct) as avg_completion, "
            f"AVG(s.engagement_score) as avg_engagement, "
            f"SUM(s.lessons_completed) as total_completed, "
            f"SUM(s.lessons_total) as total_lessons, "
            f"AVG(s.tory_accuracy) as avg_tory_accuracy "
            f"FROM tory_progress_snapshots s {where} "
            f"AND s.snapshot_date = CURDATE()"
        )

        return json.dumps({
            "type": "aggregate",
            "client_id": client_id,
            "department_id": department_id,
            "aggregate": rows[0] if rows else {},
        }, indent=2, default=str)

    else:
        return json.dumps({"error": "Provide nx_user_id, client_id, or department_id"})


async def _tool_schedule_quarterly_epp(nx_user_id: int) -> str:
    """Schedule a quarterly EPP retake and process results.

    Flow:
    1. Check if quarterly retake is due (90 days since last quarterly_epp)
    2. Fetch the user's Criteria Corp order ID from onboarding
    3. Call Criteria Corp API to fetch updated scores (3 retries with exponential backoff)
    4. If API fails, fall back to most recent mini-assessment data
    5. Compute profile drift between old and new scores
    6. If drift >= threshold, update profile and trigger re-ranking
    7. Write reassessment record and path event
    """
    profile = get_current_profile(nx_user_id)
    if not profile:
        return json.dumps({"error": f"No profile for user {nx_user_id}"})

    # Check if quarterly retake is due
    last_quarterly = get_last_reassessment(nx_user_id, "quarterly_epp")
    if last_quarterly:
        completed_at = last_quarterly.get("completed_at", "")
        if completed_at and completed_at != "NULL":
            from datetime import datetime as dt
            try:
                last_date = dt.strptime(completed_at, "%Y-%m-%d %H:%M:%S")
                days_since = (dt.now() - last_date).days
                if days_since < REASSESSMENT_QUARTERLY_DAYS:
                    return json.dumps({
                        "status": "not_due",
                        "days_since_last": days_since,
                        "days_until_next": REASSESSMENT_QUARTERLY_DAYS - days_since,
                        "message": f"Quarterly EPP retake not due for {REASSESSMENT_QUARTERLY_DAYS - days_since} more days.",
                    })
            except (ValueError, TypeError):
                pass

    # Get old scores from current profile
    try:
        old_scores = json.loads(profile.get("epp_summary", "{}"))
    except (json.JSONDecodeError, TypeError):
        old_scores = {}

    # Create pending reassessment
    reassessment_id = write_reassessment(
        nx_user_id=nx_user_id,
        profile_id=int(profile["id"]),
        reassessment_type="quarterly_epp",
        trigger_reason="quarterly_schedule",
        status="pending",
        previous_scores=old_scores,
    )

    # Try Criteria Corp API
    onboarding = get_user_onboarding(nx_user_id)
    criteria_order_id = None
    if onboarding:
        try:
            assessment = json.loads(onboarding.get("assesment_result", "{}"))
            criteria_order_id = assessment.get("orderId")
        except (json.JSONDecodeError, TypeError):
            pass

    new_raw_scores = None
    api_source = "criteria_corp"

    if criteria_order_id:
        new_raw_scores = criteria_corp_fetch_scores(criteria_order_id)

    if new_raw_scores:
        # Parse the API response into normalized scores
        new_scores = parse_epp_scores(json.dumps(new_raw_scores))
    else:
        # Fallback: use most recent mini-assessment data
        api_source = "mini_fallback"
        last_mini = get_last_reassessment(nx_user_id, "mini")
        if last_mini and last_mini.get("new_scores") and last_mini["new_scores"] != "NULL":
            try:
                mini_scores = json.loads(last_mini["new_scores"])
                # Merge mini scores into old scores (mini only covers some traits)
                new_scores = dict(old_scores)
                new_scores.update(mini_scores)
            except (json.JSONDecodeError, TypeError):
                new_scores = old_scores
        else:
            # No fallback data available — complete with no changes
            complete_reassessment(reassessment_id, {
                "path_action": "no_change",
                "drift_detected": False,
                "new_scores": old_scores,
                "result_delta": {"drift_pct": 0, "changed_traits": [], "delta_map": {}},
            })
            return json.dumps({
                "status": "completed_no_data",
                "reassessment_id": reassessment_id,
                "message": "Criteria Corp API unavailable and no mini-assessment fallback data. No changes made.",
                "api_source": api_source,
            })

    # Compute drift
    drift = compute_profile_drift(old_scores, new_scores)

    # Decide action
    drift_detected = drift["drift_pct"] >= DRIFT_THRESHOLD_PCT
    path_action = "reranked" if drift_detected else "no_change"

    result = {
        "status": "completed",
        "reassessment_id": reassessment_id,
        "api_source": api_source,
        "drift": drift,
        "drift_detected": drift_detected,
        "path_action": path_action,
    }

    if drift_detected:
        # Update profile with new scores
        new_profile = update_profile_from_scores(nx_user_id, new_scores, source="quarterly_epp")
        result["new_profile_version"] = int(new_profile["version"])

        # Re-rank recommendations
        rerank_result = rerank_recommendations(
            nx_user_id, new_profile, reassessment_id, "quarterly_epp"
        )
        result["rerank"] = rerank_result

        complete_reassessment(reassessment_id, {
            "new_scores": new_scores,
            "result_delta": drift,
            "drift_detected": True,
            "path_action": "reranked",
            "profile_id": int(new_profile["id"]),
        })
    else:
        complete_reassessment(reassessment_id, {
            "new_scores": new_scores,
            "result_delta": drift,
            "drift_detected": False,
            "path_action": "no_change",
        })
        result["message"] = (
            f"Drift of {drift['drift_pct']}% below threshold of {DRIFT_THRESHOLD_PCT}%. "
            f"No path changes needed."
        )

    return json.dumps(result, indent=2, default=str)


async def _tool_mini_assessment(nx_user_id: int, responses: list[dict]) -> str:
    """Process a mini-assessment submitted mid-lesson.

    Flow:
    1. Validate responses (3-5 questions, each with trait + value)
    2. Compute trait adjustments from responses
    3. Merge adjustments with current profile scores
    4. Compute profile drift
    5. If drift >= threshold, update profile and re-rank
    6. Write reassessment record and path event
    """
    # Validate response count
    min_q, max_q = REASSESSMENT_MINI_QUESTION_COUNT
    if len(responses) < min_q or len(responses) > max_q:
        return json.dumps({
            "error": f"Mini-assessment requires {min_q}-{max_q} responses, got {len(responses)}",
        })

    # Validate each response
    for resp in responses:
        if not resp.get("trait") or resp.get("response_value") is None:
            return json.dumps({"error": f"Invalid response: {resp}. Need trait and response_value."})
        val = float(resp["response_value"])
        if val < 0 or val > 100:
            return json.dumps({"error": f"response_value must be 0-100, got {val}"})

    profile = get_current_profile(nx_user_id)
    if not profile:
        return json.dumps({"error": f"No profile for user {nx_user_id}"})

    try:
        old_scores = json.loads(profile.get("epp_summary", "{}"))
    except (json.JSONDecodeError, TypeError):
        old_scores = {}

    # Compute trait adjustments — mini-assessments nudge scores, not replace them
    # Weighted average: 70% existing score + 30% mini-assessment response
    EXISTING_WEIGHT = 0.7
    MINI_WEIGHT = 0.3

    new_scores = dict(old_scores)
    adjustments = []

    for resp in responses:
        trait = resp["trait"]
        new_val = float(resp["response_value"])
        old_val = old_scores.get(trait, 50.0)
        blended = round(old_val * EXISTING_WEIGHT + new_val * MINI_WEIGHT, 2)
        new_scores[trait] = blended
        adjustments.append({
            "trait": trait,
            "old": old_val,
            "response": new_val,
            "blended": blended,
            "delta": round(blended - old_val, 2),
        })

    # Compute drift
    drift = compute_profile_drift(old_scores, new_scores)
    drift_detected = drift["drift_pct"] >= DRIFT_THRESHOLD_PCT
    path_action = "reranked" if drift_detected else "no_change"

    # Create reassessment record
    reassessment_id = write_reassessment(
        nx_user_id=nx_user_id,
        profile_id=int(profile["id"]),
        reassessment_type="mini",
        trigger_reason="mid_lesson",
        status="completed",
        assessment_data={"responses": responses, "adjustments": adjustments},
        previous_scores=old_scores,
        new_scores=new_scores,
        result_delta=drift,
        drift_detected=drift_detected,
        path_action=path_action,
    )

    result = {
        "status": "completed",
        "reassessment_id": reassessment_id,
        "adjustments": adjustments,
        "drift": drift,
        "drift_detected": drift_detected,
        "path_action": path_action,
    }

    if drift_detected:
        new_profile = update_profile_from_scores(nx_user_id, new_scores, source="mini_assessment")
        result["new_profile_version"] = int(new_profile["version"])

        rerank_result = rerank_recommendations(
            nx_user_id, new_profile, reassessment_id, "mini_assessment"
        )
        result["rerank"] = rerank_result
    else:
        # Still store the new scores even if no re-ranking (they accumulate)
        complete_reassessment(reassessment_id, {
            "new_scores": new_scores,
            "result_delta": drift,
            "drift_detected": False,
            "path_action": "no_change",
        })
        result["message"] = (
            f"Drift of {drift['drift_pct']}% below threshold of {DRIFT_THRESHOLD_PCT}%. "
            f"Scores recorded but no path changes."
        )

    return json.dumps(result, indent=2, default=str)


async def _tool_check_passive_signals(nx_user_id: int) -> str:
    """Check passive engagement signals and trigger reassessment if threshold met.

    Aggregates: backpack saves, lesson ratings, task completions.
    Threshold: 10+ new interactions since last reassessment of any type.
    """
    profile = get_current_profile(nx_user_id)
    if not profile:
        return json.dumps({"error": f"No profile for user {nx_user_id}"})

    # Find the last reassessment of any type
    last = get_last_reassessment(nx_user_id)
    since = last["completed_at"] if last and last.get("completed_at") != "NULL" else "2000-01-01 00:00:00"

    # Count new interactions
    counts = count_new_interactions_since(nx_user_id, since)
    total = sum(counts.values())

    result = {
        "user_id": nx_user_id,
        "since": since,
        "interaction_counts": counts,
        "total_new_interactions": total,
        "threshold": BACKPACK_SIGNAL_THRESHOLD,
        "threshold_met": total >= BACKPACK_SIGNAL_THRESHOLD,
    }

    if total < BACKPACK_SIGNAL_THRESHOLD:
        result["status"] = "below_threshold"
        result["message"] = (
            f"{total} new interactions since last reassessment "
            f"(need {BACKPACK_SIGNAL_THRESHOLD}). No action taken."
        )
        return json.dumps(result, indent=2, default=str)

    # Threshold met — derive trait signals from engagement patterns
    try:
        old_scores = json.loads(profile.get("epp_summary", "{}"))
    except (json.JSONDecodeError, TypeError):
        old_scores = {}

    # Analyze backpack saves to infer trait engagement
    backpacks = get_user_backpacks(nx_user_id)
    ratings = get_user_ratings(nx_user_id)

    # Build trait signal map from content the user engaged with
    trait_engagement: dict[str, list[float]] = {}

    # Check which lessons user saved/rated and what traits those lessons target
    engaged_lesson_ids = set()
    for bp in backpacks:
        lid = bp.get("nx_lesson_id")
        if lid and lid != "NULL":
            engaged_lesson_ids.add(int(lid))
    for r in ratings:
        lid = r.get("nx_lesson_id")
        if lid and lid != "NULL":
            engaged_lesson_ids.add(int(lid))

    for lid in engaged_lesson_ids:
        tags = get_content_tags(nx_lesson_id=lid)
        for tag in tags:
            try:
                trait_tags = json.loads(tag.get("trait_tags", "[]"))
            except (json.JSONDecodeError, TypeError):
                trait_tags = []
            for tt in trait_tags:
                trait = tt.get("trait", "")
                relevance = float(tt.get("relevance_score", 50))
                if trait:
                    trait_engagement.setdefault(trait, []).append(relevance)

    # Adjust scores: traits the user engages with more get a small boost
    PASSIVE_WEIGHT = 0.1  # Light touch — passive signals are weak
    new_scores = dict(old_scores)

    signal_adjustments = []
    for trait, scores in trait_engagement.items():
        if trait in old_scores:
            avg_engagement = sum(scores) / len(scores)
            boost = avg_engagement * PASSIVE_WEIGHT
            old_val = old_scores[trait]
            new_val = min(100, round(old_val + boost, 2))
            new_scores[trait] = new_val
            if abs(new_val - old_val) >= 1:
                signal_adjustments.append({
                    "trait": trait,
                    "old": old_val,
                    "new": new_val,
                    "delta": round(new_val - old_val, 2),
                    "engagement_count": len(scores),
                })

    # Compute drift
    drift = compute_profile_drift(old_scores, new_scores)
    drift_detected = drift["drift_pct"] >= DRIFT_THRESHOLD_PCT
    path_action = "reranked" if drift_detected else "no_change"

    reassessment_id = write_reassessment(
        nx_user_id=nx_user_id,
        profile_id=int(profile["id"]),
        reassessment_type="backpack_derived",
        trigger_reason="passive_signals",
        status="completed",
        assessment_data={
            "interaction_counts": counts,
            "signal_adjustments": signal_adjustments,
            "engaged_lessons": list(engaged_lesson_ids),
        },
        previous_scores=old_scores,
        new_scores=new_scores,
        result_delta=drift,
        drift_detected=drift_detected,
        path_action=path_action,
    )

    result["status"] = "completed"
    result["reassessment_id"] = reassessment_id
    result["signal_adjustments"] = signal_adjustments
    result["drift"] = drift
    result["drift_detected"] = drift_detected
    result["path_action"] = path_action

    if drift_detected:
        new_profile = update_profile_from_scores(nx_user_id, new_scores, source="passive_signals")
        result["new_profile_version"] = int(new_profile["version"])

        rerank_result = rerank_recommendations(
            nx_user_id, new_profile, reassessment_id, "passive_signals"
        )
        result["rerank"] = rerank_result
    else:
        result["message"] = (
            f"Passive signals aggregated. Drift of {drift['drift_pct']}% below "
            f"threshold of {DRIFT_THRESHOLD_PCT}%. Scores recorded, no path changes."
        )

    return json.dumps(result, indent=2, default=str)


async def _tool_reassessment_status(nx_user_id: int) -> str:
    """Get reassessment history and scheduling status for a learner."""
    history = get_reassessment_history(nx_user_id)

    # Parse out key dates
    last_quarterly = get_last_reassessment(nx_user_id, "quarterly_epp")
    last_mini = get_last_reassessment(nx_user_id, "mini")
    last_passive = get_last_reassessment(nx_user_id, "backpack_derived")
    last_any = get_last_reassessment(nx_user_id)

    # Calculate next quarterly due date
    next_quarterly_in = None
    if last_quarterly and last_quarterly.get("completed_at") and last_quarterly["completed_at"] != "NULL":
        from datetime import datetime as dt
        try:
            last_date = dt.strptime(last_quarterly["completed_at"], "%Y-%m-%d %H:%M:%S")
            days_since = (dt.now() - last_date).days
            next_quarterly_in = max(0, REASSESSMENT_QUARTERLY_DAYS - days_since)
        except (ValueError, TypeError):
            pass

    # Check passive signal readiness
    since = last_any["completed_at"] if last_any and last_any.get("completed_at") != "NULL" else "2000-01-01 00:00:00"
    counts = count_new_interactions_since(nx_user_id, since)
    total_interactions = sum(counts.values())

    # Summarize history
    summary = []
    for r in history[:10]:
        drift_data = {}
        if r.get("result_delta") and r["result_delta"] != "NULL":
            try:
                drift_data = json.loads(r["result_delta"])
            except (json.JSONDecodeError, TypeError):
                pass

        summary.append({
            "id": r["id"],
            "type": r["type"],
            "trigger_reason": r["trigger_reason"],
            "status": r["status"],
            "drift_pct": drift_data.get("drift_pct", 0),
            "drift_detected": r.get("drift_detected") == "1",
            "path_action": r.get("path_action"),
            "completed_at": r.get("completed_at"),
        })

    return json.dumps({
        "user_id": nx_user_id,
        "total_reassessments": len(history),
        "completed": sum(1 for r in history if r.get("status") == "completed"),
        "pending": sum(1 for r in history if r.get("status") == "pending"),
        "last_quarterly": {
            "completed_at": last_quarterly.get("completed_at") if last_quarterly else None,
            "next_due_in_days": next_quarterly_in,
        },
        "last_mini": {
            "completed_at": last_mini.get("completed_at") if last_mini else None,
        },
        "last_passive": {
            "completed_at": last_passive.get("completed_at") if last_passive else None,
        },
        "passive_signal_status": {
            "interactions_since_last": total_interactions,
            "threshold": BACKPACK_SIGNAL_THRESHOLD,
            "ready": total_interactions >= BACKPACK_SIGNAL_THRESHOLD,
        },
        "history": summary,
    }, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch tool calls."""
    try:
        if name == "tory_get_learner_data":
            result = await _tool_get_learner_data(int(arguments["nx_user_id"]))
        elif name == "tory_interpret_profile":
            result = await _tool_interpret_profile(int(arguments["nx_user_id"]))
        elif name == "tory_score_content":
            result = await _tool_score_content(
                int(arguments["nx_user_id"]),
                int(arguments.get("max_lessons", 30)),
            )
        elif name == "tory_generate_roadmap":
            result = await _tool_generate_roadmap(
                int(arguments["nx_user_id"]),
                arguments.get("mode", "discovery"),
            )
        elif name == "tory_check_coach_compatibility":
            result = await _tool_check_coach_compatibility(
                int(arguments["nx_user_id"]),
                int(arguments["coach_id"]),
            )
        elif name == "tory_generate_path":
            result = await _tool_generate_path(
                int(arguments["nx_user_id"]),
                int(arguments.get("max_recommendations", 20)),
                arguments.get("coach_id"),
            )
        elif name == "tory_get_roadmap":
            result = await _tool_get_roadmap(int(arguments["nx_user_id"]))
        elif name == "tory_get_progress":
            result = await _tool_get_progress(int(arguments["nx_user_id"]))
        elif name == "tory_list_content_tags":
            result = await _tool_list_content_tags(
                arguments.get("nx_lesson_id"),
                arguments.get("review_status"),
            )
        elif name == "tory_set_pedagogy":
            result = await _tool_set_pedagogy(
                int(arguments["client_id"]),
                arguments["mode"],
                int(arguments.get("gap_ratio", 50)),
                int(arguments.get("strength_ratio", 50)),
            )
        elif name == "tory_dashboard_snapshot":
            result = await _tool_dashboard_snapshot(
                arguments.get("nx_user_id"),
                arguments.get("client_id"),
                arguments.get("department_id"),
            )
        elif name == "tory_schedule_quarterly_epp":
            result = await _tool_schedule_quarterly_epp(
                int(arguments["nx_user_id"]),
            )
        elif name == "tory_mini_assessment":
            result = await _tool_mini_assessment(
                int(arguments["nx_user_id"]),
                arguments["responses"],
            )
        elif name == "tory_check_passive_signals":
            result = await _tool_check_passive_signals(
                int(arguments["nx_user_id"]),
            )
        elif name == "tory_reassessment_status":
            result = await _tool_reassessment_status(
                int(arguments["nx_user_id"]),
            )
        else:
            result = json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        result = json.dumps({"error": str(e)})

    return [TextContent(type="text", text=result)]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def main():
    """Start the Tory Engine MCP server."""
    print("[tory-engine] Starting Tory Engine MCP server...", file=sys.stderr)
    print(f"[tory-engine] Database: {DATABASE}", file=sys.stderr)
    print(f"[tory-engine] Project root: {PROJECT_ROOT}", file=sys.stderr)

    # Verify DB connection
    try:
        _, rows = mysql_query("SELECT COUNT(*) as cnt FROM tory_learner_profiles")
        print(f"[tory-engine] DB connected. Learner profiles: {rows[0]['cnt'] if rows else 0}", file=sys.stderr)
    except Exception as e:
        print(f"[tory-engine] DB connection warning: {e}", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
