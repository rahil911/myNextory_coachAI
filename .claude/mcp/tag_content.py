#!/usr/bin/env python3
"""
Tory Content Tagging Pipeline

Tags lesson content with EPP personality dimensions using Claude Opus.
Multi-pass confidence-gated tagging with checkpoint resumption.

Pipeline stages:
  L1 — Input enrichment: aggregate slide text per lesson from lesson_slides
  L2 — Dimension mapping: Claude Opus structured output (or keyword heuristic fallback)
  L3 — Confidence gating: auto-approve >= 75, needs_review < 50, pending otherwise

Usage:
  # With Claude API (production):
  ANTHROPIC_API_KEY=sk-... python3 tag_content.py

  # Keyword heuristic fallback (no API key needed):
  python3 tag_content.py --mode heuristic

  # Resume from checkpoint:
  python3 tag_content.py --resume

  # Dry run (no DB writes):
  python3 tag_content.py --dry-run

  # Tag specific lessons:
  python3 tag_content.py --lesson-ids 6,7,8
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATABASE = "baap"
QUERY_TIMEOUT = 60
CHECKPOINT_FILE = Path(__file__).parent.parent / "agents/tory-agent/memory/tag_checkpoint.json"

# EPP dimensions
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

ALL_EPP_DIMS = EPP_PERSONALITY_DIMS + EPP_JOBFIT_DIMS

# Confidence thresholds
CONFIDENCE_AUTO_APPROVE = 75
CONFIDENCE_NEEDS_REVIEW = 50

# Rate limiting
API_DELAY_SECONDS = 1.0
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Keyword maps for heuristic tagging
# ---------------------------------------------------------------------------

DIMENSION_KEYWORDS: dict[str, list[str]] = {
    "Achievement": [
        "goal", "accomplish", "success", "achieve", "target", "outcome",
        "result", "milestone", "ambition", "excel", "perform", "deliver",
        "complete", "finish", "win", "progress", "growth",
    ],
    "Motivation": [
        "motivat", "drive", "purpose", "passion", "inspire", "energy",
        "commit", "dedicat", "engaged", "determined", "enthus",
        "eager", "aspire", "fuel",
    ],
    "Competitiveness": [
        "compet", "rival", "outperform", "beat", "ranking", "benchmark",
        "edge", "advantage", "race", "challenge",
    ],
    "Managerial": [
        "manage", "lead", "delegate", "supervis", "direct", "oversee",
        "organiz", "coordinat", "team lead", "authority", "decision",
        "strateg", "vision",
    ],
    "Assertiveness": [
        "assert", "speak up", "boundary", "stand up", "say no", "voice",
        "express", "advocate", "confident", "firm", "direct",
        "negotiat", "push back",
    ],
    "Extroversion": [
        "social", "network", "connect", "interact", "outgoing",
        "collaborat", "communicat", "relationship", "engage with",
        "people", "team", "group", "together",
    ],
    "Cooperativeness": [
        "cooperat", "collaborat", "team", "together", "support",
        "help", "share", "partner", "assist", "collective", "harmony",
        "compromise", "agree",
    ],
    "Patience": [
        "patient", "wait", "calm", "steady", "persever", "endur",
        "tolerat", "accept", "peace", "mindful", "slow",
        "gradual", "step by step",
    ],
    "SelfConfidence": [
        "self-confiden", "believe in yourself", "self-esteem", "self-worth",
        "capable", "trust yourself", "inner strength", "empower",
        "self-assur", "courag", "brave", "bold",
    ],
    "Conscientiousness": [
        "conscientious", "detail", "careful", "thorough", "disciplin",
        "organiz", "plan", "systematic", "diligent", "responsib",
        "reliable", "consistent", "accountab", "precise",
    ],
    "Openness": [
        "open", "curious", "creative", "innovat", "new idea",
        "explor", "experiment", "adapt", "flexible", "imagin",
        "diverse", "perspective", "learn",
    ],
    "Stability": [
        "stable", "steady", "consistent", "reliable", "predictab",
        "even-tempered", "ground", "balanc", "equilibrium", "anchor",
        "routine", "secure",
    ],
    "StressTolerance": [
        "stress", "pressure", "resilien", "cope", "overwhelm",
        "anxiet", "burnout", "wellbeing", "well-being", "mental health",
        "self-care", "recover", "bounce back", "tough",
    ],
    "CustomerService": [
        "customer", "client", "service", "satisf", "feedback",
        "listen", "empathy", "respond", "resolve", "complaint",
        "expectation", "relation",
    ],
    "Manager": [
        "manage", "lead", "boss", "supervisor", "mentor", "coach",
        "develop others", "feedback", "performance review", "team",
        "delegation",
    ],
    "Sales": [
        "sell", "persuad", "influenc", "pitch", "negotiat", "close",
        "prospect", "revenue", "target", "conversion", "outreach",
    ],
    "Analyst": [
        "analy", "data", "logic", "reason", "problem-solv", "critical think",
        "assess", "evaluat", "research", "insight", "pattern",
    ],
    "Accounting": [
        "account", "financ", "budget", "audit", "number", "calcul",
        "fiscal", "cost", "expense", "report",
    ],
    "AdminAsst": [
        "admin", "organiz", "schedul", "filing", "coordinat",
        "support", "office", "clerical", "calendar", "document",
    ],
    "BankTeller": [
        "transact", "cash", "deposit", "withdraw", "bank",
        "financial", "accuracy", "count", "verify",
    ],
    "Collections": [
        "collect", "payment", "overdue", "debt", "recover",
        "follow-up", "negotiat", "resolv",
    ],
    "FrontDesk": [
        "reception", "greet", "welcome", "front desk", "check-in",
        "visitor", "phone", "first impression",
    ],
    "MedicalAsst": [
        "medical", "health", "patient", "clinical", "care",
        "procedure", "vital", "symptom",
    ],
    "Production": [
        "produc", "manufactur", "assembl", "quality", "efficien",
        "output", "process", "standard", "safety", "workflow",
    ],
    "Programmer": [
        "program", "code", "software", "develop", "technical",
        "system", "debug", "algorithm", "automat", "engineer",
    ],
}


# ---------------------------------------------------------------------------
# MySQL helpers
# ---------------------------------------------------------------------------


def mysql_query_xml(sql: str) -> list[dict]:
    """Execute query and parse XML output (handles multiline content)."""
    result = subprocess.run(
        ["mysql", DATABASE, "--xml", "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL error: {result.stderr.strip()}")

    if not result.stdout.strip():
        return []

    root = ET.fromstring(result.stdout)
    rows = []
    for row_el in root.findall("row"):
        row = {}
        for field in row_el.findall("field"):
            name = field.get("name")
            is_null = field.get("{http://www.w3.org/2001/XMLSchema-instance}nil")
            row[name] = None if is_null == "true" else (field.text or "")
        rows.append(row)
    return rows


def mysql_write(sql: str) -> bool:
    """Execute a write query. Returns success boolean."""
    result = subprocess.run(
        ["mysql", DATABASE, "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        print(f"  [ERROR] MySQL write: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def escape_sql(value: str | None) -> str:
    """Escape a string value for safe SQL insertion."""
    if value is None:
        return "NULL"
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r")
    escaped = escaped.replace("\x00", "").replace("\x1a", "")
    return f"'{escaped}'"


# ---------------------------------------------------------------------------
# L1: Input Enrichment
# ---------------------------------------------------------------------------


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fix_unicode_escapes(text: str) -> str:
    """Fix malformed unicode like u2019 -> proper apostrophe."""
    def replace_unicode(m):
        try:
            return chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return m.group(0)
    return re.sub(r'u([0-9a-fA-F]{4})', replace_unicode, text)


def extract_text_from_slide(slide_content: str | None) -> str:
    """Extract readable text from slide_content JSON."""
    if not slide_content:
        return ""

    # Fix unicode escapes before parsing
    content = fix_unicode_escapes(slide_content)

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        # If JSON parse fails, try to extract text directly
        return strip_html(content)

    if not isinstance(data, dict):
        return str(data)

    text_parts = []

    # Extract from common fields
    text_fields = [
        "slide_title", "content", "short_description", "greetings",
        "message", "message_1", "message_2", "card_title", "card_content",
        "appreciation", "advisor_content", "note",
    ]
    for field in text_fields:
        val = data.get(field)
        if val and isinstance(val, str):
            text_parts.append(strip_html(val))

    # Extract from questions arrays
    questions = data.get("questions", [])
    if isinstance(questions, list):
        for q in questions:
            if isinstance(q, str):
                text_parts.append(strip_html(q))
            elif isinstance(q, dict):
                for k in ("question", "title", "answer"):
                    if k in q and isinstance(q[k], str):
                        text_parts.append(strip_html(q[k]))

    # Extract from decision arrays
    decisions = data.get("decision", [])
    if isinstance(decisions, list):
        for d in decisions:
            if isinstance(d, dict):
                for k in ("title", "content"):
                    if k in d and isinstance(d[k], str):
                        text_parts.append(strip_html(d[k]))

    # Extract from examples
    examples = data.get("examples", [])
    if isinstance(examples, list):
        for group in examples:
            if isinstance(group, list):
                for ex in group:
                    if isinstance(ex, str):
                        text_parts.append(strip_html(ex))

    # Extract bulb examples
    bulb = data.get("bulbExamples", {})
    if isinstance(bulb, dict):
        for side in bulb.values():
            if isinstance(side, list):
                for ex in side:
                    if isinstance(ex, str):
                        text_parts.append(strip_html(ex))

    # Heads up
    heads_up = data.get("heads_up")
    if heads_up and isinstance(heads_up, str):
        text_parts.append(strip_html(heads_up))

    return " ".join(text_parts)


def build_lesson_mapping() -> dict[int, int]:
    """Build lesson_detail_id -> nx_lesson_id mapping from backpacks + ratings."""
    mapping = {}

    # From backpacks (primary source, most data)
    rows = mysql_query_xml(
        "SELECT DISTINCT nx_lesson_id, lesson_detail_id "
        "FROM backpacks WHERE deleted_at IS NULL "
        "AND nx_lesson_id IS NOT NULL AND lesson_detail_id IS NOT NULL"
    )
    for r in rows:
        ld_id = int(r["lesson_detail_id"])
        nl_id = int(r["nx_lesson_id"])
        mapping[ld_id] = nl_id

    # From ratings (fills gaps)
    rows = mysql_query_xml(
        "SELECT DISTINCT nx_lesson_id, lesson_detail_id "
        "FROM nx_user_ratings WHERE deleted_at IS NULL "
        "AND nx_lesson_id IS NOT NULL AND lesson_detail_id IS NOT NULL"
    )
    for r in rows:
        ld_id = int(r["lesson_detail_id"])
        nl_id = int(r["nx_lesson_id"])
        if ld_id not in mapping:
            mapping[ld_id] = nl_id

    return mapping


def get_lesson_content(lesson_detail_id: int) -> str:
    """Aggregate all slide text for a lesson."""
    rows = mysql_query_xml(
        f"SELECT id, type, slide_content FROM lesson_slides "
        f"WHERE lesson_detail_id = {int(lesson_detail_id)} "
        f"AND deleted_at IS NULL ORDER BY priority ASC, id ASC"
    )

    texts = []
    for row in rows:
        text = extract_text_from_slide(row.get("slide_content"))
        if text:
            slide_type = row.get("type", "unknown")
            texts.append(f"[{slide_type}] {text}")

    return "\n".join(texts)


def get_all_lesson_detail_ids() -> list[int]:
    """Get all distinct lesson_detail_ids that have content."""
    rows = mysql_query_xml(
        "SELECT DISTINCT lesson_detail_id FROM lesson_slides "
        "WHERE deleted_at IS NULL AND lesson_detail_id IS NOT NULL "
        "ORDER BY lesson_detail_id ASC"
    )
    return [int(r["lesson_detail_id"]) for r in rows]


# ---------------------------------------------------------------------------
# L2: Dimension Mapping
# ---------------------------------------------------------------------------


def tag_with_claude(lesson_text: str, pass_num: int = 1) -> dict:
    """Call Claude Opus API for EPP dimension tagging.

    Returns: {"tags": [...], "difficulty": int, "learning_style": str,
              "prerequisites": [...]}
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set")

    if pass_num == 1:
        system_prompt = (
            "You are an expert in personality psychology and the Employee Personality Profile (EPP) "
            "assessment by Criteria Corp. Your task is to analyze lesson content from a coaching "
            "platform and determine which EPP personality dimensions the lesson develops or assesses.\n\n"
            "For each relevant dimension, provide:\n"
            "- trait: the dimension name (exact match from the list)\n"
            "- relevance_score: 0-100 indicating how strongly the lesson targets this dimension\n"
            "- direction: 'builds' if the lesson develops/strengthens this trait, "
            "'challenges' if it tests or stretches this trait\n\n"
            "Also assess:\n"
            "- difficulty: 1-5 scale (1=introductory, 5=advanced)\n"
            "- learning_style: one of visual, reflective, active, theoretical, blended\n"
            "- prerequisites: list of traits with minimum scores needed (can be empty)"
        )
    else:
        system_prompt = (
            "You are a learning path designer specializing in personality development. "
            "Given coaching lesson content, determine which personality traits from the "
            "EPP (Employee Personality Profile) assessment would benefit most from this material.\n\n"
            "Think about: What personality dimensions does this lesson exercise? "
            "What traits would improve if a learner engaged deeply with this content?\n\n"
            "For each relevant dimension, provide:\n"
            "- trait: the dimension name (exact match from the list)\n"
            "- relevance_score: 0-100 indicating relevance\n"
            "- direction: 'builds' or 'challenges'\n\n"
            "Also assess difficulty (1-5), learning_style, and prerequisites."
        )

    dimensions_list = ", ".join(ALL_EPP_DIMS)
    user_prompt = (
        f"EPP Dimensions: {dimensions_list}\n\n"
        f"Lesson Content:\n{lesson_text[:8000]}\n\n"  # Truncate to avoid token limits
        "Respond with valid JSON only, no markdown. Schema:\n"
        '{"tags": [{"trait": "...", "relevance_score": N, "direction": "builds|challenges"}], '
        '"difficulty": N, "learning_style": "...", '
        '"prerequisites": [{"trait": "...", "min_score": N}]}'
    )

    # Call via curl (no SDK dependency)
    payload = json.dumps({
        "model": "claude-opus-4-20250514",
        "max_tokens": 2000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    })

    for attempt in range(MAX_RETRIES):
        try:
            result = subprocess.run(
                [
                    "curl", "-s", "-X", "POST",
                    "https://api.anthropic.com/v1/messages",
                    "-H", "content-type: application/json",
                    "-H", f"x-api-key: {api_key}",
                    "-H", "anthropic-version: 2023-06-01",
                    "-d", payload,
                ],
                capture_output=True, text=True, timeout=120,
            )

            response = json.loads(result.stdout)

            if "error" in response:
                print(f"  [WARN] API error: {response['error']}", file=sys.stderr)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise Exception(f"API error: {response['error']}")

            # Extract text content
            content_blocks = response.get("content", [])
            text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    text += block.get("text", "")

            # Parse JSON from response
            # Strip markdown code fences if present
            text = re.sub(r'^```json\s*', '', text.strip())
            text = re.sub(r'\s*```$', '', text.strip())
            return json.loads(text)

        except subprocess.TimeoutExpired:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        except json.JSONDecodeError as e:
            print(f"  [WARN] JSON parse error (attempt {attempt+1}): {e}", file=sys.stderr)
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            # Return empty result on persistent parse failure
            return {"tags": [], "difficulty": 3, "learning_style": "blended", "prerequisites": []}

    return {"tags": [], "difficulty": 3, "learning_style": "blended", "prerequisites": []}


def tag_with_heuristic(lesson_text: str, pass_num: int = 1) -> dict:
    """Keyword-based heuristic tagging (fallback when no API key).

    Uses different keyword weighting for pass1 vs pass2 to simulate
    two-pass diversity.
    """
    text_lower = lesson_text.lower()
    word_count = len(text_lower.split())

    tags = []
    for dim, keywords in DIMENSION_KEYWORDS.items():
        hit_count = 0
        matched_keywords = []
        for kw in keywords:
            # Count occurrences (case-insensitive)
            count = len(re.findall(re.escape(kw.lower()), text_lower))
            if count > 0:
                hit_count += count
                matched_keywords.append(kw)

        if not matched_keywords:
            continue

        # Compute relevance score
        # Base: proportion of keywords matched
        keyword_coverage = len(matched_keywords) / len(keywords)
        # Density: hits per 100 words
        density = min(1.0, hit_count / max(1, word_count) * 20)
        # Combined score
        raw_score = (keyword_coverage * 0.6 + density * 0.4) * 100

        # Pass variation: pass2 uses slightly different weights
        if pass_num == 2:
            raw_score = (keyword_coverage * 0.4 + density * 0.6) * 100

        # Clamp and round
        score = max(5, min(95, round(raw_score)))

        if score >= 15:  # Minimum relevance threshold
            direction = "builds"
            # Some content types are more "challenging"
            if any(kw in text_lower for kw in ["test", "quiz", "evaluate", "assess"]):
                direction = "challenges"

            tags.append({
                "trait": dim,
                "relevance_score": score,
                "direction": direction,
            })

    # Sort by relevance descending, keep top 8
    tags.sort(key=lambda x: x["relevance_score"], reverse=True)
    tags = tags[:8]

    # Estimate difficulty from text complexity
    avg_word_len = sum(len(w) for w in text_lower.split()) / max(1, word_count)
    if avg_word_len > 6:
        difficulty = 4
    elif avg_word_len > 5:
        difficulty = 3
    elif word_count < 100:
        difficulty = 2
    else:
        difficulty = 3

    # Infer learning style from slide types
    learning_style = "blended"
    if "video" in text_lower:
        learning_style = "visual"
    elif "question" in text_lower or "exercise" in text_lower:
        learning_style = "active"
    elif "reflect" in text_lower or "think about" in text_lower:
        learning_style = "reflective"

    return {
        "tags": tags,
        "difficulty": difficulty,
        "learning_style": learning_style,
        "prerequisites": [],
    }


# ---------------------------------------------------------------------------
# L3: Confidence Gating & Agreement
# ---------------------------------------------------------------------------


def compute_agreement(pass1_tags: list[dict], pass2_tags: list[dict]) -> int:
    """Compute agreement score (0-100) between two passes using Jaccard similarity."""
    if not pass1_tags and not pass2_tags:
        return 100  # Both empty = perfect agreement
    if not pass1_tags or not pass2_tags:
        return 0

    set1 = {t["trait"] for t in pass1_tags}
    set2 = {t["trait"] for t in pass2_tags}

    intersection = set1 & set2
    union = set1 | set2

    if not union:
        return 100

    jaccard = len(intersection) / len(union)

    # Also compare relevance scores for shared traits
    score_agreement = 0
    if intersection:
        map1 = {t["trait"]: t["relevance_score"] for t in pass1_tags}
        map2 = {t["trait"]: t["relevance_score"] for t in pass2_tags}
        diffs = []
        for trait in intersection:
            s1 = map1.get(trait, 0)
            s2 = map2.get(trait, 0)
            diffs.append(1 - abs(s1 - s2) / 100)
        score_agreement = sum(diffs) / len(diffs)
    else:
        score_agreement = 0

    # Weighted: 60% trait overlap, 40% score agreement
    return round((jaccard * 0.6 + score_agreement * 0.4) * 100)


def merge_tags(pass1_tags: list[dict], pass2_tags: list[dict]) -> list[dict]:
    """Merge two passes into final trait_tags by averaging scores."""
    trait_map: dict[str, dict] = {}

    for t in pass1_tags:
        trait = t["trait"]
        trait_map[trait] = {
            "trait": trait,
            "relevance_score": t["relevance_score"],
            "direction": t["direction"],
            "count": 1,
        }

    for t in pass2_tags:
        trait = t["trait"]
        if trait in trait_map:
            # Average the scores
            existing = trait_map[trait]
            existing["relevance_score"] = round(
                (existing["relevance_score"] + t["relevance_score"]) / 2
            )
            existing["count"] += 1
        else:
            trait_map[trait] = {
                "trait": trait,
                "relevance_score": t["relevance_score"],
                "direction": t["direction"],
                "count": 1,
            }

    # Boost confidence for traits found in both passes
    merged = []
    for t in trait_map.values():
        merged.append({
            "trait": t["trait"],
            "relevance_score": t["relevance_score"],
            "direction": t["direction"],
        })

    merged.sort(key=lambda x: x["relevance_score"], reverse=True)
    return merged


def compute_confidence(
    pass_agreement: int,
    tag_count: int,
    text_length: int,
    mode: str,
) -> int:
    """Compute overall confidence score (0-100)."""
    # Base from agreement between passes
    base = pass_agreement * 0.5

    # Tag quality: having 3-6 tags is ideal
    if 3 <= tag_count <= 6:
        tag_bonus = 20
    elif 1 <= tag_count <= 8:
        tag_bonus = 10
    else:
        tag_bonus = 0

    # Content quality: more text = more signal
    if text_length > 500:
        content_bonus = 20
    elif text_length > 200:
        content_bonus = 10
    else:
        content_bonus = 5

    # Mode penalty: heuristic gets a confidence penalty
    mode_penalty = 15 if mode == "heuristic" else 0

    confidence = round(base + tag_bonus + content_bonus - mode_penalty)
    return max(0, min(100, confidence))


def determine_review_status(confidence: int) -> str:
    """Determine review status from confidence score."""
    if confidence >= CONFIDENCE_AUTO_APPROVE:
        return "approved"
    elif confidence < CONFIDENCE_NEEDS_REVIEW:
        return "needs_review"
    else:
        return "pending"


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


def load_checkpoint() -> dict:
    """Load checkpoint state."""
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {"completed": [], "failed": [], "last_updated": None}
    return {"completed": [], "failed": [], "last_updated": None}


def save_checkpoint(state: dict):
    """Save checkpoint state."""
    state["last_updated"] = datetime.now().isoformat()
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# DB Write
# ---------------------------------------------------------------------------


def insert_content_tag(
    nx_lesson_id: int,
    lesson_detail_id: int,
    trait_tags: list[dict],
    difficulty: int,
    learning_style: str,
    prerequisites: list[dict],
    confidence: int,
    review_status: str,
    pass1_tags: list[dict],
    pass2_tags: list[dict],
    pass_agreement: int,
    dry_run: bool = False,
) -> bool:
    """Insert a row into tory_content_tags."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sql = (
        f"INSERT INTO tory_content_tags "
        f"(nx_lesson_id, lesson_detail_id, trait_tags, difficulty, learning_style, "
        f"prerequisites, confidence, review_status, pass1_tags, pass2_tags, "
        f"pass_agreement, created_at, updated_at) VALUES ("
        f"{int(nx_lesson_id)}, {int(lesson_detail_id)}, "
        f"{escape_sql(json.dumps(trait_tags))}, "
        f"{int(difficulty)}, "
        f"{escape_sql(learning_style)}, "
        f"{escape_sql(json.dumps(prerequisites))}, "
        f"{int(confidence)}, "
        f"{escape_sql(review_status)}, "
        f"{escape_sql(json.dumps(pass1_tags))}, "
        f"{escape_sql(json.dumps(pass2_tags))}, "
        f"{int(pass_agreement)}, "
        f"'{now}', '{now}')"
    )

    if dry_run:
        print(f"  [DRY RUN] Would insert: nx_lesson_id={nx_lesson_id}, "
              f"confidence={confidence}, status={review_status}, "
              f"tags={len(trait_tags)}")
        return True

    return mysql_write(sql)


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------


def tag_lesson(
    lesson_detail_id: int,
    nx_lesson_id: int,
    mode: str = "heuristic",
    dry_run: bool = False,
) -> dict:
    """Run the full tagging pipeline for one lesson.

    Returns: {success, confidence, review_status, tag_count, error}
    """
    # L1: Extract content
    text = get_lesson_content(lesson_detail_id)
    if not text or len(text.strip()) < 20:
        return {
            "success": False,
            "error": f"Insufficient content for lesson_detail_id={lesson_detail_id} "
                     f"(text length: {len(text)})",
        }

    # L2: Two-pass tagging
    tag_fn = tag_with_claude if mode == "claude" else tag_with_heuristic

    try:
        result1 = tag_fn(text, pass_num=1)
    except Exception as e:
        return {"success": False, "error": f"Pass 1 failed: {e}"}

    if mode == "claude":
        time.sleep(API_DELAY_SECONDS)

    try:
        result2 = tag_fn(text, pass_num=2)
    except Exception as e:
        # If pass 2 fails, use pass 1 only with lower confidence
        result2 = {"tags": [], "difficulty": 3, "learning_style": "blended", "prerequisites": []}

    pass1_tags = result1.get("tags", [])
    pass2_tags = result2.get("tags", [])

    # Validate tag structure
    for tags in [pass1_tags, pass2_tags]:
        for t in tags:
            t["trait"] = str(t.get("trait", ""))
            t["relevance_score"] = max(0, min(100, int(t.get("relevance_score", 0))))
            if t["direction"] not in ("builds", "challenges"):
                t["direction"] = "builds"

    # Filter to valid EPP dimensions only
    valid_dims = set(ALL_EPP_DIMS)
    pass1_tags = [t for t in pass1_tags if t["trait"] in valid_dims]
    pass2_tags = [t for t in pass2_tags if t["trait"] in valid_dims]

    # L3: Agreement and confidence
    agreement = compute_agreement(pass1_tags, pass2_tags)
    merged = merge_tags(pass1_tags, pass2_tags)

    confidence = compute_confidence(agreement, len(merged), len(text), mode)
    review_status = determine_review_status(confidence)

    # Pick best difficulty and learning style
    difficulty = result1.get("difficulty", 3)
    learning_style = result1.get("learning_style", "blended")
    prerequisites = result1.get("prerequisites", [])

    # Validate
    if not isinstance(difficulty, int) or difficulty < 1 or difficulty > 5:
        difficulty = 3
    if learning_style not in ("visual", "reflective", "active", "theoretical", "blended"):
        learning_style = "blended"

    # Insert
    success = insert_content_tag(
        nx_lesson_id=nx_lesson_id,
        lesson_detail_id=lesson_detail_id,
        trait_tags=merged,
        difficulty=difficulty,
        learning_style=learning_style,
        prerequisites=prerequisites,
        confidence=confidence,
        review_status=review_status,
        pass1_tags=pass1_tags,
        pass2_tags=pass2_tags,
        pass_agreement=agreement,
        dry_run=dry_run,
    )

    return {
        "success": success,
        "confidence": confidence,
        "review_status": review_status,
        "tag_count": len(merged),
        "pass_agreement": agreement,
        "top_traits": [t["trait"] for t in merged[:3]],
    }


def run_pipeline(
    mode: str = "heuristic",
    resume: bool = True,
    dry_run: bool = False,
    lesson_ids: list[int] | None = None,
):
    """Run the full content tagging pipeline."""
    print(f"\n{'='*60}")
    print(f"Tory Content Tagging Pipeline")
    print(f"Mode: {mode} | Resume: {resume} | Dry Run: {dry_run}")
    print(f"{'='*60}\n")

    # Build lesson mapping
    print("[1/4] Building lesson_detail_id -> nx_lesson_id mapping...")
    mapping = build_lesson_mapping()
    print(f"  Found {len(mapping)} lesson mappings (backpacks + ratings)")

    # Get all lesson_detail_ids
    all_ld_ids = get_all_lesson_detail_ids()
    print(f"  Total lesson_detail_ids with content: {len(all_ld_ids)}")

    # Filter to only lessons with nx_lesson_id mapping
    taggable = [(ld_id, mapping[ld_id]) for ld_id in all_ld_ids if ld_id in mapping]
    unmapped = [ld_id for ld_id in all_ld_ids if ld_id not in mapping]
    print(f"  Taggable (have nx_lesson_id): {len(taggable)}")
    if unmapped:
        print(f"  Skipping {len(unmapped)} unmapped lesson_detail_ids: {unmapped}")

    # Filter by specific lesson_ids if provided
    if lesson_ids:
        taggable = [(ld, nl) for ld, nl in taggable if nl in lesson_ids]
        print(f"  Filtered to {len(taggable)} lessons by --lesson-ids")

    # Load checkpoint
    checkpoint = load_checkpoint() if resume else {"completed": [], "failed": []}
    completed_set = set(checkpoint.get("completed", []))
    print(f"\n[2/4] Checkpoint: {len(completed_set)} lessons already tagged")

    # Check for existing tags in DB
    existing_rows = mysql_query_xml(
        "SELECT DISTINCT nx_lesson_id FROM tory_content_tags WHERE deleted_at IS NULL"
    )
    existing_ids = {int(r["nx_lesson_id"]) for r in existing_rows}
    print(f"  Existing tags in DB: {len(existing_ids)}")

    # Filter out already completed
    pending = [
        (ld, nl) for ld, nl in taggable
        if nl not in completed_set and nl not in existing_ids
    ]
    print(f"  Remaining to tag: {len(pending)}")

    if not pending:
        print("\n[DONE] All lessons already tagged!")
        return

    # Process
    print(f"\n[3/4] Tagging {len(pending)} lessons...\n")
    stats = {"success": 0, "failed": 0, "auto_approved": 0, "needs_review": 0, "pending": 0}

    for i, (ld_id, nl_id) in enumerate(pending, 1):
        print(f"  [{i}/{len(pending)}] lesson_detail_id={ld_id} -> nx_lesson_id={nl_id} ", end="")

        result = tag_lesson(ld_id, nl_id, mode=mode, dry_run=dry_run)

        if result["success"]:
            stats["success"] += 1
            status = result["review_status"]
            stats[status if status in stats else "pending"] += 1
            checkpoint.setdefault("completed", []).append(nl_id)
            print(f"OK  conf={result['confidence']} status={result['review_status']} "
                  f"tags={result['tag_count']} top={result.get('top_traits', [])}")
        else:
            stats["failed"] += 1
            checkpoint.setdefault("failed", []).append(nl_id)
            print(f"FAIL  {result.get('error', 'unknown')}")

        # Save checkpoint every 10 lessons
        if i % 10 == 0:
            save_checkpoint(checkpoint)

        # Rate limit for API mode
        if mode == "claude":
            time.sleep(API_DELAY_SECONDS)

    # Final checkpoint
    save_checkpoint(checkpoint)

    # Summary
    print(f"\n[4/4] Summary")
    print(f"{'='*60}")
    print(f"  Total processed: {stats['success'] + stats['failed']}")
    print(f"  Success: {stats['success']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Auto-approved (conf >= {CONFIDENCE_AUTO_APPROVE}): {stats.get('approved', 0)}")
    print(f"  Pending review: {stats.get('pending', 0)}")
    print(f"  Needs review (conf < {CONFIDENCE_NEEDS_REVIEW}): {stats.get('needs_review', 0)}")
    print(f"  Checkpoint saved: {CHECKPOINT_FILE}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Tory Content Tagging Pipeline")
    parser.add_argument(
        "--mode", choices=["claude", "heuristic"], default=None,
        help="Tagging mode: 'claude' (API) or 'heuristic' (keyword-based). "
             "Default: claude if ANTHROPIC_API_KEY is set, else heuristic.",
    )
    parser.add_argument(
        "--resume", action="store_true", default=True,
        help="Resume from checkpoint (default: True)",
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Start fresh, ignoring checkpoint",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be done without writing to DB",
    )
    parser.add_argument(
        "--lesson-ids", type=str, default=None,
        help="Comma-separated nx_lesson_ids to tag (e.g., 6,7,8)",
    )

    args = parser.parse_args()

    # Auto-detect mode
    mode = args.mode
    if mode is None:
        if os.environ.get("ANTHROPIC_API_KEY"):
            mode = "claude"
            print("Auto-detected ANTHROPIC_API_KEY — using Claude API mode")
        else:
            mode = "heuristic"
            print("No ANTHROPIC_API_KEY — using heuristic fallback mode")

    resume = not args.no_resume
    lesson_ids = None
    if args.lesson_ids:
        lesson_ids = [int(x.strip()) for x in args.lesson_ids.split(",")]

    run_pipeline(mode=mode, resume=resume, dry_run=args.dry_run, lesson_ids=lesson_ids)


if __name__ == "__main__":
    main()
