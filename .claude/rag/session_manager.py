"""
Session Manager for MyNextory AI Sessions
Handles creation, persistence, resume, and archival of AI sessions.

Supports three AI roles: curator, companion, creator.
Each session uses gzip-compressed LONGBLOB for state and three-tier memory:
  - Buffer: last 10 messages verbatim
  - Summary: compressed history of older messages
  - Key facts: permanent extracted insights

Storage: tory_ai_sessions table in MariaDB.
"""

import gzip
import json
import subprocess
import time
from typing import Any, Dict, List, Optional

import structlog

from config import (
    DATABASE,
    DB_QUERY_TIMEOUT,
    SONNET_MODEL,
    OPUS_MODEL,
    SONNET_INPUT_PRICE_PER_1K,
    SONNET_OUTPUT_PRICE_PER_1K,
    OPUS_INPUT_PRICE_PER_1K,
    OPUS_OUTPUT_PRICE_PER_1K,
    MEMORY_BUFFER_SIZE,
    MEMORY_SUMMARY_THRESHOLD,
    MEMORY_KEY_FACTS_MAX,
)

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# DB helper (shared with model_harness.py)
# ---------------------------------------------------------------------------

def _db_exec(sql: str, timeout: int = 10) -> bool:
    """Execute a write SQL statement. Returns True on success."""
    try:
        result = subprocess.run(
            ["mysql", DATABASE, "-e", sql],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning("db_exec_failed", sql=sql[:200], stderr=result.stderr[:200])
            return False
        return True
    except Exception as e:
        logger.error("db_exec_error", sql=sql[:200], error=str(e))
        return False


def _db_query(sql: str) -> List[Dict[str, str]]:
    """Run a read-only SQL query via mysql CLI, return list of row dicts."""
    import xml.etree.ElementTree as ET
    try:
        result = subprocess.run(
            ["mysql", DATABASE, "--xml", "-e", sql],
            capture_output=True, text=True, timeout=DB_QUERY_TIMEOUT,
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
# Session data structure
# ============================================================================

def new_session_state(
    session_type: str = "chat",
    role: str = "curator",
) -> Dict[str, Any]:
    """Create a fresh session state dict."""
    return {
        "type": session_type,
        "role": role,
        "messages": [],
        "summary": "",
        "key_facts": [],
        "steps": [],          # For instantiation sessions
        "decisions": [],      # Decision log for path reasoning
        "tool_calls": [],     # Tool call log for observability
        "metadata": {},
    }


# ============================================================================
# SessionManager
# ============================================================================

class SessionManager:
    """
    Manages AI sessions with persistence to tory_ai_sessions.

    Usage:
        mgr = SessionManager()
        session = mgr.create_session(nx_user_id=123, role='curator')
        session_id = session['id']

        # Add messages
        mgr.add_message(session, 'human', 'Why was lesson X assigned?')
        mgr.add_message(session, 'ai', 'Because...')

        # Track costs
        mgr.track_cost(session, input_tokens=500, output_tokens=200, model='claude-sonnet-4-20250514')

        # Save
        mgr.save(session)

        # Resume later
        session = mgr.load_session(session_id)
    """

    def __init__(self):
        self._cache: Dict[int, Dict] = {}  # session_id -> session state

    # -- Create --

    def create_session(
        self,
        nx_user_id: int,
        role: str = "curator",
        session_type: str = "chat",
        initiated_by: Optional[int] = None,
        model_tier: str = "sonnet",
    ) -> Dict[str, Any]:
        """Create a new session row and return the session state dict."""
        initiator_sql = f", {int(initiated_by)}" if initiated_by else ", NULL"
        safe_role = role if role in ('curator', 'companion', 'creator') else 'curator'

        sql = (
            f"INSERT INTO tory_ai_sessions "
            f"(nx_user_id, role, initiated_by, model_tier, message_count, "
            f"total_input_tokens, total_output_tokens, estimated_cost_usd, "
            f"last_active_at, created_at, updated_at) "
            f"VALUES ({int(nx_user_id)}, '{safe_role}'{initiator_sql}, "
            f"'{model_tier}', 0, 0, 0, 0.0, NOW(), NOW(), NOW())"
        )
        _db_exec(sql)

        rows = _db_query(
            f"SELECT id, created_at FROM tory_ai_sessions "
            f"WHERE nx_user_id = {int(nx_user_id)} AND role = '{safe_role}' "
            f"ORDER BY id DESC LIMIT 1"
        )
        session_id = int(rows[0]["id"]) if rows else 0

        session = {
            "id": session_id,
            "nx_user_id": nx_user_id,
            "role": safe_role,
            "model_tier": model_tier,
            **new_session_state(session_type, safe_role),
            "message_count": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "created_at": rows[0].get("created_at", "") if rows else "",
        }
        self._cache[session_id] = session
        return session

    # -- Load / Resume --

    def load_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Load a session from DB by ID, decompress state."""
        if session_id in self._cache:
            return self._cache[session_id]

        rows = _db_query(
            f"SELECT id, nx_user_id, role, key_facts, message_count, "
            f"model_tier, total_input_tokens, total_output_tokens, "
            f"estimated_cost_usd, created_at "
            f"FROM tory_ai_sessions WHERE id = {int(session_id)}"
        )
        if not rows:
            return None

        row = rows[0]
        session = {
            "id": int(row["id"]),
            "nx_user_id": int(row.get("nx_user_id", 0)),
            "role": row.get("role", "curator"),
            "model_tier": row.get("model_tier", "sonnet"),
            "messages": [],
            "summary": "",
            "key_facts": [],
            "steps": [],
            "decisions": [],
            "tool_calls": [],
            "metadata": {},
            "message_count": int(row.get("message_count", 0)),
            "total_input_tokens": int(row.get("total_input_tokens", 0)),
            "total_output_tokens": int(row.get("total_output_tokens", 0)),
            "estimated_cost_usd": float(row.get("estimated_cost_usd", 0)),
            "created_at": row.get("created_at", ""),
        }

        # Decompress session_state from gzip LONGBLOB
        state = self._decompress_state(session_id)
        if state:
            session["messages"] = state.get("messages", [])
            session["summary"] = state.get("summary", "")
            session["steps"] = state.get("steps", [])
            session["decisions"] = state.get("decisions", [])
            session["tool_calls"] = state.get("tool_calls", [])
            session["metadata"] = state.get("metadata", {})

        # Key facts from JSON text column
        kf = row.get("key_facts", "")
        if kf:
            try:
                session["key_facts"] = json.loads(kf)
            except (json.JSONDecodeError, TypeError):
                session["key_facts"] = []

        self._cache[session_id] = session
        return session

    def get_or_create_session(
        self,
        nx_user_id: int,
        role: str = "curator",
    ) -> Dict[str, Any]:
        """Get the most recent active session or create a new one."""
        safe_role = role if role in ('curator', 'companion', 'creator') else 'curator'
        rows = _db_query(
            f"SELECT id FROM tory_ai_sessions "
            f"WHERE nx_user_id = {int(nx_user_id)} "
            f"AND role = '{safe_role}' AND archived_at IS NULL "
            f"ORDER BY last_active_at DESC LIMIT 1"
        )
        if rows:
            return self.load_session(int(rows[0]["id"]))
        return self.create_session(nx_user_id, role)

    # -- Save --

    def save(self, session: Dict) -> bool:
        """Persist session state back to DB (gzip compress)."""
        session_id = session.get("id")
        if not session_id:
            return False

        try:
            # Build state blob
            state = {
                "messages": session.get("messages", [])[-MEMORY_SUMMARY_THRESHOLD:],
                "summary": session.get("summary", ""),
                "steps": session.get("steps", []),
                "decisions": session.get("decisions", []),
                "tool_calls": session.get("tool_calls", [])[-200:],  # Cap tool calls
                "metadata": session.get("metadata", {}),
            }
            compressed = gzip.compress(json.dumps(state, default=str).encode('utf-8'))
            hex_data = compressed.hex()

            # Key facts as JSON text
            kf_json = json.dumps(session.get("key_facts", []), default=str)
            kf_escaped = kf_json.replace("\\", "\\\\").replace("'", "\\'")

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
            return _db_exec(sql)
        except Exception as e:
            logger.error("save_session_failed", session_id=session_id, error=str(e))
            return False

    # -- Archive --

    def archive_session(self, session_id: int) -> bool:
        """Mark a session as archived."""
        return _db_exec(
            f"UPDATE tory_ai_sessions SET archived_at = NOW() "
            f"WHERE id = {int(session_id)}"
        )

    # -- List sessions for a user --

    def list_sessions(
        self,
        nx_user_id: int,
        role: Optional[str] = None,
        include_archived: bool = False,
    ) -> List[Dict]:
        """List sessions for a user, newest first."""
        where = f"nx_user_id = {int(nx_user_id)}"
        if role:
            safe_role = role if role in ('curator', 'companion', 'creator') else 'curator'
            where += f" AND role = '{safe_role}'"
        if not include_archived:
            where += " AND archived_at IS NULL"

        rows = _db_query(
            f"SELECT id, role, message_count, model_tier, "
            f"total_input_tokens, total_output_tokens, estimated_cost_usd, "
            f"last_active_at, created_at, archived_at "
            f"FROM tory_ai_sessions WHERE {where} "
            f"ORDER BY last_active_at DESC LIMIT 20"
        )
        return [{
            "id": int(r["id"]),
            "role": r.get("role", "curator"),
            "message_count": int(r.get("message_count", 0)),
            "model_tier": r.get("model_tier", "sonnet"),
            "total_input_tokens": int(r.get("total_input_tokens", 0)),
            "total_output_tokens": int(r.get("total_output_tokens", 0)),
            "estimated_cost_usd": float(r.get("estimated_cost_usd", 0)),
            "last_active_at": r.get("last_active_at", ""),
            "created_at": r.get("created_at", ""),
            "archived_at": r.get("archived_at"),
        } for r in rows]

    # -- Memory management --

    def add_message(self, session: Dict, role: str, content: str):
        """Add a message to the session buffer with three-tier compression."""
        session["messages"].append({
            "role": role,
            "content": content,
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
        })
        session["message_count"] = session.get("message_count", 0) + 1

        # Three-tier memory: compress when buffer exceeds threshold
        if len(session["messages"]) > MEMORY_SUMMARY_THRESHOLD:
            old = session["messages"][:-MEMORY_BUFFER_SIZE]
            session["messages"] = session["messages"][-MEMORY_BUFFER_SIZE:]
            # Build summary from old messages
            summary_parts = []
            for msg in old:
                summary_parts.append(
                    f"{msg['role']}: {msg['content'][:150]}"
                )
            new_summary = " | ".join(summary_parts)
            if session.get("summary"):
                session["summary"] = session["summary"][-3000:] + " | " + new_summary
            else:
                session["summary"] = new_summary

    def add_step(self, session: Dict, step: Dict):
        """Add a step to an instantiation session."""
        session.setdefault("steps", []).append({
            **step,
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
        })

    def add_decision(self, session: Dict, decision: Dict):
        """Add a decision to the session's decision log."""
        session.setdefault("decisions", []).append({
            **decision,
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
        })

    def add_tool_call(self, session: Dict, tool_call: Dict):
        """Add a tool call record to the session."""
        session.setdefault("tool_calls", []).append({
            **tool_call,
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
        })

    def get_memory_context(self, session: Dict) -> str:
        """Build memory context string from three-tier memory."""
        parts = []
        kf = session.get("key_facts", [])
        if kf:
            parts.append("Key facts: " + "; ".join(str(f) for f in kf[:20]))
        summary = session.get("summary", "")
        if summary:
            parts.append("Prior conversation summary: " + summary[:2000])
        return "\n".join(parts)

    # -- Cost tracking --

    def track_cost(
        self,
        session: Dict,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ):
        """Track token usage and cost for a session."""
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

    def extract_key_facts(self, text: str, session: Dict):
        """Extract key facts from AI response text."""
        key_facts = session.get("key_facts", [])
        for line in text.split("\n"):
            line = line.strip()
            if any(kw in line.lower() for kw in [
                "key insight", "important:", "note:", "flag:", "concern:",
                "pattern:", "strength:", "gap:", "tension:",
            ]):
                fact = line[:200]
                if fact not in key_facts and len(key_facts) < MEMORY_KEY_FACTS_MAX:
                    key_facts.append(fact)
        session["key_facts"] = key_facts

    # -- Session detail for API --

    def get_session_detail(self, session_id: int) -> Optional[Dict]:
        """Get full session detail including decompressed state for the API."""
        session = self.load_session(session_id)
        if not session:
            return None

        return {
            "id": session["id"],
            "nx_user_id": session["nx_user_id"],
            "role": session["role"],
            "model_tier": session["model_tier"],
            "message_count": session["message_count"],
            "total_input_tokens": session["total_input_tokens"],
            "total_output_tokens": session["total_output_tokens"],
            "estimated_cost_usd": round(session["estimated_cost_usd"], 4),
            "created_at": session["created_at"],
            "messages": session.get("messages", []),
            "summary": session.get("summary", ""),
            "key_facts": session.get("key_facts", []),
            "steps": session.get("steps", []),
            "decisions": session.get("decisions", []),
            "tool_calls": session.get("tool_calls", []),
            "metadata": session.get("metadata", {}),
        }

    def get_step_for_lesson(
        self,
        session_id: int,
        lesson_id: int,
    ) -> Optional[Dict]:
        """Get the specific decision/reasoning for a lesson from an instantiation session."""
        session = self.load_session(session_id)
        if not session:
            return None

        # Check decisions first
        for decision in session.get("decisions", []):
            if decision.get("lesson_id") == lesson_id:
                return decision

        # Check steps for build_path step which contains per-lesson decisions
        for step in session.get("steps", []):
            if step.get("step") == "build_path":
                for d in step.get("decisions", []):
                    if d.get("lesson_id") == lesson_id:
                        return {
                            "step": "build_path",
                            **d,
                        }
        return None

    # -- Internal --

    def _decompress_state(self, session_id: int) -> Optional[Dict]:
        """Decompress session_state LONGBLOB from DB."""
        try:
            result = subprocess.run(
                ["mysql", DATABASE, "--batch", "--raw", "-e",
                 f"SELECT HEX(session_state) AS state_hex "
                 f"FROM tory_ai_sessions WHERE id = {int(session_id)}"],
                capture_output=True, text=True, timeout=DB_QUERY_TIMEOUT,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    hex_data = lines[1].strip()
                    if hex_data and hex_data != "NULL":
                        binary = bytes.fromhex(hex_data)
                        decompressed = gzip.decompress(binary)
                        return json.loads(decompressed.decode('utf-8'))
        except Exception as e:
            logger.warning(
                "session_state_decompress_failed",
                session_id=session_id, error=str(e),
            )
        return None
