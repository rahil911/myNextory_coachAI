#!/usr/bin/env bash
# =============================================================================
# review-feedback.sh -- Record human override of a review verdict
#
# Usage:
#   review-feedback.sh <review-id> <override-verdict> <reason>
#
# Example:
#   review-feedback.sh review-agent-a-20260214-120000 APPROVED "False positive on SQL injection"
# =============================================================================

set -euo pipefail

REVIEW_ID="${1:?Usage: review-feedback.sh <review-id> <override-verdict> <reason>}"
OVERRIDE_VERDICT="${2:?Usage: review-feedback.sh <review-id> <override-verdict> <reason>}"
REASON="${3:?Usage: review-feedback.sh <review-id> <override-verdict> <reason>}"

BAAP_ROOT="${BAAP_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
REVIEW_DIR="$BAAP_ROOT/.claude/agents/review-agent/reviews"
MEMORY_FILE="$BAAP_ROOT/.claude/agents/review-agent/memory/MEMORY.md"

# Find the review
REVIEW_FILE="$REVIEW_DIR/${REVIEW_ID}.json"
if [ ! -f "$REVIEW_FILE" ]; then
    echo "Review not found: $REVIEW_FILE" >&2
    exit 1
fi

ORIGINAL_VERDICT="$(jq -r '.verdict' "$REVIEW_FILE")"

echo "[feedback] Recording override: $ORIGINAL_VERDICT -> $OVERRIDE_VERDICT"
echo "[feedback] Reason: $REASON"

# Add override metadata to the review JSON
jq --arg ov "$OVERRIDE_VERDICT" --arg reason "$REASON" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '. + {human_override: {original_verdict: .verdict, override_verdict: $ov, reason: $reason, timestamp: $ts}}' \
    "$REVIEW_FILE" > "${REVIEW_FILE}.tmp" && mv "${REVIEW_FILE}.tmp" "$REVIEW_FILE"

# Append to memory file for future calibration
{
    echo ""
    echo "### Override: $REVIEW_ID ($(date +%Y-%m-%d))"
    echo "- Original: $ORIGINAL_VERDICT -> Override: $OVERRIDE_VERDICT"
    echo "- Reason: $REASON"
    echo "- Findings that were wrong:"
    jq -r '.findings[] | "  - [\(.severity)] \(.dimension): \(.description)"' "$REVIEW_FILE" 2>/dev/null || true
} >> "$MEMORY_FILE"

echo "[feedback] Override recorded in $MEMORY_FILE"
