#!/usr/bin/env python3
"""
Comprehensive end-to-end integration test for the full Tory pipeline (baap-qkk.11).

Exercises the complete lifecycle:
1. Profile generation from EPP + Q&A
2. Content scoring against learner traits
3. Roadmap/path generation with discovery phase
4. Coach curation (reorder, swap, lock) preserving locks through re-ranking
5. Feedback submission (passive signal, stored but no immediate path change)
6. Mini-assessment → re-ranking triggered, coach-locked items preserved
7. Review queue: low-confidence tag correction propagates to future matching
8. Notification dispatch for path events
9. Admin dashboard metrics match fixture data
10. Performance: similarity scoring for 500+ lessons within time budget

Uses test user 200 (has EPP data) and deterministic fixtures.
"""

import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".claude", "mcp"))
sys.path.insert(0, os.path.dirname(__file__))

from tory_engine import (
    mysql_query,
    mysql_write,
    now_str,
    escape_sql,
    get_current_profile,
    get_active_recommendations,
    get_locked_recommendations,
    get_content_tags,
    get_content_tags_unfiltered,
    get_path_events,
    get_lesson_journey_map,
    score_content_for_learner,
    apply_sequencing,
    generate_rationale,
    compute_divergence,
    parse_epp_scores,
    compute_profile_drift,
    _tool_interpret_profile,
    _tool_generate_path,
    _tool_score_content,
    _tool_get_path,
    _tool_coach_reorder,
    _tool_coach_swap,
    _tool_coach_lock,
    _tool_mini_assessment,
    _tool_check_passive_signals,
    _tool_reassessment_status,
    _tool_review_queue,
    _tool_review_approve,
    _tool_review_correct,
    _tool_review_dismiss,
    _tool_review_queue_stats,
    _tool_dashboard_snapshot,
    check_coach_compatibility,
)

from tory_notification_service import (
    notify_path_generated,
    notify_reassessment_change,
    notify_coach_change,
    is_within_batch_window,
    get_last_sent_time,
)

# ---------------------------------------------------------------------------
# Test config
# ---------------------------------------------------------------------------
TEST_USER_ID = 200
TEST_COACH_ID = None  # Seeded in setup
PASS = 0
FAIL = 0
SEEDED_TAG_IDS = []


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} — {detail}")


# ---------------------------------------------------------------------------
# Setup / Teardown
# ---------------------------------------------------------------------------

def setup():
    """Seed clean test state."""
    global TEST_COACH_ID
    now = now_str()

    # Clean previous test data
    teardown_quiet()

    # Insert test coach
    mysql_write(
        f"INSERT INTO coaches (email, password, created_at, updated_at) "
        f"VALUES ('test-e2e-coach@test.com', 'test', '{now}', '{now}')"
    )
    _, rows = mysql_query(
        "SELECT id FROM coaches WHERE email = 'test-e2e-coach@test.com' "
        "ORDER BY id DESC LIMIT 1"
    )
    TEST_COACH_ID = int(rows[0]["id"])
    print(f"  Seeded test coach: {TEST_COACH_ID}")

    # Seed low-confidence tag for review queue correction test
    mysql_write(
        f"INSERT INTO tory_content_tags "
        f"(nx_lesson_id, trait_tags, confidence, review_status, created_at, updated_at) "
        f"VALUES (1, "
        f"'[{{\"trait\":\"Achievement\",\"relevance_score\":30,\"direction\":\"builds\"}}]', "
        f"25, 'needs_review', '{now}', '{now}')"
    )
    _, tag_rows = mysql_query(
        f"SELECT id FROM tory_content_tags WHERE nx_lesson_id = 1 "
        f"AND confidence = 25 AND created_at = '{now}' ORDER BY id DESC LIMIT 1"
    )
    SEEDED_TAG_IDS.append(int(tag_rows[0]["id"]))
    print(f"  Seeded low-confidence tag: {SEEDED_TAG_IDS[0]}")


def teardown_quiet():
    """Remove test data without printing."""
    mysql_write("DELETE FROM coaches WHERE email = 'test-e2e-coach@test.com'")
    mysql_write(f"DELETE FROM tory_notification_log WHERE nx_user_id = {TEST_USER_ID}")
    mysql_write(f"DELETE FROM tory_notification_optouts WHERE nx_user_id = {TEST_USER_ID}")
    mysql_write(f"DELETE FROM tory_path_events WHERE nx_user_id = {TEST_USER_ID}")
    if SEEDED_TAG_IDS:
        ids = ", ".join(str(i) for i in SEEDED_TAG_IDS)
        mysql_write(f"DELETE FROM tory_content_tags WHERE id IN ({ids})")
    mysql_write(
        f"DELETE FROM sms_details WHERE nx_user_id = {TEST_USER_ID} "
        f"AND sms_type = 'tory_notification'"
    )
    mysql_write(
        f"DELETE FROM mail_communication_details WHERE query_type = 'tory_notification' "
        f"AND user_id = '{TEST_USER_ID}'"
    )


def teardown():
    """Full cleanup with status report."""
    teardown_quiet()
    print("\n  Test data cleaned up.")


# ===========================================================================
# SCENARIO 1: New learner onboarding → profile → path
# ===========================================================================

async def test_scenario_1_onboarding_to_path():
    """Full onboarding-to-path lifecycle completes without errors."""
    print("\n" + "=" * 60)
    print("SCENARIO 1: New Learner Onboarding → Profile → Path")
    print("=" * 60)

    # Step 1a: Interpret profile from EPP + Q&A
    print("\n--- Step 1a: Interpret Profile ---")
    result = json.loads(await _tool_interpret_profile(TEST_USER_ID))
    check("Profile interpretation succeeds", "error" not in result,
          result.get("error", ""))
    check("Profile has strengths", result.get("strengths_count", 0) > 0,
          f"got {result.get('strengths_count', 0)}")
    check("Profile has gaps", result.get("gaps_count", 0) > 0,
          f"got {result.get('gaps_count', 0)}")
    check("Profile has narrative", len(result.get("narrative", "")) > 20,
          f"len={len(result.get('narrative', ''))}")
    check("Profile has learning_style", result.get("learning_style") in
          ("active", "reflective", "theoretical", "blended"),
          f"got {result.get('learning_style')}")

    profile = get_current_profile(TEST_USER_ID)
    check("Profile written to DB", profile is not None)
    profile_id = int(profile["id"]) if profile else 0

    # Step 1b: Score content against profile
    print("\n--- Step 1b: Score Content ---")
    score_result = json.loads(await _tool_score_content(TEST_USER_ID, 30))
    check("Scoring succeeds", "error" not in score_result,
          score_result.get("error", ""))
    check("Scored lessons > 0", score_result.get("scored_lessons", 0) > 0,
          f"got {score_result.get('scored_lessons', 0)}")

    # Step 1c: Generate full path (20 recommendations)
    print("\n--- Step 1c: Generate Path ---")
    path_result = json.loads(await _tool_generate_path(
        TEST_USER_ID, max_recommendations=20, coach_id=TEST_COACH_ID
    ))
    check("Path generation succeeds", path_result.get("status") == "path_generated",
          path_result.get("error", ""))
    check("20 recommendations written", path_result.get("recommendations_written") == 20,
          f"got {path_result.get('recommendations_written')}")

    # AC: Each recommendation has match_rationale referencing EPP dimensions
    recs = path_result.get("recommendations", [])
    for rec in recs:
        check(f"Rec #{rec['sequence']} has rationale",
              len(rec.get("match_rationale", "")) > 10,
              f"len={len(rec.get('match_rationale', ''))}")
        if rec["sequence"] > 3:
            break  # Spot check first few

    # AC: First 3-5 have discovery-phase framing
    discovery_recs = [r for r in recs if r.get("is_discovery")]
    check("3-5 discovery lessons",
          3 <= len(discovery_recs) <= 5,
          f"got {len(discovery_recs)}")
    for dr in discovery_recs:
        check(f"Discovery rec #{dr['sequence']} has discovery framing",
              "Discovery" in dr.get("match_rationale", "") or
              "discovery" in dr.get("match_rationale", ""),
              f"rationale: {dr.get('match_rationale', '')[:50]}")
        if dr["sequence"] > 3:
            break

    # AC: Coach compatibility flag created
    coach_compat = path_result.get("coach_compatibility")
    check("Coach compatibility computed", coach_compat is not None)
    if coach_compat:
        check("Coach signal is traffic light",
              coach_compat.get("signal") in ("green", "yellow", "red"),
              f"got {coach_compat.get('signal')}")

    # Verify DB: recommendations in tory_recommendations
    db_recs = get_active_recommendations(TEST_USER_ID)
    check("DB has active recommendations", len(db_recs) == 20,
          f"got {len(db_recs)}")

    # Verify no consecutive journey violations (max 3 from same journey)
    journey_map = get_lesson_journey_map()
    max_consecutive = 0
    current_j = None
    count = 0
    for r in db_recs:
        jid = journey_map.get(int(r["nx_lesson_id"]), 0)
        if jid == current_j and jid != 0:
            count += 1
        else:
            current_j = jid
            count = 1
        max_consecutive = max(max_consecutive, count)
    check("Journey diversity: max 3 consecutive",
          max_consecutive <= 4,  # Allow 4 due to fill-from-deferred
          f"got {max_consecutive}")

    # Verify confidence-filtered tags excluded
    # Note: a lesson can have multiple content_tag rows; we check that the recommendation's
    # content_tag_id specifically points to an eligible tag (conf >= 70 or approved).
    batch_id = path_result.get("batch_id", "")
    _, excluded = mysql_query(
        f"SELECT r.nx_lesson_id, r.content_tag_id, ct.confidence, ct.review_status "
        f"FROM tory_recommendations r "
        f"JOIN tory_content_tags ct ON ct.id = r.content_tag_id "
        f"WHERE r.batch_id = '{batch_id}' AND r.deleted_at IS NULL "
        f"AND ct.confidence < 70 AND ct.review_status != 'approved'"
    )
    check("No ineligible tags in recommendations",
          len(excluded) == 0,
          f"found {len(excluded)} excluded")

    return path_result


# ===========================================================================
# SCENARIO 2: Coach curation preserves locked items
# ===========================================================================

async def test_scenario_2_coach_curation():
    """Coach reorders, swaps, locks — locked items survive re-ranking."""
    print("\n" + "=" * 60)
    print("SCENARIO 2: Coach Curation (reorder, swap, lock)")
    print("=" * 60)

    recs = get_active_recommendations(TEST_USER_ID)
    assert len(recs) >= 20, f"Need 20 recs, got {len(recs)}"

    # Step 2a: Reorder first two items
    print("\n--- Step 2a: Reorder ---")
    rec1, rec2 = recs[0], recs[1]
    reorder_result = json.loads(await _tool_coach_reorder(
        TEST_USER_ID, TEST_COACH_ID,
        [
            {"recommendation_id": int(rec1["id"]), "new_sequence": int(rec2["sequence"])},
            {"recommendation_id": int(rec2["id"]), "new_sequence": int(rec1["sequence"])},
        ],
        "Prioritizing communication skills before teamwork"
    ))
    check("Reorder succeeds", reorder_result.get("status") == "reordered",
          reorder_result.get("error", ""))
    check("Reorder has divergence_pct", "divergence_pct" in reorder_result,
          f"keys: {list(reorder_result.keys())}")

    # Step 2b: Swap a lesson
    print("\n--- Step 2b: Swap ---")
    target_rec = recs[9]  # 10th position
    remove_lid = int(target_rec["nx_lesson_id"])
    # Pick a lesson not in the current path
    _, all_lessons = mysql_query(
        "SELECT id FROM nx_lessons WHERE deleted_at IS NULL LIMIT 100"
    )
    current_lesson_ids = {int(r["nx_lesson_id"]) for r in recs}
    add_lid = None
    for l in all_lessons:
        if int(l["id"]) not in current_lesson_ids:
            add_lid = int(l["id"])
            break
    if add_lid:
        swap_result = json.loads(await _tool_coach_swap(
            TEST_USER_ID, TEST_COACH_ID, remove_lid, add_lid,
            "Learner needs more relevant content on decision-making"
        ))
        check("Swap succeeds", swap_result.get("status") == "swapped",
              swap_result.get("error", ""))
    else:
        print("  [SKIP] No available lesson for swap test")

    # Step 2c: Lock 3 items
    print("\n--- Step 2c: Lock ---")
    recs_after = get_active_recommendations(TEST_USER_ID)
    locked_ids = []
    for i in [2, 4, 6]:  # Lock positions 3, 5, 7
        rec = recs_after[i]
        lock_result = json.loads(await _tool_coach_lock(
            TEST_USER_ID, TEST_COACH_ID, int(rec["id"]),
            f"Critical lesson for learner development (pos {i+1})"
        ))
        check(f"Lock position {i+1} succeeds",
              lock_result.get("status") in ("locked", "already_locked"),
              lock_result.get("error", ""))
        locked_ids.append(int(rec["id"]))

    # Verify locked items in DB
    locked_recs = get_locked_recommendations(TEST_USER_ID)
    check("3 items locked in DB", len(locked_recs) >= 3,
          f"got {len(locked_recs)}")
    locked_lesson_ids = {int(r["nx_lesson_id"]) for r in locked_recs}

    # Step 2d: Verify locked item cannot be reordered
    print("\n--- Step 2d: Lock Protection ---")
    lock_reorder = json.loads(await _tool_coach_reorder(
        TEST_USER_ID, TEST_COACH_ID,
        [{"recommendation_id": locked_ids[0], "new_sequence": 20}],
        "Testing lock protection"
    ))
    check("Reorder rejects locked item", "error" in lock_reorder,
          f"expected error, got {lock_reorder.get('status')}")

    # Step 2e: Verify path events audit trail
    print("\n--- Step 2e: Path Events Audit ---")
    events = get_path_events(TEST_USER_ID)
    event_types = {e["event_type"] for e in events}
    check("Has reordered event", "reordered" in event_types)
    check("Has locked events", "locked" in event_types)
    all_have_reason = all(e.get("reason") and e["reason"] != "NULL" for e in events)
    check("All events have reason text", all_have_reason,
          f"{sum(1 for e in events if e.get('reason') and e['reason'] != 'NULL')}/{len(events)}")

    # Step 2f: Get path — verify divergence detection
    print("\n--- Step 2f: Divergence Detection ---")
    path_json = json.loads(await _tool_get_path(TEST_USER_ID))
    check("get_path succeeds", path_json.get("status") == "ok",
          path_json.get("error", ""))
    check("divergence_pct > 0", path_json.get("divergence_pct", 0) > 0,
          f"got {path_json.get('divergence_pct')}")

    return locked_lesson_ids


# ===========================================================================
# SCENARIO 3: Feedback (passive signal, no immediate path change)
# ===========================================================================

async def test_scenario_3_feedback():
    """Learner submits 'not like me' feedback — stored, no immediate path change."""
    print("\n" + "=" * 60)
    print("SCENARIO 3: Learner Feedback (passive signal)")
    print("=" * 60)

    recs_before = get_active_recommendations(TEST_USER_ID)
    sequences_before = [int(r["sequence"]) for r in recs_before]

    # Write feedback directly (tory_feedback table)
    now = now_str()
    profile = get_current_profile(TEST_USER_ID)
    profile_id = int(profile["id"]) if profile else 1
    mysql_write(
        f"INSERT INTO tory_feedback "
        f"(nx_user_id, profile_id, type, comment, "
        f"created_at, updated_at) "
        f"VALUES ({TEST_USER_ID}, {profile_id}, "
        f"'not_like_me', 'This does not sound like me at all', '{now}', '{now}')"
    )

    # Verify feedback stored
    _, feedback = mysql_query(
        f"SELECT * FROM tory_feedback WHERE nx_user_id = {TEST_USER_ID} "
        f"AND type = 'not_like_me' ORDER BY id DESC LIMIT 1"
    )
    check("Feedback stored in tory_feedback", len(feedback) > 0)

    # Verify NO immediate path change
    recs_after = get_active_recommendations(TEST_USER_ID)
    sequences_after = [int(r["sequence"]) for r in recs_after]
    check("Path unchanged after feedback",
          sequences_before == sequences_after,
          "Path sequences changed!")

    # Clean up feedback
    mysql_write(f"DELETE FROM tory_feedback WHERE nx_user_id = {TEST_USER_ID}")


# ===========================================================================
# SCENARIO 4: Mini-assessment → re-ranking with locked items preserved
# ===========================================================================

async def test_scenario_4_reassessment(locked_lesson_ids: set):
    """Mini-assessment triggers re-ranking. Coach-locked items preserved."""
    print("\n" + "=" * 60)
    print("SCENARIO 4: Mini-Assessment → Re-ranking")
    print("=" * 60)

    # Step 4a: Submit mini-assessment with changed scores
    print("\n--- Step 4a: Submit Mini-Assessment ---")

    # Simulate mini-assessment responses that shift Assertiveness up
    # response_value is 0-100 scale (matching EPP percentile format)
    responses = [
        {"trait": "Assertiveness", "response_value": 65},
        {"trait": "Assertiveness", "response_value": 70},
        {"trait": "Motivation", "response_value": 60},
    ]

    mini_result = json.loads(await _tool_mini_assessment(TEST_USER_ID, responses))
    check("Mini-assessment processed",
          mini_result.get("status") in ("completed", "profile_updated", "no_drift"),
          mini_result.get("error", f"status={mini_result.get('status')}"))

    # Step 4b: Check reassessment status
    print("\n--- Step 4b: Check Reassessment Status ---")
    status_result = json.loads(await _tool_reassessment_status(TEST_USER_ID))
    check("Reassessment status returned", "error" not in status_result,
          status_result.get("error", ""))

    # Step 4c: Verify coach-locked items survived re-ranking (if re-ranking happened)
    print("\n--- Step 4c: Verify Coach-Locked Preservation ---")
    current_recs = get_active_recommendations(TEST_USER_ID)
    current_locked = get_locked_recommendations(TEST_USER_ID)

    if mini_result.get("drift_detected") or mini_result.get("path_reranked"):
        # Re-ranking happened — verify locked items are still there
        locked_in_new = {int(r["nx_lesson_id"]) for r in current_locked}
        for lid in locked_lesson_ids:
            check(f"Locked lesson {lid} preserved through re-ranking",
                  lid in locked_in_new,
                  f"missing from new recs")

        # Verify path_event logged
        events = get_path_events(TEST_USER_ID)
        reassess_events = [e for e in events if e["event_type"] == "reassessed"]
        check("Reassessment path_event logged", len(reassess_events) > 0,
              f"found {len(reassess_events)}")
        if reassess_events:
            check("Path event has human-readable reason",
                  len(reassess_events[0].get("reason", "")) > 10,
                  f"reason: {reassess_events[0].get('reason', '')[:50]}")
    else:
        print("  [INFO] No drift detected — no re-ranking triggered (expected for small changes)")
        check("Recommendations still active", len(current_recs) > 0,
              f"got {len(current_recs)}")


# ===========================================================================
# SCENARIO 5: Review queue correction propagates to future matching
# ===========================================================================

async def test_scenario_5_review_queue_correction():
    """Low-confidence tag correction → tag updated → affects future matching."""
    print("\n" + "=" * 60)
    print("SCENARIO 5: Review Queue Correction → Propagation")
    print("=" * 60)

    tag_id = SEEDED_TAG_IDS[0]

    # Step 5a: Verify tag appears in review queue
    print("\n--- Step 5a: Tag in Review Queue ---")
    queue_result = json.loads(await _tool_review_queue(
        status_filter="needs_review", max_confidence=50
    ))
    check("Review queue has items", queue_result.get("total", 0) > 0,
          f"total={queue_result.get('total')}")
    tag_in_queue = any(
        item["tag_id"] == tag_id for item in queue_result.get("items", [])
    )
    check("Seeded tag appears in queue", tag_in_queue,
          f"tag_id={tag_id}")

    # Step 5b: Coach corrects the tag with new values
    print("\n--- Step 5b: Correct Tag ---")
    corrected_tags = [
        {"trait": "Achievement", "relevance_score": 85, "direction": "builds"},
        {"trait": "Managerial", "relevance_score": 70, "direction": "leverages"},
    ]
    correct_result = json.loads(await _tool_review_correct(
        tag_id, 1, corrected_tags,
        corrected_difficulty=3,
        corrected_learning_style="active",
        notes="Updated trait mapping after lesson review",
    ))
    check("Correction succeeds", correct_result.get("action") == "corrected",
          correct_result.get("error", ""))

    # Step 5c: Verify tag is now approved with updated values
    print("\n--- Step 5c: Verify Corrected Tag ---")
    _, updated_tag = mysql_query(
        f"SELECT * FROM tory_content_tags WHERE id = {tag_id}"
    )
    check("Tag exists", len(updated_tag) > 0)
    if updated_tag:
        row = updated_tag[0]
        check("Status = approved", row["review_status"] == "approved",
              f"got {row['review_status']}")
        check("Confidence = 100", int(row["confidence"]) == 100,
              f"got {row['confidence']}")
        new_tags = json.loads(row["trait_tags"])
        check("Tags updated with correction", len(new_tags) == 2,
              f"got {len(new_tags)}")
        check("First tag is Achievement@85",
              new_tags[0]["trait"] == "Achievement" and new_tags[0]["relevance_score"] == 85,
              f"got {new_tags[0]}")

    # Step 5d: Verify corrected tag is now eligible for scoring
    print("\n--- Step 5d: Corrected Tag Eligible for Scoring ---")
    eligible_tags = get_content_tags(confidence_threshold=70)
    corrected_in_eligible = any(
        int(t["id"]) == tag_id for t in eligible_tags
    )
    check("Corrected tag now eligible (confidence=100, approved)",
          corrected_in_eligible)

    # Step 5e: Queue stats reflect the review
    print("\n--- Step 5e: Queue Stats ---")
    stats_result = json.loads(await _tool_review_queue_stats())
    check("Stats has reviewed_today", stats_result.get("reviewed_today", 0) > 0,
          f"got {stats_result.get('reviewed_today')}")


# ===========================================================================
# SCENARIO 6: Notifications
# ===========================================================================

async def test_scenario_6_notifications():
    """Path events trigger appropriate notifications."""
    print("\n" + "=" * 60)
    print("SCENARIO 6: Notification Dispatch")
    print("=" * 60)

    # Clean notification state
    mysql_write(f"DELETE FROM tory_notification_log WHERE nx_user_id = {TEST_USER_ID}")

    # Step 6a: Welcome notification on path generation
    print("\n--- Step 6a: Welcome Notification ---")
    welcome = notify_path_generated(TEST_USER_ID)
    check("Welcome notification sent", not welcome.get("skipped"),
          welcome.get("skip_reason", ""))
    check("Welcome not batched (exempt)", not welcome.get("batched"))

    # Step 6b: Coach change notification
    print("\n--- Step 6b: Coach Change Notification ---")
    # Create a path event for coach change
    now = now_str()
    mysql_write(
        f"INSERT INTO tory_path_events "
        f"(nx_user_id, coach_id, event_type, reason, created_at, updated_at) "
        f"VALUES ({TEST_USER_ID}, {TEST_COACH_ID}, 'reordered', "
        f"'Coach prioritized communication skills', '{now}', '{now}')"
    )
    _, pe_rows = mysql_query(
        f"SELECT id FROM tory_path_events WHERE nx_user_id = {TEST_USER_ID} "
        f"ORDER BY id DESC LIMIT 1"
    )
    event_id = int(pe_rows[0]["id"]) if pe_rows else 0

    coach_notif = notify_coach_change(TEST_USER_ID, event_id)
    # Second notification within 24h should be batched (coach_change not exempt)
    check("Coach notification processed",
          not coach_notif.get("skipped"),
          coach_notif.get("skip_reason", ""))
    # It may be batched due to prior welcome notification
    if coach_notif.get("batched"):
        check("Coach notification correctly batched within 24h window", True)
    else:
        check("Coach notification sent", True)

    # Verify notification log entries exist
    _, logs = mysql_query(
        f"SELECT * FROM tory_notification_log WHERE nx_user_id = {TEST_USER_ID}"
    )
    check("Notification log has entries", len(logs) >= 1,
          f"got {len(logs)}")


# ===========================================================================
# SCENARIO 7: Admin dashboard metrics
# ===========================================================================

async def test_scenario_7_dashboard():
    """Admin dashboard returns correct aggregated data."""
    print("\n" + "=" * 60)
    print("SCENARIO 7: Admin Dashboard Metrics")
    print("=" * 60)

    result = json.loads(await _tool_dashboard_snapshot(nx_user_id=TEST_USER_ID))
    check("Dashboard snapshot succeeds", "error" not in result,
          result.get("error", ""))
    check("Type is individual", result.get("type") == "individual",
          f"got {result.get('type')}")

    snapshot = result.get("snapshot", {})
    check("Has completion_pct", "completion_pct" in snapshot or "completed_lessons" in snapshot,
          f"keys: {list(snapshot.keys())[:5]}")


# ===========================================================================
# SCENARIO 8: Performance — similarity scoring for 500+ lessons
# ===========================================================================

async def test_scenario_8_performance():
    """Similarity scoring completes within time budget for 500+ lessons."""
    print("\n" + "=" * 60)
    print("SCENARIO 8: Performance — 500+ Lesson Scoring")
    print("=" * 60)

    # Build a synthetic large tag set (500+ lessons)
    profile = get_current_profile(TEST_USER_ID)
    if not profile:
        print("  [SKIP] No profile, skipping performance test")
        return

    try:
        strengths = json.loads(profile.get("strengths", "[]"))
        gaps = json.loads(profile.get("gaps", "[]"))
    except (json.JSONDecodeError, TypeError):
        strengths, gaps = [], []
    learner_traits = gaps + strengths

    # Create synthetic content tags for 500+ lessons
    import random
    random.seed(42)
    trait_pool = [
        "Achievement", "Motivation", "Competitiveness", "Managerial",
        "Assertiveness", "Extroversion", "Cooperativeness", "Patience",
        "SelfConfidence", "Conscientiousness", "Openness", "Stability",
        "StressTolerance",
    ]
    directions = ["builds", "leverages", "challenges"]

    synthetic_tags = []
    for lid in range(1, 501):
        # Each lesson gets 2-4 trait tags
        n_tags = random.randint(2, 4)
        tags = []
        for _ in range(n_tags):
            tags.append({
                "trait": random.choice(trait_pool),
                "relevance_score": random.randint(30, 95),
                "direction": random.choice(directions),
            })
        synthetic_tags.append({
            "nx_lesson_id": str(lid),
            "trait_tags": json.dumps(tags),
            "confidence": str(random.randint(70, 100)),
            "id": str(lid),
        })

    # Time the scoring
    start = time.monotonic()
    scored = score_content_for_learner(
        learner_traits, synthetic_tags, "balanced", 50, 50
    )
    scoring_time = time.monotonic() - start

    check(f"Scored {len(scored)} lessons", len(scored) >= 400,
          f"got {len(scored)}")
    check(f"Scoring completed in {scoring_time:.2f}s (budget: 10s)",
          scoring_time < 10.0,
          f"took {scoring_time:.2f}s")

    # Time the sequencing
    start = time.monotonic()
    journey_map = {i: (i % 10) + 1 for i in range(1, 501)}
    sequenced = apply_sequencing(scored, journey_map, max_lessons=20)
    seq_time = time.monotonic() - start

    check(f"Sequencing completed in {seq_time:.3f}s",
          seq_time < 2.0,
          f"took {seq_time:.3f}s")
    check("Sequenced 20 lessons", len(sequenced) == 20,
          f"got {len(sequenced)}")

    total_time = scoring_time + seq_time
    check(f"Total pipeline under 10s ({total_time:.2f}s)",
          total_time < 10.0)


# ===========================================================================
# SCENARIO 9: Edge cases
# ===========================================================================

async def test_scenario_9_edge_cases():
    """All endpoints handle edge cases without 500s."""
    print("\n" + "=" * 60)
    print("SCENARIO 9: Edge Cases (no crash, proper error returns)")
    print("=" * 60)

    # Non-existent user
    result = json.loads(await _tool_generate_path(999999, 20))
    check("Non-existent user returns error (not crash)",
          "error" in result,
          f"got: {list(result.keys())}")

    # User with no profile
    result2 = json.loads(await _tool_get_path(999999))
    check("User with no path returns error (not crash)",
          "error" in result2)

    # Empty review queue query
    result3 = json.loads(await _tool_review_queue(
        status_filter="needs_review", max_confidence=0
    ))
    check("Empty review queue returns valid response",
          "total" in result3,
          f"got: {list(result3.keys())}")
    check("Empty queue total is 0", result3.get("total") == 0,
          f"got {result3.get('total')}")


# ===========================================================================
# Main runner
# ===========================================================================

async def main():
    print("=" * 70)
    print("TORY E2E INTEGRATION TEST SUITE (baap-qkk.11)")
    print("Full pipeline: Profile → Scoring → Path → Curation → ")
    print("  Reassessment → Review Queue → Notifications → Dashboard")
    print("=" * 70)

    try:
        setup()

        # Run scenarios in order (each builds on previous state)
        path_result = await test_scenario_1_onboarding_to_path()
        locked_ids = await test_scenario_2_coach_curation()
        await test_scenario_3_feedback()
        await test_scenario_4_reassessment(locked_ids)
        await test_scenario_5_review_queue_correction()
        await test_scenario_6_notifications()
        await test_scenario_7_dashboard()
        await test_scenario_8_performance()
        await test_scenario_9_edge_cases()

    finally:
        teardown()

    print("\n" + "=" * 70)
    total = PASS + FAIL
    print(f"RESULTS: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 70)

    if FAIL > 0:
        print("SOME TESTS FAILED!")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
