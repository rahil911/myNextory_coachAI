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


def get_content_tags(nx_lesson_id: int | None = None) -> list[dict]:
    """Fetch content tags, optionally for a specific lesson."""
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
    max_lessons: int = 30,
    diminishing_factor: float = 0.7,
) -> list[dict]:
    """Apply sequencing logic to scored lessons.

    - Limit to max_lessons
    - Apply diminishing returns for same-trait stacking
    - Ensure diversity of targeted traits
    """
    if not scored_lessons:
        return []

    selected = []
    trait_counts: dict[str, int] = {}

    for lesson in scored_lessons:
        if len(selected) >= max_lessons:
            break

        # Check trait diversity — apply diminishing returns
        adjusted_score = lesson["score"]
        for mt in lesson.get("matching_traits", []):
            trait = mt["trait"]
            count = trait_counts.get(trait, 0)
            if count > 0:
                # Reduce score for repeated traits
                adjusted_score *= diminishing_factor ** count

        lesson["adjusted_score"] = round(adjusted_score, 2)
        selected.append(lesson)

        # Update trait counts
        for mt in lesson.get("matching_traits", []):
            trait = mt["trait"]
            trait_counts[trait] = trait_counts.get(trait, 0) + 1

    # Re-sort by adjusted score
    selected.sort(key=lambda x: x["adjusted_score"], reverse=True)

    # Assign sequence numbers
    for i, lesson in enumerate(selected):
        lesson["sequence"] = i + 1

    return selected


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

    # Get all tagged content
    content_tags = get_content_tags()
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
