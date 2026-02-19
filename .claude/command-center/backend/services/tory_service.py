"""
tory_service.py — Learner profile and feedback management for the Tory engine.

Provides profile generation (via tory_engine MCP), profile retrieval,
and learner feedback storage.
"""

import json
import subprocess
from datetime import datetime
from typing import Any

DATABASE = "baap"
QUERY_TIMEOUT = 30


def _mysql_query(sql: str) -> list[dict]:
    """Execute a read-only MySQL query, return list of row dicts."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL error: {result.stderr.strip()}")
    output = result.stdout.strip()
    if not output:
        return []
    lines = output.split("\n")
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        rows.append({h: (values[i] if i < len(values) else None) for i, h in enumerate(headers)})
    return rows


def _mysql_write(sql: str) -> None:
    """Execute a write query."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL write error: {result.stderr.strip()}")


def _escape(value: str) -> str:
    """Escape a string for safe SQL insertion."""
    if value is None:
        return "NULL"
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r")
    escaped = escaped.replace("\x00", "").replace("\x1a", "")
    return f"'{escaped}'"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_json_field(val: str | None) -> Any:
    """Safely parse a JSON field from DB, returning raw string on failure."""
    if not val or val == "NULL":
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


class ToryService:
    """Service for Tory learner profile and feedback operations."""

    def get_profile(self, learner_id: int) -> dict | None:
        """Fetch the latest learner profile with parsed JSON fields."""
        rows = _mysql_query(
            f"SELECT p.*, u.email, o.first_name, o.last_name "
            f"FROM tory_learner_profiles p "
            f"JOIN nx_users u ON u.id = p.nx_user_id "
            f"LEFT JOIN nx_user_onboardings o ON o.nx_user_id = p.nx_user_id "
            f"WHERE p.nx_user_id = {int(learner_id)} "
            f"AND p.deleted_at IS NULL "
            f"ORDER BY p.version DESC LIMIT 1"
        )
        if not rows:
            return None

        row = rows[0]
        return {
            "id": int(row["id"]),
            "nx_user_id": int(row["nx_user_id"]),
            "email": row.get("email"),
            "first_name": row.get("first_name"),
            "last_name": row.get("last_name"),
            "epp_summary": _parse_json_field(row.get("epp_summary")),
            "motivation_cluster": _parse_json_field(row.get("motivation_cluster")),
            "strengths": _parse_json_field(row.get("strengths")),
            "gaps": _parse_json_field(row.get("gaps")),
            "learning_style": row.get("learning_style"),
            "profile_narrative": row.get("profile_narrative"),
            "confidence": int(row.get("confidence", 0)),
            "version": int(row.get("version", 1)),
            "source": row.get("source"),
            "feedback_flags": int(row.get("feedback_flags", 0)),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def has_completed_onboarding(self, learner_id: int) -> bool:
        """Check if learner has completed EPP + Q&A onboarding."""
        rows = _mysql_query(
            f"SELECT id, assesment_result, why_did_you_come "
            f"FROM nx_user_onboardings "
            f"WHERE nx_user_id = {int(learner_id)} "
            f"AND deleted_at IS NULL LIMIT 1"
        )
        if not rows:
            return False
        row = rows[0]
        has_epp = row.get("assesment_result") and row["assesment_result"] != "NULL"
        has_qa = row.get("why_did_you_come") and row["why_did_you_come"] != "NULL"
        return bool(has_epp and has_qa)

    def user_exists(self, learner_id: int) -> bool:
        """Check if a user exists."""
        rows = _mysql_query(
            f"SELECT id FROM nx_users WHERE id = {int(learner_id)} "
            f"AND deleted_at IS NULL LIMIT 1"
        )
        return len(rows) > 0

    def create_feedback(self, learner_id: int, feedback_type: str, comment: str | None = None) -> dict:
        """Store learner feedback (e.g. 'not_like_me') and increment profile flag count."""
        profile = self.get_profile(learner_id)
        profile_id = profile["id"] if profile else None
        profile_version = profile["version"] if profile else None
        now = _now()

        comment_sql = _escape(comment) if comment else "NULL"
        profile_id_sql = str(profile_id) if profile_id else "NULL"
        version_sql = str(profile_version) if profile_version else "NULL"

        _mysql_write(
            f"INSERT INTO tory_feedback "
            f"(nx_user_id, profile_id, type, comment, profile_version, resolved, created_at, updated_at) "
            f"VALUES ({int(learner_id)}, {profile_id_sql}, {_escape(feedback_type)}, "
            f"{comment_sql}, {version_sql}, 0, '{now}', '{now}')"
        )

        # Increment feedback_flags on the profile
        if profile_id:
            _mysql_write(
                f"UPDATE tory_learner_profiles SET feedback_flags = feedback_flags + 1, "
                f"updated_at = '{now}' WHERE id = {profile_id}"
            )

        # Fetch the created feedback
        rows = _mysql_query(
            f"SELECT * FROM tory_feedback "
            f"WHERE nx_user_id = {int(learner_id)} "
            f"ORDER BY id DESC LIMIT 1"
        )
        row = rows[0] if rows else {}
        return {
            "id": int(row.get("id", 0)),
            "nx_user_id": int(learner_id),
            "profile_id": profile_id,
            "type": feedback_type,
            "comment": comment,
            "profile_version": profile_version,
            "created_at": row.get("created_at", now),
        }
