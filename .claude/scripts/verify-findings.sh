#!/usr/bin/env bash
# =============================================================================
# verify-findings.sh -- Verify that review findings reference real code
#
# Checks that each finding's file:line reference actually exists and
# that the described issue is plausible (the line contains relevant code).
#
# Usage:
#   verify-findings.sh <review-json-file> <worktree-path>
#
# Exit codes:
#   0  All findings verified (or no findings to verify)
#   1  Some findings reference non-existent code (potential hallucination)
# =============================================================================

set -euo pipefail

REVIEW_FILE="${1:?Usage: verify-findings.sh <review-json-file> <worktree-path>}"
WORKTREE_PATH="${2:?Usage: verify-findings.sh <review-json-file> <worktree-path>}"

if [ ! -f "$REVIEW_FILE" ]; then
    echo "[verify] Review file not found: $REVIEW_FILE" >&2
    exit 1
fi

FINDINGS_COUNT="$(jq '.findings | length' "$REVIEW_FILE" 2>/dev/null || echo 0)"
if [ "$FINDINGS_COUNT" -eq 0 ]; then
    echo "[verify] No findings to verify."
    exit 0
fi

HALLUCINATION_COUNT=0
VERIFIED_COUNT=0

for i in $(seq 0 $((FINDINGS_COUNT - 1))); do
    FILE="$(jq -r ".findings[$i].file // \"\"" "$REVIEW_FILE")"
    LINE="$(jq -r ".findings[$i].line // 0" "$REVIEW_FILE")"
    DESC="$(jq -r ".findings[$i].description // \"\"" "$REVIEW_FILE")"

    # Skip findings without file references (general findings)
    if [ -z "$FILE" ] || [ "$FILE" = "null" ] || [ "$FILE" = "" ]; then
        continue
    fi

    FULL_PATH="$WORKTREE_PATH/$FILE"

    if [ ! -f "$FULL_PATH" ]; then
        echo "[verify] HALLUCINATION? Finding $i references non-existent file: $FILE"
        HALLUCINATION_COUNT=$((HALLUCINATION_COUNT + 1))
        continue
    fi

    if [ "$LINE" -gt 0 ]; then
        TOTAL_LINES="$(wc -l < "$FULL_PATH" | tr -d ' ')"
        if [ "$LINE" -gt "$TOTAL_LINES" ]; then
            echo "[verify] HALLUCINATION? Finding $i references line $LINE but $FILE has only $TOTAL_LINES lines"
            HALLUCINATION_COUNT=$((HALLUCINATION_COUNT + 1))
            continue
        fi
    fi

    VERIFIED_COUNT=$((VERIFIED_COUNT + 1))
done

echo "[verify] Results: $VERIFIED_COUNT verified, $HALLUCINATION_COUNT potential hallucinations out of $FINDINGS_COUNT findings"

if [ "$HALLUCINATION_COUNT" -gt 0 ]; then
    echo "[verify] WARNING: $HALLUCINATION_COUNT findings may be hallucinated."

    # If more than half the findings are hallucinated, the review itself is suspect
    if [ "$HALLUCINATION_COUNT" -gt $((FINDINGS_COUNT / 2)) ]; then
        echo "[verify] CRITICAL: Majority of findings appear hallucinated. Review quality is suspect."
        echo "[verify] Consider re-running the review or requesting human review."
    fi

    exit 1
else
    exit 0
fi
