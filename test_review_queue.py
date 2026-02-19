#!/usr/bin/env python3
"""
E2E test for Coach Review Queue (baap-qkk.10)

Tests all 6 acceptance criteria:
1. Queue displays pending items with lesson context and tag details
2. Approve action updates review_status and preserves content_tags
3. Correct action updates both review_status and content_tags with new values
4. Dismiss action marks item dismissed without modifying content_tags
5. Bulk approve works for filtered selections
6. Queue stats show accurate counts

Prerequisites: tory_content_tags populated (seeded by baap-qkk.4)
"""

import asyncio
import json
import sys

sys.path.insert(0, ".claude/mcp")
from tory_engine import (
    mysql_query,
    mysql_write,
    now_str,
    _tool_review_queue,
    _tool_review_approve,
    _tool_review_correct,
    _tool_review_dismiss,
    _tool_review_bulk_approve,
    _tool_review_queue_stats,
)

TEST_REVIEWER_ID = 1  # Use existing user as reviewer

PASS = 0
FAIL = 0

# Track test tag IDs for cleanup
SEEDED_TAG_IDS = []


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} — {detail}")


async def setup():
    """Seed test data: create content tags with various confidence levels."""
    now = now_str()

    # Create tags with known states for testing
    test_tags = [
        # Low confidence, needs_review — will test approve
        (1, '[{"trait":"Achievement","relevance_score":60,"direction":"builds"}]', 35, "needs_review"),
        # Medium confidence, pending — will test correct
        (2, '[{"trait":"Managerial","relevance_score":50,"direction":"builds"}]', 55, "pending"),
        # Low confidence, pending — will test dismiss
        (3, '[{"trait":"Patience","relevance_score":40,"direction":"leverages"}]', 30, "pending"),
        # High confidence, pending — will test bulk approve
        (4, '[{"trait":"Assertiveness","relevance_score":75,"direction":"builds"}]', 80, "pending"),
        (5, '[{"trait":"Extroversion","relevance_score":70,"direction":"builds"}]', 75, "pending"),
        # Another low confidence for queue listing
        (6, '[{"trait":"Cooperativeness","relevance_score":45,"direction":"challenges"}]', 42, "needs_review"),
    ]

    for lesson_id, tags, conf, status in test_tags:
        mysql_write(
            f"INSERT INTO tory_content_tags "
            f"(nx_lesson_id, trait_tags, confidence, review_status, created_at, updated_at) "
            f"VALUES ({lesson_id}, '{tags}', {conf}, '{status}', '{now}', '{now}')"
        )
        _, rows = mysql_query(
            f"SELECT id FROM tory_content_tags WHERE nx_lesson_id = {lesson_id} "
            f"AND confidence = {conf} AND created_at = '{now}' ORDER BY id DESC LIMIT 1"
        )
        SEEDED_TAG_IDS.append(int(rows[0]["id"]))

    print(f"Seeded {len(SEEDED_TAG_IDS)} test tags: {SEEDED_TAG_IDS}")


async def test_review_queue_displays():
    """AC1: Queue displays all pending items with lesson context and tag details."""
    print("\n--- AC1: Queue displays pending items ---")

    result = json.loads(await _tool_review_queue())
    check("Returns items", result["total"] > 0, f"total={result.get('total')}")
    check("Has items list", len(result["items"]) > 0, f"items={len(result.get('items', []))}")

    # Check first item has expected fields
    item = result["items"][0]
    check("Has tag_id", "tag_id" in item, str(item.keys()))
    check("Has nx_lesson_id", "nx_lesson_id" in item, str(item.keys()))
    check("Has lesson_title", "lesson_title" in item, str(item.keys()))
    check("Has trait_tags", "trait_tags" in item, str(item.keys()))
    check("Has confidence", "confidence" in item, str(item.keys()))
    check("Has review_status", "review_status" in item, str(item.keys()))
    check("Has pass_agreement", "pass_agreement" in item, str(item.keys()))

    # Check ordering (lowest confidence first)
    confidences = [i["confidence"] for i in result["items"]]
    check("Ordered by confidence ASC", confidences == sorted(confidences),
          f"got {confidences[:5]}")

    # Test status filter
    result_nr = json.loads(await _tool_review_queue(status_filter="needs_review"))
    for item in result_nr["items"]:
        check(f"Status filter: item {item['tag_id']} is needs_review",
              item["review_status"] == "needs_review",
              f"got {item['review_status']}")
    if not result_nr["items"]:
        check("Status filter returned results", False, "no needs_review items found")

    # Test confidence range filter
    result_low = json.loads(await _tool_review_queue(max_confidence=50))
    for item in result_low["items"]:
        check(f"Confidence filter: item {item['tag_id']} conf <= 50",
              item["confidence"] <= 50,
              f"got confidence={item['confidence']}")

    # Test pagination
    result_p1 = json.loads(await _tool_review_queue(limit=2, offset=0))
    result_p2 = json.loads(await _tool_review_queue(limit=2, offset=2))
    check("Pagination: page 1 has 2 items", len(result_p1["items"]) == 2,
          f"got {len(result_p1['items'])}")
    if result_p1["items"] and result_p2["items"]:
        check("Pagination: pages are different",
              result_p1["items"][0]["tag_id"] != result_p2["items"][0]["tag_id"],
              "same first item on both pages")


async def test_approve_action():
    """AC2: Approve preserves content_tags and updates review_status."""
    print("\n--- AC2: Approve action ---")
    tag_id = SEEDED_TAG_IDS[0]  # needs_review, conf=35

    # Get original tags before approval
    _, before = mysql_query(
        f"SELECT trait_tags, review_status FROM tory_content_tags WHERE id = {tag_id}"
    )
    original_tags = before[0]["trait_tags"]

    # Approve
    result = json.loads(await _tool_review_approve(tag_id, TEST_REVIEWER_ID, notes="Looks good"))
    check("Approve returns action=approved", result.get("action") == "approved",
          f"got {result.get('action')}")
    check("Approve returns tag_id", result.get("tag_id") == tag_id,
          f"got {result.get('tag_id')}")

    # Verify DB state
    _, after = mysql_query(
        f"SELECT trait_tags, review_status, reviewed_by, reviewed_at, review_notes "
        f"FROM tory_content_tags WHERE id = {tag_id}"
    )
    row = after[0]
    check("Status updated to approved", row["review_status"] == "approved",
          f"got {row['review_status']}")
    check("Reviewer recorded", row["reviewed_by"] == str(TEST_REVIEWER_ID),
          f"got {row['reviewed_by']}")
    check("Reviewed_at set", row["reviewed_at"] is not None and row["reviewed_at"] != "NULL",
          f"got {row['reviewed_at']}")
    check("Trait tags preserved", row["trait_tags"] == original_tags,
          f"original: {original_tags}, after: {row['trait_tags']}")
    check("Notes recorded", row["review_notes"] == "Looks good",
          f"got {row['review_notes']}")

    # Verify re-approve fails
    result2 = json.loads(await _tool_review_approve(tag_id, TEST_REVIEWER_ID))
    check("Re-approve blocked", "error" in result2, f"expected error, got {result2}")


async def test_correct_action():
    """AC3: Correct updates both review_status and content_tags with new values."""
    print("\n--- AC3: Correct action ---")
    tag_id = SEEDED_TAG_IDS[1]  # pending, conf=55

    # Get original tags
    _, before = mysql_query(
        f"SELECT trait_tags, confidence FROM tory_content_tags WHERE id = {tag_id}"
    )
    original_tags = before[0]["trait_tags"]
    original_conf = int(before[0]["confidence"])

    # Correct with new tags
    corrected = [
        {"trait": "Managerial", "relevance_score": 80, "direction": "builds"},
        {"trait": "Achievement", "relevance_score": 65, "direction": "leverages"},
    ]
    result = json.loads(await _tool_review_correct(
        tag_id, TEST_REVIEWER_ID, corrected,
        corrected_difficulty=3,
        corrected_learning_style="active",
        notes="Managerial focus is much stronger",
    ))
    check("Correct returns action=corrected", result.get("action") == "corrected",
          f"got {result.get('action')}")
    check("Returns corrected_tags", len(result.get("corrected_tags", [])) == 2,
          f"got {result.get('corrected_tags')}")
    check("Returns original_tags", len(result.get("original_tags", [])) > 0,
          f"got {result.get('original_tags')}")

    # Verify DB state
    _, after = mysql_query(
        f"SELECT trait_tags, review_status, reviewed_by, confidence, difficulty, "
        f"learning_style, review_notes "
        f"FROM tory_content_tags WHERE id = {tag_id}"
    )
    row = after[0]
    check("Status updated to approved", row["review_status"] == "approved",
          f"got {row['review_status']}")
    check("Confidence set to 100", int(row["confidence"]) == 100,
          f"got {row['confidence']}")
    check("Difficulty updated", int(row["difficulty"]) == 3,
          f"got {row['difficulty']}")
    check("Learning style updated", row["learning_style"] == "active",
          f"got {row['learning_style']}")

    # Verify new tags are stored
    new_tags = json.loads(row["trait_tags"])
    check("New tags have 2 items", len(new_tags) == 2, f"got {len(new_tags)}")
    check("First tag is Managerial@80", new_tags[0]["trait"] == "Managerial" and new_tags[0]["relevance_score"] == 80,
          f"got {new_tags[0]}")

    # Verify correction record in review_notes
    correction = json.loads(row["review_notes"])
    check("Correction stores original_tags", "original_tags" in correction,
          f"keys: {correction.keys()}")
    check("Correction stores corrected_by", correction.get("corrected_by") == TEST_REVIEWER_ID,
          f"got {correction.get('corrected_by')}")


async def test_dismiss_action():
    """AC4: Dismiss marks item dismissed without modifying content_tags."""
    print("\n--- AC4: Dismiss action ---")
    tag_id = SEEDED_TAG_IDS[2]  # pending, conf=30

    # Get original tags
    _, before = mysql_query(
        f"SELECT trait_tags FROM tory_content_tags WHERE id = {tag_id}"
    )
    original_tags = before[0]["trait_tags"]

    # Dismiss
    result = json.loads(await _tool_review_dismiss(
        tag_id, TEST_REVIEWER_ID, notes="Tags look wrong, needs re-tagging"
    ))
    check("Dismiss returns action=dismissed", result.get("action") == "dismissed",
          f"got {result.get('action')}")

    # Verify DB state
    _, after = mysql_query(
        f"SELECT trait_tags, review_status, reviewed_by "
        f"FROM tory_content_tags WHERE id = {tag_id}"
    )
    row = after[0]
    check("Status updated to dismissed", row["review_status"] == "dismissed",
          f"got {row['review_status']}")
    check("Trait tags NOT modified", row["trait_tags"] == original_tags,
          f"original: {original_tags}, after: {row['trait_tags']}")
    check("Reviewer recorded", row["reviewed_by"] == str(TEST_REVIEWER_ID),
          f"got {row['reviewed_by']}")


async def test_bulk_approve():
    """AC5: Bulk approve works for filtered selections."""
    print("\n--- AC5: Bulk approve ---")

    # Bulk approve tags with confidence >= 75 (should catch our seeded tags 4 and 5)
    result = json.loads(await _tool_review_bulk_approve(
        TEST_REVIEWER_ID, min_confidence=75, notes="High confidence batch"
    ))
    check("Bulk approve returns action", result.get("action") == "bulk_approved",
          f"got {result.get('action')}")
    check("Approved count > 0", result.get("approved_count", 0) > 0,
          f"got {result.get('approved_count')}")

    # Verify the two high-conf test tags are now approved
    for idx in [3, 4]:  # SEEDED_TAG_IDS[3] and [4]
        tag_id = SEEDED_TAG_IDS[idx]
        _, rows = mysql_query(
            f"SELECT review_status, reviewed_by FROM tory_content_tags WHERE id = {tag_id}"
        )
        if rows:
            check(f"Tag {tag_id} approved", rows[0]["review_status"] == "approved",
                  f"got {rows[0]['review_status']}")

    # Test bulk approve by specific IDs — approve remaining needs_review tag
    remaining_id = SEEDED_TAG_IDS[5]  # needs_review, conf=42
    result2 = json.loads(await _tool_review_bulk_approve(
        TEST_REVIEWER_ID, tag_ids=[remaining_id]
    ))
    check("Bulk approve by IDs works", result2.get("approved_count", 0) >= 1,
          f"got {result2.get('approved_count')}")

    _, rows = mysql_query(
        f"SELECT review_status FROM tory_content_tags WHERE id = {remaining_id}"
    )
    if rows:
        check(f"Tag {remaining_id} approved by ID", rows[0]["review_status"] == "approved",
              f"got {rows[0]['review_status']}")


async def test_queue_stats():
    """AC6: Queue stats show accurate counts."""
    print("\n--- AC6: Queue stats ---")

    result = json.loads(await _tool_review_queue_stats())

    check("Has total_pending", "total_pending" in result, str(result.keys()))
    check("Has reviewed_today", "reviewed_today" in result, str(result.keys()))
    check("Has avg_confidence_pending", "avg_confidence_pending" in result, str(result.keys()))
    check("Has status_breakdown", "status_breakdown" in result, str(result.keys()))
    check("Has confidence_distribution", "confidence_distribution" in result, str(result.keys()))

    # Verify the stats are numeric and sensible
    check("total_pending is int", isinstance(result["total_pending"], int),
          f"type={type(result['total_pending'])}")
    check("reviewed_today >= 0", result["reviewed_today"] >= 0,
          f"got {result['reviewed_today']}")
    check("avg_confidence is float", isinstance(result["avg_confidence_pending"], (int, float)),
          f"type={type(result['avg_confidence_pending'])}")

    # We just approved several tags, so reviewed_today should be > 0
    check("reviewed_today > 0 (we just reviewed)", result["reviewed_today"] > 0,
          f"got {result['reviewed_today']}")

    # Verify breakdown has expected keys
    breakdown = result["status_breakdown"]
    check("Breakdown has approved", "approved" in breakdown,
          f"keys: {breakdown.keys()}")

    # Confidence distribution
    dist = result["confidence_distribution"]
    check("Distribution has buckets", len(dist) == 4,
          f"got {len(dist)} buckets: {dist.keys()}")


async def cleanup():
    """Remove test data."""
    if SEEDED_TAG_IDS:
        id_list = ", ".join(str(i) for i in SEEDED_TAG_IDS)
        mysql_write(f"DELETE FROM tory_content_tags WHERE id IN ({id_list})")
        print(f"\nCleaned up {len(SEEDED_TAG_IDS)} test tags")


async def main():
    print("=" * 60)
    print("E2E Test: Coach Review Queue (baap-qkk.10)")
    print("=" * 60)

    try:
        await setup()
        await test_review_queue_displays()
        await test_approve_action()
        await test_correct_action()
        await test_dismiss_action()
        await test_bulk_approve()
        await test_queue_stats()
    finally:
        await cleanup()

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    print(f"{'=' * 60}")

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
