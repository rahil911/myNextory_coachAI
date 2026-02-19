#!/usr/bin/env python3
"""
E2E test for Coach Curation API (baap-qkk.5)

Tests all 4 coach curation tools:
1. tory_get_path — GET path with source field
2. tory_coach_reorder — PUT reorder with path_event
3. tory_coach_swap — POST swap with path_event
4. tory_coach_lock — PUT lock with path_event
+ divergence detection >30% flagging

Prerequisites: tory_recommendations for user 200 (seeded by baap-qkk.4)
"""

import asyncio
import json
import subprocess
import sys

sys.path.insert(0, ".claude/mcp")
from tory_engine import (
    mysql_query,
    mysql_write,
    now_str,
    _tool_get_path,
    _tool_coach_reorder,
    _tool_coach_swap,
    _tool_coach_lock,
    get_active_recommendations,
    get_path_events,
    compute_divergence,
)

TEST_USER_ID = 200
TEST_COACH_ID = None  # set after seeding

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} — {detail}")


async def setup():
    """Seed a test coach."""
    global TEST_COACH_ID
    now = now_str()

    # Insert test coach
    mysql_write(
        f"INSERT INTO coaches (email, password, created_at, updated_at) "
        f"VALUES ('test-coach-curation@test.com', 'test', '{now}', '{now}')"
    )
    _, rows = mysql_query(
        "SELECT id FROM coaches WHERE email = 'test-coach-curation@test.com' "
        "ORDER BY id DESC LIMIT 1"
    )
    TEST_COACH_ID = int(rows[0]["id"])
    print(f"Seeded test coach: {TEST_COACH_ID}")

    # Reset recommendations to clean state (source=tory, locked=0)
    mysql_write(
        f"UPDATE tory_recommendations SET source = 'tory', locked_by_coach = 0, "
        f"updated_at = '{now}' WHERE nx_user_id = {TEST_USER_ID} AND deleted_at IS NULL"
    )

    # Clean up any previous test path events
    mysql_write(
        f"DELETE FROM tory_path_events WHERE nx_user_id = {TEST_USER_ID}"
    )


async def test_get_path_initial():
    """AC4: GET path returns ordered recommendations with source field."""
    print("\n--- Test: GET path (initial state) ---")

    result = json.loads(await _tool_get_path(TEST_USER_ID))

    check("get_path returns ok status", result.get("status") == "ok")
    check("get_path has path items", len(result.get("path", [])) == 20,
          f"got {len(result.get('path', []))}")
    check("get_path has divergence_pct field", "divergence_pct" in result)
    check("initial divergence is 0%", result.get("divergence_pct") == 0,
          f"got {result.get('divergence_pct')}")

    # All items should have source='tory'
    path = result.get("path", [])
    all_tory = all(item.get("source") == "tory" for item in path)
    check("all items source=tory initially", all_tory)

    # Items should have recommendation_id, sequence, lesson_name, source
    first = path[0] if path else {}
    check("path item has recommendation_id", "recommendation_id" in first)
    check("path item has sequence", "sequence" in first)
    check("path item has source", "source" in first)
    check("path item has locked_by_coach", "locked_by_coach" in first)

    return result


async def test_reorder():
    """AC1: PUT reorder updates ranks and creates a reordered path_event with reason."""
    print("\n--- Test: PUT reorder ---")

    recs = get_active_recommendations(TEST_USER_ID)
    # Swap sequence of first two items
    rec1, rec2 = recs[0], recs[1]
    ordering = [
        {"recommendation_id": int(rec1["id"]), "new_sequence": int(rec2["sequence"])},
        {"recommendation_id": int(rec2["id"]), "new_sequence": int(rec1["sequence"])},
    ]

    result = json.loads(await _tool_coach_reorder(
        TEST_USER_ID, TEST_COACH_ID, ordering,
        "Learner should start with communication skills before teamwork"
    ))

    check("reorder returns status=reordered", result.get("status") == "reordered")
    check("reorder affected 2 items", result.get("items_reordered") == 2,
          f"got {result.get('items_reordered')}")
    check("reorder has reason", result.get("reason") != "")
    check("reorder has divergence_pct", "divergence_pct" in result)

    # Verify DB: sequences actually swapped
    recs_after = get_active_recommendations(TEST_USER_ID)
    rec1_after = next(r for r in recs_after if int(r["id"]) == int(rec1["id"]))
    rec2_after = next(r for r in recs_after if int(r["id"]) == int(rec2["id"]))
    check("rec1 has rec2's old sequence",
          int(rec1_after["sequence"]) == int(rec2["sequence"]),
          f"expected {rec2['sequence']}, got {rec1_after['sequence']}")
    check("rec2 has rec1's old sequence",
          int(rec2_after["sequence"]) == int(rec1["sequence"]),
          f"expected {rec1['sequence']}, got {rec2_after['sequence']}")

    # Source should be 'coach' for reordered items
    check("rec1 source=coach after reorder", rec1_after.get("source") == "coach")
    check("rec2 source=coach after reorder", rec2_after.get("source") == "coach")

    # AC5: path_event with reason
    events = get_path_events(TEST_USER_ID)
    reorder_events = [e for e in events if e["event_type"] == "reordered"]
    check("reordered path_event created", len(reorder_events) >= 1)
    check("path_event has reason text",
          reorder_events[0].get("reason", "") != "" if reorder_events else False)


async def test_swap():
    """AC2: POST swap replaces a lesson and creates a swapped path_event."""
    print("\n--- Test: POST swap ---")

    recs = get_active_recommendations(TEST_USER_ID)
    # Pick a non-locked rec to swap (use sequence 10, lesson 5)
    target_rec = next(r for r in recs if int(r["sequence"]) == 10)
    remove_lesson_id = int(target_rec["nx_lesson_id"])
    add_lesson_id = 3  # "Decision Making Under Pressure" — not in path

    result = json.loads(await _tool_coach_swap(
        TEST_USER_ID, TEST_COACH_ID, remove_lesson_id, add_lesson_id,
        "Learner needs decision-making practice more than current lesson"
    ))

    check("swap returns status=swapped", result.get("status") == "swapped")
    check("swap removed correct lesson",
          result.get("removed_lesson_id") == remove_lesson_id)
    check("swap added correct lesson",
          result.get("added_lesson_id") == add_lesson_id)
    check("swap has reason", result.get("reason") != "")

    # Verify DB: lesson was actually replaced
    recs_after = get_active_recommendations(TEST_USER_ID)
    rec_after = next(r for r in recs_after if int(r["id"]) == int(target_rec["id"]))
    check("lesson replaced in DB",
          int(rec_after["nx_lesson_id"]) == add_lesson_id,
          f"expected {add_lesson_id}, got {rec_after['nx_lesson_id']}")
    check("swapped item source=coach", rec_after.get("source") == "coach")
    check("sequence preserved after swap",
          int(rec_after["sequence"]) == int(target_rec["sequence"]))

    # AC5: path_event with reason
    events = get_path_events(TEST_USER_ID)
    swap_events = [e for e in events if e["event_type"] == "swapped"]
    check("swapped path_event created", len(swap_events) >= 1)
    check("swap event has reason",
          swap_events[0].get("reason", "") != "" if swap_events else False)

    # Verify swap of already-in-path lesson is rejected
    result2 = json.loads(await _tool_coach_swap(
        TEST_USER_ID, TEST_COACH_ID, add_lesson_id, int(recs[0]["nx_lesson_id"]),
        "testing duplicate rejection"
    ))
    check("swap rejects duplicate lesson", "error" in result2,
          f"expected error, got {result2.get('status')}")


async def test_lock():
    """AC3: PUT lock sets locked_by_coach=true and locked items survive re-ranking."""
    print("\n--- Test: PUT lock ---")

    recs = get_active_recommendations(TEST_USER_ID)
    target = recs[2]  # Lock the 3rd item
    rec_id = int(target["id"])

    result = json.loads(await _tool_coach_lock(
        TEST_USER_ID, TEST_COACH_ID, rec_id,
        "This lesson is critical for the learner's development plan"
    ))

    check("lock returns status=locked", result.get("status") == "locked")
    check("lock has reason", result.get("reason") != "")

    # Verify DB
    recs_after = get_active_recommendations(TEST_USER_ID)
    locked_rec = next(r for r in recs_after if int(r["id"]) == rec_id)
    check("locked_by_coach=1 in DB",
          str(locked_rec.get("locked_by_coach")) == "1",
          f"got {locked_rec.get('locked_by_coach')}")
    check("locked item source=coach", locked_rec.get("source") == "coach")

    # AC5: path_event
    events = get_path_events(TEST_USER_ID)
    lock_events = [e for e in events if e["event_type"] == "locked"]
    check("locked path_event created", len(lock_events) >= 1)

    # Verify locked item cannot be reordered
    result2 = json.loads(await _tool_coach_reorder(
        TEST_USER_ID, TEST_COACH_ID,
        [{"recommendation_id": rec_id, "new_sequence": 20}],
        "testing lock protection"
    ))
    check("reorder rejects locked item", "error" in result2,
          f"expected error, got {result2.get('status')}")

    # Verify locked item cannot be swapped
    result3 = json.loads(await _tool_coach_swap(
        TEST_USER_ID, TEST_COACH_ID,
        int(locked_rec["nx_lesson_id"]), 7,
        "testing lock protection on swap"
    ))
    check("swap rejects locked item", "error" in result3,
          f"expected error, got {result3.get('status')}")

    # Already locked -> idempotent
    result4 = json.loads(await _tool_coach_lock(
        TEST_USER_ID, TEST_COACH_ID, rec_id, "re-locking"
    ))
    check("re-lock returns already_locked", result4.get("status") == "already_locked")


async def test_divergence_detection():
    """AC6: Divergence >30% is detected and logged but not blocked."""
    print("\n--- Test: Divergence detection ---")

    # Current state: 3 items modified out of 20 = 15%
    div = compute_divergence(TEST_USER_ID)
    check("divergence reflects modifications", div > 0,
          f"got {div}%")

    # Lock 5 more items to push divergence above 30%
    recs = get_active_recommendations(TEST_USER_ID)
    unlocked = [r for r in recs
                if str(r.get("locked_by_coach", "0")) == "0"
                and r.get("source") == "tory"]

    locked_count = 0
    for r in unlocked[:5]:
        await _tool_coach_lock(
            TEST_USER_ID, TEST_COACH_ID, int(r["id"]),
            "Locking for divergence test"
        )
        locked_count += 1

    div_after = compute_divergence(TEST_USER_ID)
    check(f"divergence now >30% after bulk locks", div_after > 30,
          f"got {div_after}%")

    # GET path should show flagged
    path_result = json.loads(await _tool_get_path(TEST_USER_ID))
    check("get_path shows divergence_flagged=true",
          path_result.get("divergence_flagged") is True,
          f"got {path_result.get('divergence_flagged')}")
    check("get_path has coach_insight_note",
          "coach_insight_note" in path_result)

    # Verify the flag doesn't block operations — reorder still works
    unlocked_recs = [r for r in get_active_recommendations(TEST_USER_ID)
                     if str(r.get("locked_by_coach", "0")) == "0"]
    if len(unlocked_recs) >= 2:
        r1, r2 = unlocked_recs[0], unlocked_recs[1]
        result = json.loads(await _tool_coach_reorder(
            TEST_USER_ID, TEST_COACH_ID,
            [
                {"recommendation_id": int(r1["id"]), "new_sequence": int(r2["sequence"])},
                {"recommendation_id": int(r2["id"]), "new_sequence": int(r1["sequence"])},
            ],
            "Reorder despite high divergence"
        ))
        check("reorder still works at high divergence",
              result.get("status") == "reordered")
        check("reorder event flagged_for_review at >30%",
              result.get("flagged_for_review") is True)

    # Check that path events record divergence
    events = get_path_events(TEST_USER_ID, limit=5)
    flagged_events = [e for e in events if str(e.get("flagged_for_review", "0")) == "1"]
    check("path events flagged when divergence >30%", len(flagged_events) > 0,
          f"found {len(flagged_events)} flagged events")


async def test_path_events_audit():
    """AC5: Verify all path events have coach reason text."""
    print("\n--- Test: Path events audit trail ---")

    events = get_path_events(TEST_USER_ID, limit=50)
    check("path events exist", len(events) > 0, f"found {len(events)}")

    # All events should have non-empty reason
    events_with_reason = [e for e in events if e.get("reason") and e["reason"] != "NULL"]
    check("all events have reason text",
          len(events_with_reason) == len(events),
          f"{len(events_with_reason)}/{len(events)} have reasons")

    # Should have all 3 event types
    types = {e["event_type"] for e in events}
    check("has reordered events", "reordered" in types)
    check("has swapped events", "swapped" in types)
    check("has locked events", "locked" in types)

    # Events have recommendation_ids
    events_with_ids = [e for e in events
                       if e.get("recommendation_ids") and e["recommendation_ids"] != "NULL"]
    check("events have recommendation_ids",
          len(events_with_ids) == len(events),
          f"{len(events_with_ids)}/{len(events)}")


async def teardown():
    """Clean up test data."""
    now = now_str()

    # Reset recommendations back to tory state
    mysql_write(
        f"UPDATE tory_recommendations SET source = 'tory', locked_by_coach = 0, "
        f"updated_at = '{now}' WHERE nx_user_id = {TEST_USER_ID} AND deleted_at IS NULL"
    )

    # Restore original sequences (1-20 by id order)
    recs = get_active_recommendations(TEST_USER_ID)
    for i, rec in enumerate(sorted(recs, key=lambda r: int(r["id"]))):
        mysql_write(
            f"UPDATE tory_recommendations SET sequence = {i + 1}, "
            f"updated_at = '{now}' WHERE id = {int(rec['id'])}"
        )

    # Restore swapped lesson back (rec at sequence 10 was swapped to lesson 3)
    # Find the rec that now has lesson 3
    _, swapped = mysql_query(
        f"SELECT id FROM tory_recommendations WHERE nx_user_id = {TEST_USER_ID} "
        f"AND nx_lesson_id = 3 AND deleted_at IS NULL LIMIT 1"
    )
    if swapped:
        mysql_write(
            f"UPDATE tory_recommendations SET nx_lesson_id = 5, "
            f"match_rationale = 'Restored after test', updated_at = '{now}' "
            f"WHERE id = {int(swapped[0]['id'])}"
        )

    # Delete test path events
    mysql_write(f"DELETE FROM tory_path_events WHERE nx_user_id = {TEST_USER_ID}")

    # Delete test coach
    mysql_write(
        f"DELETE FROM coaches WHERE email = 'test-coach-curation@test.com'"
    )

    print("\nTest data cleaned up.")


async def main():
    print("=" * 60)
    print("E2E Test: Coach Curation API (baap-qkk.5)")
    print("=" * 60)

    await setup()

    try:
        await test_get_path_initial()
        await test_reorder()
        await test_swap()
        await test_lock()
        await test_divergence_detection()
        await test_path_events_audit()
    finally:
        await teardown()

    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed out of {PASS + FAIL}")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
