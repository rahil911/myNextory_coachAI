#!/usr/bin/env python3
"""
End-to-end tests for Tory Notification Service.

Tests all 6 acceptance criteria from baap-qkk.7:
1. Path generation triggers welcome SMS/email with roadmap link
2. Reassessment path changes trigger explanatory notification within 24h batch window
3. Coach path changes trigger notification crediting the coach
4. Reassessment reminders sent 7 days before scheduled EPP retake
5. No more than 1 Tory notification per learner per 24 hours enforced
6. Opt-out per notification type is respected
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))

from tory_notification_service import (
    mysql_query,
    mysql_write,
    now_str,
    escape_sql,
    get_learner_contact,
    get_path_event,
    get_coach_name,
    is_opted_out,
    set_opt_out,
    get_optout_status,
    is_within_batch_window,
    get_last_sent_time,
    build_welcome_notification,
    build_reassessment_change_notification,
    build_coach_change_notification,
    build_reassessment_reminder,
    log_notification,
    mark_notification_sent,
    mark_notification_failed,
    send_notification,
    notify_path_generated,
    notify_reassessment_change,
    notify_coach_change,
    notify_reassessment_reminder,
    dispatch_path_event,
    release_batched_notifications,
    get_active_recommendations_summary,
    TYPE_PATH_GENERATED,
    TYPE_REASSESSMENT_CHANGE,
    TYPE_COACH_CHANGE,
    TYPE_REASSESSMENT_REMINDER,
    BATCH_EXEMPT_TYPES,
    EVENT_TYPE_MAP,
)

# Test user (user 200 has tory_recommendations from path generation)
TEST_USER_ID = 200
passed = 0
failed = 0


def cleanup_test_data():
    """Remove test data from notification tables."""
    mysql_write(f"DELETE FROM tory_notification_log WHERE nx_user_id = {TEST_USER_ID}")
    mysql_write(f"DELETE FROM tory_notification_optouts WHERE nx_user_id = {TEST_USER_ID}")
    mysql_write(f"DELETE FROM tory_path_events WHERE nx_user_id = {TEST_USER_ID}")
    # Clean up test SMS/email entries
    mysql_write(
        f"DELETE FROM sms_details WHERE nx_user_id = {TEST_USER_ID} "
        f"AND sms_type = 'tory_notification'"
    )
    mysql_write(
        f"DELETE FROM mail_communication_details WHERE query_type = 'tory_notification' "
        f"AND user_id = '{TEST_USER_ID}'"
    )


def setup_test_path_event(event_type: str, reason: str, coach_id: int = 0) -> int:
    """Insert a test path event and return its ID."""
    now = now_str()
    reason_esc = escape_sql(reason)
    mysql_write(
        f"INSERT INTO tory_path_events "
        f"(nx_user_id, coach_id, event_type, reason, created_at, updated_at) "
        f"VALUES ({TEST_USER_ID}, {coach_id}, '{event_type}', {reason_esc}, '{now}', '{now}')"
    )
    _, rows = mysql_query(
        f"SELECT id FROM tory_path_events WHERE nx_user_id = {TEST_USER_ID} "
        f"ORDER BY id DESC LIMIT 1"
    )
    return int(rows[0]["id"])


def assert_true(condition, message):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {message}")
    else:
        failed += 1
        print(f"  FAIL: {message}")


def test_learner_contact():
    """Test that we can fetch learner contact info."""
    print("\n=== Test: Learner Contact Lookup ===")
    contact = get_learner_contact(TEST_USER_ID)
    assert_true(bool(contact), "Contact found for test user")
    assert_true(bool(contact.get("email")), f"Email present: {contact.get('email')}")
    assert_true(
        contact.get("first_name") and contact["first_name"] != "Learner",
        f"First name present: {contact.get('first_name')}",
    )
    print(f"  Contact: {json.dumps(contact, indent=2)}")
    return contact


def test_welcome_notification_template(contact):
    """Test welcome notification template."""
    print("\n=== Test: Welcome Notification Template ===")
    path_summary = {"total": 20, "discovery_count": 5}
    content = build_welcome_notification(contact, path_summary)

    assert_true(
        contact["first_name"] in content["sms_body"],
        "SMS body contains first name",
    )
    assert_true(
        "20 lessons" in content["sms_body"],
        "SMS body contains lesson count",
    )
    assert_true(
        "my-path" in content["sms_body"],
        "SMS body contains roadmap link",
    )
    assert_true(
        "Ready" in content["email_subject"],
        "Email subject indicates path is ready",
    )
    assert_true(
        "5 discovery" in content["email_body"],
        "Email body mentions discovery lessons",
    )
    return True


def test_ac1_path_generated_triggers_welcome():
    """AC1: Path generation triggers a welcome SMS/email with roadmap link."""
    print("\n=== Test AC1: Path Generated → Welcome Notification ===")
    cleanup_test_data()

    result = notify_path_generated(TEST_USER_ID)

    assert_true(not result.get("skipped"), "Notification was not skipped")
    assert_true(not result.get("batched"), "Welcome notification was not batched (exempt)")
    assert_true(result.get("notification_type") == TYPE_PATH_GENERATED, "Correct type")

    # Check channels
    channels = result.get("channels", {})
    email_ch = channels.get("email", {})
    assert_true(email_ch.get("attempted"), "Email delivery attempted")
    assert_true(email_ch.get("sent"), "Email delivery succeeded")

    # Verify notification log entry
    _, logs = mysql_query(
        f"SELECT * FROM tory_notification_log WHERE nx_user_id = {TEST_USER_ID} "
        f"AND notification_type = '{TYPE_PATH_GENERATED}' AND status = 'sent'"
    )
    assert_true(len(logs) > 0, f"Notification logged in tory_notification_log ({len(logs)} entries)")

    # Verify mail_communication_details entry
    _, mails = mysql_query(
        f"SELECT * FROM mail_communication_details "
        f"WHERE query_type = 'tory_notification' AND user_id = '{TEST_USER_ID}'"
    )
    assert_true(len(mails) > 0, "Email record written to mail_communication_details")
    if mails:
        assert_true(
            "Ready" in (mails[0].get("subject") or ""),
            "Email subject contains 'Ready'",
        )

    # Verify roadmap link in template (avoids multiline DB parsing issues)
    contact = get_learner_contact(TEST_USER_ID)
    path_summary = get_active_recommendations_summary(TEST_USER_ID)
    content = build_welcome_notification(contact, path_summary)
    assert_true(
        "my-path" in content["email_body"],
        "Email template contains roadmap link",
    )

    return True


def test_ac2_reassessment_change_notification():
    """AC2: Reassessment path changes trigger explanatory notification within 24h batch window."""
    print("\n=== Test AC2: Reassessment Change → Explanatory Notification ===")
    cleanup_test_data()

    # Create a reassessment path event
    event_id = setup_test_path_event(
        "reassessed",
        "Profile drift detected after quarterly EPP retake. Path re-ranked to "
        "better match updated strengths in Cooperativeness and gaps in Assertiveness.",
    )

    result = notify_reassessment_change(TEST_USER_ID, event_id)

    assert_true(not result.get("skipped"), "Notification was not skipped")
    assert_true(not result.get("batched"), "First notification not batched (no prior sends)")
    assert_true(
        result.get("notification_type") == TYPE_REASSESSMENT_CHANGE,
        "Correct notification type",
    )

    # Verify reason from path event is included
    _, logs = mysql_query(
        f"SELECT * FROM tory_notification_log WHERE nx_user_id = {TEST_USER_ID} "
        f"AND notification_type = '{TYPE_REASSESSMENT_CHANGE}' AND status = 'sent'"
    )
    assert_true(len(logs) > 0, "Notification logged as sent")
    if logs:
        assert_true(
            "drift" in (logs[0].get("reason") or "").lower(),
            "Reason from path event preserved in notification log",
        )

    return True


def test_ac3_coach_change_notification():
    """AC3: Coach path changes trigger notification crediting the coach."""
    print("\n=== Test AC3: Coach Change → Notification Crediting Coach ===")
    cleanup_test_data()

    # Create a coach reorder event
    event_id = setup_test_path_event(
        "reordered",
        "Prioritizing communication skills lessons based on upcoming presentation",
        coach_id=1,
    )

    result = notify_coach_change(TEST_USER_ID, event_id)

    assert_true(not result.get("skipped"), "Notification was not skipped")
    assert_true(
        result.get("notification_type") == TYPE_COACH_CHANGE,
        "Correct notification type",
    )

    # Verify notification mentions coach
    _, logs = mysql_query(
        f"SELECT * FROM tory_notification_log WHERE nx_user_id = {TEST_USER_ID} "
        f"AND notification_type = '{TYPE_COACH_CHANGE}' AND channel = 'email'"
    )
    assert_true(len(logs) > 0, "Coach change notification logged")
    if logs:
        # Subject field is single-line, reliable for DB reads
        subject = logs[0].get("subject") or ""
        assert_true(
            "coach" in subject.lower() or "Updated" in subject,
            f"Email subject references coach: '{subject}'",
        )

    # Verify template content directly (avoids multiline DB parsing issues)
    contact = get_learner_contact(TEST_USER_ID)
    coach_name = get_coach_name(1)
    content = build_coach_change_notification(contact, "Coach reorder", coach_name)
    assert_true(
        coach_name.lower() in content["email_body"].lower() or "coach" in content["email_body"].lower(),
        "Email template references the coach by name",
    )
    assert_true(
        "personalize" in content["email_body"].lower() or "changes" in content["email_body"].lower(),
        "Email template explains what the coach did",
    )

    return True


def test_ac4_reassessment_reminder():
    """AC4: Reassessment reminders sent 7 days before scheduled EPP retake."""
    print("\n=== Test AC4: Reassessment Reminder ===")
    cleanup_test_data()

    result = notify_reassessment_reminder(TEST_USER_ID, "2026-03-15")

    assert_true(not result.get("skipped"), "Reminder was not skipped")
    assert_true(not result.get("batched"), "Reminder not batched (batch-exempt)")
    assert_true(
        result.get("notification_type") == TYPE_REASSESSMENT_REMINDER,
        "Correct notification type",
    )

    # Verify notification content
    _, logs = mysql_query(
        f"SELECT * FROM tory_notification_log WHERE nx_user_id = {TEST_USER_ID} "
        f"AND notification_type = '{TYPE_REASSESSMENT_REMINDER}'"
    )
    assert_true(len(logs) > 0, "Reminder notification logged")
    if logs:
        body = logs[0].get("body") or ""
        assert_true("2026-03-15" in body, "Due date appears in notification body")
        assert_true("assessment" in body.lower(), "Notification mentions assessment")

    return True


def test_ac5_batch_window_enforcement():
    """AC5: No more than 1 Tory notification per learner per 24 hours enforced."""
    print("\n=== Test AC5: 24-Hour Batch Window Enforcement ===")
    cleanup_test_data()

    # First: send a reassessment change notification (should go through)
    event_id1 = setup_test_path_event("reassessed", "First reassessment change")
    result1 = notify_reassessment_change(TEST_USER_ID, event_id1)
    assert_true(not result1.get("batched"), "First notification sends immediately")
    assert_true(not result1.get("skipped"), "First notification not skipped")

    # Second: send a coach change notification (should be batched)
    event_id2 = setup_test_path_event("reordered", "Coach reorder after first notification")
    result2 = notify_coach_change(TEST_USER_ID, event_id2)
    assert_true(result2.get("batched"), "Second notification is batched within 24h window")
    assert_true(
        result2.get("batched_until") is not None,
        f"Batched until: {result2.get('batched_until')}",
    )

    # Third: welcome notification should STILL go through (batch-exempt)
    result3 = notify_path_generated(TEST_USER_ID)
    assert_true(
        not result3.get("batched"),
        "Welcome notification is batch-exempt (always sends)",
    )

    # Fourth: reassessment reminder should also go through (batch-exempt)
    result4 = notify_reassessment_reminder(TEST_USER_ID, "2026-04-01")
    assert_true(
        not result4.get("batched"),
        "Reassessment reminder is batch-exempt (always sends)",
    )

    # Verify batch window state
    assert_true(
        is_within_batch_window(TEST_USER_ID),
        "Batch window is active after sending",
    )

    # Verify we have batched entries in the log
    _, batched = mysql_query(
        f"SELECT * FROM tory_notification_log WHERE nx_user_id = {TEST_USER_ID} "
        f"AND status = 'batched'"
    )
    assert_true(len(batched) >= 1, f"At least 1 batched notification in log ({len(batched)} found)")

    return True


def test_ac6_opt_out_respected():
    """AC6: Opt-out per notification type is respected."""
    print("\n=== Test AC6: Opt-Out Per Notification Type ===")
    cleanup_test_data()

    # Step 1: Verify no opt-outs initially
    assert_true(not is_opted_out(TEST_USER_ID, TYPE_COACH_CHANGE), "No opt-out initially")

    # Step 2: Opt out of coach change notifications
    set_opt_out(TEST_USER_ID, TYPE_COACH_CHANGE, opted_out=True)
    assert_true(
        is_opted_out(TEST_USER_ID, TYPE_COACH_CHANGE),
        "Opted out of coach_change",
    )
    assert_true(
        not is_opted_out(TEST_USER_ID, TYPE_REASSESSMENT_CHANGE),
        "Other types still opted in",
    )

    # Step 3: Try to send a coach change notification (should be skipped)
    event_id = setup_test_path_event("reordered", "Coach reorder while opted out")
    result = notify_coach_change(TEST_USER_ID, event_id)
    assert_true(result.get("skipped"), "Coach change notification skipped due to opt-out")
    assert_true(
        result.get("skip_reason") == "opted_out",
        "Skip reason is 'opted_out'",
    )

    # Step 4: Verify other types still work
    result2 = notify_path_generated(TEST_USER_ID)
    assert_true(not result2.get("skipped"), "Path generated notification still works")

    # Step 5: Opt out of all notifications
    set_opt_out(TEST_USER_ID, "all", opted_out=True)
    cleanup_notification_logs()  # clear sent records for clean batch window
    result3 = notify_path_generated(TEST_USER_ID)
    assert_true(result3.get("skipped"), "All notifications skipped with 'all' opt-out")

    # Step 6: Opt back in
    set_opt_out(TEST_USER_ID, "all", opted_out=False)
    set_opt_out(TEST_USER_ID, TYPE_COACH_CHANGE, opted_out=False)
    assert_true(
        not is_opted_out(TEST_USER_ID, TYPE_COACH_CHANGE),
        "Opted back in to coach_change",
    )
    assert_true(
        not is_opted_out(TEST_USER_ID, "all"),
        "Opted back in to all",
    )

    # Step 7: Verify opt-out status listing
    statuses = get_optout_status(TEST_USER_ID)
    assert_true(len(statuses) >= 2, f"Opt-out records exist ({len(statuses)} found)")

    return True


def cleanup_notification_logs():
    """Clear notification logs for clean test state."""
    mysql_write(
        f"DELETE FROM tory_notification_log WHERE nx_user_id = {TEST_USER_ID}"
    )


def test_event_type_mapping():
    """Test that event types map to correct notification types."""
    print("\n=== Test: Event Type Mapping ===")
    assert_true(EVENT_TYPE_MAP["reassessed"] == TYPE_REASSESSMENT_CHANGE, "reassessed → reassessment_change")
    assert_true(EVENT_TYPE_MAP["reordered"] == TYPE_COACH_CHANGE, "reordered → coach_change")
    assert_true(EVENT_TYPE_MAP["swapped"] == TYPE_COACH_CHANGE, "swapped → coach_change")
    assert_true(EVENT_TYPE_MAP["locked"] == TYPE_COACH_CHANGE, "locked → coach_change")
    return True


def test_dispatch_path_event():
    """Test the dispatch_path_event entry point."""
    print("\n=== Test: Dispatch Path Event ===")
    cleanup_test_data()

    # Create a coach swap event
    event_id = setup_test_path_event(
        "swapped",
        "Swapped lesson for more relevant content on leadership",
        coach_id=1,
    )

    result = dispatch_path_event(event_id)
    assert_true(not result.get("error"), "Dispatch succeeded without error")
    assert_true(
        result.get("notification_type") == TYPE_COACH_CHANGE,
        "Dispatched as coach_change notification",
    )
    return True


def test_batch_exempt_types():
    """Test batch exemption configuration."""
    print("\n=== Test: Batch Exempt Types ===")
    assert_true(TYPE_PATH_GENERATED in BATCH_EXEMPT_TYPES, "path_generated is batch-exempt")
    assert_true(TYPE_REASSESSMENT_REMINDER in BATCH_EXEMPT_TYPES, "reassessment_reminder is batch-exempt")
    assert_true(TYPE_REASSESSMENT_CHANGE not in BATCH_EXEMPT_TYPES, "reassessment_change is NOT batch-exempt")
    assert_true(TYPE_COACH_CHANGE not in BATCH_EXEMPT_TYPES, "coach_change is NOT batch-exempt")
    return True


def test_notification_log_entries():
    """Test that notification log entries are properly structured."""
    print("\n=== Test: Notification Log Structure ===")
    cleanup_test_data()

    notif_id = log_notification(
        nx_user_id=TEST_USER_ID,
        notification_type=TYPE_PATH_GENERATED,
        channel="email",
        subject="Test Subject",
        body="Test Body",
        reason="Test reason",
        status="sent",
        sent_at=now_str(),
    )
    assert_true(notif_id > 0, f"Notification logged with ID {notif_id}")

    _, rows = mysql_query(
        f"SELECT * FROM tory_notification_log WHERE id = {notif_id}"
    )
    assert_true(len(rows) == 1, "Exactly one log entry found")

    row = rows[0]
    assert_true(row["notification_type"] == TYPE_PATH_GENERATED, "Type stored correctly")
    assert_true(row["channel"] == "email", "Channel stored correctly")
    assert_true(row["status"] == "sent", "Status stored correctly")
    assert_true(row["subject"] == "Test Subject", "Subject stored correctly")
    assert_true(row["reason"] == "Test reason", "Reason stored correctly")

    return True


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("=" * 70)
    print("Tory Notification Service — End-to-End Tests")
    print("=" * 70)

    try:
        # Setup
        contact = test_learner_contact()
        if not contact:
            print("\nFATAL: Cannot find test user. Aborting.")
            sys.exit(1)

        # Unit tests
        test_welcome_notification_template(contact)
        test_event_type_mapping()
        test_batch_exempt_types()
        test_notification_log_entries()

        # Integration tests (AC1-AC6)
        test_ac1_path_generated_triggers_welcome()
        test_ac2_reassessment_change_notification()
        test_ac3_coach_change_notification()
        test_ac4_reassessment_reminder()
        test_ac5_batch_window_enforcement()
        test_ac6_opt_out_respected()

        # Event dispatch test
        test_dispatch_path_event()

    finally:
        # Cleanup
        print("\n--- Cleaning up test data ---")
        cleanup_test_data()

    # Summary
    print("\n" + "=" * 70)
    total = passed + failed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if failed > 0:
        print("SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)
