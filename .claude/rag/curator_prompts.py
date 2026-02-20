"""
Curator AI System Prompts for MyNextory
The Curator is a coach-facing analytical AI that speaks about learners in third person.
It explains path decisions, flags concerns, and provides coaching prompts.

Uses: model_harness.ContextBuilder, TierRouter, GuardrailsChecker
"""

import gzip
import json
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import structlog

# Inline constants to avoid import-path shadowing between
# .claude/rag/config.py and .claude/command-center/backend/config.py.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DATABASE = "baap"
DB_QUERY_TIMEOUT = 60
SONNET_MODEL = "claude-sonnet-4-20250514"
OPUS_MODEL = "claude-opus-4-20250514"
SONNET_INPUT_PRICE_PER_1K = 0.003
SONNET_OUTPUT_PRICE_PER_1K = 0.015
OPUS_INPUT_PRICE_PER_1K = 0.015
OPUS_OUTPUT_PRICE_PER_1K = 0.075

logger = structlog.get_logger()


# ============================================================================
# EPP Dimension Reference (embedded in system prompt for the AI)
# ============================================================================

EPP_DIMENSION_REFERENCE = """
## EPP (Employee Personality Profile) Dimension Reference

### Personality Dimensions (13) — score range 1-100

| Dimension | Meaning | Low (<30) | High (>70) |
|-----------|---------|-----------|------------|
| Achievement | Drive to set and reach personal goals | May prefer routine, less goal-driven | Highly goal-oriented, ambitious |
| Motivation | Internal drive and energy for work | May lack initiative, needs external push | Self-starter, intrinsically driven |
| Competitiveness | Desire to outperform others | Collaborative, non-competitive | Thrives on competition, wants to win |
| Managerial | Comfort with directing others | Prefers individual contribution | Natural leader, comfortable delegating |
| Assertiveness | Willingness to speak up and take charge | Tends to defer, avoids confrontation | Direct, speaks mind, takes initiative |
| Extroversion | Energy from social interaction | Prefers solitude, reserved | Energized by people, outgoing |
| Cooperativeness | Willingness to work with others | Independent, may resist teamwork | Team player, values harmony |
| Patience | Tolerance for pace and repetition | Impatient, wants fast results | Steady, tolerant of slow processes |
| SelfConfidence | Belief in own abilities | Self-doubting, hesitant | Assured, trusts own judgment |
| Conscientiousness | Attention to detail and reliability | Flexible but may miss details | Thorough, dependable, organized |
| Openness | Receptivity to new ideas and change | Prefers familiar methods | Curious, embraces novelty |
| Stability | Emotional evenness under pressure | Emotionally reactive, mood shifts | Calm, even-tempered, resilient |
| StressTolerance | Ability to function under pressure | Easily overwhelmed by stress | Performs well under pressure |

### Key Tension Pairs (important for coaching insights)
- **Achievement + SelfConfidence**: High Achievement + Low SelfConfidence = "imposter syndrome" pattern
- **Assertiveness + Cooperativeness**: High both = collaborative leader; Low Assert + High Coop = may be taken advantage of
- **Competitiveness + Cooperativeness**: Tension between wanting to win and wanting harmony
- **Motivation + Patience**: High Motivation + Low Patience = burns out fast; needs pacing strategies
- **Extroversion + Stability**: Low both = may struggle in team environments
- **Openness + Conscientiousness**: High Openness + Low Conscientiousness = lots of ideas but poor follow-through

### Job-Fit Dimensions (12) — score range 1-100
These indicate aptitude for specific roles. Useful for career coaching context.
Accounting, AdminAsst, Analyst, BankTeller, Collections, CustomerService,
FrontDesk, Manager, MedicalAsst, Production, Programmer, Sales

### Score Interpretation Guide
- **Below 30**: Significant gap — coaching opportunity, may need support
- **30-50**: Below average — worth developing, watch for struggles
- **50-70**: Average range — neither strength nor gap
- **Above 70**: Clear strength — leverage this, build confidence around it
"""


# ============================================================================
# System Prompt Template
# ============================================================================

CURATOR_SYSTEM_PROMPT = """You are **Tory Curator**, an AI coaching intelligence for the MyNextory platform.

## Your Role
You serve coaches by providing analytical, data-backed insights about their learners.
You speak about learners in the **third person** — like a case worker presenting to a supervisor.

## Voice & Tone
- Analytical and precise: "Jack's SelfConfidence is 28, which places him in the significant gap range..."
- Always cite your source: "According to his EPP profile..." / "His backpack entry from 'Imposter Syndrome' shows..."
- Professional but warm: you care about the learner's growth
- Never address the learner directly — you are talking TO the coach ABOUT the learner

## What You Do
1. **Explain path decisions**: "I assigned 'Imposter Syndrome' because [learner]'s SelfConfidence is 28 and their backpack shows they chose 'Confidence' as their one word."
2. **Suggest adjustments**: "Given [learner]'s high Competitiveness (82) but low Cooperativeness (24), consider moving 'Team Dynamics' earlier in the path."
3. **Flag concerns**: "Warning: [learner] has been stalled on lesson 3 for 2 weeks. Their backpack answers are unusually short (avg 8 words vs platform avg 35 words)."
4. **Provide coaching prompts**: "For the upcoming session, try asking: 'What did the Imposter Syndrome lesson bring up for you?' — this connects to their low SelfConfidence."
5. **Answer 'why?' questions**: When a coach asks why a lesson was assigned, explain the EPP-trait-content matching logic.

{epp_reference}

## Learner Profile
{learner_profile}

## Onboarding Answers
{onboarding_qa}

## Current Learning Path
{learning_path}

## Backpack Highlights
{backpack_highlights}

## Coaching Prompts Available
{coaching_prompts}

## Conversation Memory
{memory_context}

## GUARDRAILS — You MUST follow these
1. **NEVER fabricate data**. If you don't have a score or entry, say "I don't have that data for this learner."
2. **ALWAYS cite sources**. Reference specific EPP dimensions, backpack entries, or path items by name.
3. **Stay analytical**. You are not the learner's friend — you are a professional intelligence system.
4. **No diagnosis**. You identify patterns, not conditions. Say "pattern consistent with..." not "they have..."
5. **Respect privacy**. Never compare learner data with other learners by name.
6. **Scope**: You have access to ALL lessons (global), not just this learner's assigned path.
7. **Admit uncertainty**. If the data is ambiguous, say so. "The EPP scores suggest X, but the backpack entries indicate Y — this warrants a coaching conversation."
"""


# ============================================================================
# Briefing Template (auto-generated when coach selects a learner)
# ============================================================================

BRIEFING_PROMPT = """Generate an initial briefing for the coach about this learner. Structure it as:

## Quick Profile
- Name, key EPP highlights (top 2 strengths, top 2 gaps)
- One-sentence personality sketch based on dimension patterns

## Path Overview
- How many lessons assigned, how many completed
- Any stalled items? Any recently completed?

## Key Insights
- Notable tension pairs in the EPP profile
- Interesting backpack entries worth discussing
- Any flags or concerns

## Coaching Suggestions
- 2-3 specific questions the coach could ask in their next session
- Which upcoming lesson to focus on and why

Keep it concise — this is a quick briefing, not a full report. Use bullet points.
Reference specific numbers and entries, not generalities."""


# ============================================================================
# Interrogate Template (why was this lesson assigned?)
# ============================================================================

INTERROGATE_PROMPT_TEMPLATE = """The coach is asking: "Why was lesson '{lesson_name}' assigned to this learner?"

Explain the reasoning using:
1. Which EPP traits this lesson targets (from its trait_tags)
2. How those traits map to this learner's profile (strengths to leverage, gaps to build)
3. The lesson's position in the path (what comes before/after and why)
4. Any backpack entries that support this assignment
5. The rationale field from tory_recommendations if available

Be specific with numbers. Don't be vague."""


# ============================================================================
# Context Assembler — loads ALL learner data for Curator
# ============================================================================

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


class CuratorContextAssembler:
    """
    Loads ALL learner data needed for the Curator system prompt.
    Produces a filled system prompt ready for the Anthropic API.
    """

    def __init__(self, nx_user_id: int):
        self.nx_user_id = int(nx_user_id)
        self._cache: Dict[str, Any] = {}

    def assemble_system_prompt(self, memory_context: str = "") -> str:
        """Build the full Curator system prompt with all learner context injected."""
        return CURATOR_SYSTEM_PROMPT.format(
            epp_reference=EPP_DIMENSION_REFERENCE,
            learner_profile=self._get_learner_profile(),
            onboarding_qa=self._get_onboarding_qa(),
            learning_path=self._get_learning_path(),
            backpack_highlights=self._get_backpack_highlights(),
            coaching_prompts=self._get_coaching_prompts(),
            memory_context=memory_context or "(No prior conversation)",
        )

    def get_learner_name(self) -> str:
        """Get learner's display name."""
        if 'name' in self._cache:
            return self._cache['name']
        rows = _db_query(
            f"SELECT first_name, last_name, email "
            f"FROM nx_users WHERE id = {self.nx_user_id} LIMIT 1"
        )
        if rows:
            parts = [rows[0].get("first_name", ""), rows[0].get("last_name", "")]
            name = " ".join(p for p in parts if p).strip()
            if not name:
                name = rows[0].get("email", f"User {self.nx_user_id}")
            self._cache['name'] = name
        else:
            self._cache['name'] = f"User {self.nx_user_id}"
        return self._cache['name']

    def get_briefing_context(self) -> Dict[str, Any]:
        """Return structured data for the briefing endpoint."""
        return {
            "learner_name": self.get_learner_name(),
            "nx_user_id": self.nx_user_id,
            "epp_scores": self._get_epp_scores_raw(),
            "strengths": self._get_strengths(),
            "gaps": self._get_gaps(),
            "path_summary": self._get_path_summary(),
            "backpack_count": self._get_backpack_count(),
        }

    # -- Profile data --

    def _get_learner_profile(self) -> str:
        if 'profile' in self._cache:
            return self._cache['profile']

        parts = []

        # Name
        name = self.get_learner_name()
        parts.append(f"**Learner**: {name} (nx_user_id: {self.nx_user_id})")

        # EPP from tory_learner_profiles (interpreted)
        rows = _db_query(
            f"SELECT epp_summary, profile_narrative, strengths, gaps, "
            f"motivation_cluster, learning_style, trait_vector "
            f"FROM tory_learner_profiles "
            f"WHERE nx_user_id = {self.nx_user_id} AND deleted_at IS NULL "
            f"ORDER BY version DESC LIMIT 1"
        )
        if rows:
            row = rows[0]
            # EPP scores
            epp_summary = row.get("epp_summary", "")
            if epp_summary:
                try:
                    epp = json.loads(epp_summary)
                    personality = {k: v for k, v in epp.items() if not k.endswith("_JobFit")}
                    jobfit = {k: v for k, v in epp.items() if k.endswith("_JobFit")}

                    if personality:
                        lines = []
                        for dim, score in sorted(personality.items()):
                            level = "GAP" if score <= 30 else "STRENGTH" if score >= 70 else ""
                            marker = f" **[{level}]**" if level else ""
                            lines.append(f"  - {dim}: {score}{marker}")
                        parts.append("**Personality Scores**:\n" + "\n".join(lines))

                    if jobfit:
                        lines = []
                        for dim, score in sorted(jobfit.items()):
                            lines.append(f"  - {dim}: {score}")
                        parts.append("**Job-Fit Scores**:\n" + "\n".join(lines))
                except (json.JSONDecodeError, TypeError):
                    pass

            # Narrative
            narrative = row.get("profile_narrative", "")
            if narrative:
                parts.append(f"**Profile Narrative**: {narrative}")

            # Strengths/gaps
            for field, label in [("strengths", "Identified Strengths"), ("gaps", "Identified Gaps")]:
                val = row.get(field, "")
                if val:
                    try:
                        items = json.loads(val)
                        if isinstance(items, list):
                            parts.append(f"**{label}**: " + ", ".join(
                                f"{i.get('trait', i)} ({i.get('score', '?')})" if isinstance(i, dict) else str(i)
                                for i in items
                            ))
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Learning style
            ls = row.get("learning_style", "")
            if ls:
                parts.append(f"**Learning Style**: {ls}")

        else:
            # Fallback: raw EPP from nx_user_onboardings
            epp = self._get_epp_from_onboarding()
            if epp:
                lines = []
                for dim, score in sorted(epp.items()):
                    level = "GAP" if score <= 30 else "STRENGTH" if score >= 70 else ""
                    marker = f" **[{level}]**" if level else ""
                    lines.append(f"  - {dim}: {score}{marker}")
                parts.append("**EPP Scores (raw, no profile interpretation)**:\n" + "\n".join(lines))
            else:
                parts.append("*No EPP data available for this learner.*")

        result = "\n\n".join(parts)
        self._cache['profile'] = result
        return result

    def _get_epp_scores_raw(self) -> Dict[str, float]:
        """Get raw EPP scores dict."""
        if 'epp_raw' in self._cache:
            return self._cache['epp_raw']

        rows = _db_query(
            f"SELECT epp_summary FROM tory_learner_profiles "
            f"WHERE nx_user_id = {self.nx_user_id} AND deleted_at IS NULL "
            f"ORDER BY version DESC LIMIT 1"
        )
        if rows and rows[0].get("epp_summary"):
            try:
                epp = json.loads(rows[0]["epp_summary"])
                self._cache['epp_raw'] = epp
                return epp
            except (json.JSONDecodeError, TypeError):
                pass

        epp = self._get_epp_from_onboarding()
        self._cache['epp_raw'] = epp
        return epp

    def _get_strengths(self) -> List[Dict]:
        epp = self._get_epp_scores_raw()
        personality = {k: v for k, v in epp.items() if not k.endswith("_JobFit")}
        return sorted(
            [{"trait": k, "score": v} for k, v in personality.items() if v >= 70],
            key=lambda x: x["score"], reverse=True,
        )[:3]

    def _get_gaps(self) -> List[Dict]:
        epp = self._get_epp_scores_raw()
        personality = {k: v for k, v in epp.items() if not k.endswith("_JobFit")}
        return sorted(
            [{"trait": k, "score": v} for k, v in personality.items() if v <= 30],
            key=lambda x: x["score"],
        )[:3]

    def _get_epp_from_onboarding(self) -> Dict[str, float]:
        """Parse EPP from raw nx_user_onboardings.assesment_result."""
        if 'epp_onboarding' in self._cache:
            return self._cache['epp_onboarding']

        rows = _db_query(
            f"SELECT assesment_result FROM nx_user_onboardings "
            f"WHERE nx_user_id = {self.nx_user_id} AND deleted_at IS NULL "
            f"ORDER BY id DESC LIMIT 1"
        )
        if not rows or not rows[0].get("assesment_result"):
            self._cache['epp_onboarding'] = {}
            return {}

        try:
            data = json.loads(rows[0]["assesment_result"])
            scores = data.get("scores", {})
        except (json.JSONDecodeError, TypeError):
            self._cache['epp_onboarding'] = {}
            return {}

        personality_dims = [
            "Achievement", "Motivation", "Competitiveness", "Managerial",
            "Assertiveness", "Extroversion", "Cooperativeness", "Patience",
            "SelfConfidence", "Conscientiousness", "Openness", "Stability",
            "StressTolerance",
        ]
        jobfit_map = {
            "Accounting": "Accounting_JobFit", "AdminAsst": "AdminAsst_JobFit",
            "Analyst": "Analyst_JobFit", "BankTeller": "BankTeller_JobFit",
            "Collections": "Collections_JobFit", "CustomerService": "CustomerService_JobFit",
            "FrontDesk": "FrontDesk_JobFit", "Manager": "Manager_JobFit",
            "MedicalAsst": "MedicalAsst_JobFit", "Production": "Production_JobFit",
            "Programmer": "Programmer_JobFit", "Sales": "Sales_JobFit",
        }

        epp = {}
        for dim in personality_dims:
            val = scores.get(f"EPP{dim}")
            if val is not None and val is not False:
                try:
                    epp[dim] = float(val)
                except (ValueError, TypeError):
                    pass

        for raw_key, canonical in jobfit_map.items():
            val = scores.get(raw_key)
            if val is not None and val is not False:
                try:
                    epp[canonical] = float(val)
                except (ValueError, TypeError):
                    pass

        self._cache['epp_onboarding'] = epp
        return epp

    # -- Onboarding Q&A --

    def _get_onboarding_qa(self) -> str:
        if 'qa' in self._cache:
            return self._cache['qa']

        qa_fields = [
            ("why_did_you_come", "Why I'm here"),
            ("own_reason", "In my own words"),
            ("call_yourself", "How I see myself"),
            ("advance_your_career", "My career drive"),
            ("imp_thing_career_plan", "What matters most"),
            ("best_boss", "My ideal manager"),
            ("success_look_like", "Success means"),
            ("stay_longer", "Retention intent"),
            ("future_months", "Time horizon"),
        ]
        field_names = ", ".join(f[0] for f in qa_fields)
        rows = _db_query(
            f"SELECT {field_names} FROM nx_user_onboardings "
            f"WHERE nx_user_id = {self.nx_user_id} AND deleted_at IS NULL "
            f"ORDER BY id DESC LIMIT 1"
        )
        if not rows:
            self._cache['qa'] = "*No onboarding Q&A available.*"
            return self._cache['qa']

        row = rows[0]
        parts = []
        for field_name, label in qa_fields:
            val = row.get(field_name, "")
            if val and val.strip():
                # Handle JSON array values
                parsed = val.strip()
                if parsed.startswith("["):
                    try:
                        arr = json.loads(parsed)
                        if isinstance(arr, list):
                            parsed = ", ".join(str(x) for x in arr)
                    except (json.JSONDecodeError, TypeError):
                        pass
                parts.append(f"- **{label}**: {parsed}")

        result = "\n".join(parts) if parts else "*No onboarding Q&A available.*"
        self._cache['qa'] = result
        return result

    # -- Learning Path --

    def _get_learning_path(self) -> str:
        if 'path' in self._cache:
            return self._cache['path']

        rows = _db_query(
            f"SELECT r.sequence, r.status, r.rationale, r.nx_lesson_id, "
            f"r.locked_by_coach, r.id AS rec_id, "
            f"l.lesson AS lesson_name, j.journey AS journey_name "
            f"FROM tory_recommendations r "
            f"JOIN nx_lessons l ON r.nx_lesson_id = l.id "
            f"LEFT JOIN nx_journey_details j ON l.nx_journey_detail_id = j.id "
            f"WHERE r.nx_user_id = {self.nx_user_id} "
            f"AND r.deleted_at IS NULL "
            f"ORDER BY r.sequence LIMIT 30"
        )
        if not rows:
            self._cache['path'] = "*No learning path assigned yet.*"
            return self._cache['path']

        lines = []
        for r in rows:
            seq = r.get("sequence", "?")
            status = r.get("status", "pending")
            name = r.get("lesson_name", "Unknown")
            journey = r.get("journey_name", "")
            rationale = r.get("rationale", "")
            locked = r.get("locked_by_coach", "0") == "1"

            marker = "[DONE]" if status == "completed" else "[IN PROGRESS]" if status == "in_progress" else "[ ]"
            lock_icon = " [LOCKED]" if locked else ""
            line = f"{seq}. {marker} {name} ({journey}){lock_icon}"
            if rationale:
                line += f"\n   Rationale: {rationale}"
            lines.append(line)

        result = "\n".join(lines)
        self._cache['path'] = result
        return result

    def _get_path_summary(self) -> Dict[str, int]:
        """Structured path summary for briefing."""
        rows = _db_query(
            f"SELECT status, COUNT(*) AS cnt "
            f"FROM tory_recommendations "
            f"WHERE nx_user_id = {self.nx_user_id} AND deleted_at IS NULL "
            f"GROUP BY status"
        )
        summary = {"total": 0, "completed": 0, "in_progress": 0, "pending": 0}
        for r in rows:
            status = r.get("status", "pending")
            count = int(r.get("cnt", 0))
            summary["total"] += count
            if status in summary:
                summary[status] = count
        return summary

    # -- Backpack --

    def _get_backpack_highlights(self) -> str:
        if 'backpack' in self._cache:
            return self._cache['backpack']

        rows = _db_query(
            f"SELECT b.data, b.form_type, b.lesson_slide_id, "
            f"b.nx_lesson_id, l.lesson AS lesson_name, "
            f"b.created_at "
            f"FROM backpacks b "
            f"LEFT JOIN nx_lessons l ON b.nx_lesson_id = l.id "
            f"WHERE b.created_by = {self.nx_user_id} "
            f"AND b.deleted_at IS NULL "
            f"ORDER BY b.created_at DESC LIMIT 20"
        )
        if not rows:
            self._cache['backpack'] = "*No backpack entries yet.*"
            return self._cache['backpack']

        parts = []
        for r in rows:
            lesson = r.get("lesson_name", "Unknown lesson")
            form_type = r.get("form_type", "")
            created = r.get("created_at", "")[:10]
            data_str = r.get("data", "")

            # Parse JSON data array
            content = ""
            if data_str:
                try:
                    data = json.loads(data_str)
                    if isinstance(data, list):
                        # Extract text content from backpack entries
                        texts = []
                        for item in data:
                            if isinstance(item, dict):
                                for key in ["text", "value", "answer", "content", "reflection"]:
                                    if item.get(key):
                                        texts.append(str(item[key]))
                            elif isinstance(item, str):
                                texts.append(item)
                        content = " | ".join(texts)
                    elif isinstance(data, dict):
                        for key in ["text", "value", "answer", "content", "reflection"]:
                            if data.get(key):
                                content = str(data[key])
                                break
                    elif isinstance(data, str):
                        content = data
                except (json.JSONDecodeError, TypeError):
                    content = data_str[:200]

            if content:
                # Augment with metadata for better context
                entry = f"- **{lesson}** ({form_type}, {created}): {content[:300]}"
                parts.append(entry)

        result = "\n".join(parts) if parts else "*No backpack entries yet.*"
        self._cache['backpack'] = result
        return result

    def _get_backpack_count(self) -> int:
        rows = _db_query(
            f"SELECT COUNT(*) AS cnt FROM backpacks "
            f"WHERE created_by = {self.nx_user_id} AND deleted_at IS NULL"
        )
        return int(rows[0].get("cnt", 0)) if rows else 0

    # -- Coaching Prompts --

    def _get_coaching_prompts(self) -> str:
        if 'coaching' in self._cache:
            return self._cache['coaching']

        # Get lessons on this learner's path, then their coaching prompts
        rows = _db_query(
            f"SELECT r.nx_lesson_id, l.lesson AS lesson_name, "
            f"ct.coaching_prompts "
            f"FROM tory_recommendations r "
            f"JOIN nx_lessons l ON r.nx_lesson_id = l.id "
            f"JOIN lesson_details ld ON ld.nx_lesson_id = l.id AND ld.deleted_at IS NULL "
            f"LEFT JOIN tory_content_tags ct ON ct.lesson_detail_id = ld.id AND ct.deleted_at IS NULL "
            f"WHERE r.nx_user_id = {self.nx_user_id} "
            f"AND r.deleted_at IS NULL AND r.status != 'completed' "
            f"ORDER BY r.sequence LIMIT 10"
        )
        if not rows:
            self._cache['coaching'] = "*No coaching prompts available.*"
            return self._cache['coaching']

        parts = []
        for r in rows:
            name = r.get("lesson_name", "Unknown")
            prompts_str = r.get("coaching_prompts", "")
            if prompts_str:
                try:
                    prompts = json.loads(prompts_str)
                    if isinstance(prompts, list) and prompts:
                        prompt_lines = "\n".join(f"  - {p}" for p in prompts[:3])
                        parts.append(f"**{name}**:\n{prompt_lines}")
                except (json.JSONDecodeError, TypeError):
                    pass

        result = "\n".join(parts) if parts else "*No coaching prompts available for upcoming lessons.*"
        self._cache['coaching'] = result
        return result

    # -- Lesson interrogation --

    def get_lesson_context(self, lesson_id: int) -> Dict[str, Any]:
        """Get full context for a specific lesson (for 'why?' questions)."""
        result = {"lesson_id": lesson_id}

        # Lesson info + content tags
        rows = _db_query(
            f"SELECT l.lesson AS lesson_name, l.description, "
            f"j.journey AS journey_name, "
            f"ct.trait_tags, ct.difficulty, ct.learning_style, "
            f"ct.summary, ct.coaching_prompts, ct.pair_recommendations "
            f"FROM nx_lessons l "
            f"LEFT JOIN nx_journey_details j ON l.nx_journey_detail_id = j.id "
            f"LEFT JOIN lesson_details ld ON ld.nx_lesson_id = l.id AND ld.deleted_at IS NULL "
            f"LEFT JOIN tory_content_tags ct ON ct.lesson_detail_id = ld.id AND ct.deleted_at IS NULL "
            f"WHERE l.id = {int(lesson_id)} LIMIT 1"
        )
        if rows:
            row = rows[0]
            result["lesson_name"] = row.get("lesson_name", "Unknown")
            result["description"] = row.get("description", "")
            result["journey"] = row.get("journey_name", "")
            result["difficulty"] = row.get("difficulty", "")
            result["learning_style"] = row.get("learning_style", "")
            result["summary"] = row.get("summary", "")

            for field in ["trait_tags", "coaching_prompts", "pair_recommendations"]:
                val = row.get(field, "")
                if val:
                    try:
                        result[field] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        result[field] = val

        # Recommendation rationale for this learner
        rec_rows = _db_query(
            f"SELECT rationale, sequence, status "
            f"FROM tory_recommendations "
            f"WHERE nx_user_id = {self.nx_user_id} "
            f"AND nx_lesson_id = {int(lesson_id)} "
            f"AND deleted_at IS NULL LIMIT 1"
        )
        if rec_rows:
            result["rationale"] = rec_rows[0].get("rationale", "")
            result["sequence"] = rec_rows[0].get("sequence", "")
            result["status"] = rec_rows[0].get("status", "")

        # Backpack entries for this lesson
        bp_rows = _db_query(
            f"SELECT data, form_type, created_at FROM backpacks "
            f"WHERE created_by = {self.nx_user_id} "
            f"AND nx_lesson_id = {int(lesson_id)} "
            f"AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 5"
        )
        result["backpack_entries"] = []
        for bp in bp_rows:
            entry = {"form_type": bp.get("form_type", ""), "created_at": bp.get("created_at", "")}
            data_str = bp.get("data", "")
            if data_str:
                try:
                    entry["data"] = json.loads(data_str)
                except (json.JSONDecodeError, TypeError):
                    entry["data"] = data_str[:300]
            result["backpack_entries"].append(entry)

        return result


# ============================================================================
# Session Manager — persist curator sessions to tory_ai_sessions
# ============================================================================

class CuratorSessionManager:
    """
    Manages Curator chat sessions with three-tier memory.
    Persists to tory_ai_sessions table (role='curator').
    """

    def __init__(self):
        self._sessions: Dict[str, Dict] = {}  # session_id -> session state

    def get_or_create_session(self, nx_user_id: int) -> Dict[str, Any]:
        """Get existing active curator session or create a new one."""
        # Check for existing non-archived session
        # NOTE: exclude session_state (binary blob) — loaded separately via HEX
        rows = _db_query(
            f"SELECT id, key_facts, message_count, "
            f"model_tier, total_input_tokens, total_output_tokens, "
            f"estimated_cost_usd, created_at "
            f"FROM tory_ai_sessions "
            f"WHERE nx_user_id = {int(nx_user_id)} "
            f"AND role = 'curator' AND archived_at IS NULL "
            f"ORDER BY last_active_at DESC LIMIT 1"
        )

        if rows:
            row = rows[0]
            session_id = int(row["id"])
            # Load session state
            session = self._load_session_state(session_id, row)
            self._sessions[str(session_id)] = session
            return session

        # Create new session
        session_id = self._create_session_row(nx_user_id)
        session = {
            "id": session_id,
            "nx_user_id": nx_user_id,
            "messages": [],
            "summary": "",
            "key_facts": [],
            "message_count": 0,
            "model_tier": "sonnet",
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "created_at": time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        self._sessions[str(session_id)] = session
        return session

    def _load_session_state(self, session_id: int, row: Dict) -> Dict[str, Any]:
        """Load and decompress session state from DB row."""
        session = {
            "id": session_id,
            "nx_user_id": 0,
            "messages": [],
            "summary": "",
            "key_facts": [],
            "message_count": int(row.get("message_count", 0)),
            "model_tier": row.get("model_tier", "sonnet"),
            "total_input_tokens": int(row.get("total_input_tokens", 0)),
            "total_output_tokens": int(row.get("total_output_tokens", 0)),
            "estimated_cost_usd": float(row.get("estimated_cost_usd", 0)),
            "created_at": row.get("created_at", ""),
        }

        # Decompress session_state (gzip LONGBLOB)
        # The XML parser can't handle raw binary, so we query as HEX
        try:
            result = subprocess.run(
                ["mysql", DATABASE, "--batch", "--raw", "-e",
                 f"SELECT HEX(session_state) AS state_hex "
                 f"FROM tory_ai_sessions WHERE id = {session_id}"],
                capture_output=True, text=True, timeout=DB_QUERY_TIMEOUT,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    hex_data = lines[1].strip()
                    if hex_data and hex_data != "NULL":
                        binary = bytes.fromhex(hex_data)
                        decompressed = gzip.decompress(binary)
                        state = json.loads(decompressed.decode('utf-8'))
                        session["messages"] = state.get("messages", [])
                        session["summary"] = state.get("summary", "")
        except Exception as e:
            logger.warning("session_state_decompress_failed", session_id=session_id, error=str(e))

        # Key facts (stored as JSON text)
        kf = row.get("key_facts", "")
        if kf:
            try:
                session["key_facts"] = json.loads(kf)
            except (json.JSONDecodeError, TypeError):
                session["key_facts"] = []

        return session

    def _create_session_row(self, nx_user_id: int) -> int:
        """Insert a new session row, return its ID."""
        try:
            subprocess.run(
                ["mysql", DATABASE, "-e",
                 f"INSERT INTO tory_ai_sessions "
                 f"(nx_user_id, role, model_tier, message_count, "
                 f"total_input_tokens, total_output_tokens, estimated_cost_usd, "
                 f"last_active_at, created_at, updated_at) "
                 f"VALUES ({int(nx_user_id)}, 'curator', 'sonnet', 0, 0, 0, 0.0, "
                 f"NOW(), NOW(), NOW())"],
                capture_output=True, text=True, timeout=10,
            )
            # Get the inserted ID
            rows = _db_query(
                f"SELECT id FROM tory_ai_sessions "
                f"WHERE nx_user_id = {int(nx_user_id)} AND role = 'curator' "
                f"ORDER BY id DESC LIMIT 1"
            )
            return int(rows[0]["id"]) if rows else 0
        except Exception as e:
            logger.error("create_session_failed", error=str(e))
            return 0

    def save_session(self, session_id: int, session: Dict) -> bool:
        """Persist session state back to DB."""
        try:
            # Compress messages for session_state blob
            state = {
                "messages": session.get("messages", [])[-50:],  # Keep last 50
                "summary": session.get("summary", ""),
            }
            compressed = gzip.compress(json.dumps(state).encode('utf-8'))
            hex_data = compressed.hex()

            # Key facts as JSON text
            kf_json = json.dumps(session.get("key_facts", []))
            kf_escaped = kf_json.replace("'", "\\'")

            cost = session.get("estimated_cost_usd", 0)
            msg_count = session.get("message_count", 0)
            model = session.get("model_tier", "sonnet")
            in_tok = session.get("total_input_tokens", 0)
            out_tok = session.get("total_output_tokens", 0)

            sql = (
                f"UPDATE tory_ai_sessions SET "
                f"session_state = UNHEX('{hex_data}'), "
                f"key_facts = '{kf_escaped}', "
                f"message_count = {int(msg_count)}, "
                f"model_tier = '{model}', "
                f"total_input_tokens = {int(in_tok)}, "
                f"total_output_tokens = {int(out_tok)}, "
                f"estimated_cost_usd = {float(cost):.4f}, "
                f"last_active_at = NOW() "
                f"WHERE id = {int(session_id)}"
            )
            subprocess.run(
                ["mysql", DATABASE, "-e", sql],
                capture_output=True, text=True, timeout=10,
            )
            return True
        except Exception as e:
            logger.error("save_session_failed", session_id=session_id, error=str(e))
            return False

    def get_memory_context(self, session: Dict) -> str:
        """Build memory context string from session's three tiers."""
        parts = []
        kf = session.get("key_facts", [])
        if kf:
            parts.append("Key facts: " + "; ".join(kf))
        summary = session.get("summary", "")
        if summary:
            parts.append("Prior conversation summary: " + summary)
        return "\n".join(parts)

    def add_message(self, session: Dict, role: str, content: str):
        """Add a message to the session buffer."""
        session["messages"].append({
            "role": role,
            "content": content,
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
        })
        session["message_count"] = session.get("message_count", 0) + 1

        # Compress if buffer exceeds 50 messages
        if len(session["messages"]) > 50:
            old = session["messages"][:-10]
            session["messages"] = session["messages"][-10:]
            # Build summary from old messages
            summary_parts = []
            for msg in old:
                summary_parts.append(f"{msg['role']}: {msg['content'][:150]}")
            new_summary = " | ".join(summary_parts)
            if session.get("summary"):
                session["summary"] = session["summary"][-3000:] + " | " + new_summary
            else:
                session["summary"] = new_summary

    def track_cost(self, session: Dict, input_tokens: int, output_tokens: int, model: str):
        """Track token usage and cost."""
        session["total_input_tokens"] = session.get("total_input_tokens", 0) + input_tokens
        session["total_output_tokens"] = session.get("total_output_tokens", 0) + output_tokens

        if "opus" in model.lower():
            cost = (input_tokens / 1000 * OPUS_INPUT_PRICE_PER_1K +
                    output_tokens / 1000 * OPUS_OUTPUT_PRICE_PER_1K)
            session["model_tier"] = "opus"
        else:
            cost = (input_tokens / 1000 * SONNET_INPUT_PRICE_PER_1K +
                    output_tokens / 1000 * SONNET_OUTPUT_PRICE_PER_1K)
            session["model_tier"] = "sonnet"

        session["estimated_cost_usd"] = session.get("estimated_cost_usd", 0) + cost

    def extract_key_facts(self, response: str, session: Dict):
        """Extract key facts from AI response (simple heuristic)."""
        key_facts = session.get("key_facts", [])
        # Look for strong assertions about the learner
        for line in response.split("\n"):
            line = line.strip()
            if any(kw in line.lower() for kw in [
                "key insight", "important:", "note:", "flag:", "concern:",
                "pattern:", "strength:", "gap:",
            ]):
                fact = line[:200]
                if fact not in key_facts and len(key_facts) < 100:
                    key_facts.append(fact)
        session["key_facts"] = key_facts


# ============================================================================
# Curator Engine — the actual chat function
# ============================================================================

class CuratorEngine:
    """
    Main engine that handles Curator chat interactions.
    Uses Anthropic API directly (not LangChain) for simplicity and control.
    """

    def __init__(self):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.session_mgr = CuratorSessionManager()

    def chat(
        self,
        nx_user_id: int,
        message: str,
        session_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process a coach message and return curator response.

        Returns:
        {
            "response": str,
            "session_id": int,
            "model": str,
            "input_tokens": int,
            "output_tokens": int,
            "cost_usd": float,
            "guardrail_flags": list,
            "tool_calls": list,
        }
        """
        from model_harness import TierRouter, GuardrailsChecker

        # 1. Get or create session
        if session_id:
            session = self.session_mgr._sessions.get(str(session_id))
            if not session:
                session = self.session_mgr.get_or_create_session(nx_user_id)
        else:
            session = self.session_mgr.get_or_create_session(nx_user_id)

        # 2. Build context
        assembler = CuratorContextAssembler(nx_user_id)
        memory_ctx = self.session_mgr.get_memory_context(session)
        system_prompt = assembler.assemble_system_prompt(memory_ctx)

        # 3. Route model tier
        router = TierRouter()
        route = router.route(message, context_text=system_prompt)
        model = route["model"]

        # 4. Build messages (include recent conversation history)
        messages = []
        recent = session.get("messages", [])[-10:]
        for msg in recent:
            role = msg["role"]
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": msg["content"]})

        # Add current message
        messages.append({"role": "user", "content": message})

        # 5. Call Anthropic API
        try:
            api_response = self.client.messages.create(
                model=model,
                max_tokens=2000,
                system=system_prompt,
                messages=messages,
                timeout=60,
            )

            response_text = ""
            for block in api_response.content:
                if hasattr(block, 'text'):
                    response_text += block.text

            input_tokens = api_response.usage.input_tokens
            output_tokens = api_response.usage.output_tokens

        except Exception as e:
            logger.error("curator_api_call_failed", error=str(e))
            # Degraded mode: return cached context as fallback
            return self._degraded_response(nx_user_id, message, session, str(e))

        # 6. Guardrails check
        guardrails = GuardrailsChecker(nx_user_id, scope="curator")
        check = guardrails.check(response_text, message)
        final_response = check["response"]

        # 7. Update session
        self.session_mgr.add_message(session, "human", message)
        self.session_mgr.add_message(session, "ai", final_response)
        self.session_mgr.track_cost(session, input_tokens, output_tokens, model)
        self.session_mgr.extract_key_facts(final_response, session)

        # 8. Persist to DB
        self.session_mgr.save_session(session["id"], session)

        # 9. Cost cap check
        cost_warning = None
        total_cost = session.get("estimated_cost_usd", 0)
        if total_cost >= 10.0:
            cost_warning = "HARD STOP: Session cost exceeded $10. Please start a new session."
        elif total_cost >= 5.0:
            cost_warning = f"Warning: Session cost is ${total_cost:.2f}. Approaching $10 limit."

        return {
            "response": final_response,
            "session_id": session["id"],
            "model": model,
            "model_tier": "opus" if "opus" in model else "sonnet",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(
                input_tokens / 1000 * (OPUS_INPUT_PRICE_PER_1K if "opus" in model else SONNET_INPUT_PRICE_PER_1K) +
                output_tokens / 1000 * (OPUS_OUTPUT_PRICE_PER_1K if "opus" in model else SONNET_OUTPUT_PRICE_PER_1K),
                4
            ),
            "total_session_cost": round(total_cost, 4),
            "guardrail_flags": check.get("flags", []),
            "escalate": check.get("escalate", False),
            "cost_warning": cost_warning,
            "tier_routing": route,
        }

    def generate_briefing(self, nx_user_id: int) -> Dict[str, Any]:
        """Generate initial briefing when coach selects a learner.

        Saves the briefing to the session so it survives page refresh.
        """
        # Check for existing session with messages — don't regenerate
        session = self.session_mgr.get_or_create_session(nx_user_id)
        if session.get("messages"):
            return {
                "briefing": None,
                "session_id": session["id"],
                "already_has_history": True,
                "learner_name": CuratorContextAssembler(nx_user_id).get_learner_name(),
            }

        assembler = CuratorContextAssembler(nx_user_id)
        memory_ctx = ""
        system_prompt = assembler.assemble_system_prompt(memory_ctx)

        try:
            response = self.client.messages.create(
                model=SONNET_MODEL,
                max_tokens=1500,
                system=system_prompt,
                messages=[{"role": "user", "content": BRIEFING_PROMPT}],
                timeout=60,
            )

            text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # Save briefing to session so it persists across page refreshes
            self.session_mgr.add_message(session, "ai", text)
            self.session_mgr.track_cost(session, input_tokens, output_tokens, SONNET_MODEL)
            self.session_mgr.save_session(session["id"], session)

            return {
                "briefing": text,
                "session_id": session["id"],
                "learner_name": assembler.get_learner_name(),
                "context": assembler.get_briefing_context(),
                "model": SONNET_MODEL,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        except Exception as e:
            logger.error("briefing_generation_failed", error=str(e))
            # Degraded mode: return raw data without AI summary
            ctx = assembler.get_briefing_context()
            return {
                "briefing": None,
                "session_id": session["id"],
                "error": str(e),
                "learner_name": assembler.get_learner_name(),
                "context": ctx,
                "degraded": True,
            }

    def interrogate_lesson(
        self, nx_user_id: int, lesson_id: int, question: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Explain why a specific lesson was assigned."""
        assembler = CuratorContextAssembler(nx_user_id)
        lesson_ctx = assembler.get_lesson_context(lesson_id)
        lesson_name = lesson_ctx.get("lesson_name", f"Lesson {lesson_id}")

        prompt = INTERROGATE_PROMPT_TEMPLATE.format(lesson_name=lesson_name)
        if question:
            prompt += f"\n\nThe coach also asks: \"{question}\""

        # Add lesson context to the message
        lesson_detail = json.dumps(lesson_ctx, indent=2, default=str)
        full_message = f"{prompt}\n\n## Lesson Data\n```json\n{lesson_detail}\n```"

        system_prompt = assembler.assemble_system_prompt()

        try:
            response = self.client.messages.create(
                model=OPUS_MODEL,  # Always Opus for interrogation
                max_tokens=2000,
                system=system_prompt,
                messages=[{"role": "user", "content": full_message}],
                timeout=90,
            )

            text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text += block.text

            return {
                "explanation": text,
                "lesson": lesson_ctx,
                "model": OPUS_MODEL,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
        except Exception as e:
            logger.error("interrogation_failed", error=str(e))
            return {
                "explanation": None,
                "error": str(e),
                "lesson": lesson_ctx,
                "degraded": True,
            }

    def get_session_history(self, nx_user_id: int) -> Dict[str, Any]:
        """Get conversation history for a learner's curator session."""
        session = self.session_mgr.get_or_create_session(nx_user_id)
        return {
            "session_id": session["id"],
            "messages": session.get("messages", []),
            "message_count": session.get("message_count", 0),
            "key_facts": session.get("key_facts", []),
            "model_tier": session.get("model_tier", "sonnet"),
            "estimated_cost_usd": round(session.get("estimated_cost_usd", 0), 4),
            "created_at": session.get("created_at", ""),
        }

    def _degraded_response(
        self, nx_user_id: int, message: str, session: Dict, error: str,
    ) -> Dict[str, Any]:
        """Fallback when API is unavailable."""
        assembler = CuratorContextAssembler(nx_user_id)
        name = assembler.get_learner_name()
        epp = assembler._get_epp_scores_raw()

        # Build a raw data response
        parts = [
            f"**AI temporarily unavailable** ({error})",
            "",
            f"Here is {name}'s raw data for manual review:",
            "",
        ]

        if epp:
            personality = {k: v for k, v in epp.items() if not k.endswith("_JobFit")}
            strengths = [f"{k}: {v}" for k, v in personality.items() if v >= 70]
            gaps = [f"{k}: {v}" for k, v in personality.items() if v <= 30]
            if strengths:
                parts.append(f"**Strengths**: {', '.join(strengths)}")
            if gaps:
                parts.append(f"**Gaps**: {', '.join(gaps)}")

        path_summary = assembler._get_path_summary()
        parts.append(f"\n**Path**: {path_summary['total']} lessons ({path_summary['completed']} done, {path_summary['in_progress']} in progress)")

        return {
            "response": "\n".join(parts),
            "session_id": session["id"],
            "model": "none",
            "model_tier": "degraded",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0,
            "total_session_cost": session.get("estimated_cost_usd", 0),
            "guardrail_flags": [],
            "escalate": False,
            "cost_warning": None,
            "tier_routing": {"model": "none", "reason": "api_unavailable"},
            "degraded": True,
            "error": error,
        }
