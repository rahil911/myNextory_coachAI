"""
AI Instantiation Flow for MyNextory
The visible "birth" of a learner's AI — 5-step process that streams
reasoning to the coach via a callback.

Steps:
  1. Read & Interpret EPP (personality assessment)
  2. Read & Interpret Onboarding Q&A
  3. Form the Learner Model (synthesis)
  4. Build the Path (with live reasoning per lesson)
  5. Generate Coaching Prompts

Each step:
  - Calls Claude API via model_harness
  - Produces visible reasoning text
  - Stores step result in session via session_manager
  - Supports idempotent recovery (resume from last completed step)

Usage:
    from instantiation import InstantiationEngine

    engine = InstantiationEngine()
    result = engine.run(nx_user_id=123, on_event=my_callback)
    # on_event receives: {type: 'step_start'|'reasoning'|'step_complete'|...}
"""

import json
import time
from typing import Any, Callable, Dict, List, Optional

import structlog
from anthropic import Anthropic

from rag_config import (
    ANTHROPIC_API_KEY,
    DATABASE,
    DB_QUERY_TIMEOUT,
    OPUS_MODEL,
    SONNET_MODEL,
    EPP_PERSONALITY_DIMS,
    OPUS_INPUT_PRICE_PER_1K,
    OPUS_OUTPUT_PRICE_PER_1K,
)
from session_manager import SessionManager, _db_query

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------

STEPS = [
    {"name": "read_epp", "label": "Read & Interpret EPP"},
    {"name": "read_onboarding", "label": "Read & Interpret Onboarding Q&A"},
    {"name": "form_model", "label": "Form the Learner Model"},
    {"name": "build_path", "label": "Build the Learning Path"},
    {"name": "generate_prompts", "label": "Generate Coaching Prompts"},
]

# ---------------------------------------------------------------------------
# System prompts for each step
# ---------------------------------------------------------------------------

INSTANTIATION_SYSTEM = """You are Tory, an AI coaching intelligence performing a learner instantiation.
You are reading data about a learner and forming a mental model of who they are.
Speak in first person as the AI ("I'm reading...", "I see that...").
Be analytical but warm. Reference specific numbers and patterns.
The coach is watching you think — be transparent about your reasoning."""

STEP1_PROMPT = """Read this learner's EPP (Employee Personality Profile) assessment data.
Narrate your analysis as you read each dimension. Call out:
- The 2-3 highest scores (strengths to leverage)
- The 2-3 lowest scores (gaps to develop)
- Notable tension pairs (e.g., high Achievement + low SelfConfidence = imposter pattern)
- What this profile suggests about how the learner operates

EPP Dimension Reference:
- Below 30: Significant gap
- 30-50: Below average
- 50-70: Average
- Above 70: Clear strength

Key tension pairs to watch:
- Achievement + SelfConfidence: imposter syndrome pattern
- Assertiveness + Cooperativeness: leadership vs harmony tension
- Competitiveness + Cooperativeness: winning vs team tension
- Motivation + Patience: burnout risk
- Openness + Conscientiousness: ideas vs follow-through

Learner: {learner_name} (ID: {nx_user_id})

EPP Scores:
{epp_data}

Narrate your reading of this assessment. Be specific with numbers."""

STEP2_PROMPT = """Now read this learner's onboarding Q&A responses.
Cross-reference what they said with the EPP profile you just analyzed.
Look for:
- Consistency between what they say and what the EPP shows
- Interesting tensions or contradictions
- What motivates them in their own words
- How they see themselves vs how the EPP sees them

Learner: {learner_name}
EPP Profile Summary (from Step 1): {epp_summary}

Onboarding Responses:
{qa_data}

Narrate your reading of these responses. Connect them to the EPP scores."""

STEP3_PROMPT = """Synthesize everything you know about this learner into a cohesive narrative.
You have:
1. Their EPP personality profile (29 dimensions)
2. Their onboarding Q&A responses (their own words)

Create a learner model that captures:
- WHO they are (personality sketch in 2-3 sentences)
- What DRIVES them (motivation cluster)
- Their STRENGTHS (what to leverage in coaching)
- Their GAPS (what to develop, with care)
- Key TENSIONS (conflicting traits that need coaching attention)
- COACHING APPROACH (how to work with this specific learner)

Learner: {learner_name}
EPP Analysis: {epp_summary}
Q&A Analysis: {qa_summary}

Write a comprehensive but concise learner model. This will guide all future path decisions."""

STEP4_PROMPT = """Now build a learning path for this learner.
You have their full profile and a library of scored lessons.

For EACH lesson you recommend, explain:
1. WHY this lesson (which EPP traits does it target?)
2. WHY this position (what comes before/after and why?)
3. Is this a STRENGTH lesson (leveraging what they're good at) or a GAP lesson (developing a weakness)?
4. What should the coach watch for when this learner takes this lesson?

Rules:
- Start with lower-difficulty, reflective lessons (build safety first)
- Alternate between gap and strength lessons (don't overwhelm with gaps)
- Max 3 consecutive lessons from the same journey
- First 3-5 lessons are "discovery phase" — exploratory, low-stakes

Learner: {learner_name}
Learner Model: {learner_model}

Available Lessons (scored by relevance):
{scored_lessons}

Build and explain the path. For each lesson, state your reasoning."""

STEP5_PROMPT = """Generate personalized coaching prompts for this learner's coach.

Based on the learner's profile and the path you just built, create:

1. **Session openers** (3): Questions to start coaching sessions that connect to this learner's profile
2. **Per-lesson prompts** (for the first 5 path items): Specific questions or watch-points for each lesson
3. **Red flags to watch**: Behavioral signals that indicate the learner is struggling
4. **Encouragement anchors**: Specific strengths to reference when the learner needs a boost

Learner: {learner_name}
Learner Model: {learner_model}
Path Built: {path_summary}

Generate the coaching prompts. Be specific — reference their EPP scores and onboarding answers."""


# ============================================================================
# Data loaders
# ============================================================================

def _get_learner_name(nx_user_id: int) -> str:
    """Get learner's display name."""
    rows = _db_query(
        f"SELECT first_name, last_name, email "
        f"FROM nx_users WHERE id = {int(nx_user_id)} LIMIT 1"
    )
    if rows:
        parts = [rows[0].get("first_name", ""), rows[0].get("last_name", "")]
        name = " ".join(p for p in parts if p).strip()
        return name or rows[0].get("email", f"User {nx_user_id}")
    return f"User {nx_user_id}"


def _get_epp_data(nx_user_id: int) -> Dict[str, Any]:
    """Load EPP data from tory_learner_profiles or raw onboarding."""
    # Try interpreted profile first
    rows = _db_query(
        f"SELECT epp_summary, trait_vector FROM tory_learner_profiles "
        f"WHERE nx_user_id = {int(nx_user_id)} AND deleted_at IS NULL "
        f"ORDER BY version DESC LIMIT 1"
    )
    if rows and rows[0].get("epp_summary"):
        try:
            return {"scores": json.loads(rows[0]["epp_summary"]), "source": "tory_profile"}
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback: raw assessment from onboarding
    rows = _db_query(
        f"SELECT assesment_result FROM nx_user_onboardings "
        f"WHERE nx_user_id = {int(nx_user_id)} AND deleted_at IS NULL "
        f"ORDER BY id DESC LIMIT 1"
    )
    if not rows or not rows[0].get("assesment_result"):
        return {"scores": {}, "source": "none"}

    try:
        data = json.loads(rows[0]["assesment_result"])
        scores_raw = data.get("scores", {})
    except (json.JSONDecodeError, TypeError):
        return {"scores": {}, "source": "none"}

    epp = {}
    for dim in EPP_PERSONALITY_DIMS:
        val = scores_raw.get(f"EPP{dim}")
        if val is not None and val is not False:
            try:
                epp[dim] = float(val)
            except (ValueError, TypeError):
                pass

    jobfit_map = {
        "Accounting": "Accounting_JobFit", "AdminAsst": "AdminAsst_JobFit",
        "Analyst": "Analyst_JobFit", "BankTeller": "BankTeller_JobFit",
        "Collections": "Collections_JobFit", "CustomerService": "CustomerService_JobFit",
        "FrontDesk": "FrontDesk_JobFit", "Manager": "Manager_JobFit",
        "MedicalAsst": "MedicalAsst_JobFit", "Production": "Production_JobFit",
        "Programmer": "Programmer_JobFit", "Sales": "Sales_JobFit",
    }
    for raw_key, canonical in jobfit_map.items():
        val = scores_raw.get(raw_key)
        if val is not None and val is not False:
            try:
                epp[canonical] = float(val)
            except (ValueError, TypeError):
                pass

    return {"scores": epp, "source": "raw_assessment"}


def _get_onboarding_qa(nx_user_id: int) -> List[Dict[str, str]]:
    """Load onboarding Q&A responses."""
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
        f"WHERE nx_user_id = {int(nx_user_id)} AND deleted_at IS NULL "
        f"ORDER BY id DESC LIMIT 1"
    )
    if not rows:
        return []

    row = rows[0]
    result = []
    for field_name, label in qa_fields:
        val = row.get(field_name, "")
        if val and val.strip():
            parsed = val.strip()
            if parsed.startswith("["):
                try:
                    arr = json.loads(parsed)
                    if isinstance(arr, list):
                        parsed = ", ".join(str(x) for x in arr)
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append({"field": field_name, "label": label, "value": parsed})
    return result


def _get_scored_lessons(nx_user_id: int, limit: int = 30) -> List[Dict]:
    """Get lessons scored by content tags, suitable for path building."""
    rows = _db_query(
        f"SELECT l.id AS lesson_id, l.lesson AS lesson_name, "
        f"j.journey AS journey_name, j.id AS journey_id, "
        f"ct.trait_tags, ct.difficulty, ct.learning_style, "
        f"ct.summary, ct.estimated_minutes, ct.emotional_tone "
        f"FROM nx_lessons l "
        f"LEFT JOIN nx_journey_details j ON l.nx_journey_detail_id = j.id "
        f"LEFT JOIN lesson_details ld ON ld.nx_lesson_id = l.id AND ld.deleted_at IS NULL "
        f"LEFT JOIN tory_content_tags ct ON ct.lesson_detail_id = ld.id AND ct.deleted_at IS NULL "
        f"WHERE l.deleted_at IS NULL AND ct.id IS NOT NULL "
        f"ORDER BY ct.confidence DESC LIMIT {int(limit)}"
    )
    lessons = []
    for r in rows:
        lesson = {
            "lesson_id": int(r.get("lesson_id", 0)),
            "lesson_name": r.get("lesson_name", ""),
            "journey_name": r.get("journey_name", ""),
            "journey_id": int(r.get("journey_id", 0)) if r.get("journey_id") else 0,
            "difficulty": int(r.get("difficulty", 3)) if r.get("difficulty") else 3,
            "learning_style": r.get("learning_style", ""),
            "summary": r.get("summary", ""),
            "estimated_minutes": int(r.get("estimated_minutes", 15)) if r.get("estimated_minutes") else 15,
            "emotional_tone": r.get("emotional_tone", ""),
        }
        # Parse trait_tags JSON
        tt = r.get("trait_tags", "")
        if tt:
            try:
                lesson["trait_tags"] = json.loads(tt)
            except (json.JSONDecodeError, TypeError):
                lesson["trait_tags"] = []
        else:
            lesson["trait_tags"] = []
        lessons.append(lesson)
    return lessons


def _get_existing_path(nx_user_id: int) -> List[Dict]:
    """Get existing tory_recommendations for this learner."""
    rows = _db_query(
        f"SELECT r.id, r.sequence, r.nx_lesson_id, r.status, r.rationale, "
        f"l.lesson AS lesson_name "
        f"FROM tory_recommendations r "
        f"JOIN nx_lessons l ON r.nx_lesson_id = l.id "
        f"WHERE r.nx_user_id = {int(nx_user_id)} AND r.deleted_at IS NULL "
        f"ORDER BY r.sequence LIMIT 30"
    )
    return [{
        "recommendation_id": int(r["id"]),
        "sequence": int(r.get("sequence", 0)),
        "lesson_id": int(r.get("nx_lesson_id", 0)),
        "lesson_name": r.get("lesson_name", ""),
        "status": r.get("status", "pending"),
        "rationale": r.get("rationale", ""),
    } for r in rows]


# ============================================================================
# InstantiationEngine
# ============================================================================

class InstantiationEngine:
    """
    Runs the 5-step AI instantiation flow for a learner.

    Each step calls Claude Opus for deep analysis, stores reasoning in
    the session, and calls on_event() for real-time streaming.
    """

    def __init__(self):
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.session_mgr = SessionManager()

    def run(
        self,
        nx_user_id: int,
        on_event: Optional[Callable] = None,
        session_id: Optional[int] = None,
        initiated_by: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Run the full instantiation flow.

        Args:
            nx_user_id: The learner to instantiate
            on_event: Callback for streaming events
            session_id: Resume an existing session (for idempotent recovery)
            initiated_by: nx_user_id of the coach who triggered this

        Returns:
            {session_id, steps, decisions, cost, completed}
        """
        emit = on_event or (lambda e: None)

        # Load or create session
        if session_id:
            session = self.session_mgr.load_session(session_id)
            if not session:
                session = self._new_session(nx_user_id, initiated_by)
        else:
            session = self._new_session(nx_user_id, initiated_by)

        # Determine which steps are already completed (idempotent recovery)
        completed_steps = {
            s["step"] for s in session.get("steps", [])
            if s.get("status") == "complete"
        }

        learner_name = _get_learner_name(nx_user_id)
        session["metadata"]["learner_name"] = learner_name

        emit({
            "type": "instantiation_start",
            "session_id": session["id"],
            "learner_name": learner_name,
            "nx_user_id": nx_user_id,
            "total_steps": len(STEPS),
            "completed_steps": len(completed_steps),
        })

        # Accumulate context across steps
        context = {
            "learner_name": learner_name,
            "nx_user_id": nx_user_id,
        }

        try:
            # Step 1: Read EPP
            if "read_epp" not in completed_steps:
                result = self._step_read_epp(session, context, emit)
                context["epp_summary"] = result
            else:
                # Load from saved step
                for s in session["steps"]:
                    if s["step"] == "read_epp":
                        context["epp_summary"] = s.get("reasoning", "")

            # Step 2: Read Onboarding Q&A
            if "read_onboarding" not in completed_steps:
                result = self._step_read_onboarding(session, context, emit)
                context["qa_summary"] = result
            else:
                for s in session["steps"]:
                    if s["step"] == "read_onboarding":
                        context["qa_summary"] = s.get("reasoning", "")

            # Step 3: Form Learner Model
            if "form_model" not in completed_steps:
                result = self._step_form_model(session, context, emit)
                context["learner_model"] = result
            else:
                for s in session["steps"]:
                    if s["step"] == "form_model":
                        context["learner_model"] = s.get("reasoning", "")

            # Step 4: Build Path
            if "build_path" not in completed_steps:
                result = self._step_build_path(session, context, emit)
                context["path_summary"] = result
            else:
                for s in session["steps"]:
                    if s["step"] == "build_path":
                        context["path_summary"] = s.get("reasoning", "")

            # Step 5: Generate Coaching Prompts
            if "generate_prompts" not in completed_steps:
                self._step_generate_prompts(session, context, emit)

            # Final save
            self.session_mgr.save(session)

            emit({
                "type": "instantiation_complete",
                "session_id": session["id"],
                "total_cost": round(session.get("estimated_cost_usd", 0), 4),
                "total_steps": len(STEPS),
            })

            return {
                "session_id": session["id"],
                "steps": session.get("steps", []),
                "decisions": session.get("decisions", []),
                "cost_usd": round(session.get("estimated_cost_usd", 0), 4),
                "total_input_tokens": session.get("total_input_tokens", 0),
                "total_output_tokens": session.get("total_output_tokens", 0),
                "completed": True,
            }

        except Exception as e:
            logger.error("instantiation_failed", nx_user_id=nx_user_id, error=str(e))
            # Save progress even on failure (idempotent recovery)
            self.session_mgr.save(session)
            emit({
                "type": "instantiation_error",
                "session_id": session["id"],
                "error": str(e),
            })
            return {
                "session_id": session["id"],
                "steps": session.get("steps", []),
                "decisions": session.get("decisions", []),
                "cost_usd": round(session.get("estimated_cost_usd", 0), 4),
                "completed": False,
                "error": str(e),
            }

    def resume_session(
        self,
        session_id: int,
        message: str,
        on_event: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Resume a completed session with a follow-up question.
        The AI responds in the context of its original reasoning.
        """
        emit = on_event or (lambda e: None)
        session = self.session_mgr.load_session(session_id)
        if not session:
            return {"error": "Session not found"}

        nx_user_id = session["nx_user_id"]

        # Build context from stored session
        steps_context = ""
        for step in session.get("steps", []):
            steps_context += f"\n## Step: {step.get('label', step.get('step', ''))}\n"
            steps_context += step.get("reasoning", "")
            steps_context += "\n"

        decisions_context = ""
        for d in session.get("decisions", []):
            decisions_context += (
                f"- Lesson {d.get('lesson_id')}: {d.get('lesson_name', '')} — "
                f"{d.get('reasoning', '')}\n"
            )

        system_prompt = (
            f"{INSTANTIATION_SYSTEM}\n\n"
            f"## Your Previous Analysis\n"
            f"You previously performed a full instantiation for this learner. "
            f"Here is what you reasoned:\n"
            f"{steps_context}\n"
            f"## Path Decisions Made\n"
            f"{decisions_context}\n"
            f"## Key Facts\n"
            f"{'; '.join(str(f) for f in session.get('key_facts', []))}\n\n"
            f"The coach is now asking a follow-up question about your reasoning. "
            f"Answer in context of your original analysis. Be specific."
        )

        # Build messages with conversation history
        messages = []
        for msg in session.get("messages", [])[-10:]:
            role = msg["role"]
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": msg["content"]})
        messages.append({"role": "user", "content": message})

        emit({"type": "resume_start", "session_id": session_id})

        try:
            response = self.client.messages.create(
                model=OPUS_MODEL,
                max_tokens=2000,
                system=system_prompt,
                messages=messages,
                timeout=90,
            )

            response_text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    response_text += block.text

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # Update session
            self.session_mgr.add_message(session, "human", message)
            self.session_mgr.add_message(session, "ai", response_text)
            self.session_mgr.track_cost(session, input_tokens, output_tokens, OPUS_MODEL)
            self.session_mgr.extract_key_facts(response_text, session)
            self.session_mgr.save(session)

            emit({"type": "resume_complete", "session_id": session_id})

            return {
                "response": response_text,
                "session_id": session_id,
                "model": OPUS_MODEL,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(
                    input_tokens / 1000 * OPUS_INPUT_PRICE_PER_1K +
                    output_tokens / 1000 * OPUS_OUTPUT_PRICE_PER_1K, 4
                ),
            }

        except Exception as e:
            logger.error("resume_failed", session_id=session_id, error=str(e))
            emit({"type": "resume_error", "session_id": session_id, "error": str(e)})
            return {"error": str(e), "session_id": session_id}

    def get_lesson_reasoning(
        self,
        nx_user_id: int,
        lesson_id: int,
    ) -> Optional[Dict]:
        """Get the AI's reasoning for a specific lesson in the path."""
        # Find the most recent instantiation session
        rows = _db_query(
            f"SELECT id FROM tory_ai_sessions "
            f"WHERE nx_user_id = {int(nx_user_id)} AND role = 'curator' "
            f"AND archived_at IS NULL "
            f"ORDER BY last_active_at DESC LIMIT 5"
        )
        for row in rows:
            sid = int(row["id"])
            decision = self.session_mgr.get_step_for_lesson(sid, lesson_id)
            if decision:
                return {
                    "session_id": sid,
                    **decision,
                }
        return None

    # -- Internal: individual steps --

    def _new_session(self, nx_user_id: int, initiated_by: Optional[int]) -> Dict:
        return self.session_mgr.create_session(
            nx_user_id=nx_user_id,
            role="curator",
            session_type="instantiation",
            initiated_by=initiated_by,
            model_tier="opus",
        )

    def _call_claude(
        self,
        session: Dict,
        system: str,
        user_prompt: str,
        emit: Callable,
        step_name: str,
    ) -> tuple:
        """Call Claude Opus and return (response_text, input_tokens, output_tokens)."""
        emit({"type": "api_call_start", "step": step_name, "model": OPUS_MODEL})

        response = self.client.messages.create(
            model=OPUS_MODEL,
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
            timeout=120,
        )

        response_text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                response_text += block.text

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        # Track cost
        self.session_mgr.track_cost(session, input_tokens, output_tokens, OPUS_MODEL)

        # Log tool call for observability
        self.session_mgr.add_tool_call(session, {
            "step": step_name,
            "tool": "claude_api",
            "model": OPUS_MODEL,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        })

        emit({"type": "api_call_complete", "step": step_name, "tokens": input_tokens + output_tokens})
        return response_text, input_tokens, output_tokens

    def _step_read_epp(self, session: Dict, context: Dict, emit: Callable) -> str:
        step_name = "read_epp"
        step_idx = 0
        emit({"type": "step_start", "step": step_name, "step_index": step_idx, "label": STEPS[step_idx]["label"]})

        # Load data
        epp_data = _get_epp_data(context["nx_user_id"])
        scores = epp_data["scores"]

        self.session_mgr.add_tool_call(session, {
            "step": step_name,
            "tool": "load_epp_data",
            "input": {"nx_user_id": context["nx_user_id"]},
            "output": {"score_count": len(scores), "source": epp_data["source"]},
        })

        if not scores:
            reasoning = "No EPP assessment data available for this learner."
            emit({"type": "reasoning", "step": step_name, "text": reasoning})
            self.session_mgr.add_step(session, {
                "step": step_name,
                "label": STEPS[step_idx]["label"],
                "status": "complete",
                "reasoning": reasoning,
                "data": {},
            })
            self.session_mgr.save(session)
            emit({"type": "step_complete", "step": step_name, "step_index": step_idx})
            return reasoning

        # Format scores for the prompt
        personality = {k: v for k, v in scores.items() if not k.endswith("_JobFit")}
        epp_text = "\n".join(
            f"  {dim}: {score} {'[STRENGTH]' if score >= 70 else '[GAP]' if score <= 30 else ''}"
            for dim, score in sorted(personality.items())
        )

        prompt = STEP1_PROMPT.format(
            learner_name=context["learner_name"],
            nx_user_id=context["nx_user_id"],
            epp_data=epp_text,
        )

        reasoning, in_tok, out_tok = self._call_claude(
            session, INSTANTIATION_SYSTEM, prompt, emit, step_name
        )

        emit({"type": "reasoning", "step": step_name, "text": reasoning})

        self.session_mgr.add_step(session, {
            "step": step_name,
            "label": STEPS[step_idx]["label"],
            "status": "complete",
            "reasoning": reasoning,
            "data": {"scores": scores, "source": epp_data["source"]},
            "tokens": {"input": in_tok, "output": out_tok},
        })
        self.session_mgr.extract_key_facts(reasoning, session)
        self.session_mgr.save(session)

        emit({"type": "step_complete", "step": step_name, "step_index": step_idx})
        return reasoning

    def _step_read_onboarding(self, session: Dict, context: Dict, emit: Callable) -> str:
        step_name = "read_onboarding"
        step_idx = 1
        emit({"type": "step_start", "step": step_name, "step_index": step_idx, "label": STEPS[step_idx]["label"]})

        qa_data = _get_onboarding_qa(context["nx_user_id"])

        self.session_mgr.add_tool_call(session, {
            "step": step_name,
            "tool": "load_onboarding_qa",
            "input": {"nx_user_id": context["nx_user_id"]},
            "output": {"answer_count": len(qa_data)},
        })

        if not qa_data:
            reasoning = "No onboarding Q&A responses available for this learner."
            emit({"type": "reasoning", "step": step_name, "text": reasoning})
            self.session_mgr.add_step(session, {
                "step": step_name,
                "label": STEPS[step_idx]["label"],
                "status": "complete",
                "reasoning": reasoning,
                "data": {},
            })
            self.session_mgr.save(session)
            emit({"type": "step_complete", "step": step_name, "step_index": step_idx})
            return reasoning

        qa_text = "\n".join(
            f"  **{qa['label']}**: {qa['value']}" for qa in qa_data
        )

        prompt = STEP2_PROMPT.format(
            learner_name=context["learner_name"],
            epp_summary=context.get("epp_summary", "(No EPP data)")[:2000],
            qa_data=qa_text,
        )

        reasoning, in_tok, out_tok = self._call_claude(
            session, INSTANTIATION_SYSTEM, prompt, emit, step_name
        )

        emit({"type": "reasoning", "step": step_name, "text": reasoning})

        self.session_mgr.add_step(session, {
            "step": step_name,
            "label": STEPS[step_idx]["label"],
            "status": "complete",
            "reasoning": reasoning,
            "data": {"qa_responses": qa_data},
            "tokens": {"input": in_tok, "output": out_tok},
        })
        self.session_mgr.extract_key_facts(reasoning, session)
        self.session_mgr.save(session)

        emit({"type": "step_complete", "step": step_name, "step_index": step_idx})
        return reasoning

    def _step_form_model(self, session: Dict, context: Dict, emit: Callable) -> str:
        step_name = "form_model"
        step_idx = 2
        emit({"type": "step_start", "step": step_name, "step_index": step_idx, "label": STEPS[step_idx]["label"]})

        prompt = STEP3_PROMPT.format(
            learner_name=context["learner_name"],
            epp_summary=context.get("epp_summary", "(No EPP data)")[:2000],
            qa_summary=context.get("qa_summary", "(No Q&A data)")[:2000],
        )

        reasoning, in_tok, out_tok = self._call_claude(
            session, INSTANTIATION_SYSTEM, prompt, emit, step_name
        )

        emit({"type": "reasoning", "step": step_name, "text": reasoning})

        self.session_mgr.add_step(session, {
            "step": step_name,
            "label": STEPS[step_idx]["label"],
            "status": "complete",
            "reasoning": reasoning,
            "tokens": {"input": in_tok, "output": out_tok},
        })
        self.session_mgr.extract_key_facts(reasoning, session)
        self.session_mgr.save(session)

        emit({"type": "step_complete", "step": step_name, "step_index": step_idx})
        return reasoning

    def _step_build_path(self, session: Dict, context: Dict, emit: Callable) -> str:
        step_name = "build_path"
        step_idx = 3
        emit({"type": "step_start", "step": step_name, "step_index": step_idx, "label": STEPS[step_idx]["label"]})

        # Load scored lessons
        scored_lessons = _get_scored_lessons(context["nx_user_id"])

        self.session_mgr.add_tool_call(session, {
            "step": step_name,
            "tool": "load_scored_lessons",
            "input": {"nx_user_id": context["nx_user_id"]},
            "output": {"lesson_count": len(scored_lessons)},
        })

        # Also check existing path
        existing_path = _get_existing_path(context["nx_user_id"])

        self.session_mgr.add_tool_call(session, {
            "step": step_name,
            "tool": "load_existing_path",
            "input": {"nx_user_id": context["nx_user_id"]},
            "output": {"existing_count": len(existing_path)},
        })

        # Format lessons for prompt
        lessons_text = ""
        for i, lesson in enumerate(scored_lessons[:25], 1):
            tags = lesson.get("trait_tags", [])
            tag_str = ", ".join(
                f"{t.get('trait', '?')}({t.get('direction', '?')}:{t.get('relevance_score', '?')})"
                for t in (tags if isinstance(tags, list) else [])
            )
            lessons_text += (
                f"{i}. {lesson['lesson_name']} (Journey: {lesson['journey_name']}, "
                f"Difficulty: {lesson['difficulty']}, Style: {lesson['learning_style']}, "
                f"~{lesson['estimated_minutes']}min)\n"
                f"   Traits: {tag_str}\n"
                f"   Summary: {lesson.get('summary', '')[:100]}\n"
            )

        if existing_path:
            lessons_text += "\n\nExisting path (already assigned):\n"
            for p in existing_path:
                lessons_text += f"  #{p['sequence']}: {p['lesson_name']} ({p['status']})\n"

        prompt = STEP4_PROMPT.format(
            learner_name=context["learner_name"],
            learner_model=context.get("learner_model", "(No model)")[:3000],
            scored_lessons=lessons_text,
        )

        reasoning, in_tok, out_tok = self._call_claude(
            session, INSTANTIATION_SYSTEM, prompt, emit, step_name
        )

        emit({"type": "reasoning", "step": step_name, "text": reasoning})

        # Parse decisions from the reasoning (heuristic extraction)
        decisions = self._extract_path_decisions(reasoning, scored_lessons)
        for d in decisions:
            self.session_mgr.add_decision(session, d)
            emit({
                "type": "decision",
                "step": step_name,
                "lesson_id": d.get("lesson_id"),
                "lesson_name": d.get("lesson_name", ""),
                "reasoning": d.get("reasoning", ""),
            })

        self.session_mgr.add_step(session, {
            "step": step_name,
            "label": STEPS[step_idx]["label"],
            "status": "complete",
            "reasoning": reasoning,
            "decisions": decisions,
            "data": {
                "scored_lesson_count": len(scored_lessons),
                "existing_path_count": len(existing_path),
            },
            "tokens": {"input": in_tok, "output": out_tok},
        })
        self.session_mgr.extract_key_facts(reasoning, session)
        self.session_mgr.save(session)

        emit({"type": "step_complete", "step": step_name, "step_index": step_idx})
        return reasoning

    def _step_generate_prompts(self, session: Dict, context: Dict, emit: Callable) -> str:
        step_name = "generate_prompts"
        step_idx = 4
        emit({"type": "step_start", "step": step_name, "step_index": step_idx, "label": STEPS[step_idx]["label"]})

        prompt = STEP5_PROMPT.format(
            learner_name=context["learner_name"],
            learner_model=context.get("learner_model", "(No model)")[:3000],
            path_summary=context.get("path_summary", "(No path)")[:3000],
        )

        reasoning, in_tok, out_tok = self._call_claude(
            session, INSTANTIATION_SYSTEM, prompt, emit, step_name
        )

        emit({"type": "reasoning", "step": step_name, "text": reasoning})

        self.session_mgr.add_step(session, {
            "step": step_name,
            "label": STEPS[step_idx]["label"],
            "status": "complete",
            "reasoning": reasoning,
            "tokens": {"input": in_tok, "output": out_tok},
        })
        self.session_mgr.extract_key_facts(reasoning, session)
        self.session_mgr.save(session)

        emit({"type": "step_complete", "step": step_name, "step_index": step_idx})
        return reasoning

    def _extract_path_decisions(
        self,
        reasoning: str,
        scored_lessons: List[Dict],
    ) -> List[Dict]:
        """
        Extract per-lesson decisions from the AI's path reasoning.
        Maps lesson names mentioned in the reasoning to lesson IDs.
        """
        decisions = []
        lesson_lookup = {
            l["lesson_name"].lower(): l for l in scored_lessons
        }

        # Split reasoning into paragraphs and look for lesson references
        paragraphs = reasoning.split("\n")
        current_lesson = None
        current_reasoning = []

        for line in paragraphs:
            line_stripped = line.strip()
            if not line_stripped:
                if current_lesson and current_reasoning:
                    decisions.append({
                        "lesson_id": current_lesson["lesson_id"],
                        "lesson_name": current_lesson["lesson_name"],
                        "reasoning": " ".join(current_reasoning),
                    })
                    current_reasoning = []
                continue

            # Check if this line introduces a lesson
            matched_lesson = None
            for name, lesson in lesson_lookup.items():
                if name in line_stripped.lower() or (
                    len(name) > 5 and name[:10] in line_stripped.lower()
                ):
                    matched_lesson = lesson
                    break

            if matched_lesson and matched_lesson != current_lesson:
                # Save previous lesson's reasoning
                if current_lesson and current_reasoning:
                    decisions.append({
                        "lesson_id": current_lesson["lesson_id"],
                        "lesson_name": current_lesson["lesson_name"],
                        "reasoning": " ".join(current_reasoning),
                    })
                current_lesson = matched_lesson
                current_reasoning = [line_stripped]
            elif current_lesson:
                current_reasoning.append(line_stripped)

        # Don't forget the last one
        if current_lesson and current_reasoning:
            decisions.append({
                "lesson_id": current_lesson["lesson_id"],
                "lesson_name": current_lesson["lesson_name"],
                "reasoning": " ".join(current_reasoning),
            })

        return decisions


# ============================================================================
# Status checker for in-progress instantiations
# ============================================================================

def get_instantiation_status(nx_user_id: int) -> Optional[Dict]:
    """Check if there's an active instantiation session and return its progress."""
    rows = _db_query(
        f"SELECT id FROM tory_ai_sessions "
        f"WHERE nx_user_id = {int(nx_user_id)} AND role = 'curator' "
        f"AND archived_at IS NULL "
        f"ORDER BY last_active_at DESC LIMIT 1"
    )
    if not rows:
        return None

    session_id = int(rows[0]["id"])
    mgr = SessionManager()
    session = mgr.load_session(session_id)
    if not session:
        return None

    steps = session.get("steps", [])
    if not steps:
        return None

    session_type = session.get("metadata", {}).get("type") or session.get("type", "")
    if session_type != "instantiation" and not any(s.get("step") == "read_epp" for s in steps):
        return None

    completed_steps = [s for s in steps if s.get("status") == "complete"]
    total_steps = len(STEPS)

    return {
        "session_id": session_id,
        "total_steps": total_steps,
        "completed_steps": len(completed_steps),
        "steps": [{
            "step": s.get("step", ""),
            "label": s.get("label", ""),
            "status": s.get("status", "pending"),
        } for s in steps],
        "is_complete": len(completed_steps) >= total_steps,
        "cost_usd": round(session.get("estimated_cost_usd", 0), 4),
    }
