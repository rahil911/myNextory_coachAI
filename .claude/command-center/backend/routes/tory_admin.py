"""
routes/tory_admin.py — HR/Admin dashboard endpoints for Tory progress tracking.

GET  /api/tory/admin/cohort         — All learners with progress summary
GET  /api/tory/admin/learner/{id}   — Individual drilldown (path, events, reassessments)
GET  /api/tory/admin/metrics        — Aggregate metrics (completion, match scores, content gaps)
"""

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/tory/admin", tags=["tory-admin"])

DATABASE = "baap"
QUERY_TIMEOUT = 30


def _mysql_query(sql: str) -> list[dict]:
    """Execute a read-only MySQL query, return list of row dicts."""
    import subprocess
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


def _parse_json(val):
    if not val or val == "NULL":
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


def _safe_int(val, default=0):
    try:
        return int(val) if val and val != "NULL" else default
    except (ValueError, TypeError):
        return default


def _safe_float(val, default=0.0):
    try:
        return float(val) if val and val != "NULL" else default
    except (ValueError, TypeError):
        return default


# ── Cohort Overview ──────────────────────────────────────────────────────────

@router.get("/cohort")
async def get_cohort(
    sort_by: str = Query("completion_pct", description="Sort field"),
    sort_dir: str = Query("desc", description="asc or desc"),
    coach_filter: str = Query(None, description="Filter by coach name"),
    department_filter: str = Query(None, description="Filter by department"),
):
    """All learners with Tory profiles, progress counts, phase, coach info."""

    rows = _mysql_query(
        "SELECT p.nx_user_id, p.confidence, p.version, p.learning_style, "
        "p.feedback_flags, p.created_at AS profile_created, p.updated_at AS profile_updated, "
        "u.email, o.first_name, o.last_name, "
        "d.department_title AS department, cl.company_name, "
        "cf.coach_id, cf.compat_signal, c.username AS coach_name "
        "FROM tory_learner_profiles p "
        "JOIN nx_users u ON u.id = p.nx_user_id "
        "LEFT JOIN nx_user_onboardings o ON o.nx_user_id = p.nx_user_id "
        "LEFT JOIN employees e ON e.nx_user_id = p.nx_user_id AND e.deleted_at IS NULL "
        "LEFT JOIN departments d ON d.id = e.department_id AND d.deleted_at IS NULL "
        "LEFT JOIN clients cl ON cl.id = d.client_id AND cl.deleted_at IS NULL "
        "LEFT JOIN tory_coach_flags cf ON cf.nx_user_id = p.nx_user_id AND cf.deleted_at IS NULL "
        "AND cf.id = (SELECT MAX(cf2.id) FROM tory_coach_flags cf2 "
        "  WHERE cf2.nx_user_id = p.nx_user_id AND cf2.deleted_at IS NULL) "
        "LEFT JOIN coaches c ON c.id = cf.coach_id "
        "WHERE p.deleted_at IS NULL "
        "AND p.version = ("
        "  SELECT MAX(p2.version) FROM tory_learner_profiles p2 "
        "  WHERE p2.nx_user_id = p.nx_user_id AND p2.deleted_at IS NULL"
        ") "
        "ORDER BY p.nx_user_id"
    )

    # Get recommendation counts per user
    rec_rows = _mysql_query(
        "SELECT nx_user_id, "
        "COUNT(*) AS total, "
        "SUM(is_discovery) AS discovery_count, "
        "SUM(locked_by_coach) AS coach_modified, "
        "AVG(match_score) AS avg_match_score, "
        "source "
        "FROM tory_recommendations "
        "WHERE deleted_at IS NULL "
        "GROUP BY nx_user_id"
    )
    rec_map = {}
    for r in rec_rows:
        rec_map[r["nx_user_id"]] = r

    # Get path event counts per user
    event_rows = _mysql_query(
        "SELECT nx_user_id, COUNT(*) AS event_count, "
        "MAX(created_at) AS last_activity "
        "FROM tory_path_events "
        "WHERE deleted_at IS NULL "
        "GROUP BY nx_user_id"
    )
    event_map = {r["nx_user_id"]: r for r in event_rows}

    # Get reassessment counts
    reassess_rows = _mysql_query(
        "SELECT nx_user_id, COUNT(*) AS reassess_count, "
        "SUM(CASE WHEN drift_detected = 1 THEN 1 ELSE 0 END) AS drift_count "
        "FROM tory_reassessments "
        "WHERE deleted_at IS NULL "
        "GROUP BY nx_user_id"
    )
    reassess_map = {r["nx_user_id"]: r for r in reassess_rows}

    learners = []
    for row in rows:
        uid = row["nx_user_id"]
        rec = rec_map.get(uid, {})
        evt = event_map.get(uid, {})
        rea = reassess_map.get(uid, {})

        total_lessons = _safe_int(rec.get("total"), 0)
        discovery_count = _safe_int(rec.get("discovery_count"), 0)
        coach_modified = _safe_int(rec.get("coach_modified"), 0)

        # Determine phase
        reassess_count = _safe_int(rea.get("reassess_count"), 0)
        if reassess_count > 0:
            phase = "reassessed"
        elif total_lessons > 0 and discovery_count < total_lessons:
            phase = "active"
        elif discovery_count > 0:
            phase = "discovery"
        else:
            phase = "profiled"

        # Completion: for now, path_events with event_type tracking marks progress
        # We'll use event count as a proxy for engagement
        event_count = _safe_int(evt.get("event_count"), 0)
        last_activity = evt.get("last_activity") or row.get("profile_updated")

        learner = {
            "nx_user_id": _safe_int(uid),
            "email": row.get("email"),
            "first_name": row.get("first_name"),
            "last_name": row.get("last_name"),
            "department": row.get("department"),
            "company_name": row.get("company_name"),
            "total_lessons": total_lessons,
            "discovery_count": discovery_count,
            "coach_modified": coach_modified,
            "avg_match_score": round(_safe_float(rec.get("avg_match_score")), 1),
            "phase": phase,
            "confidence": _safe_int(row.get("confidence")),
            "version": _safe_int(row.get("version"), 1),
            "learning_style": row.get("learning_style"),
            "feedback_flags": _safe_int(row.get("feedback_flags")),
            "event_count": event_count,
            "last_activity": last_activity,
            "coach_name": row.get("coach_name"),
            "coach_id": _safe_int(row.get("coach_id")) if row.get("coach_id") else None,
            "compat_signal": row.get("compat_signal"),
            "reassess_count": reassess_count,
            "profile_created": row.get("profile_created"),
        }
        learners.append(learner)

    # Apply filters
    if coach_filter:
        learners = [l for l in learners if l.get("coach_name") and coach_filter.lower() in l["coach_name"].lower()]
    if department_filter:
        learners = [l for l in learners if l.get("department") and department_filter.lower() in l["department"].lower()]

    # Sort
    valid_sorts = {"completion_pct", "avg_match_score", "last_activity", "first_name", "coach_name", "phase", "total_lessons", "confidence"}
    if sort_by not in valid_sorts:
        sort_by = "avg_match_score"

    reverse = sort_dir.lower() != "asc"
    learners.sort(key=lambda l: (l.get(sort_by) or "") if isinstance(l.get(sort_by), str) else (l.get(sort_by) or 0), reverse=reverse)

    return {
        "learners": learners,
        "total": len(learners),
    }


# ── CSV Export ───────────────────────────────────────────────────────────────

@router.get("/cohort/csv")
async def export_cohort_csv():
    """Export cohort table as CSV download."""
    data = await get_cohort(
        sort_by="first_name", sort_dir="asc",
        coach_filter=None, department_filter=None,
    )
    learners = data["learners"]

    output = io.StringIO()
    fieldnames = [
        "nx_user_id", "first_name", "last_name", "email", "department",
        "total_lessons", "discovery_count", "coach_modified", "avg_match_score",
        "phase", "confidence", "learning_style", "coach_name", "compat_signal",
        "feedback_flags", "event_count", "last_activity", "profile_created",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for l in learners:
        writer.writerow(l)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tory_cohort_export.csv"},
    )


# ── Individual Learner Drilldown ─────────────────────────────────────────────

@router.get("/learner/{learner_id}")
async def get_learner_drilldown(learner_id: int):
    """Full drilldown: profile, path, events timeline, reassessment history, feedback."""

    # Profile
    profile_rows = _mysql_query(
        f"SELECT p.*, u.email, o.first_name, o.last_name "
        f"FROM tory_learner_profiles p "
        f"JOIN nx_users u ON u.id = p.nx_user_id "
        f"LEFT JOIN nx_user_onboardings o ON o.nx_user_id = p.nx_user_id "
        f"WHERE p.nx_user_id = {int(learner_id)} AND p.deleted_at IS NULL "
        f"ORDER BY p.version DESC LIMIT 1"
    )
    if not profile_rows:
        return {"error": "No profile found", "learner_id": learner_id}

    pr = profile_rows[0]
    profile = {
        "id": _safe_int(pr["id"]),
        "nx_user_id": _safe_int(pr["nx_user_id"]),
        "email": pr.get("email"),
        "first_name": pr.get("first_name"),
        "last_name": pr.get("last_name"),
        "epp_summary": _parse_json(pr.get("epp_summary")),
        "strengths": _parse_json(pr.get("strengths")),
        "gaps": _parse_json(pr.get("gaps")),
        "motivation_cluster": _parse_json(pr.get("motivation_cluster")),
        "learning_style": pr.get("learning_style"),
        "profile_narrative": pr.get("profile_narrative"),
        "confidence": _safe_int(pr.get("confidence")),
        "version": _safe_int(pr.get("version"), 1),
        "source": pr.get("source"),
        "feedback_flags": _safe_int(pr.get("feedback_flags")),
        "created_at": pr.get("created_at"),
        "updated_at": pr.get("updated_at"),
    }

    # Recommendations (full path)
    recs = _mysql_query(
        f"SELECT r.id, r.nx_lesson_id, r.sequence, r.match_score, r.gap_contribution, "
        f"r.strength_contribution, r.adjusted_score, r.is_discovery, r.source, "
        f"r.locked_by_coach, r.match_rationale, r.matching_traits, r.confidence, "
        f"r.pedagogy_mode, r.batch_id, r.created_at, "
        f"l.lesson AS lesson_title, jd.journey AS journey_title "
        f"FROM tory_recommendations r "
        f"LEFT JOIN nx_lessons l ON r.nx_lesson_id = l.id "
        f"LEFT JOIN nx_journey_details jd ON l.nx_journey_detail_id = jd.id "
        f"WHERE r.nx_user_id = {int(learner_id)} AND r.deleted_at IS NULL "
        f"ORDER BY r.sequence"
    )
    recommendations = []
    for r in recs:
        recommendations.append({
            "id": _safe_int(r["id"]),
            "nx_lesson_id": _safe_int(r["nx_lesson_id"]),
            "sequence": _safe_int(r["sequence"]),
            "match_score": _safe_float(r.get("match_score")),
            "gap_contribution": _safe_float(r.get("gap_contribution")),
            "strength_contribution": _safe_float(r.get("strength_contribution")),
            "adjusted_score": _safe_float(r.get("adjusted_score")),
            "is_discovery": r.get("is_discovery") == "1",
            "source": r.get("source", "tory"),
            "locked_by_coach": r.get("locked_by_coach") == "1",
            "match_rationale": r.get("match_rationale"),
            "matching_traits": _parse_json(r.get("matching_traits")),
            "pedagogy_mode": r.get("pedagogy_mode"),
            "lesson_title": r.get("lesson_title"),
            "journey_title": r.get("journey_title"),
            "created_at": r.get("created_at"),
        })

    # Path events timeline
    events = _mysql_query(
        f"SELECT pe.id, pe.event_type, pe.reason, pe.details, pe.divergence_pct, "
        f"pe.flagged_for_review, pe.created_at, c.username AS coach_name "
        f"FROM tory_path_events pe "
        f"LEFT JOIN coaches c ON pe.coach_id = c.id "
        f"WHERE pe.nx_user_id = {int(learner_id)} AND pe.deleted_at IS NULL "
        f"ORDER BY pe.created_at DESC"
    )
    path_events = []
    for e in events:
        path_events.append({
            "id": _safe_int(e["id"]),
            "event_type": e.get("event_type"),
            "reason": e.get("reason"),
            "details": _parse_json(e.get("details")),
            "divergence_pct": _safe_int(e.get("divergence_pct")) if e.get("divergence_pct") and e["divergence_pct"] != "NULL" else None,
            "flagged_for_review": e.get("flagged_for_review") == "1",
            "coach_name": e.get("coach_name"),
            "created_at": e.get("created_at"),
        })

    # Reassessment history
    reassessments = _mysql_query(
        f"SELECT id, type, trigger_reason, status, drift_detected, path_action, "
        f"sent_at, completed_at, expires_at, created_at "
        f"FROM tory_reassessments "
        f"WHERE nx_user_id = {int(learner_id)} AND deleted_at IS NULL "
        f"ORDER BY created_at DESC"
    )
    reassessment_history = []
    for ra in reassessments:
        reassessment_history.append({
            "id": _safe_int(ra["id"]),
            "type": ra.get("type"),
            "trigger_reason": ra.get("trigger_reason"),
            "status": ra.get("status"),
            "drift_detected": ra.get("drift_detected") == "1",
            "path_action": ra.get("path_action"),
            "sent_at": ra.get("sent_at"),
            "completed_at": ra.get("completed_at"),
            "created_at": ra.get("created_at"),
        })

    # Feedback history
    feedback = _mysql_query(
        f"SELECT id, type, comment, profile_version, resolved, created_at "
        f"FROM tory_feedback "
        f"WHERE nx_user_id = {int(learner_id)} AND deleted_at IS NULL "
        f"ORDER BY created_at DESC"
    )
    feedback_history = []
    for fb in feedback:
        feedback_history.append({
            "id": _safe_int(fb["id"]),
            "type": fb.get("type"),
            "comment": fb.get("comment"),
            "profile_version": _safe_int(fb.get("profile_version")),
            "resolved": fb.get("resolved") == "1",
            "created_at": fb.get("created_at"),
        })

    # Coach flags
    flags = _mysql_query(
        f"SELECT cf.*, c.username AS coach_name "
        f"FROM tory_coach_flags cf "
        f"LEFT JOIN coaches c ON cf.coach_id = c.id "
        f"WHERE cf.nx_user_id = {int(learner_id)} AND cf.deleted_at IS NULL "
        f"ORDER BY cf.id DESC LIMIT 1"
    )
    coach = None
    if flags:
        f = flags[0]
        coach = {
            "coach_id": _safe_int(f["coach_id"]),
            "coach_name": f.get("coach_name"),
            "compat_signal": f.get("compat_signal", "green"),
            "compat_message": f.get("compat_message"),
        }

    return {
        "profile": profile,
        "recommendations": recommendations,
        "path_events": path_events,
        "reassessment_history": reassessment_history,
        "feedback_history": feedback_history,
        "coach": coach,
        "discovery_count": sum(1 for r in recommendations if r["is_discovery"]),
        "total_count": len(recommendations),
        "coach_modified_count": sum(1 for r in recommendations if r["locked_by_coach"]),
    }


# ── Aggregate Metrics ────────────────────────────────────────────────────────

@router.get("/metrics")
async def get_aggregate_metrics():
    """Aggregate metrics: active paths, avg completion, avg match, content gaps, coach stats."""

    # Active paths count
    active_paths = _mysql_query(
        "SELECT COUNT(DISTINCT nx_user_id) AS cnt "
        "FROM tory_recommendations WHERE deleted_at IS NULL"
    )
    total_active_paths = _safe_int(active_paths[0]["cnt"]) if active_paths else 0

    # Total profiles
    total_profiles = _mysql_query(
        "SELECT COUNT(DISTINCT nx_user_id) AS cnt "
        "FROM tory_learner_profiles WHERE deleted_at IS NULL"
    )
    total_profile_count = _safe_int(total_profiles[0]["cnt"]) if total_profiles else 0

    # Average match score
    avg_score = _mysql_query(
        "SELECT AVG(match_score) AS avg_score, "
        "MIN(match_score) AS min_score, MAX(match_score) AS max_score "
        "FROM tory_recommendations WHERE deleted_at IS NULL"
    )
    avg_match = round(_safe_float(avg_score[0]["avg_score"]), 1) if avg_score else 0
    min_match = round(_safe_float(avg_score[0]["min_score"]), 1) if avg_score else 0
    max_match = round(_safe_float(avg_score[0]["max_score"]), 1) if avg_score else 0

    # Coach intervention rate
    total_recs = _mysql_query(
        "SELECT COUNT(*) AS total, SUM(locked_by_coach) AS coach_locked, "
        "SUM(CASE WHEN source = 'coach' THEN 1 ELSE 0 END) AS coach_sourced "
        "FROM tory_recommendations WHERE deleted_at IS NULL"
    )
    total_rec_count = _safe_int(total_recs[0]["total"]) if total_recs else 0
    coach_locked = _safe_int(total_recs[0]["coach_locked"]) if total_recs else 0
    coach_sourced = _safe_int(total_recs[0]["coach_sourced"]) if total_recs else 0
    intervention_rate = round((coach_locked + coach_sourced) / max(total_rec_count, 1) * 100, 1)

    # Content gap heatmap: EPP dimensions with fewer than 5 tagged lessons
    # Get all trait tags from content_tags and count lessons per trait
    trait_rows = _mysql_query(
        "SELECT trait_tags FROM tory_content_tags "
        "WHERE deleted_at IS NULL AND review_status != 'rejected'"
    )

    trait_lesson_count = {}
    for tr in trait_rows:
        tags = _parse_json(tr.get("trait_tags"))
        if isinstance(tags, list):
            for tag in tags:
                trait_name = tag.get("trait") if isinstance(tag, dict) else str(tag)
                if trait_name:
                    trait_lesson_count[trait_name] = trait_lesson_count.get(trait_name, 0) + 1

    # All 29 EPP dimensions
    epp_dimensions = [
        "Achievement", "Motivation", "Competitiveness", "Goal_Setting",
        "Planning", "Initiative", "Team_Player", "Manageability",
        "Decisiveness", "Accommodation", "Savvy", "Dominance",
        "Self_Confidence", "Empathy", "Helpfulness", "Sociability",
        "Approval_Seeking", "Self_Disclosure", "Composure",
        "Positive_About_People", "Social_Desirability",
        "JobFit_Accountability", "JobFit_Interpersonal_Skills",
        "JobFit_Management_Leadership", "JobFit_Motivational_Fit",
        "JobFit_Self_Management", "Energy", "Stress_Tolerance",
        "Openness_To_Feedback",
    ]

    content_gaps = []
    for dim in epp_dimensions:
        count = trait_lesson_count.get(dim, 0)
        content_gaps.append({
            "dimension": dim,
            "lesson_count": count,
            "is_gap": count < 5,
        })

    # Sort: gaps first (fewest lessons), then by name
    content_gaps.sort(key=lambda g: (0 if g["is_gap"] else 1, g["lesson_count"], g["dimension"]))

    # Content tag stats
    tag_stats = _mysql_query(
        "SELECT review_status, COUNT(*) AS cnt, AVG(confidence) AS avg_conf "
        "FROM tory_content_tags WHERE deleted_at IS NULL "
        "GROUP BY review_status"
    )
    content_review = {}
    for ts in tag_stats:
        content_review[ts["review_status"]] = {
            "count": _safe_int(ts["cnt"]),
            "avg_confidence": round(_safe_float(ts.get("avg_conf")), 1),
        }

    # Path events breakdown
    event_stats = _mysql_query(
        "SELECT event_type, COUNT(*) AS cnt "
        "FROM tory_path_events WHERE deleted_at IS NULL "
        "GROUP BY event_type"
    )
    event_breakdown = {e["event_type"]: _safe_int(e["cnt"]) for e in event_stats}

    # Pedagogy mode distribution
    pedagogy_rows = _mysql_query(
        "SELECT pedagogy_mode, COUNT(DISTINCT nx_user_id) AS user_count "
        "FROM tory_recommendations "
        "WHERE deleted_at IS NULL AND pedagogy_mode IS NOT NULL "
        "GROUP BY pedagogy_mode"
    )
    pedagogy_distribution = {p["pedagogy_mode"]: _safe_int(p["user_count"]) for p in pedagogy_rows}

    return {
        "summary": {
            "total_active_paths": total_active_paths,
            "total_profiles": total_profile_count,
            "avg_match_score": avg_match,
            "min_match_score": min_match,
            "max_match_score": max_match,
            "coach_intervention_rate": intervention_rate,
            "total_recommendations": total_rec_count,
            "coach_locked": coach_locked,
            "coach_sourced": coach_sourced,
        },
        "content_gaps": content_gaps,
        "content_review": content_review,
        "event_breakdown": event_breakdown,
        "pedagogy_distribution": pedagogy_distribution,
    }


# ── Activity Heatmap ──────────────────────────────────────────────────────────

@router.get("/activity-heatmap")
async def get_activity_heatmap():
    """Activity counts grouped by date and type for last 12 weeks."""
    rows = _mysql_query(
        "SELECT DATE(created_at) AS day, log_name, COUNT(*) AS cnt "
        "FROM activity_log "
        "WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 12 WEEK) "
        "GROUP BY DATE(created_at), log_name "
        "ORDER BY day"
    )
    # Build day→{type→count} map
    days = {}
    for r in rows:
        d = r["day"]
        if d not in days:
            days[d] = {"date": d, "total": 0, "breakdown": {}}
        cnt = _safe_int(r["cnt"])
        days[d]["breakdown"][r["log_name"]] = cnt
        days[d]["total"] += cnt

    return {"days": list(days.values())}


# ── EPP Aggregate ─────────────────────────────────────────────────────────────

@router.get("/epp-aggregate")
async def get_epp_aggregate():
    """Aggregate EPP scores across all assessed users. Returns per-dimension averages."""
    rows = _mysql_query(
        "SELECT nx_user_id, assesment_result FROM nx_user_onboardings "
        "WHERE assesment_result IS NOT NULL AND assesment_result != 'NULL' "
        "AND assesment_result != ''"
    )

    dimension_sums = {}
    dimension_counts = {}
    user_count = 0

    for r in rows:
        parsed = _parse_json(r.get("assesment_result"))
        if not isinstance(parsed, dict):
            continue
        # EPP scores are nested under 'scores' key with EPP prefix
        scores = parsed.get("scores", parsed)
        if not isinstance(scores, dict):
            continue
        has_epp = False
        for dim, val in scores.items():
            if not dim.startswith("EPP") or dim in ("EPPPercentMatch", "EPPInconsistency", "EPPInvalid"):
                continue
            score = _safe_float(val)
            if score > 0:
                # Strip EPP prefix for cleaner labels
                clean_dim = dim[3:]  # "EPPAchievement" → "Achievement"
                dimension_sums[clean_dim] = dimension_sums.get(clean_dim, 0) + score
                dimension_counts[clean_dim] = dimension_counts.get(clean_dim, 0) + 1
                has_epp = True
        if has_epp:
            user_count += 1

    averages = {}
    for dim in dimension_sums:
        cnt = dimension_counts[dim]
        averages[dim] = round(dimension_sums[dim] / cnt, 1) if cnt > 0 else 0

    return {
        "user_count": user_count,
        "dimension_averages": averages,
    }


# ── Onboarding Funnel ────────────────────────────────────────────────────────

@router.get("/funnel")
async def get_funnel():
    """Onboarding funnel: total_users → has_epp → has_profile → has_path → active_30d."""
    total = _mysql_query("SELECT COUNT(*) AS cnt FROM nx_users WHERE deleted_at IS NULL")
    total_users = _safe_int(total[0]["cnt"]) if total else 0

    has_epp = _mysql_query(
        "SELECT COUNT(DISTINCT nx_user_id) AS cnt FROM nx_user_onboardings "
        "WHERE assesment_result IS NOT NULL AND assesment_result != 'NULL' AND assesment_result != ''"
    )
    epp_count = _safe_int(has_epp[0]["cnt"]) if has_epp else 0

    has_profile = _mysql_query(
        "SELECT COUNT(DISTINCT nx_user_id) AS cnt FROM tory_learner_profiles WHERE deleted_at IS NULL"
    )
    profile_count = _safe_int(has_profile[0]["cnt"]) if has_profile else 0

    has_path = _mysql_query(
        "SELECT COUNT(DISTINCT nx_user_id) AS cnt FROM tory_recommendations WHERE deleted_at IS NULL"
    )
    path_count = _safe_int(has_path[0]["cnt"]) if has_path else 0

    active_30d = _mysql_query(
        "SELECT COUNT(DISTINCT subject_id) AS cnt FROM activity_log "
        "WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) "
        "AND subject_type LIKE '%User%'"
    )
    active_count = _safe_int(active_30d[0]["cnt"]) if active_30d else 0

    steps = [
        {"label": "Total Users", "count": total_users},
        {"label": "Completed EPP", "count": epp_count},
        {"label": "AI Profiled", "count": profile_count},
        {"label": "Has Learning Path", "count": path_count},
        {"label": "Active (30d)", "count": active_count},
    ]
    # Add conversion percentages
    for i, step in enumerate(steps):
        if i == 0:
            step["conversion"] = 100
        else:
            prev = steps[i - 1]["count"]
            step["conversion"] = round(step["count"] / max(prev, 1) * 100, 1)

    return {"steps": steps}


# ── Learner Activity Timeline ────────────────────────────────────────────────

@router.get("/learner/{learner_id}/activity")
async def get_learner_activity(learner_id: int):
    """Recent activity log entries for a specific learner."""
    rows = _mysql_query(
        f"SELECT log_name, description, properties, created_at "
        f"FROM activity_log "
        f"WHERE subject_id = {int(learner_id)} AND subject_type LIKE '%User%' "
        f"ORDER BY created_at DESC LIMIT 50"
    )
    activities = []
    for r in rows:
        activities.append({
            "type": r.get("log_name"),
            "description": r.get("description"),
            "properties": _parse_json(r.get("properties")),
            "created_at": r.get("created_at"),
        })
    return {"activities": activities, "total": len(activities)}


# ── Learner Backpack ─────────────────────────────────────────────────────────

@router.get("/learner/{learner_id}/backpack")
async def get_learner_backpack(learner_id: int):
    """Backpack entries (reflections) for a specific learner."""
    rows = _mysql_query(
        f"SELECT b.id, b.form_type, b.data, b.created_at, "
        f"l.lesson AS lesson_title, jd.journey AS journey_title "
        f"FROM backpacks b "
        f"LEFT JOIN nx_lessons l ON b.nx_lesson_id = l.id "
        f"LEFT JOIN nx_journey_details jd ON b.nx_journey_detail_id = jd.id "
        f"WHERE b.created_by = {int(learner_id)} AND b.user_type = 'User' "
        f"AND b.deleted_at IS NULL "
        f"ORDER BY b.created_at DESC LIMIT 30"
    )
    entries = []
    for r in rows:
        entries.append({
            "id": _safe_int(r["id"]),
            "form_type": r.get("form_type"),
            "data": _parse_json(r.get("data")),
            "lesson_title": r.get("lesson_title"),
            "journey_title": r.get("journey_title"),
            "created_at": r.get("created_at"),
        })
    return {"entries": entries, "total": len(entries)}


# ── Match Score Distribution ─────────────────────────────────────────────────

@router.get("/score-distribution")
async def get_score_distribution():
    """Match score histogram: count of learners per score bucket."""
    rows = _mysql_query(
        "SELECT "
        "CASE "
        "  WHEN avg_score < 20 THEN '0-20' "
        "  WHEN avg_score < 40 THEN '20-40' "
        "  WHEN avg_score < 60 THEN '40-60' "
        "  WHEN avg_score < 80 THEN '60-80' "
        "  ELSE '80-100' "
        "END AS bucket, COUNT(*) AS cnt "
        "FROM ("
        "  SELECT nx_user_id, AVG(match_score) AS avg_score "
        "  FROM tory_recommendations WHERE deleted_at IS NULL "
        "  GROUP BY nx_user_id"
        ") sub GROUP BY bucket ORDER BY bucket"
    )
    buckets = []
    for r in rows:
        buckets.append({"range": r["bucket"], "count": _safe_int(r["cnt"])})
    return {"buckets": buckets}


# ── Coach Workload ───────────────────────────────────────────────────────────

@router.get("/coach-workload")
async def get_coach_workload():
    """Learner count per coach with average compatibility."""
    rows = _mysql_query(
        "SELECT c.username AS coach_name, c.id AS coach_id, "
        "COUNT(DISTINCT cf.nx_user_id) AS learner_count, "
        "AVG(CASE WHEN cf.compat_signal = 'green' THEN 3 "
        "  WHEN cf.compat_signal = 'yellow' THEN 2 "
        "  WHEN cf.compat_signal = 'red' THEN 1 ELSE 2 END) AS avg_compat "
        "FROM tory_coach_flags cf "
        "JOIN coaches c ON cf.coach_id = c.id "
        "WHERE cf.deleted_at IS NULL "
        "GROUP BY c.id, c.username "
        "ORDER BY learner_count DESC"
    )
    coaches = []
    for r in rows:
        coaches.append({
            "coach_name": r.get("coach_name"),
            "coach_id": _safe_int(r["coach_id"]),
            "learner_count": _safe_int(r["learner_count"]),
            "avg_compat": round(_safe_float(r.get("avg_compat")), 1),
        })
    return {"coaches": coaches}


# ── Lesson Popularity ────────────────────────────────────────────────────────

@router.get("/lesson-popularity")
async def get_lesson_popularity():
    """Top 10 lessons by number of learners assigned."""
    rows = _mysql_query(
        "SELECT r.nx_lesson_id, l.lesson AS lesson_title, "
        "jd.journey AS journey_title, "
        "COUNT(DISTINCT r.nx_user_id) AS learner_count "
        "FROM tory_recommendations r "
        "LEFT JOIN nx_lessons l ON r.nx_lesson_id = l.id "
        "LEFT JOIN nx_journey_details jd ON l.nx_journey_detail_id = jd.id "
        "WHERE r.deleted_at IS NULL "
        "GROUP BY r.nx_lesson_id, l.lesson, jd.journey "
        "ORDER BY learner_count DESC LIMIT 10"
    )
    lessons = []
    for r in rows:
        lessons.append({
            "lesson_id": _safe_int(r["nx_lesson_id"]),
            "lesson_title": r.get("lesson_title") or f"Lesson {r['nx_lesson_id']}",
            "journey_title": r.get("journey_title") or "",
            "learner_count": _safe_int(r["learner_count"]),
        })
    return {"lessons": lessons}


# ── Companies List ───────────────────────────────────────────────────────────

@router.get("/companies")
async def get_companies():
    """All companies with learner counts."""
    rows = _mysql_query(
        "SELECT cl.id, cl.company_name, COUNT(DISTINCT e.nx_user_id) AS user_count "
        "FROM clients cl "
        "LEFT JOIN departments d ON d.client_id = cl.id AND d.deleted_at IS NULL "
        "LEFT JOIN employees e ON e.department_id = d.id AND e.deleted_at IS NULL "
        "WHERE cl.deleted_at IS NULL "
        "GROUP BY cl.id, cl.company_name "
        "ORDER BY cl.company_name"
    )
    companies = []
    for r in rows:
        companies.append({
            "id": _safe_int(r["id"]),
            "name": r.get("company_name"),
            "user_count": _safe_int(r["user_count"]),
        })
    return {"companies": companies}
