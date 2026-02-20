"""
Model Harness for MyNextory RAG System
Runtime framework that turns a raw LLM into the Curator or Companion.

Provides:
- ContextBuilder: assembles prompt from static, dynamic, and memory tiers
- TierRouter: decides Sonnet vs Opus based on query complexity
- GuardrailsChecker: post-processing safety checks
- ResponseFormatter: output formatting for web/mobile/API
"""

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import structlog
from anthropic import Anthropic

from rag_config import (
    ANTHROPIC_API_KEY,
    DATABASE,
    DB_QUERY_TIMEOUT,
    DEFAULT_TOP_K,
    EPP_PERSONALITY_DIMS,
    EPP_JOBFIT_DIMS,
    ALL_EPP_DIMS,
    OPUS_MODEL,
    SONNET_MODEL,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Token budgets (approximate, for context assembly)
# ---------------------------------------------------------------------------
TOKEN_BUDGET = {
    'system': 1500,
    'profile': 1000,
    'path': 1500,
    'rag': 2000,
    'backpack': 1500,
    'memory': 2000,
    'query': 200,
    'response': 2000,
    'total': 12000,
}

# Characters-per-token estimate for budget enforcement
CHARS_PER_TOKEN = 4


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _db_query(sql: str) -> List[Dict[str, str]]:
    """Run a read-only SQL query via mysql CLI, return list of row dicts."""
    try:
        result = subprocess.run(
            ["mysql", DATABASE, "--xml", "-e", sql],
            capture_output=True, text=True,
            timeout=DB_QUERY_TIMEOUT,
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


# ============================================================================
# ContextBuilder
# ============================================================================

class ContextBuilder:
    """
    Assembles the full prompt context from three tiers:

    Static:
      - Persona prompt (system instruction for Companion or Curator)
      - EPP profile (29 dims from tory_learner_profiles.epp_summary)
      - Onboarding Q&A (from nx_user_onboardings)
      - Learning path (current roadmap items)
      - Profile narrative (from tory_learner_profiles.profile_narrative)

    Dynamic:
      - RAG retrieval (4 chunks via HybridQueryEngine)
      - Backpack entries (user's saved items)
      - Recent activity (completions, ratings)

    Memory:
      - Buffer: last 10 messages verbatim
      - Summary: last 50 messages compressed
      - Key facts: permanent learner facts
    """

    COMPANION_PERSONA = (
        "You are Tory, a warm and insightful AI learning companion on the "
        "MyNextory coaching platform. You help learners explore their assigned "
        "lessons, reflect on their growth, and connect concepts to their goals. "
        "Speak in a supportive, encouraging tone. Use the learner's profile "
        "to personalize your responses. Only discuss content from their "
        "assigned learning path."
    )

    CURATOR_PERSONA = (
        "You are Tory Curator, an AI coaching assistant for MyNextory coaches. "
        "You help coaches understand learner profiles, review lesson content, "
        "suggest path adjustments, and provide data-driven coaching insights. "
        "You have access to all lessons and learner data. Be analytical, "
        "precise, and reference specific EPP dimensions when relevant."
    )

    def __init__(self, nx_user_id: int, scope: str = "companion"):
        self.nx_user_id = nx_user_id
        self.scope = scope
        self._cache: Dict[str, Any] = {}

    def build(
        self,
        rag_chunks: Optional[List[Dict]] = None,
        backpack_entries: Optional[List[Dict]] = None,
        memory: Optional[Any] = None,
        query: str = "",
    ) -> Dict[str, str]:
        """
        Assemble the full context dict with keys:
          system, profile, path, rag, backpack, memory, query
        Each value is a string within its token budget.
        """
        return {
            'system': self._build_system(),
            'profile': self._build_profile(),
            'path': self._build_path(),
            'rag': self._build_rag(rag_chunks),
            'backpack': self._build_backpack(backpack_entries),
            'memory': self._build_memory(memory),
            'query': _truncate_to_tokens(query, TOKEN_BUDGET['query']),
        }

    def build_messages(
        self,
        rag_chunks: Optional[List[Dict]] = None,
        backpack_entries: Optional[List[Dict]] = None,
        memory: Optional[Any] = None,
        query: str = "",
    ) -> List[Dict[str, str]]:
        """Build Anthropic-formatted messages list from context tiers."""
        ctx = self.build(rag_chunks, backpack_entries, memory, query)

        system_parts = [ctx['system']]
        if ctx['profile']:
            system_parts.append(f"\n## Learner Profile\n{ctx['profile']}")
        if ctx['path']:
            system_parts.append(f"\n## Learning Path\n{ctx['path']}")
        if ctx['memory']:
            system_parts.append(f"\n## Conversation Memory\n{ctx['memory']}")

        user_parts = []
        if ctx['rag']:
            user_parts.append(f"## Retrieved Context\n{ctx['rag']}")
        if ctx['backpack']:
            user_parts.append(f"## Learner's Backpack Notes\n{ctx['backpack']}")
        user_parts.append(f"\n## Question\n{ctx['query']}")

        return {
            'system': "\n".join(system_parts),
            'user': "\n\n".join(user_parts),
        }

    # -- Static tier --

    def _build_system(self) -> str:
        if self.scope == "curator":
            return _truncate_to_tokens(
                self.CURATOR_PERSONA, TOKEN_BUDGET['system']
            )
        return _truncate_to_tokens(
            self.COMPANION_PERSONA, TOKEN_BUDGET['system']
        )

    def _build_profile(self) -> str:
        parts = []

        # EPP summary from tory_learner_profiles
        epp = self._get_epp_summary()
        if epp:
            parts.append(epp)

        # Onboarding Q&A
        qa = self._get_onboarding_qa()
        if qa:
            parts.append(qa)

        # Profile narrative
        narrative = self._get_profile_narrative()
        if narrative:
            parts.append(f"Narrative: {narrative}")

        return _truncate_to_tokens("\n".join(parts), TOKEN_BUDGET['profile'])

    def _build_path(self) -> str:
        rows = _db_query(
            f"SELECT r.sequence, r.status, r.rationale, "
            f"l.lesson_name, j.journey_name "
            f"FROM tory_recommendations r "
            f"JOIN nx_lessons l ON r.nx_lesson_id = l.id "
            f"LEFT JOIN nx_journeys j ON l.journey_id = j.id "
            f"WHERE r.nx_user_id = {int(self.nx_user_id)} "
            f"AND r.deleted_at IS NULL "
            f"ORDER BY r.sequence LIMIT 20"
        )
        if not rows:
            return ""

        lines = []
        for r in rows:
            status_marker = "[done]" if r.get("status") == "completed" else "[ ]"
            name = r.get("lesson_name", "Unknown")
            journey = r.get("journey_name", "")
            seq = r.get("sequence", "?")
            lines.append(f"{seq}. {status_marker} {name} ({journey})")

        return _truncate_to_tokens("\n".join(lines), TOKEN_BUDGET['path'])

    # -- Dynamic tier --

    def _build_rag(self, chunks: Optional[List[Dict]]) -> str:
        if not chunks:
            return ""
        parts = []
        for i, chunk in enumerate(chunks[:DEFAULT_TOP_K], 1):
            content = chunk.get('content', '')
            source = chunk.get('metadata', {}).get('source', 'lesson')
            score = chunk.get('adjusted_score', chunk.get('similarity_score', 0))
            parts.append(
                f"[Source {i}: {source} (relevance: {score:.2f})]\n{content}"
            )
        return _truncate_to_tokens("\n\n".join(parts), TOKEN_BUDGET['rag'])

    def _build_backpack(self, entries: Optional[List[Dict]]) -> str:
        if not entries:
            return ""
        parts = []
        for entry in entries[:10]:
            content = entry.get('content', '')
            parts.append(f"- {content[:200]}")
        return _truncate_to_tokens("\n".join(parts), TOKEN_BUDGET['backpack'])

    # -- Memory tier --

    def _build_memory(self, memory) -> str:
        if memory is None:
            return ""
        # ThreeTierMemory from chat_manager.py
        if hasattr(memory, 'get_context_string'):
            ctx = memory.get_context_string()
            recent = memory.get_recent_messages()
            parts = []
            if ctx:
                parts.append(ctx)
            if recent:
                msgs = [
                    f"{m['role']}: {m['content'][:150]}"
                    for m in recent[-10:]
                ]
                parts.append("Recent exchange:\n" + "\n".join(msgs))
            return _truncate_to_tokens("\n".join(parts), TOKEN_BUDGET['memory'])
        return ""

    # -- DB helpers --

    def _get_epp_summary(self) -> str:
        if 'epp' in self._cache:
            return self._cache['epp']

        rows = _db_query(
            f"SELECT epp_summary, trait_vector "
            f"FROM tory_learner_profiles "
            f"WHERE nx_user_id = {int(self.nx_user_id)} "
            f"ORDER BY created_at DESC LIMIT 1"
        )
        if not rows:
            self._cache['epp'] = ""
            return ""

        summary = rows[0].get("epp_summary", "")
        self._cache['epp'] = summary
        return summary

    def _get_onboarding_qa(self) -> str:
        if 'qa' in self._cache:
            return self._cache['qa']

        rows = _db_query(
            f"SELECT question, answer "
            f"FROM nx_user_onboardings "
            f"WHERE user_id = {int(self.nx_user_id)} "
            f"ORDER BY id LIMIT 10"
        )
        if not rows:
            self._cache['qa'] = ""
            return ""

        parts = []
        for r in rows:
            q = r.get("question", "")
            a = r.get("answer", "")
            if q and a:
                parts.append(f"Q: {q}\nA: {a}")

        result = "\n".join(parts)
        self._cache['qa'] = result
        return result

    def _get_profile_narrative(self) -> str:
        if 'narrative' in self._cache:
            return self._cache['narrative']

        rows = _db_query(
            f"SELECT profile_narrative "
            f"FROM tory_learner_profiles "
            f"WHERE nx_user_id = {int(self.nx_user_id)} "
            f"ORDER BY created_at DESC LIMIT 1"
        )
        if not rows:
            self._cache['narrative'] = ""
            return ""

        narrative = rows[0].get("profile_narrative", "")
        self._cache['narrative'] = narrative
        return narrative


# ============================================================================
# TierRouter
# ============================================================================

class TierRouter:
    """
    Decide whether a query should use Sonnet (default) or Opus (premium).

    Upgrade to Opus when:
    - Keywords: "why", "analyze", "compare", "deep dive", "explain the reasoning"
    - Retrieved context exceeds 8K tokens
    - Question references 3+ different lessons
    """

    UPGRADE_KEYWORDS = [
        "why", "analyze", "compare", "deep dive", "explain the reasoning",
        "what's the difference", "evaluate", "critically", "in depth",
        "trade-off", "tradeoff", "pros and cons", "root cause",
    ]

    CONTEXT_TOKEN_THRESHOLD = 8000
    LESSON_REF_THRESHOLD = 3

    def route(
        self,
        query: str,
        rag_chunks: Optional[List[Dict]] = None,
        context_text: str = "",
    ) -> Dict[str, Any]:
        """
        Returns {model, reason, score} where score is 0.0-1.0.
        Score >= 0.7 triggers Opus.
        """
        score = 0.0
        reasons = []

        # Check keywords
        query_lower = query.lower()
        matched_keywords = [
            kw for kw in self.UPGRADE_KEYWORDS if kw in query_lower
        ]
        if matched_keywords:
            score += 0.4
            reasons.append(f"complexity_keywords: {matched_keywords[:3]}")

        # Check context size
        context_tokens = len(context_text) // CHARS_PER_TOKEN
        if context_tokens > self.CONTEXT_TOKEN_THRESHOLD:
            score += 0.3
            reasons.append(f"large_context: {context_tokens} tokens")

        # Check lesson references in query
        if rag_chunks:
            lesson_ids = set()
            for chunk in rag_chunks:
                lid = chunk.get('metadata', {}).get('nx_lesson_id')
                if lid:
                    lesson_ids.add(lid)
            if len(lesson_ids) >= self.LESSON_REF_THRESHOLD:
                score += 0.3
                reasons.append(f"multi_lesson: {len(lesson_ids)} lessons")

        use_opus = score >= 0.7
        model = OPUS_MODEL if use_opus else SONNET_MODEL

        return {
            'model': model,
            'use_opus': use_opus,
            'score': round(score, 2),
            'reasons': reasons,
        }


# ============================================================================
# GuardrailsChecker
# ============================================================================

class GuardrailsChecker:
    """
    Post-processing safety checks on LLM responses.

    Checks:
    1. No content fabrication (citations must trace to real chunks)
    2. No data leakage (other learner IDs in response)
    3. Scope enforcement (Companion: assigned lessons only)
    4. Distress detection (escalation keywords)
    """

    DISTRESS_KEYWORDS = [
        "harm", "hopeless", "give up", "suicide", "self-harm",
        "kill myself", "end it all", "worthless", "no point",
        "can't go on", "want to die",
    ]

    ESCALATION_MESSAGE = (
        "I can sense you may be going through a difficult time. "
        "Please reach out to your coach or a trusted person for support. "
        "If you're in crisis, please contact a helpline in your area. "
        "Your wellbeing matters most."
    )

    def __init__(self, nx_user_id: int, scope: str = "companion"):
        self.nx_user_id = nx_user_id
        self.scope = scope

    def check(
        self,
        response: str,
        query: str,
        rag_chunks: Optional[List[Dict]] = None,
        assigned_lesson_ids: Optional[set] = None,
    ) -> Dict[str, Any]:
        """
        Run all guardrail checks. Returns:
        {
            passed: bool,
            response: str (possibly modified),
            flags: [list of triggered checks],
            escalate: bool,
        }
        """
        flags = []
        modified_response = response
        escalate = False

        # 1. Distress detection (check query AND response)
        distress_result = self._check_distress(query)
        if distress_result:
            flags.append(distress_result)
            escalate = True
            modified_response = (
                f"{self.ESCALATION_MESSAGE}\n\n{modified_response}"
            )

        # 2. Data leakage check
        leakage = self._check_data_leakage(response)
        if leakage:
            flags.append(leakage)
            modified_response = self._redact_leakage(modified_response)

        # 3. Fabrication check
        fabrication = self._check_fabrication(response, rag_chunks)
        if fabrication:
            flags.append(fabrication)

        # 4. Scope enforcement (Companion only)
        if self.scope == "companion" and assigned_lesson_ids:
            scope_violation = self._check_scope(response, assigned_lesson_ids)
            if scope_violation:
                flags.append(scope_violation)

        passed = len(flags) == 0 or (
            len(flags) == 1 and flags[0].get('severity') == 'info'
        )

        return {
            'passed': passed,
            'response': modified_response,
            'flags': flags,
            'escalate': escalate,
        }

    def _check_distress(self, text: str) -> Optional[Dict]:
        text_lower = text.lower()
        found = [kw for kw in self.DISTRESS_KEYWORDS if kw in text_lower]
        if found:
            return {
                'check': 'distress_detection',
                'severity': 'critical',
                'keywords': found,
                'action': 'escalate_to_coach',
            }
        return None

    def _check_data_leakage(self, response: str) -> Optional[Dict]:
        # Look for patterns like "user_id=123" or "nx_user_id: 456"
        id_pattern = r'(?:user_id|nx_user_id|learner_id)\s*[=:]\s*(\d+)'
        matches = re.findall(id_pattern, response, re.IGNORECASE)
        leaked_ids = [
            int(m) for m in matches if int(m) != self.nx_user_id
        ]
        if leaked_ids:
            return {
                'check': 'data_leakage',
                'severity': 'high',
                'leaked_ids': leaked_ids,
                'action': 'redact',
            }
        return None

    def _redact_leakage(self, response: str) -> str:
        """Remove other users' IDs from the response."""
        def _redact_match(match):
            found_id = int(match.group(1))
            if found_id != self.nx_user_id:
                return match.group(0).replace(match.group(1), "[REDACTED]")
            return match.group(0)

        pattern = r'(?:user_id|nx_user_id|learner_id)\s*[=:]\s*(\d+)'
        return re.sub(pattern, _redact_match, response, flags=re.IGNORECASE)

    def _check_fabrication(
        self, response: str, rag_chunks: Optional[List[Dict]]
    ) -> Optional[Dict]:
        if not rag_chunks:
            return None

        # Check for specific citation patterns like [Source 1], [1], etc.
        citation_pattern = r'\[(?:Source\s+)?(\d+)\]'
        cited_indices = [
            int(m) for m in re.findall(citation_pattern, response)
        ]

        if cited_indices:
            max_valid = len(rag_chunks)
            invalid = [i for i in cited_indices if i > max_valid or i < 1]
            if invalid:
                return {
                    'check': 'fabrication',
                    'severity': 'medium',
                    'invalid_citations': invalid,
                    'max_valid': max_valid,
                    'action': 'warn',
                }
        return None

    def _check_scope(
        self, response: str, assigned_lesson_ids: set
    ) -> Optional[Dict]:
        # Look for lesson ID references in the response
        lesson_pattern = r'lesson[_\s]*(?:id)?[:\s]*(\d+)'
        mentioned_ids = {
            int(m) for m in re.findall(lesson_pattern, response, re.IGNORECASE)
        }
        out_of_scope = mentioned_ids - assigned_lesson_ids
        if out_of_scope:
            return {
                'check': 'scope_violation',
                'severity': 'medium',
                'out_of_scope_lessons': list(out_of_scope),
                'action': 'warn',
            }
        return None


# ============================================================================
# ResponseFormatter
# ============================================================================

class ResponseFormatter:
    """
    Format LLM responses for different output targets.
    Modes: markdown (web), plain_text (mobile), structured_json (API)
    """

    def format(
        self,
        response: str,
        mode: str = "markdown",
        metadata: Optional[Dict] = None,
    ) -> Any:
        if mode == "plain_text":
            return self._to_plain_text(response)
        elif mode == "structured_json":
            return self._to_structured_json(response, metadata)
        else:
            return self._to_markdown(response)

    def _to_markdown(self, response: str) -> str:
        """Return response as-is (LLMs already produce markdown)."""
        return response.strip()

    def _to_plain_text(self, response: str) -> str:
        """Strip markdown formatting for mobile display."""
        text = response
        # Remove headers
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # Remove bold/italic
        text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
        # Remove inline code
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # Remove links, keep text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Remove images
        text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
        # Collapse multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _to_structured_json(
        self, response: str, metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Structured JSON output for API consumers."""
        # Split response into paragraphs
        paragraphs = [
            p.strip() for p in response.split('\n\n') if p.strip()
        ]

        result = {
            'content': response.strip(),
            'paragraphs': paragraphs,
            'word_count': len(response.split()),
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        }
        if metadata:
            result['metadata'] = metadata
        return result
