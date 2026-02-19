#!/usr/bin/env python3
"""
Tory Notification Service — SMS/email notifications for learning path events.

Triggers notifications when:
1. Path generated → welcome SMS/email with roadmap link
2. Reassessment path change → explanatory notification
3. Coach path change → notification crediting the coach
4. Reassessment reminder → 7 days before scheduled EPP retake

Enforces:
- 24-hour batch window: max 1 Tory notification per learner per 24h (except initial generation)
- Opt-out tracking: per learner, per notification type

Bead: baap-qkk.7
"""

import json
import subprocess
from datetime import datetime, timedelta
from typing import Optional

DATABASE = "baap"
QUERY_TIMEOUT = 30
APP_URL = "https://app.mynextory.com"

# Notification types
TYPE_PATH_GENERATED = "path_generated"
TYPE_REASSESSMENT_CHANGE = "reassessment_change"
TYPE_COACH_CHANGE = "coach_change"
TYPE_REASSESSMENT_REMINDER = "reassessment_reminder"

ALL_NOTIFICATION_TYPES = [
    TYPE_PATH_GENERATED,
    TYPE_REASSESSMENT_CHANGE,
    TYPE_COACH_CHANGE,
    TYPE_REASSESSMENT_REMINDER,
]

# Map tory_path_events.event_type → notification type
EVENT_TYPE_MAP = {
    "reassessed": TYPE_REASSESSMENT_CHANGE,
    "reordered": TYPE_COACH_CHANGE,
    "swapped": TYPE_COACH_CHANGE,
    "locked": TYPE_COACH_CHANGE,
}

# Batch-exempt types (always send immediately)
BATCH_EXEMPT_TYPES = {TYPE_PATH_GENERATED, TYPE_REASSESSMENT_REMINDER}

BATCH_WINDOW_HOURS = 24


# ---------------------------------------------------------------------------
# MySQL helpers (mirrors tory_engine.py pattern)
# ---------------------------------------------------------------------------


def mysql_query(sql: str) -> tuple[list[str], list[dict]]:
    """Execute a read-only MySQL query."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL error: {result.stderr.strip()}")

    output = result.stdout.strip()
    if not output:
        return [], []

    lines = output.split("\n")
    headers = lines[0].split("\t")
    if len(lines) < 2:
        return headers, []

    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        row = {h: (values[i] if i < len(values) else None) for i, h in enumerate(headers)}
        rows.append(row)
    return headers, rows


def mysql_write(sql: str) -> None:
    """Execute a write query."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL write error: {result.stderr.strip()}")


def escape_sql(value: str) -> str:
    """Escape a string for safe SQL insertion."""
    if value is None:
        return "NULL"
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r")
    escaped = escaped.replace("\x00", "").replace("\x1a", "")
    return f"'{escaped}'"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


def get_learner_contact(nx_user_id: int) -> dict:
    """Fetch learner email, mobile, and first name for notification delivery."""
    _, rows = mysql_query(
        f"SELECT u.id, u.email, o.first_name, o.last_name, o.mobile_no "
        f"FROM nx_users u "
        f"LEFT JOIN nx_user_onboardings o ON o.nx_user_id = u.id "
        f"WHERE u.id = {int(nx_user_id)} AND u.deleted_at IS NULL "
        f"LIMIT 1"
    )
    if not rows:
        return {}
    row = rows[0]
    return {
        "nx_user_id": int(row["id"]),
        "email": row.get("email"),
        "first_name": row.get("first_name") or "Learner",
        "last_name": row.get("last_name") or "",
        "mobile_no": row.get("mobile_no"),
    }


def get_path_event(event_id: int) -> Optional[dict]:
    """Fetch a single path event by ID."""
    _, rows = mysql_query(
        f"SELECT * FROM tory_path_events WHERE id = {int(event_id)} "
        f"AND deleted_at IS NULL LIMIT 1"
    )
    return rows[0] if rows else None


def get_coach_name(coach_id: int) -> str:
    """Fetch coach display name."""
    if not coach_id or int(coach_id) == 0:
        return "your coach"
    _, rows = mysql_query(
        f"SELECT cp.first_name, cp.last_name FROM coach_profiles cp "
        f"WHERE cp.coach_id = {int(coach_id)} LIMIT 1"
    )
    if rows and rows[0].get("first_name"):
        first = rows[0]["first_name"]
        last = rows[0].get("last_name") or ""
        return f"{first} {last}".strip()
    return "your coach"


def get_pending_reassessments_due_in_days(days: int) -> list[dict]:
    """Find reassessments with status=pending whose created_at + 90 days is within
    `days` days from now (i.e., the EPP retake is due in ~`days` days)."""
    target_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    _, rows = mysql_query(
        f"SELECT r.*, DATE_ADD(r.created_at, INTERVAL 90 DAY) AS due_date "
        f"FROM tory_reassessments r "
        f"WHERE r.status = 'pending' "
        f"AND r.type = 'quarterly' "
        f"AND r.deleted_at IS NULL "
        f"AND DATE(DATE_ADD(r.created_at, INTERVAL 90 DAY)) = '{target_date}' "
    )
    return rows


def get_active_recommendations_summary(nx_user_id: int) -> dict:
    """Summarize a learner's current path for notification content."""
    _, rows = mysql_query(
        f"SELECT COUNT(*) as total, "
        f"SUM(is_discovery) as discovery_count "
        f"FROM tory_recommendations "
        f"WHERE nx_user_id = {int(nx_user_id)} AND deleted_at IS NULL"
    )
    if not rows:
        return {"total": 0, "discovery_count": 0}
    return {
        "total": int(rows[0].get("total") or 0),
        "discovery_count": int(rows[0].get("discovery_count") or 0),
    }


# ---------------------------------------------------------------------------
# Opt-out management
# ---------------------------------------------------------------------------


def is_opted_out(nx_user_id: int, notification_type: str) -> bool:
    """Check if a learner has opted out of a specific notification type."""
    _, rows = mysql_query(
        f"SELECT opted_out FROM tory_notification_optouts "
        f"WHERE nx_user_id = {int(nx_user_id)} "
        f"AND notification_type IN ('{notification_type}', 'all') "
        f"AND opted_out = 1 "
        f"AND deleted_at IS NULL "
        f"LIMIT 1"
    )
    return len(rows) > 0


def set_opt_out(nx_user_id: int, notification_type: str, opted_out: bool = True) -> None:
    """Set or clear an opt-out for a learner and notification type."""
    now = now_str()
    if opted_out:
        mysql_write(
            f"INSERT INTO tory_notification_optouts "
            f"(nx_user_id, notification_type, opted_out, opted_out_at, created_at, updated_at) "
            f"VALUES ({int(nx_user_id)}, '{notification_type}', 1, '{now}', '{now}', '{now}') "
            f"ON DUPLICATE KEY UPDATE opted_out = 1, opted_out_at = '{now}', "
            f"opted_in_at = NULL, updated_at = '{now}'"
        )
    else:
        mysql_write(
            f"INSERT INTO tory_notification_optouts "
            f"(nx_user_id, notification_type, opted_out, opted_in_at, created_at, updated_at) "
            f"VALUES ({int(nx_user_id)}, '{notification_type}', 0, '{now}', '{now}', '{now}') "
            f"ON DUPLICATE KEY UPDATE opted_out = 0, opted_in_at = '{now}', updated_at = '{now}'"
        )


def get_optout_status(nx_user_id: int) -> list[dict]:
    """Get all opt-out records for a learner."""
    _, rows = mysql_query(
        f"SELECT notification_type, opted_out, opted_out_at, opted_in_at "
        f"FROM tory_notification_optouts "
        f"WHERE nx_user_id = {int(nx_user_id)} AND deleted_at IS NULL"
    )
    return rows


# ---------------------------------------------------------------------------
# Batch window enforcement
# ---------------------------------------------------------------------------


def get_last_sent_time(nx_user_id: int) -> Optional[datetime]:
    """Get the most recent sent_at for a learner's Tory notifications."""
    _, rows = mysql_query(
        f"SELECT sent_at FROM tory_notification_log "
        f"WHERE nx_user_id = {int(nx_user_id)} "
        f"AND status = 'sent' "
        f"AND deleted_at IS NULL "
        f"ORDER BY sent_at DESC LIMIT 1"
    )
    if not rows or not rows[0].get("sent_at"):
        return None
    return datetime.strptime(rows[0]["sent_at"], "%Y-%m-%d %H:%M:%S")


def is_within_batch_window(nx_user_id: int) -> bool:
    """Check if the learner received a Tory notification within the last 24 hours."""
    last_sent = get_last_sent_time(nx_user_id)
    if not last_sent:
        return False
    return (datetime.now() - last_sent) < timedelta(hours=BATCH_WINDOW_HOURS)


def get_batched_notifications(nx_user_id: int) -> list[dict]:
    """Get notifications currently in batched state for a learner."""
    _, rows = mysql_query(
        f"SELECT * FROM tory_notification_log "
        f"WHERE nx_user_id = {int(nx_user_id)} "
        f"AND status = 'batched' "
        f"AND deleted_at IS NULL "
        f"ORDER BY created_at ASC"
    )
    return rows


def release_batched_notifications() -> list[dict]:
    """Find and return batched notifications whose window has expired.
    Called periodically (e.g., every hour) by a background worker."""
    now = now_str()
    _, rows = mysql_query(
        f"SELECT * FROM tory_notification_log "
        f"WHERE status = 'batched' "
        f"AND batched_until IS NOT NULL "
        f"AND batched_until <= '{now}' "
        f"AND deleted_at IS NULL "
        f"ORDER BY nx_user_id, created_at ASC"
    )
    return rows


# ---------------------------------------------------------------------------
# Notification templates
# ---------------------------------------------------------------------------


def build_welcome_notification(contact: dict, path_summary: dict) -> dict:
    """Build welcome SMS/email content for a newly generated path."""
    first_name = contact["first_name"]
    total = path_summary["total"]
    discovery = path_summary["discovery_count"]
    roadmap_link = f"{APP_URL}/my-path"

    sms_body = (
        f"Hi {first_name}! Your personalized learning path is ready on myNextory. "
        f"{total} lessons selected just for you. Start exploring: {roadmap_link}"
    )

    email_subject = "Your Personalized Learning Path is Ready!"
    email_body = (
        f"Hi {first_name},\n\n"
        f"Great news! Your personalized learning path has been created on myNextory.\n\n"
        f"We've selected {total} lessons tailored to your unique profile"
    )
    if discovery:
        email_body += (
            f", starting with {discovery} discovery lessons to help us "
            f"understand your learning preferences"
        )
    email_body += (
        f".\n\n"
        f"View your path: {roadmap_link}\n\n"
        f"Your coach will be available to guide you along the way.\n\n"
        f"Best,\nThe myNextory Team"
    )

    return {
        "notification_type": TYPE_PATH_GENERATED,
        "sms_body": sms_body,
        "email_subject": email_subject,
        "email_body": email_body,
    }


def build_reassessment_change_notification(contact: dict, reason: str) -> dict:
    """Build notification for a reassessment-triggered path change."""
    first_name = contact["first_name"]
    roadmap_link = f"{APP_URL}/my-path"

    # Clean up reason for user-facing message
    user_reason = reason if reason and reason != "NULL" else "your updated assessment results"

    sms_body = (
        f"Hi {first_name}, your myNextory learning path has been updated based on "
        f"{user_reason}. Check it out: {roadmap_link}"
    )

    email_subject = "Your Learning Path Has Been Updated"
    email_body = (
        f"Hi {first_name},\n\n"
        f"Your learning path on myNextory has been updated.\n\n"
        f"Why: {user_reason}\n\n"
        f"Your path now better reflects your current strengths and growth areas. "
        f"Some lessons may have been reordered or replaced to match your updated profile.\n\n"
        f"View your updated path: {roadmap_link}\n\n"
        f"Best,\nThe myNextory Team"
    )

    return {
        "notification_type": TYPE_REASSESSMENT_CHANGE,
        "sms_body": sms_body,
        "email_subject": email_subject,
        "email_body": email_body,
    }


def build_coach_change_notification(contact: dict, reason: str, coach_name: str) -> dict:
    """Build notification for a coach-initiated path change."""
    first_name = contact["first_name"]
    roadmap_link = f"{APP_URL}/my-path"

    user_reason = reason if reason and reason != "NULL" else "personalize your learning experience"

    sms_body = (
        f"Hi {first_name}, {coach_name} has personalized your myNextory learning path. "
        f"See what's new: {roadmap_link}"
    )

    email_subject = f"{coach_name} Updated Your Learning Path"
    email_body = (
        f"Hi {first_name},\n\n"
        f"{coach_name} has made changes to your learning path on myNextory.\n\n"
        f"Why: {user_reason}\n\n"
        f"Your coach knows your goals and has tailored your path to help you "
        f"get there faster.\n\n"
        f"View your updated path: {roadmap_link}\n\n"
        f"Best,\nThe myNextory Team"
    )

    return {
        "notification_type": TYPE_COACH_CHANGE,
        "sms_body": sms_body,
        "email_subject": email_subject,
        "email_body": email_body,
    }


def build_reassessment_reminder(contact: dict, due_date: str) -> dict:
    """Build reminder notification for upcoming EPP retake."""
    first_name = contact["first_name"]
    assessment_link = f"{APP_URL}/assessment"

    sms_body = (
        f"Hi {first_name}, your myNextory assessment retake is coming up on {due_date}. "
        f"Complete it to keep your learning path up to date!"
    )

    email_subject = "Your Assessment Retake is Coming Up"
    email_body = (
        f"Hi {first_name},\n\n"
        f"Your quarterly EPP assessment retake is scheduled for {due_date}.\n\n"
        f"Completing the retake helps us keep your learning path aligned with "
        f"your growth and development.\n\n"
        f"Start your assessment: {assessment_link}\n\n"
        f"Best,\nThe myNextory Team"
    )

    return {
        "notification_type": TYPE_REASSESSMENT_REMINDER,
        "sms_body": sms_body,
        "email_subject": email_subject,
        "email_body": email_body,
    }


# ---------------------------------------------------------------------------
# Notification delivery
# ---------------------------------------------------------------------------


def log_notification(
    nx_user_id: int,
    notification_type: str,
    channel: str,
    subject: Optional[str],
    body: str,
    reason: Optional[str],
    status: str,
    path_event_id: Optional[int] = None,
    batched_until: Optional[str] = None,
    sent_at: Optional[str] = None,
) -> int:
    """Write a notification record to tory_notification_log. Returns the new row ID."""
    now = now_str()
    subject_esc = escape_sql(subject) if subject else "NULL"
    body_esc = escape_sql(body)
    reason_esc = escape_sql(reason) if reason else "NULL"
    pe_id = int(path_event_id) if path_event_id else "NULL"
    batch_val = f"'{batched_until}'" if batched_until else "NULL"
    sent_val = f"'{sent_at}'" if sent_at else "NULL"

    sql = (
        f"INSERT INTO tory_notification_log "
        f"(nx_user_id, notification_type, channel, path_event_id, "
        f"subject, body, reason, status, batched_until, sent_at, "
        f"created_at, updated_at) "
        f"VALUES ({int(nx_user_id)}, '{notification_type}', '{channel}', "
        f"{pe_id}, {subject_esc}, {body_esc}, {reason_esc}, "
        f"'{status}', {batch_val}, {sent_val}, '{now}', '{now}')"
    )
    mysql_write(sql)

    _, rows = mysql_query(
        f"SELECT id FROM tory_notification_log WHERE nx_user_id = {int(nx_user_id)} "
        f"ORDER BY id DESC LIMIT 1"
    )
    return int(rows[0]["id"]) if rows else 0


def mark_notification_sent(notification_id: int) -> None:
    """Mark a notification as sent."""
    now = now_str()
    mysql_write(
        f"UPDATE tory_notification_log SET status = 'sent', sent_at = '{now}', "
        f"updated_at = '{now}' WHERE id = {int(notification_id)}"
    )


def mark_notification_failed(notification_id: int, error: str) -> None:
    """Mark a notification as failed."""
    now = now_str()
    error_esc = escape_sql(error[:500])
    mysql_write(
        f"UPDATE tory_notification_log SET status = 'failed', "
        f"error_detail = {error_esc}, updated_at = '{now}' "
        f"WHERE id = {int(notification_id)}"
    )


def deliver_sms(mobile_no: str, body: str, nx_user_id: int) -> bool:
    """Send an SMS via the existing sms_details infrastructure.

    In production, this would call the SMS provider API (ClickSend).
    For now, we log the SMS to sms_details for the background job to pick up.
    """
    if not mobile_no or mobile_no == "NULL":
        return False
    now = now_str()
    body_esc = escape_sql(body)
    mobile_esc = escape_sql(mobile_no)
    mysql_write(
        f"INSERT INTO sms_details "
        f"(nx_user_id, sms_type, mobile_number, message, created_at) "
        f"VALUES ({int(nx_user_id)}, 'tory_notification', {mobile_esc}, "
        f"{body_esc}, '{now}')"
    )
    return True


def deliver_email(email: str, subject: str, body: str, nx_user_id: int) -> bool:
    """Send an email via the existing mail infrastructure.

    Logs to mail_communication_details for the background mailer to pick up.
    """
    if not email or email == "NULL":
        return False
    now = now_str()
    subject_esc = escape_sql(subject)
    body_esc = escape_sql(body)
    mysql_write(
        f"INSERT INTO mail_communication_details "
        f"(query_type, subject, description, status, from_type, from_id, "
        f"user_id, created_at, updated_at) "
        f"VALUES ('tory_notification', {subject_esc}, {body_esc}, 'pending', "
        f"'system', 0, '{int(nx_user_id)}', '{now}', '{now}')"
    )
    return True


# ---------------------------------------------------------------------------
# Core notification dispatcher
# ---------------------------------------------------------------------------


def send_notification(
    nx_user_id: int,
    notification_type: str,
    sms_body: str,
    email_subject: str,
    email_body: str,
    reason: Optional[str] = None,
    path_event_id: Optional[int] = None,
) -> dict:
    """Send a notification to a learner via SMS and email.

    Handles opt-out checking and batch window enforcement.
    Returns a result dict with delivery status for each channel.
    """
    result = {
        "nx_user_id": nx_user_id,
        "notification_type": notification_type,
        "channels": {},
        "skipped": False,
        "batched": False,
    }

    # 1. Check opt-out
    if is_opted_out(nx_user_id, notification_type):
        # Log as skipped
        log_notification(
            nx_user_id=nx_user_id,
            notification_type=notification_type,
            channel="all",
            subject=email_subject,
            body=email_body,
            reason=reason,
            status="skipped",
            path_event_id=path_event_id,
        )
        result["skipped"] = True
        result["skip_reason"] = "opted_out"
        return result

    # 2. Check batch window (exempt types bypass this)
    if notification_type not in BATCH_EXEMPT_TYPES and is_within_batch_window(nx_user_id):
        batched_until = (datetime.now() + timedelta(hours=BATCH_WINDOW_HOURS)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        log_notification(
            nx_user_id=nx_user_id,
            notification_type=notification_type,
            channel="all",
            subject=email_subject,
            body=email_body,
            reason=reason,
            status="batched",
            path_event_id=path_event_id,
            batched_until=batched_until,
        )
        result["batched"] = True
        result["batched_until"] = batched_until
        return result

    # 3. Fetch contact info
    contact = get_learner_contact(nx_user_id)
    if not contact:
        result["skipped"] = True
        result["skip_reason"] = "user_not_found"
        return result

    # 4. Deliver SMS
    sms_result = {"attempted": False, "sent": False}
    if contact.get("mobile_no") and contact["mobile_no"] != "NULL":
        sms_result["attempted"] = True
        try:
            ok = deliver_sms(contact["mobile_no"], sms_body, nx_user_id)
            sms_result["sent"] = ok
            notif_id = log_notification(
                nx_user_id=nx_user_id,
                notification_type=notification_type,
                channel="sms",
                subject=None,
                body=sms_body,
                reason=reason,
                status="sent" if ok else "failed",
                path_event_id=path_event_id,
                sent_at=now_str() if ok else None,
            )
            if not ok:
                mark_notification_failed(notif_id, "No mobile number or delivery failed")
        except Exception as e:
            sms_result["error"] = str(e)
            log_notification(
                nx_user_id=nx_user_id,
                notification_type=notification_type,
                channel="sms",
                subject=None,
                body=sms_body,
                reason=reason,
                status="failed",
                path_event_id=path_event_id,
            )
    result["channels"]["sms"] = sms_result

    # 5. Deliver email
    email_result = {"attempted": False, "sent": False}
    if contact.get("email") and contact["email"] != "NULL":
        email_result["attempted"] = True
        try:
            ok = deliver_email(contact["email"], email_subject, email_body, nx_user_id)
            email_result["sent"] = ok
            notif_id = log_notification(
                nx_user_id=nx_user_id,
                notification_type=notification_type,
                channel="email",
                subject=email_subject,
                body=email_body,
                reason=reason,
                status="sent" if ok else "failed",
                path_event_id=path_event_id,
                sent_at=now_str() if ok else None,
            )
            if not ok:
                mark_notification_failed(notif_id, "No email or delivery failed")
        except Exception as e:
            email_result["error"] = str(e)
            log_notification(
                nx_user_id=nx_user_id,
                notification_type=notification_type,
                channel="email",
                subject=email_subject,
                body=email_body,
                reason=reason,
                status="failed",
                path_event_id=path_event_id,
            )
    result["channels"]["email"] = email_result

    return result


# ---------------------------------------------------------------------------
# Public trigger functions (called by tory_engine or background workers)
# ---------------------------------------------------------------------------


def notify_path_generated(nx_user_id: int) -> dict:
    """Trigger 1: Send welcome notification when a new learning path is generated.

    Always sends immediately (batch-exempt).
    """
    contact = get_learner_contact(nx_user_id)
    if not contact:
        return {"error": "user_not_found", "nx_user_id": nx_user_id}

    path_summary = get_active_recommendations_summary(nx_user_id)
    content = build_welcome_notification(contact, path_summary)

    return send_notification(
        nx_user_id=nx_user_id,
        notification_type=TYPE_PATH_GENERATED,
        sms_body=content["sms_body"],
        email_subject=content["email_subject"],
        email_body=content["email_body"],
        reason="Learning path generated",
    )


def notify_reassessment_change(nx_user_id: int, path_event_id: int) -> dict:
    """Trigger 2: Notify learner that their path changed due to reassessment.

    Subject to 24-hour batch window.
    """
    event = get_path_event(path_event_id)
    if not event:
        return {"error": "event_not_found", "path_event_id": path_event_id}

    contact = get_learner_contact(nx_user_id)
    if not contact:
        return {"error": "user_not_found", "nx_user_id": nx_user_id}

    reason = event.get("reason", "")
    content = build_reassessment_change_notification(contact, reason)

    return send_notification(
        nx_user_id=nx_user_id,
        notification_type=TYPE_REASSESSMENT_CHANGE,
        sms_body=content["sms_body"],
        email_subject=content["email_subject"],
        email_body=content["email_body"],
        reason=reason,
        path_event_id=path_event_id,
    )


def notify_coach_change(nx_user_id: int, path_event_id: int) -> dict:
    """Trigger 3: Notify learner that their coach personalized their path.

    Subject to 24-hour batch window. Credits the coach by name.
    """
    event = get_path_event(path_event_id)
    if not event:
        return {"error": "event_not_found", "path_event_id": path_event_id}

    contact = get_learner_contact(nx_user_id)
    if not contact:
        return {"error": "user_not_found", "nx_user_id": nx_user_id}

    coach_id = int(event.get("coach_id") or 0)
    coach_name = get_coach_name(coach_id)
    reason = event.get("reason", "")
    content = build_coach_change_notification(contact, reason, coach_name)

    return send_notification(
        nx_user_id=nx_user_id,
        notification_type=TYPE_COACH_CHANGE,
        sms_body=content["sms_body"],
        email_subject=content["email_subject"],
        email_body=content["email_body"],
        reason=reason,
        path_event_id=path_event_id,
    )


def notify_reassessment_reminder(nx_user_id: int, due_date: str) -> dict:
    """Trigger 4: Send reminder 7 days before scheduled EPP retake.

    Always sends immediately (batch-exempt, time-sensitive).
    """
    contact = get_learner_contact(nx_user_id)
    if not contact:
        return {"error": "user_not_found", "nx_user_id": nx_user_id}

    content = build_reassessment_reminder(contact, due_date)

    return send_notification(
        nx_user_id=nx_user_id,
        notification_type=TYPE_REASSESSMENT_REMINDER,
        sms_body=content["sms_body"],
        email_subject=content["email_subject"],
        email_body=content["email_body"],
        reason=f"EPP retake due {due_date}",
    )


# ---------------------------------------------------------------------------
# Event dispatcher (maps path events → notifications)
# ---------------------------------------------------------------------------


def dispatch_path_event(path_event_id: int) -> dict:
    """Given a tory_path_events row ID, determine and send the appropriate notification.

    This is the main entry point for the event-driven notification pipeline.
    """
    event = get_path_event(path_event_id)
    if not event:
        return {"error": "event_not_found", "path_event_id": path_event_id}

    event_type = event.get("event_type", "")
    nx_user_id = int(event["nx_user_id"])
    notification_type = EVENT_TYPE_MAP.get(event_type)

    if not notification_type:
        return {
            "skipped": True,
            "reason": f"No notification mapping for event_type={event_type}",
        }

    if notification_type == TYPE_REASSESSMENT_CHANGE:
        return notify_reassessment_change(nx_user_id, path_event_id)
    elif notification_type == TYPE_COACH_CHANGE:
        return notify_coach_change(nx_user_id, path_event_id)

    return {"skipped": True, "reason": f"Unhandled notification_type={notification_type}"}


# ---------------------------------------------------------------------------
# Background worker: process batched + send reminders
# ---------------------------------------------------------------------------


def process_batched_notifications() -> list[dict]:
    """Release batched notifications whose window has expired.

    Picks the most recent notification per learner (coalesces multiple
    batched notifications into one) and sends it.
    """
    eligible = release_batched_notifications()
    if not eligible:
        return []

    # Group by user, take the most recent one per user
    by_user: dict[int, dict] = {}
    for notif in eligible:
        uid = int(notif["nx_user_id"])
        by_user[uid] = notif  # last one wins (ordered by created_at ASC)

    results = []
    for uid, notif in by_user.items():
        # Re-send the most recent batched notification
        contact = get_learner_contact(uid)
        if not contact:
            continue

        notif_type = notif["notification_type"]
        subject = notif.get("subject")
        body = notif.get("body", "")

        # Deliver
        sms_ok = False
        email_ok = False
        if contact.get("mobile_no") and contact["mobile_no"] != "NULL":
            sms_ok = deliver_sms(contact["mobile_no"], body, uid)
        if contact.get("email") and contact["email"] != "NULL" and subject:
            email_ok = deliver_email(contact["email"], subject, body, uid)

        # Mark sent
        mark_notification_sent(int(notif["id"]))

        # Mark all other batched notifications for this user as skipped (coalesced)
        for other in eligible:
            if int(other["nx_user_id"]) == uid and other["id"] != notif["id"]:
                now = now_str()
                coalesced_id = notif["id"]
                other_id = int(other["id"])
                mysql_write(
                    f"UPDATE tory_notification_log SET status = 'skipped', "
                    f"error_detail = 'coalesced into notification {coalesced_id}', "
                    f"updated_at = '{now}' WHERE id = {other_id}"
                )

        results.append({
            "nx_user_id": uid,
            "notification_id": int(notif["id"]),
            "type": notif_type,
            "sms_sent": sms_ok,
            "email_sent": email_ok,
        })

    return results


def check_and_send_reassessment_reminders() -> list[dict]:
    """Check for reassessments due in 7 days and send reminders.

    Should be called daily by a background worker/cron job.
    """
    due_reassessments = get_pending_reassessments_due_in_days(7)
    results = []

    for reassessment in due_reassessments:
        nx_user_id = int(reassessment["nx_user_id"])
        due_date = reassessment.get("due_date", "upcoming")

        # Check if we already sent a reminder for this reassessment
        _, existing = mysql_query(
            f"SELECT id FROM tory_notification_log "
            f"WHERE nx_user_id = {nx_user_id} "
            f"AND notification_type = '{TYPE_REASSESSMENT_REMINDER}' "
            f"AND reason LIKE '%{due_date}%' "
            f"AND status = 'sent' "
            f"AND deleted_at IS NULL "
            f"LIMIT 1"
        )
        if existing:
            continue  # Already reminded

        result = notify_reassessment_reminder(nx_user_id, due_date)
        results.append(result)

    return results
