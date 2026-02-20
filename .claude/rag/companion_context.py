"""
Companion Context Assembler
Loads all learner data and builds prompt context for the Companion AI.

Data sources:
- EPP profile → translated to human language (never raw scores)
- Backpack entries → parsed from JSON arrays with slide question pairing
- Learning path → from tory_recommendations
- Progress data → completion %, ratings, recent activity
- FAISS retrieval → scoped to assigned lessons only
- Conversation memory → three-tier (buffer, summary, key_facts)
"""

import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from html import unescape
from typing import Any, Dict, List, Optional

import structlog

from companion_prompts import (
    COMPANION_SYSTEM_PROMPT,
    get_mode_prompt,
    translate_epp_profile,
    get_greeting_template,
    get_available_actions,
)

logger = structlog.get_logger()

DATABASE = "baap"
QUERY_TIMEOUT = 30


def _db_query(sql: str) -> List[Dict[str, str]]:
    """Run a read-only SQL query via mysql CLI, return list of row dicts."""
    try:
        result = subprocess.run(
            ["mysql", DATABASE, "--xml", "-e", sql],
            capture_output=True, text=True, timeout=QUERY_TIMEOUT,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        root = ET.fromstring(result.stdout)
        rows = []
        for row_el in root.findall("row"):
            row = {}
            for field in row_el.findall("field"):
                name = field.get("name")
                row[name] = field.text or ""
            rows.append(row)
        return rows
    except Exception as e:
        logger.warning("db_query_failed", sql=sql[:120], error=str(e))
        return []


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode entities."""
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


# ============================================================================
# Learner Data Loader
# ============================================================================

class CompanionContext:
    """
    Assembles all context needed for a Companion AI response.
    Handles graceful degradation when data is missing.
    """

    def __init__(self, nx_user_id: int):
        self.nx_user_id = int(nx_user_id)
        self._cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Profile context (EPP translated to human language)
    # ------------------------------------------------------------------

    def get_profile_context(self) -> str:
        """Build the learner profile section — NEVER expose raw scores."""
        if 'profile_ctx' in self._cache:
            return self._cache['profile_ctx']

        parts = []

        # Learner name
        name = self._get_learner_name()
        if name:
            parts.append(f"Name: {name}")

        # Learning style
        style = self._get_learning_style()
        if style:
            parts.append(f"Learning style: {style}")

        # Onboarding answers — their own words
        onboarding = self._get_onboarding_answers()
        if onboarding:
            parts.append("What they shared during onboarding:")
            parts.append(onboarding)

        # EPP profile translated
        epp_translated = self._get_epp_translated()
        if epp_translated:
            parts.append(epp_translated)

        # Profile narrative (AI-generated summary)
        narrative = self._get_profile_narrative()
        if narrative:
            parts.append(f"Profile summary: {narrative}")

        result = "\n\n".join(parts) if parts else "No profile data available yet."
        self._cache['profile_ctx'] = result
        return result

    def _get_learner_name(self) -> str:
        rows = _db_query(
            f"SELECT o.first_name, o.last_name "
            f"FROM nx_user_onboardings o "
            f"WHERE o.nx_user_id = {self.nx_user_id} "
            f"AND o.deleted_at IS NULL LIMIT 1"
        )
        if rows:
            first = rows[0].get("first_name", "")
            last = rows[0].get("last_name", "")
            return f"{first} {last}".strip()
        return ""

    def _get_learning_style(self) -> str:
        rows = _db_query(
            f"SELECT learning_style FROM tory_learner_profiles "
            f"WHERE nx_user_id = {self.nx_user_id} "
            f"AND deleted_at IS NULL "
            f"ORDER BY version DESC LIMIT 1"
        )
        if rows and rows[0].get("learning_style"):
            return rows[0]["learning_style"]
        return ""

    def _get_onboarding_answers(self) -> str:
        """Get onboarding Q&A formatted as context."""
        rows = _db_query(
            f"SELECT question, answer "
            f"FROM nx_user_onboardings "
            f"WHERE user_id = {self.nx_user_id} "
            f"ORDER BY id LIMIT 10"
        )
        if not rows:
            return ""
        parts = []
        for r in rows:
            q = r.get("question", "")
            a = r.get("answer", "")
            if q and a and a != "NULL":
                parts.append(f"  Q: {q}\n  A: {_strip_html(a)[:200]}")
        return "\n".join(parts) if parts else ""

    def _get_epp_translated(self) -> str:
        """Get EPP profile translated to human language."""
        rows = _db_query(
            f"SELECT epp_summary, strengths, gaps "
            f"FROM tory_learner_profiles "
            f"WHERE nx_user_id = {self.nx_user_id} "
            f"AND deleted_at IS NULL "
            f"ORDER BY version DESC LIMIT 1"
        )
        if not rows:
            return ""

        row = rows[0]
        epp_summary = {}
        strengths = []
        gaps = []

        try:
            if row.get("epp_summary"):
                epp_summary = json.loads(row["epp_summary"])
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            if row.get("strengths"):
                strengths = json.loads(row["strengths"])
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            if row.get("gaps"):
                gaps = json.loads(row["gaps"])
        except (json.JSONDecodeError, TypeError):
            pass

        return translate_epp_profile(epp_summary, strengths, gaps)

    def _get_profile_narrative(self) -> str:
        rows = _db_query(
            f"SELECT profile_narrative FROM tory_learner_profiles "
            f"WHERE nx_user_id = {self.nx_user_id} "
            f"AND deleted_at IS NULL "
            f"ORDER BY version DESC LIMIT 1"
        )
        if rows and rows[0].get("profile_narrative"):
            return _truncate(rows[0]["profile_narrative"], 500)
        return ""

    # ------------------------------------------------------------------
    # Learning path context
    # ------------------------------------------------------------------

    def get_path_context(self) -> str:
        """Build the learning path section with completion status."""
        if 'path_ctx' in self._cache:
            return self._cache['path_ctx']

        recs = self._get_recommendations()
        if not recs:
            result = "No learning path assigned yet."
            self._cache['path_ctx'] = result
            return result

        lines = []
        for r in recs:
            status = "[done]" if r.get("completed") else "[ ]"
            seq = r.get("sequence", "?")
            name = r.get("lesson_name", "Unknown")
            journey = r.get("journey_name", "")
            discovery = " (discovery)" if r.get("is_discovery") else ""
            lines.append(f"{seq}. {status} {name} ({journey}){discovery}")

        result = "\n".join(lines)
        self._cache['path_ctx'] = result
        return result

    def _get_recommendations(self) -> List[Dict]:
        """Get full recommendation list with metadata."""
        if 'recs' in self._cache:
            return self._cache['recs']

        rows = _db_query(
            f"SELECT r.sequence, r.nx_lesson_id, r.is_discovery, "
            f"r.match_rationale, r.source, r.locked_by_coach, "
            f"l.lesson_name, j.journey_name "
            f"FROM tory_recommendations r "
            f"JOIN nx_lessons l ON r.nx_lesson_id = l.id "
            f"LEFT JOIN nx_journeys j ON l.journey_id = j.id "
            f"WHERE r.nx_user_id = {self.nx_user_id} "
            f"AND r.deleted_at IS NULL "
            f"ORDER BY r.sequence LIMIT 30"
        )

        # Get completed lesson IDs
        completed_ids = self._get_completed_lesson_ids()

        recs = []
        for r in rows:
            lid = int(r.get("nx_lesson_id", 0))
            recs.append({
                "sequence": int(r.get("sequence", 0)),
                "nx_lesson_id": lid,
                "lesson_name": r.get("lesson_name", "Unknown"),
                "journey_name": r.get("journey_name", ""),
                "is_discovery": r.get("is_discovery") == "1",
                "completed": lid in completed_ids,
                "source": r.get("source", "tory"),
            })

        self._cache['recs'] = recs
        return recs

    def _get_completed_lesson_ids(self) -> set:
        """Get lesson IDs the learner has completed."""
        if 'completed_ids' in self._cache:
            return self._cache['completed_ids']

        rows = _db_query(
            f"SELECT DISTINCT nx_lesson_id FROM nx_lesson_users "
            f"WHERE nx_user_id = {self.nx_user_id} "
            f"AND status = 'completed' AND deleted_at IS NULL"
        )
        ids = {int(r["nx_lesson_id"]) for r in rows if r.get("nx_lesson_id")}
        self._cache['completed_ids'] = ids
        return ids

    def get_assigned_lesson_ids(self) -> set:
        """Get the set of lesson IDs in the learner's path — for FAISS scope filtering."""
        recs = self._get_recommendations()
        return {r["nx_lesson_id"] for r in recs}

    def get_assigned_lesson_detail_ids(self) -> set:
        """Get lesson_detail_ids for scope filtering FAISS results."""
        if 'assigned_detail_ids' in self._cache:
            return self._cache['assigned_detail_ids']

        lesson_ids = self.get_assigned_lesson_ids()
        if not lesson_ids:
            return set()

        ids_str = ",".join(str(i) for i in lesson_ids)
        rows = _db_query(
            f"SELECT DISTINCT id FROM nx_lesson_details "
            f"WHERE nx_lesson_id IN ({ids_str}) AND deleted_at IS NULL"
        )
        detail_ids = {int(r["id"]) for r in rows if r.get("id")}
        self._cache['assigned_detail_ids'] = detail_ids
        return detail_ids

    # ------------------------------------------------------------------
    # Backpack context — learner's own words
    # ------------------------------------------------------------------

    def get_backpack_context(self, lesson_detail_id: int = None) -> str:
        """
        Get backpack entries with slide question pairing.
        If lesson_detail_id given, scope to that lesson. Otherwise, recent entries.
        """
        if lesson_detail_id:
            return self._get_backpack_for_lesson(lesson_detail_id)
        return self._get_recent_backpack()

    def _get_backpack_for_lesson(self, lesson_detail_id: int) -> str:
        """Get backpack entries for a specific lesson, paired with their slide questions."""
        rows = _db_query(
            f"SELECT b.data, b.form_type, b.lesson_slide_id, "
            f"ls.slide_content "
            f"FROM backpacks b "
            f"LEFT JOIN lesson_slides ls ON b.lesson_slide_id = ls.id "
            f"WHERE b.lesson_detail_id = {int(lesson_detail_id)} "
            f"AND b.created_by = {self.nx_user_id} "
            f"AND b.deleted_at IS NULL "
            f"ORDER BY b.id"
        )
        return self._format_backpack_entries(rows)

    def _get_recent_backpack(self) -> str:
        """Get most recent backpack entries across all lessons."""
        rows = _db_query(
            f"SELECT b.data, b.form_type, b.lesson_slide_id, "
            f"ls.slide_content, l.lesson_name "
            f"FROM backpacks b "
            f"LEFT JOIN lesson_slides ls ON b.lesson_slide_id = ls.id "
            f"LEFT JOIN nx_lesson_details ld ON b.lesson_detail_id = ld.id "
            f"LEFT JOIN nx_lessons l ON ld.nx_lesson_id = l.id "
            f"WHERE b.created_by = {self.nx_user_id} "
            f"AND b.deleted_at IS NULL "
            f"ORDER BY b.created_at DESC LIMIT 20"
        )
        return self._format_backpack_entries(rows)

    def _format_backpack_entries(self, rows: List[Dict]) -> str:
        """
        Parse backpack data (JSON array) and pair with slide questions.
        backpacks.data is a JSON ARRAY of answers corresponding to slide questions.
        """
        if not rows:
            return ""

        entries = []
        for row in rows:
            data_raw = row.get("data", "")
            form_type = row.get("form_type", "")
            lesson_name = row.get("lesson_name", "")
            slide_content_raw = row.get("slide_content", "")

            # Parse the data JSON array
            answers = self._parse_backpack_data(data_raw)
            if not answers:
                continue

            # Try to extract questions from the slide content
            questions = self._extract_questions_from_slide(slide_content_raw)

            prefix = f"From {lesson_name}: " if lesson_name else ""

            if questions and len(questions) == len(answers):
                # Pair questions with answers
                for q, a in zip(questions, answers):
                    a_clean = _strip_html(str(a)).strip()
                    if a_clean and a_clean != "NULL":
                        entries.append(f"{prefix}Q: {_strip_html(q)} | Their answer: \"{a_clean}\"")
            else:
                # No question pairing available, use raw answers
                for a in answers:
                    a_clean = _strip_html(str(a)).strip()
                    if a_clean and a_clean != "NULL" and len(a_clean) > 2:
                        entries.append(f"{prefix}({form_type}) \"{a_clean}\"")

        return "\n".join(entries[:15]) if entries else ""

    def _parse_backpack_data(self, data_raw: str) -> list:
        """Parse backpack data which is a JSON array of answers."""
        if not data_raw:
            return []
        try:
            parsed = json.loads(data_raw)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except (json.JSONDecodeError, TypeError):
            # Not JSON — might be a raw string
            if data_raw.strip():
                return [data_raw.strip()]
            return []

    def _extract_questions_from_slide(self, slide_content_raw: str) -> list:
        """Extract question texts from slide_content JSON."""
        if not slide_content_raw:
            return []
        try:
            content = json.loads(slide_content_raw)
            if isinstance(content, dict):
                # Check common question field patterns
                questions = content.get("questions", [])
                if questions and isinstance(questions, list):
                    return [
                        q.get("question", q.get("text", str(q)))
                        if isinstance(q, dict) else str(q)
                        for q in questions
                    ]
                # Single question field
                q = content.get("question", "")
                if q:
                    return [q]
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    # ------------------------------------------------------------------
    # Progress context
    # ------------------------------------------------------------------

    def get_progress_context(self) -> str:
        """Build progress summary: completion %, recent activity."""
        recs = self._get_recommendations()
        completed_ids = self._get_completed_lesson_ids()

        if not recs:
            return "No learning path assigned yet."

        total = len(recs)
        completed = sum(1 for r in recs if r["completed"])
        pct = round((completed / total) * 100) if total > 0 else 0

        parts = [f"Progress: {completed}/{total} lessons complete ({pct}%)"]

        # Next uncompleted lesson
        for r in recs:
            if not r["completed"]:
                parts.append(f"Next up: {r['lesson_name']} ({r['journey_name']})")
                break

        # Recent completions
        if completed > 0:
            recent_done = [r for r in recs if r["completed"]][-3:]
            done_names = [r["lesson_name"] for r in recent_done]
            parts.append(f"Recently completed: {', '.join(done_names)}")

        return "\n".join(parts)

    def get_progress_data(self) -> Dict:
        """Get structured progress data for API responses."""
        recs = self._get_recommendations()
        completed_ids = self._get_completed_lesson_ids()

        total = len(recs)
        completed = sum(1 for r in recs if r["completed"])
        pct = round((completed / total) * 100) if total > 0 else 0

        next_lesson = None
        last_completed = None
        for r in recs:
            if not r["completed"] and not next_lesson:
                next_lesson = r
            if r["completed"]:
                last_completed = r

        return {
            "total_lessons": total,
            "completed_lessons": completed,
            "completion_pct": pct,
            "next_lesson": next_lesson,
            "last_completed": last_completed,
            "has_path": total > 0,
            "has_completed": completed > 0,
        }

    # ------------------------------------------------------------------
    # Full prompt assembly
    # ------------------------------------------------------------------

    def build_system_prompt(self, mode: str = "teach", memory_context: str = "",
                           rag_context: str = "", backpack_override: str = "") -> str:
        """
        Assemble the full system prompt with profile, path, memory, and mode.
        """
        profile_ctx = self.get_profile_context()
        path_ctx = self.get_path_context()
        progress_ctx = self.get_progress_context()
        backpack_ctx = backpack_override or self.get_backpack_context()

        # Build the base system prompt
        system = COMPANION_SYSTEM_PROMPT.format(
            profile_context=profile_ctx or "No profile data available yet.",
            path_context=path_ctx or "No learning path assigned yet.",
            memory_context=memory_context or "No prior conversation context.",
        )

        # Add mode-specific sub-prompt
        mode_prompt = get_mode_prompt(
            mode,
            rag_context=rag_context,
            backpack_context=backpack_ctx,
            path_context=path_ctx,
            progress_context=progress_ctx,
        )
        system = f"{system}\n\n{mode_prompt}"

        # Add backpack as reference if available and not in reflect mode
        if backpack_ctx and mode != "reflect":
            system += f"\n\n## Learner's own words (from backpack)\n{backpack_ctx}"

        return system

    def build_greeting(self) -> Dict:
        """
        Build a contextual greeting based on learner state.
        Returns {greeting, quick_actions, progress}.
        """
        progress = self.get_progress_data()
        has_profile = bool(self._get_epp_translated())
        has_path = progress["has_path"]
        has_progress = progress["has_completed"]

        # Check if they just completed something
        just_completed = False  # Would need session state to determine

        # Check if returning user (has prior session)
        is_returning = self._has_prior_session()

        template = get_greeting_template(
            has_profile=has_profile,
            has_path=has_path,
            has_progress=has_progress,
            just_completed=just_completed,
            is_returning=is_returning,
        )

        # Fill in template variables
        greeting_vars = {
            "completion_pct": progress["completion_pct"],
            "last_lesson": (
                progress["last_completed"]["lesson_name"]
                if progress["last_completed"] else "your lessons"
            ),
            "next_lesson": (
                progress["next_lesson"]["lesson_name"]
                if progress["next_lesson"] else "your next lesson"
            ),
            "completed_lesson": (
                progress["last_completed"]["lesson_name"]
                if progress["last_completed"] else ""
            ),
            "profile_hook": self._get_profile_hook(),
        }

        try:
            greeting = template.format(**greeting_vars)
        except (KeyError, IndexError):
            greeting = template  # Use raw template if format fails

        actions = get_available_actions(has_path, has_progress)

        return {
            "greeting": greeting,
            "quick_actions": actions,
            "progress": progress,
        }

    def _get_profile_hook(self) -> str:
        """Get a short hook from the learner's profile for the greeting."""
        rows = _db_query(
            f"SELECT b.data FROM backpacks b "
            f"WHERE b.created_by = {self.nx_user_id} "
            f"AND b.form_type = 'select-one-word' "
            f"AND b.deleted_at IS NULL "
            f"ORDER BY b.id LIMIT 1"
        )
        if rows and rows[0].get("data"):
            word = _strip_html(rows[0]["data"]).strip()
            if word and len(word) < 30:
                return f"I see you chose \"{word}\" as your guiding word — that tells me a lot about what matters to you."
        return ""

    def _has_prior_session(self) -> bool:
        """Check if learner has a prior companion session."""
        rows = _db_query(
            f"SELECT id FROM tory_ai_sessions "
            f"WHERE nx_user_id = {self.nx_user_id} "
            f"AND role = 'companion' "
            f"AND archived_at IS NULL "
            f"LIMIT 1"
        )
        return len(rows) > 0

    # ------------------------------------------------------------------
    # FAISS scope filtering
    # ------------------------------------------------------------------

    def filter_rag_results(self, results: List[Dict]) -> List[Dict]:
        """
        Post-filter FAISS results to only include content from assigned lessons.
        Personal (backpack) results are always included.
        """
        assigned_detail_ids = self.get_assigned_lesson_detail_ids()
        if not assigned_detail_ids:
            return results  # No path = no filtering (graceful degradation)

        filtered = []
        for r in results:
            # Always include personal/backpack results
            if r.get("is_personal", False):
                filtered.append(r)
                continue

            # Check if the result's lesson_detail_id is in the assigned set
            meta = r.get("metadata", {})
            detail_id = meta.get("lesson_detail_id")
            if detail_id is not None and int(detail_id) in assigned_detail_ids:
                filtered.append(r)

        return filtered

    def format_rag_for_prompt(self, results: List[Dict]) -> str:
        """Format RAG results into a prompt-friendly string with citations."""
        if not results:
            return ""
        parts = []
        for i, r in enumerate(results[:5], 1):
            content = r.get("content", "")
            meta = r.get("metadata", {})
            source = meta.get("lesson_name", meta.get("source", "lesson"))
            slide_idx = meta.get("slide_index", "")
            score = r.get("adjusted_score", r.get("similarity_score", 0))

            citation = source
            if slide_idx:
                citation = f"slide {slide_idx} of '{source}'"

            parts.append(f"[Source {i}: {citation} (relevance: {score:.2f})]\n{content}")

        return "\n\n".join(parts)
