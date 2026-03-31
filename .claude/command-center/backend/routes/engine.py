"""
engine.py — Tory Engine observability API.
Returns live stats, config, and pipeline data for the Engine dashboard.
"""

import json
import subprocess
from fastapi import APIRouter

router = APIRouter(prefix="/api/engine", tags=["engine"])


def _sql(query: str) -> list[dict]:
    """Run read-only SQL and return list of dicts."""
    try:
        result = subprocess.run(
            ["mysql", "baap", "--batch", "--raw", "-e", query],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            return []
        headers = lines[0].split("\t")
        rows = []
        for line in lines[1:]:
            vals = line.split("\t")
            rows.append(dict(zip(headers, vals)))
        return rows
    except Exception:
        return []


def _sql_one(query: str) -> dict:
    rows = _sql(query)
    return rows[0] if rows else {}


@router.get("/stats")
async def get_engine_stats():
    """Live statistics from all Tory Engine tables."""

    # Profiles
    profiles = _sql_one("SELECT COUNT(*) as total, COUNT(DISTINCT nx_user_id) as users FROM tory_learner_profiles")

    # Recommendations
    recs = _sql_one("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT nx_user_id) as users_with_paths,
               ROUND(AVG(match_score), 1) as avg_score,
               SUM(is_discovery = 1) as discovery_count,
               SUM(locked_by_coach = 1) as coach_locked,
               SUM(source = 'coach') as coach_modified
        FROM tory_recommendations
    """)

    # Content tags
    tags = _sql_one("""
        SELECT COUNT(*) as total,
               SUM(review_status = 'approved') as approved,
               SUM(review_status = 'pending') as pending,
               SUM(review_status = 'needs_review') as needs_review,
               SUM(review_status = 'corrected') as corrected,
               SUM(review_status = 'dismissed') as dismissed,
               ROUND(AVG(confidence), 1) as avg_confidence
        FROM tory_content_tags
    """)

    # Lessons coverage
    lessons = _sql_one("""
        SELECT
            (SELECT COUNT(DISTINCT ld.id) FROM lesson_details ld JOIN nx_lessons nl ON nl.id = ld.nx_lesson_id) as total_lessons,
            (SELECT COUNT(DISTINCT nx_lesson_id) FROM tory_content_tags) as tagged_lessons
    """)

    # Reassessments
    reassess = _sql_one("""
        SELECT COUNT(*) as total,
               SUM(type = 'quarterly_epp') as quarterly,
               SUM(type = 'mini') as mini,
               SUM(type = 'backpack_derived') as passive,
               SUM(drift_detected = 1) as drift_triggered,
               SUM(path_action = 'reranked') as paths_reranked
        FROM tory_reassessments
    """)

    # Roadmaps
    roadmaps = _sql_one("""
        SELECT COUNT(*) as total,
               SUM(mode = 'discovery') as discovery,
               SUM(mode = 'full') as full_paths
        FROM tory_roadmaps
    """)

    # AI Sessions
    sessions = _sql_one("""
        SELECT COUNT(*) as total,
               SUM(role = 'curator') as curator,
               SUM(role = 'companion') as companion,
               SUM(role = 'instantiation') as instantiation,
               SUM(message_count) as total_messages
        FROM tory_ai_sessions
    """)

    # Path events (coach actions)
    events = _sql_one("""
        SELECT COUNT(*) as total,
               SUM(event_type = 'reordered') as reorders,
               SUM(event_type = 'swapped') as swaps,
               SUM(event_type = 'locked') as locks
        FROM tory_path_events
    """)

    # Coach flags
    flags = _sql_one("""
        SELECT COUNT(*) as total,
               SUM(signal = 'green') as green,
               SUM(signal = 'yellow') as yellow,
               SUM(signal = 'red') as red
        FROM tory_coach_flags
    """)

    # Pedagogy config
    pedagogy = _sql("SELECT client_id, mode, gap_ratio, strength_ratio FROM tory_pedagogy_config")

    # Score distribution
    score_dist = _sql("""
        SELECT
            CASE
                WHEN match_score >= 80 THEN '80-100'
                WHEN match_score >= 60 THEN '60-79'
                WHEN match_score >= 40 THEN '40-59'
                WHEN match_score >= 20 THEN '20-39'
                ELSE '0-19'
            END as bucket,
            COUNT(*) as count
        FROM tory_recommendations
        GROUP BY bucket
        ORDER BY bucket DESC
    """)

    # Confidence distribution
    conf_dist = _sql("""
        SELECT
            CASE
                WHEN confidence >= 80 THEN '80-100'
                WHEN confidence >= 60 THEN '60-79'
                WHEN confidence >= 40 THEN '40-59'
                WHEN confidence >= 20 THEN '20-39'
                ELSE '0-19'
            END as bucket,
            COUNT(*) as count
        FROM tory_content_tags
        GROUP BY bucket
        ORDER BY bucket DESC
    """)

    # Trait coverage (which traits appear in content tags)
    trait_coverage = _sql("""
        SELECT
            JSON_UNQUOTE(jt.trait) as trait_name,
            COUNT(*) as tag_count
        FROM tory_content_tags ct,
             JSON_TABLE(ct.trait_tags, '$[*]' COLUMNS(trait VARCHAR(100) PATH '$.trait')) jt
        GROUP BY trait_name
        ORDER BY tag_count DESC
        LIMIT 20
    """)

    # Top matched traits in recommendations
    top_matched = _sql("""
        SELECT
            JSON_UNQUOTE(jt.trait) as trait_name,
            JSON_UNQUOTE(jt.type) as match_type,
            COUNT(*) as match_count
        FROM tory_recommendations r,
             JSON_TABLE(r.matching_traits, '$[*]' COLUMNS(
                trait VARCHAR(100) PATH '$.trait',
                type VARCHAR(20) PATH '$.type'
             )) jt
        GROUP BY trait_name, match_type
        ORDER BY match_count DESC
        LIMIT 30
    """)

    return {
        "profiles": profiles,
        "recommendations": recs,
        "content_tags": tags,
        "lessons": lessons,
        "reassessments": reassess,
        "roadmaps": roadmaps,
        "ai_sessions": sessions,
        "path_events": events,
        "coach_flags": flags,
        "pedagogy": pedagogy,
        "score_distribution": score_dist,
        "confidence_distribution": conf_dist,
        "trait_coverage": trait_coverage,
        "top_matched_traits": top_matched,
    }


@router.get("/users")
async def get_engine_users():
    """Users with Tory profiles — for the pipeline trace dropdown."""
    rows = _sql("""
        SELECT tp.nx_user_id,
               CONCAT(COALESCE(uo.first_name, ''), ' ', COALESCE(uo.last_name, '')) as name,
               tp.learning_style,
               tp.confidence,
               COALESCE(tr.cnt, 0) as path_lessons
        FROM tory_learner_profiles tp
        LEFT JOIN nx_user_onboardings uo ON uo.nx_user_id = tp.nx_user_id
        LEFT JOIN (
            SELECT nx_user_id, COUNT(*) as cnt
            FROM tory_recommendations
            GROUP BY nx_user_id
        ) tr ON tr.nx_user_id = tp.nx_user_id
        WHERE tp.id IN (
            SELECT MAX(id) FROM tory_learner_profiles GROUP BY nx_user_id
        )
        ORDER BY tr.cnt DESC, uo.first_name ASC
        LIMIT 200
    """)
    return rows


@router.get("/pipeline/{user_id}")
async def get_pipeline_trace(user_id: int):
    """Full pipeline trace for a single user — shows every step from EPP to path."""

    # Profile
    profile = _sql_one(f"""
        SELECT nx_user_id, epp_summary, strengths, gaps,
               learning_style, motivation_cluster, confidence,
               profile_narrative, version, source, created_at
        FROM tory_learner_profiles
        WHERE nx_user_id = {int(user_id)}
        ORDER BY id DESC LIMIT 1
    """)

    # Recommendations with full scoring
    recs = _sql(f"""
        SELECT r.nx_lesson_id, r.match_score, r.adjusted_score,
               r.gap_contribution, r.strength_contribution,
               r.matching_traits, r.sequence, r.is_discovery,
               r.match_rationale, r.source, r.locked_by_coach, r.confidence,
               nl.lesson as lesson_name,
               ct.difficulty, ct.learning_style, ct.emotional_tone,
               ct.summary, ct.confidence as tag_confidence
        FROM tory_recommendations r
        LEFT JOIN nx_lessons nl ON nl.id = r.nx_lesson_id
        LEFT JOIN tory_content_tags ct ON ct.nx_lesson_id = r.nx_lesson_id
        WHERE r.nx_user_id = {int(user_id)}
        ORDER BY r.sequence ASC
    """)

    # Reassessment history
    reassessments = _sql(f"""
        SELECT type, trigger_reason, status, drift_detected,
               result_delta, path_action, created_at
        FROM tory_reassessments
        WHERE nx_user_id = {int(user_id)}
        ORDER BY created_at DESC
        LIMIT 10
    """)

    # Coach flag
    flag = _sql_one(f"""
        SELECT signal, message, warnings
        FROM tory_coach_flags
        WHERE nx_user_id = {int(user_id)}
        ORDER BY id DESC LIMIT 1
    """)

    # Path events
    path_events = _sql(f"""
        SELECT event_type, details, coach_id, created_at
        FROM tory_path_events
        WHERE nx_user_id = {int(user_id)}
        ORDER BY created_at DESC
        LIMIT 20
    """)

    return {
        "user_id": user_id,
        "profile": profile,
        "recommendations": recs,
        "reassessments": reassessments,
        "coach_flag": flag,
        "path_events": path_events,
    }
