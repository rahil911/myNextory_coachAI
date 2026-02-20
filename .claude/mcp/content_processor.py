#!/usr/bin/env python3
"""
Tory Content Processor — 15-Field Extraction Pipeline

Replaces tag_content.py as the primary content tagging mechanism.
Processes lessons through Claude Opus to extract 15 structured fields per lesson,
then embeds RAG chunks into FAISS for semantic retrieval.

5-Stage Pipeline:
  L1 — Text Extraction: aggregate slide text with type annotations
  L2 — Claude Opus Single-Call: extract all 15 fields in one structured call
  L2b — Second Pass (agreement scoring): different prompt, compare results
  L3 — Confidence Gating: auto-approve >= 75, needs_review < 50
  L4 — Embed RAG Chunks: OpenAI text-embedding-3-small → FAISS
  L5 — Store in DB: write to tory_content_tags + tory_rag_chunks

Usage (as MCP tools registered in tory_engine.py):
  - tory_process_content(lesson_detail_id)  — single lesson
  - tory_process_all_content()              — batch all unprocessed

Rate limiting: max 5 Opus calls/min.
Cost tracking: log tokens per call.
"""

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

# Rate limiting: 5 Opus calls per minute (each lesson = 2 calls)
OPUS_RPM_LIMIT = 5
OPUS_CALL_INTERVAL = 60.0 / OPUS_RPM_LIMIT  # 12 seconds between calls

# Confidence thresholds
CONFIDENCE_AUTO_APPROVE = 75
CONFIDENCE_NEEDS_REVIEW = 50

# API retry config
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds, exponential backoff

# Cost tracking (per 1K tokens)
OPUS_INPUT_PRICE_PER_1K = 0.015
OPUS_OUTPUT_PRICE_PER_1K = 0.075
EMBEDDING_PRICE_PER_1K = 0.00002

# EPP dimensions (must match tory_engine.py and epp-dimensions.md)
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

# ---------------------------------------------------------------------------
# EPP Dimension Descriptions (embedded in Opus prompt for grounding)
# Source: .claude/knowledge/epp-dimensions.md
# ---------------------------------------------------------------------------

EPP_DIMENSION_DESCRIPTIONS = """
## Personality Dimensions (13)

- Achievement: Drive to accomplish goals and exceed standards. High scorers set ambitious targets.
- Motivation: Internal drive and energy level. High scorers are self-starters who initiate action.
- Competitiveness: Desire to outperform others and win. High scorers thrive in competitive environments.
- Managerial: Comfort with leading, directing, and managing others. High scorers naturally take charge.
- Assertiveness: Willingness to speak up, push back, and advocate for oneself. High scorers are direct.
- Extroversion: Preference for social interaction. High scorers are energized by groups.
- Cooperativeness: Orientation toward teamwork, harmony, and helping others.
- Patience: Tolerance for delay, pace of work, and frustration threshold.
- SelfConfidence: Trust in one's own abilities and judgment. Low scorers experience imposter feelings.
- Conscientiousness: Attention to detail, organization, and rule-following.
- Openness: Receptivity to new ideas, change, and unconventional approaches.
- Stability: Emotional evenness and resilience to stress.
- StressTolerance: Ability to function effectively under pressure and high-stakes situations.

## Job Fit Dimensions (12)

- Accounting: Success in detail-oriented financial roles (Conscientiousness, Stability)
- AdminAsst: Success in administrative support roles (Cooperativeness, Conscientiousness)
- Analyst: Success in analytical/research roles (Achievement, Conscientiousness, Openness)
- BankTeller: Success in transaction processing (Conscientiousness, Patience, Stability)
- Collections: Success in debt collection/negotiation (Assertiveness, StressTolerance)
- CustomerService: Success in customer-facing roles (Cooperativeness, Patience, Stability)
- FrontDesk: Success in reception/greeting roles (Extroversion, Cooperativeness)
- Manager: Success in people management (Assertiveness, Achievement, Managerial)
- MedicalAsst: Success in healthcare support (Cooperativeness, Conscientiousness, StressTolerance)
- Production: Success in manufacturing/operations (Conscientiousness, Patience)
- Programmer: Success in software development (Achievement, Conscientiousness, low Extroversion)
- Sales: Success in sales roles (Extroversion, Competitiveness, Assertiveness)

## Content Mapping Directions
- builds: Lesson directly targets/develops this trait
- leverages: Lesson requires this trait to engage fully
- challenges: Lesson may be uncomfortable for people high/low on this trait
"""

# ---------------------------------------------------------------------------
# MySQL helpers (matches tory_engine.py pattern)
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
# L1: Text Extraction (from tag_content.py)
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

    content = fix_unicode_escapes(slide_content)

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
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


def get_lesson_content_annotated(lesson_detail_id: int) -> tuple[str, list[dict]]:
    """Aggregate all slide text for a lesson with type annotations.

    Returns:
        (annotated_text, slides_metadata)
        where slides_metadata is [{slide_id, type, priority, text_length}]
    """
    rows = mysql_query_xml(
        f"SELECT id, type, slide_content, priority FROM lesson_slides "
        f"WHERE lesson_detail_id = {int(lesson_detail_id)} "
        f"AND deleted_at IS NULL ORDER BY priority ASC, id ASC"
    )

    parts = []
    slides_meta = []
    for i, row in enumerate(rows):
        text = extract_text_from_slide(row.get("slide_content"))
        slide_type = row.get("type", "unknown")
        slide_id = row.get("id", "?")

        slides_meta.append({
            "slide_index": i,
            "slide_id": int(slide_id) if slide_id != "?" else 0,
            "type": slide_type,
            "text_length": len(text),
        })

        if text:
            parts.append(
                f"[SLIDE {i + 1} - type: {slide_type}, slide_id: {slide_id}]\n{text}"
            )

    return "\n\n".join(parts), slides_meta


def get_lesson_metadata(lesson_detail_id: int) -> dict | None:
    """Get lesson name and journey context for richer Opus prompts."""
    rows = mysql_query_xml(
        f"SELECT ld.id, nl.lesson as lesson_name, "
        f"jd.journey as journey_name, jd.id as journey_id "
        f"FROM lesson_details ld "
        f"LEFT JOIN nx_lessons nl ON nl.id = ld.nx_lesson_id "
        f"LEFT JOIN nx_journey_details jd ON jd.id = ld.nx_journey_detail_id "
        f"WHERE ld.id = {int(lesson_detail_id)} AND ld.deleted_at IS NULL "
        f"LIMIT 1"
    )
    return rows[0] if rows else None


def build_lesson_mapping() -> dict[int, int]:
    """Build lesson_detail_id -> nx_lesson_id mapping from backpacks + ratings."""
    mapping = {}
    rows = mysql_query_xml(
        "SELECT DISTINCT nx_lesson_id, lesson_detail_id "
        "FROM backpacks WHERE deleted_at IS NULL "
        "AND nx_lesson_id IS NOT NULL AND lesson_detail_id IS NOT NULL"
    )
    for r in rows:
        mapping[int(r["lesson_detail_id"])] = int(r["nx_lesson_id"])

    rows = mysql_query_xml(
        "SELECT DISTINCT nx_lesson_id, lesson_detail_id "
        "FROM nx_user_ratings WHERE deleted_at IS NULL "
        "AND nx_lesson_id IS NOT NULL AND lesson_detail_id IS NOT NULL"
    )
    for r in rows:
        ld_id = int(r["lesson_detail_id"])
        if ld_id not in mapping:
            mapping[ld_id] = int(r["nx_lesson_id"])

    return mapping


# ---------------------------------------------------------------------------
# L2: Claude Opus Single-Call (15 fields)
# ---------------------------------------------------------------------------

# Global cost tracker
_cost_tracker = {
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cost_usd": 0.0,
    "calls": 0,
}

# Rate limiter: track last Opus call time
_last_opus_call = 0.0


def _rate_limit_opus():
    """Enforce rate limit: wait if needed to stay under 5 calls/min."""
    global _last_opus_call
    now = time.monotonic()
    elapsed = now - _last_opus_call
    if elapsed < OPUS_CALL_INTERVAL:
        wait = OPUS_CALL_INTERVAL - elapsed
        print(f"  [RATE LIMIT] Waiting {wait:.1f}s before next Opus call", file=sys.stderr)
        time.sleep(wait)
    _last_opus_call = time.monotonic()


def _track_cost(input_tokens: int, output_tokens: int):
    """Track API cost."""
    input_cost = (input_tokens / 1000) * OPUS_INPUT_PRICE_PER_1K
    output_cost = (output_tokens / 1000) * OPUS_OUTPUT_PRICE_PER_1K
    _cost_tracker["total_input_tokens"] += input_tokens
    _cost_tracker["total_output_tokens"] += output_tokens
    _cost_tracker["total_cost_usd"] += input_cost + output_cost
    _cost_tracker["calls"] += 1


def _build_system_prompt_pass1() -> str:
    """Build the system prompt for the primary extraction pass."""
    return f"""You are an expert content analyst for a corporate coaching platform that uses the
Employee Personality Profile (EPP) assessment by Criteria Corp. Your task is to deeply analyze
lesson content and extract 15 structured fields.

{EPP_DIMENSION_DESCRIPTIONS}

## Your Task
Analyze the provided lesson content (with slide-level annotations) and return a JSON object
with ALL 15 fields below. Be thorough and specific.

## Output Schema (JSON)
{{
  "trait_tags": [
    {{"trait": "<EPP dimension name>", "relevance_score": <0-100>, "direction": "builds|leverages|challenges"}}
  ],
  "difficulty": <1-5>,
  "learning_style": "visual|reflective|active|theoretical|blended",
  "prerequisites": ["<concept names that learners should know first>"],
  "summary": "<2-3 sentence summary of the lesson's purpose and approach>",
  "learning_objectives": ["After this lesson you can..."],
  "key_concepts": ["concept1", "concept2"],
  "emotional_tone": "motivational|instructional|reflective|challenging",
  "target_seniority": "junior|mid|senior|all",
  "estimated_minutes": <int>,
  "coaching_prompts": ["Discussion starter for coach-learner dialogue"],
  "content_quality": {{"score": <1-5>, "notes": "<brief quality assessment>"}},
  "pair_recommendations": [
    {{"lesson_name": "<name of a lesson that pairs well>", "reason": "<why>", "shared_dimension": "<EPP dim>"}}
  ],
  "slide_analysis": [
    {{"slide_index": <0-based>, "role": "<intro|core|exercise|reflection|summary>", "importance": "<high|medium|low>"}}
  ],
  "rag_chunks": [
    {{"chunk_text": "<semantic chunk suitable for RAG retrieval>", "chunk_type": "concept|exercise|example|insight", "topic": "<topic label>", "slide_indices": [<0-based indices>]}}
  ]
}}

## Rules
- trait_tags: Include 3-8 EPP dimensions. Use EXACT dimension names from the list above.
  Only include dimensions with relevance_score >= 20.
- difficulty: 1=introductory, 2=foundational, 3=intermediate, 4=advanced, 5=expert
- learning_style: Based on dominant interaction mode (video=visual, questions=active, etc.)
- estimated_minutes: Estimate based on slide count and content density
- coaching_prompts: 2-4 prompts that help a coach discuss this lesson with a learner
- content_quality: Assess completeness, clarity, engagement level
- pair_recommendations: 1-3 suggestions (can reference general topic if exact lesson name unknown)
- slide_analysis: One entry per slide, classify its pedagogical role
- rag_chunks: 2-6 semantic chunks optimized for retrieval. Each chunk should be self-contained,
  150-500 words, and capture a distinct concept or exercise from the lesson.

Return ONLY valid JSON, no markdown fences, no explanation."""


def _build_system_prompt_pass2() -> str:
    """Build the system prompt for the second (agreement) pass."""
    return f"""You are a learning path designer specializing in personality development for corporate
coaching. Given lesson content from a coaching platform, analyze which EPP (Employee Personality
Profile) dimensions this material targets.

{EPP_DIMENSION_DESCRIPTIONS}

Think about:
- What personality dimensions does this lesson exercise or develop?
- What traits would improve if a learner engaged deeply with this content?
- What is the emotional journey the learner goes through?

Return a JSON object with these fields:
{{
  "trait_tags": [
    {{"trait": "<EPP dimension name>", "relevance_score": <0-100>, "direction": "builds|leverages|challenges"}}
  ],
  "difficulty": <1-5>,
  "learning_style": "visual|reflective|active|theoretical|blended",
  "summary": "<2-3 sentence summary>"
}}

Rules:
- Use EXACT dimension names from the EPP list above.
- Include 3-8 dimensions with relevance_score >= 20.
- Think independently — do not assume which dimensions are relevant based on lesson title alone.
- Return ONLY valid JSON, no markdown fences."""


def call_claude_opus(
    lesson_text: str,
    system_prompt: str,
    lesson_name: str = "",
    journey_name: str = "",
) -> tuple[dict, int, int]:
    """Call Claude Opus API with structured prompt.

    Returns: (parsed_response, input_tokens, output_tokens)
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set")

    # Rate limit
    _rate_limit_opus()

    context_parts = []
    if lesson_name:
        context_parts.append(f"Lesson: {lesson_name}")
    if journey_name:
        context_parts.append(f"Journey: {journey_name}")
    context_header = "\n".join(context_parts)

    user_prompt = f"""{context_header}

Lesson Content:
{lesson_text[:12000]}"""

    payload = json.dumps({
        "model": "claude-opus-4-20250514",
        "max_tokens": 4000,
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
                err_msg = response["error"]
                print(f"  [WARN] API error (attempt {attempt + 1}): {err_msg}", file=sys.stderr)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY ** (attempt + 1))
                    continue
                raise Exception(f"API error: {err_msg}")

            # Extract token usage
            usage = response.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            _track_cost(input_tokens, output_tokens)

            # Extract text content
            content_blocks = response.get("content", [])
            text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    text += block.get("text", "")

            # Strip markdown fences if present
            text = re.sub(r'^```json\s*', '', text.strip())
            text = re.sub(r'\s*```$', '', text.strip())

            return json.loads(text), input_tokens, output_tokens

        except subprocess.TimeoutExpired:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY ** (attempt + 1))
                continue
            raise
        except json.JSONDecodeError as e:
            print(f"  [WARN] JSON parse error (attempt {attempt + 1}): {e}", file=sys.stderr)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY)
                continue
            return {}, 0, 0

    return {}, 0, 0


# ---------------------------------------------------------------------------
# L2b: Agreement Scoring (reused from tag_content.py)
# ---------------------------------------------------------------------------


def compute_agreement(pass1_tags: list[dict], pass2_tags: list[dict]) -> int:
    """Compute agreement score (0-100) between two passes using Jaccard + score similarity."""
    if not pass1_tags and not pass2_tags:
        return 100
    if not pass1_tags or not pass2_tags:
        return 0

    set1 = {t["trait"] for t in pass1_tags}
    set2 = {t["trait"] for t in pass2_tags}

    intersection = set1 & set2
    union = set1 | set2

    if not union:
        return 100

    jaccard = len(intersection) / len(union)

    score_agreement = 0.0
    if intersection:
        map1 = {t["trait"]: t["relevance_score"] for t in pass1_tags}
        map2 = {t["trait"]: t["relevance_score"] for t in pass2_tags}
        diffs = []
        for trait in intersection:
            s1 = map1.get(trait, 0)
            s2 = map2.get(trait, 0)
            diffs.append(1 - abs(s1 - s2) / 100)
        score_agreement = sum(diffs) / len(diffs)

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

    merged = []
    for t in trait_map.values():
        merged.append({
            "trait": t["trait"],
            "relevance_score": t["relevance_score"],
            "direction": t["direction"],
        })

    merged.sort(key=lambda x: x["relevance_score"], reverse=True)
    return merged


# ---------------------------------------------------------------------------
# L3: Confidence Gating
# ---------------------------------------------------------------------------


def compute_confidence(
    pass_agreement: int,
    tag_count: int,
    text_length: int,
    has_15_fields: bool,
) -> int:
    """Compute overall confidence score (0-100)."""
    # Base from agreement between passes
    base = pass_agreement * 0.5

    # Tag quality: 3-6 tags is ideal
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

    # Completeness bonus: all 15 fields extracted
    completeness_bonus = 10 if has_15_fields else 0

    confidence = round(base + tag_bonus + content_bonus + completeness_bonus)
    return max(0, min(100, confidence))


def determine_review_status(confidence: int) -> str:
    """Determine review status from confidence score."""
    if confidence >= CONFIDENCE_AUTO_APPROVE:
        return "approved"
    elif confidence < CONFIDENCE_NEEDS_REVIEW:
        return "needs_review"
    return "pending"


# ---------------------------------------------------------------------------
# L4: Embed RAG Chunks
# ---------------------------------------------------------------------------


def embed_rag_chunks(
    chunks: list[dict],
    lesson_detail_id: int,
    nx_lesson_id: int,
) -> list[str]:
    """Embed RAG chunks via OpenAI and insert into FAISS + tory_rag_chunks.

    Returns list of faiss_doc_ids for each chunk.
    """
    if not chunks:
        return []

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("  [WARN] OPENAI_API_KEY not set — skipping RAG embedding", file=sys.stderr)
        return _store_chunks_without_embedding(chunks, lesson_detail_id)

    # Collect chunk texts for batch embedding
    texts = [c.get("chunk_text", "") for c in chunks if c.get("chunk_text")]
    if not texts:
        return []

    # Call OpenAI embedding API
    try:
        payload = json.dumps({
            "model": "text-embedding-3-small",
            "input": texts,
        })
        result = subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                "https://api.openai.com/v1/embeddings",
                "-H", "content-type: application/json",
                "-H", f"Authorization: Bearer {api_key}",
                "-d", payload,
            ],
            capture_output=True, text=True, timeout=60,
        )
        response = json.loads(result.stdout)

        if "error" in response:
            print(f"  [WARN] Embedding API error: {response['error']}", file=sys.stderr)
            return _store_chunks_without_embedding(chunks, lesson_detail_id)

        # Track embedding cost
        usage = response.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)
        _cost_tracker["total_cost_usd"] += (total_tokens / 1000) * EMBEDDING_PRICE_PER_1K

        embeddings = [item["embedding"] for item in response.get("data", [])]

    except Exception as e:
        print(f"  [WARN] Embedding failed: {e}", file=sys.stderr)
        return _store_chunks_without_embedding(chunks, lesson_detail_id)

    # Try to add to FAISS via shared_vector_manager
    faiss_doc_ids = _add_to_faiss(
        texts, embeddings, chunks, lesson_detail_id, nx_lesson_id
    )

    # Store chunk metadata in tory_rag_chunks
    _store_chunks_in_db(chunks, lesson_detail_id, faiss_doc_ids)

    return faiss_doc_ids


def _add_to_faiss(
    texts: list[str],
    embeddings: list[list[float]],
    chunks: list[dict],
    lesson_detail_id: int,
    nx_lesson_id: int,
) -> list[str]:
    """Add embeddings to FAISS index. Returns doc IDs."""
    import uuid

    doc_ids = []

    try:
        # Try using shared_vector_manager
        sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
        from shared_vector_manager import SharedVectorManager
        from langchain_core.documents import Document

        manager = SharedVectorManager()
        documents = []
        for i, (text, chunk) in enumerate(zip(texts, chunks)):
            doc = Document(
                page_content=text,
                metadata={
                    "lesson_detail_id": lesson_detail_id,
                    "nx_lesson_id": nx_lesson_id,
                    "chunk_type": chunk.get("chunk_type", "concept"),
                    "topic": chunk.get("topic", ""),
                    "slide_indices": json.dumps(chunk.get("slide_indices", [])),
                    "source": "content_processor",
                },
            )
            documents.append(doc)

        manager.add_documents(documents, source="content_processor")

        # Generate IDs matching what FAISS assigned
        for i in range(len(texts)):
            doc_ids.append(f"cp_{lesson_detail_id}_{i}")

    except Exception as e:
        print(f"  [WARN] FAISS insertion failed: {e}. Storing chunks without vectors.", file=sys.stderr)
        for i in range(len(texts)):
            doc_ids.append(f"cp_{lesson_detail_id}_{i}")

    return doc_ids


def _store_chunks_without_embedding(
    chunks: list[dict], lesson_detail_id: int
) -> list[str]:
    """Store chunks in DB without FAISS embedding (fallback)."""
    doc_ids = [f"cp_{lesson_detail_id}_{i}" for i in range(len(chunks))]
    _store_chunks_in_db(chunks, lesson_detail_id, doc_ids)
    return doc_ids


def _store_chunks_in_db(
    chunks: list[dict], lesson_detail_id: int, faiss_doc_ids: list[str]
):
    """Insert chunk metadata into tory_rag_chunks."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for i, chunk in enumerate(chunks):
        doc_id = faiss_doc_ids[i] if i < len(faiss_doc_ids) else f"cp_{lesson_detail_id}_{i}"
        slide_ids = json.dumps(chunk.get("slide_indices", []))

        sql = (
            f"INSERT INTO tory_rag_chunks "
            f"(lesson_detail_id, chunk_index, chunk_text, chunk_type, topic, "
            f"slide_ids, faiss_doc_id, embedding_model, created_at) VALUES ("
            f"{int(lesson_detail_id)}, {i}, "
            f"{escape_sql(chunk.get('chunk_text', ''))}, "
            f"{escape_sql(chunk.get('chunk_type', 'concept'))}, "
            f"{escape_sql(chunk.get('topic', ''))}, "
            f"{escape_sql(slide_ids)}, "
            f"{escape_sql(doc_id)}, "
            f"'text-embedding-3-small', "
            f"'{now}')"
        )
        mysql_write(sql)


# ---------------------------------------------------------------------------
# L5: Store in DB
# ---------------------------------------------------------------------------


def store_content_tag(
    nx_lesson_id: int,
    lesson_detail_id: int,
    pass1_result: dict,
    pass2_result: dict,
    merged_tags: list[dict],
    pass_agreement: int,
    confidence: int,
    review_status: str,
    rag_chunk_ids: list[str],
) -> bool:
    """Write all 15 fields to tory_content_tags."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Extract fields from pass1 (primary), falling back to defaults
    difficulty = pass1_result.get("difficulty", 3)
    if not isinstance(difficulty, int) or difficulty < 1 or difficulty > 5:
        difficulty = 3

    learning_style = pass1_result.get("learning_style", "blended")
    valid_styles = {"visual", "reflective", "active", "theoretical", "blended"}
    if learning_style not in valid_styles:
        learning_style = "blended"

    emotional_tone = pass1_result.get("emotional_tone", "instructional")
    valid_tones = {"motivational", "instructional", "reflective", "challenging"}
    if emotional_tone not in valid_tones:
        emotional_tone = "instructional"

    target_seniority = pass1_result.get("target_seniority", "all")
    valid_seniority = {"junior", "mid", "senior", "all"}
    if target_seniority not in valid_seniority:
        target_seniority = "all"

    estimated_minutes = pass1_result.get("estimated_minutes", 15)
    if not isinstance(estimated_minutes, int) or estimated_minutes < 1:
        estimated_minutes = 15

    prerequisites = pass1_result.get("prerequisites", [])
    summary = pass1_result.get("summary", "")
    learning_objectives = pass1_result.get("learning_objectives", [])
    key_concepts = pass1_result.get("key_concepts", [])
    coaching_prompts = pass1_result.get("coaching_prompts", [])
    content_quality = pass1_result.get("content_quality", {"score": 3, "notes": ""})
    pair_recommendations = pass1_result.get("pair_recommendations", [])
    slide_analysis = pass1_result.get("slide_analysis", [])

    # Build SQL — insert or update
    sql = (
        f"INSERT INTO tory_content_tags "
        f"(nx_lesson_id, lesson_detail_id, trait_tags, difficulty, learning_style, "
        f"prerequisites, confidence, review_status, pass1_tags, pass2_tags, "
        f"pass_agreement, summary, learning_objectives, key_concepts, "
        f"emotional_tone, target_seniority, estimated_minutes, coaching_prompts, "
        f"content_quality, pair_recommendations, slide_analysis, rag_chunk_ids, "
        f"processed_at, created_at, updated_at) VALUES ("
        f"{int(nx_lesson_id)}, {int(lesson_detail_id)}, "
        f"{escape_sql(json.dumps(merged_tags))}, "
        f"{int(difficulty)}, "
        f"{escape_sql(learning_style)}, "
        f"{escape_sql(json.dumps(prerequisites))}, "
        f"{int(confidence)}, "
        f"{escape_sql(review_status)}, "
        f"{escape_sql(json.dumps(pass1_result.get('trait_tags', [])))}, "
        f"{escape_sql(json.dumps(pass2_result.get('trait_tags', [])))}, "
        f"{int(pass_agreement)}, "
        f"{escape_sql(summary)}, "
        f"{escape_sql(json.dumps(learning_objectives))}, "
        f"{escape_sql(json.dumps(key_concepts))}, "
        f"{escape_sql(emotional_tone)}, "
        f"{escape_sql(target_seniority)}, "
        f"{int(estimated_minutes)}, "
        f"{escape_sql(json.dumps(coaching_prompts))}, "
        f"{escape_sql(json.dumps(content_quality))}, "
        f"{escape_sql(json.dumps(pair_recommendations))}, "
        f"{escape_sql(json.dumps(slide_analysis))}, "
        f"{escape_sql(json.dumps(rag_chunk_ids))}, "
        f"'{now}', '{now}', '{now}')"
    )

    return mysql_write(sql)


# ---------------------------------------------------------------------------
# Main Pipeline: Process Single Lesson
# ---------------------------------------------------------------------------


def process_lesson(lesson_detail_id: int, nx_lesson_id: int) -> dict:
    """Run the full 5-stage pipeline for one lesson.

    Returns: {
        success, confidence, review_status, tag_count, pass_agreement,
        chunk_count, cost_usd, input_tokens, output_tokens, error
    }
    """
    cost_before = _cost_tracker["total_cost_usd"]

    # --- L1: Text Extraction ---
    annotated_text, slides_meta = get_lesson_content_annotated(lesson_detail_id)
    if not annotated_text or len(annotated_text.strip()) < 20:
        return {
            "success": False,
            "error": f"Insufficient content (text length: {len(annotated_text)})",
        }

    # Get lesson metadata for richer context
    meta = get_lesson_metadata(lesson_detail_id)
    lesson_name = meta.get("lesson_name", "") if meta else ""
    journey_name = meta.get("journey_name", "") if meta else ""

    # --- L2: Primary Opus Call (15 fields) ---
    try:
        pass1_result, in1, out1 = call_claude_opus(
            annotated_text,
            _build_system_prompt_pass1(),
            lesson_name=lesson_name,
            journey_name=journey_name,
        )
    except Exception as e:
        return {"success": False, "error": f"Pass 1 failed: {e}"}

    if not pass1_result:
        return {"success": False, "error": "Pass 1 returned empty result"}

    # --- L2b: Second Pass (agreement scoring) ---
    try:
        pass2_result, in2, out2 = call_claude_opus(
            annotated_text,
            _build_system_prompt_pass2(),
            lesson_name=lesson_name,
            journey_name=journey_name,
        )
    except Exception as e:
        # If pass 2 fails, proceed with pass 1 only (lower confidence)
        pass2_result = {"trait_tags": [], "difficulty": 3, "learning_style": "blended", "summary": ""}

    # Validate and filter tags to valid EPP dims
    valid_dims = set(ALL_EPP_DIMS)
    pass1_tags = [
        t for t in pass1_result.get("trait_tags", [])
        if isinstance(t, dict) and t.get("trait") in valid_dims
    ]
    pass2_tags = [
        t for t in pass2_result.get("trait_tags", [])
        if isinstance(t, dict) and t.get("trait") in valid_dims
    ]

    # Normalize tag fields
    for tags in [pass1_tags, pass2_tags]:
        for t in tags:
            t["trait"] = str(t.get("trait", ""))
            t["relevance_score"] = max(0, min(100, int(t.get("relevance_score", 0))))
            if t.get("direction") not in ("builds", "leverages", "challenges"):
                t["direction"] = "builds"

    # --- L3: Confidence Gating ---
    agreement = compute_agreement(pass1_tags, pass2_tags)
    merged_tags = merge_tags(pass1_tags, pass2_tags)

    # Check if all 15 fields are present
    required_fields = [
        "trait_tags", "difficulty", "learning_style", "prerequisites",
        "summary", "learning_objectives", "key_concepts", "emotional_tone",
        "target_seniority", "estimated_minutes", "coaching_prompts",
        "content_quality", "pair_recommendations", "slide_analysis", "rag_chunks",
    ]
    has_15 = all(pass1_result.get(f) is not None for f in required_fields)

    confidence = compute_confidence(agreement, len(merged_tags), len(annotated_text), has_15)
    review_status = determine_review_status(confidence)

    # --- L4: Embed RAG Chunks ---
    rag_chunks = pass1_result.get("rag_chunks", [])
    if not isinstance(rag_chunks, list):
        rag_chunks = []

    chunk_ids = embed_rag_chunks(rag_chunks, lesson_detail_id, nx_lesson_id)

    # --- L5: Store in DB ---
    success = store_content_tag(
        nx_lesson_id=nx_lesson_id,
        lesson_detail_id=lesson_detail_id,
        pass1_result=pass1_result,
        pass2_result=pass2_result,
        merged_tags=merged_tags,
        pass_agreement=agreement,
        confidence=confidence,
        review_status=review_status,
        rag_chunk_ids=chunk_ids,
    )

    cost_this = _cost_tracker["total_cost_usd"] - cost_before

    return {
        "success": success,
        "confidence": confidence,
        "review_status": review_status,
        "tag_count": len(merged_tags),
        "pass_agreement": agreement,
        "chunk_count": len(chunk_ids),
        "cost_usd": round(cost_this, 4),
        "input_tokens": in1 + (in2 if 'in2' in dir() else 0),
        "output_tokens": out1 + (out2 if 'out2' in dir() else 0),
        "top_traits": [t["trait"] for t in merged_tags[:3]],
        "fields_extracted": sum(1 for f in required_fields if pass1_result.get(f) is not None),
    }


# ---------------------------------------------------------------------------
# MCP Tool Handlers (called from tory_engine.py)
# ---------------------------------------------------------------------------


async def tool_process_content(lesson_detail_id: int) -> str:
    """Process a single lesson through the 15-field pipeline.

    MCP tool: tory_process_content
    """
    # Resolve nx_lesson_id
    mapping = build_lesson_mapping()

    # Find the nx_lesson_id for this lesson_detail_id
    nx_lesson_id = mapping.get(lesson_detail_id)
    if nx_lesson_id is None:
        # Try direct lookup via lesson_details -> nx_lessons
        rows = mysql_query_xml(
            f"SELECT nl.id FROM nx_lessons nl "
            f"JOIN lesson_details ld ON ld.nx_lesson_id = nl.id "
            f"WHERE ld.id = {int(lesson_detail_id)} AND nl.deleted_at IS NULL "
            f"LIMIT 1"
        )
        if rows:
            nx_lesson_id = int(rows[0]["id"])

    if nx_lesson_id is None:
        return json.dumps({
            "error": f"Cannot resolve nx_lesson_id for lesson_detail_id={lesson_detail_id}",
            "hint": "This lesson_detail_id has no matching nx_lesson entry.",
        })

    # Check if already processed
    existing = mysql_query_xml(
        f"SELECT id, confidence, review_status, processed_at "
        f"FROM tory_content_tags "
        f"WHERE lesson_detail_id = {int(lesson_detail_id)} AND deleted_at IS NULL "
        f"LIMIT 1"
    )
    if existing:
        return json.dumps({
            "status": "already_processed",
            "existing": existing[0],
            "hint": "Delete existing row or use tory_process_all_content(force=true) to reprocess.",
        })

    # Process
    result = process_lesson(lesson_detail_id, nx_lesson_id)

    return json.dumps({
        "lesson_detail_id": lesson_detail_id,
        "nx_lesson_id": nx_lesson_id,
        **result,
        "cost_tracker": {
            "total_calls": _cost_tracker["calls"],
            "total_cost_usd": round(_cost_tracker["total_cost_usd"], 4),
        },
    })


async def tool_process_all_content(force: bool = False) -> str:
    """Process all unprocessed lessons through the 15-field pipeline.

    MCP tool: tory_process_all_content
    """
    # Build mapping
    mapping = build_lesson_mapping()

    # Also try nx_lessons direct lookup for unmapped ones
    rows = mysql_query_xml(
        "SELECT ld.id as lesson_detail_id, ld.nx_lesson_id "
        "FROM lesson_details ld "
        "WHERE ld.deleted_at IS NULL AND ld.nx_lesson_id IS NOT NULL"
    )
    for r in rows:
        ld_id = int(r["lesson_detail_id"])
        if ld_id not in mapping:
            mapping[ld_id] = int(r["nx_lesson_id"])

    # Get all lesson_detail_ids with content
    all_rows = mysql_query_xml(
        "SELECT DISTINCT lesson_detail_id FROM lesson_slides "
        "WHERE deleted_at IS NULL AND lesson_detail_id IS NOT NULL "
        "ORDER BY lesson_detail_id ASC"
    )
    all_ld_ids = [int(r["lesson_detail_id"]) for r in all_rows]

    # Filter to those with nx_lesson_id mapping
    taggable = [(ld_id, mapping[ld_id]) for ld_id in all_ld_ids if ld_id in mapping]

    # Filter out already processed (unless force)
    if not force:
        existing_rows = mysql_query_xml(
            "SELECT DISTINCT lesson_detail_id FROM tory_content_tags "
            "WHERE deleted_at IS NULL AND processed_at IS NOT NULL"
        )
        existing_ids = {int(r["lesson_detail_id"]) for r in existing_rows}
        pending = [(ld, nl) for ld, nl in taggable if ld not in existing_ids]
    else:
        pending = taggable

    if not pending:
        return json.dumps({
            "status": "all_processed",
            "total_lessons": len(taggable),
            "message": "All lessons already processed.",
        })

    # Process each lesson
    results = {
        "total": len(pending),
        "success": 0,
        "failed": 0,
        "approved": 0,
        "pending_review": 0,
        "needs_review": 0,
        "lessons": [],
        "errors": [],
    }

    for i, (ld_id, nl_id) in enumerate(pending):
        print(
            f"  [{i + 1}/{len(pending)}] Processing lesson_detail_id={ld_id} "
            f"(nx_lesson_id={nl_id})...",
            file=sys.stderr,
        )

        result = process_lesson(ld_id, nl_id)

        if result.get("success"):
            results["success"] += 1
            status = result.get("review_status", "pending")
            if status == "approved":
                results["approved"] += 1
            elif status == "needs_review":
                results["needs_review"] += 1
            else:
                results["pending_review"] += 1

            results["lessons"].append({
                "lesson_detail_id": ld_id,
                "nx_lesson_id": nl_id,
                "confidence": result.get("confidence"),
                "review_status": result.get("review_status"),
                "tag_count": result.get("tag_count"),
                "chunk_count": result.get("chunk_count"),
                "top_traits": result.get("top_traits", []),
            })
        else:
            results["failed"] += 1
            results["errors"].append({
                "lesson_detail_id": ld_id,
                "error": result.get("error", "unknown"),
            })

    results["cost_tracker"] = {
        "total_calls": _cost_tracker["calls"],
        "total_input_tokens": _cost_tracker["total_input_tokens"],
        "total_output_tokens": _cost_tracker["total_output_tokens"],
        "total_cost_usd": round(_cost_tracker["total_cost_usd"], 4),
    }

    return json.dumps(results)
