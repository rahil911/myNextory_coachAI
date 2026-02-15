#!/usr/bin/env bash
# =============================================================================
# review-verdict.sh -- Query the latest review verdict for an agent
#
# Usage:
#   review-verdict.sh <agent-name>          # Print latest verdict
#   review-verdict.sh <agent-name> --json   # Print full JSON
#   review-verdict.sh <agent-name> --check  # Exit code only (0=approved)
#   review-verdict.sh --list                # List all recent reviews
#   review-verdict.sh --stats               # Print review statistics
# =============================================================================

set -euo pipefail

BAAP_ROOT="${BAAP_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
REVIEW_DIR="$BAAP_ROOT/.claude/agents/review-agent/reviews"

# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

case "${1:---help}" in
    --list)
        echo "Recent reviews:"
        echo "==============="
        for f in "$REVIEW_DIR"/review-*.json; do
            [ -f "$f" ] || continue
            AGENT="$(basename "$f" | sed 's/review-\(.*\)-[0-9]*.json/\1/')"
            VERDICT="$(jq -r '.verdict // "UNKNOWN"' "$f" 2>/dev/null)"
            SCORE="$(jq -r '.weighted_total // "?"' "$f" 2>/dev/null)"
            TIMESTAMP="$(basename "$f" | grep -oE '[0-9]{8}-[0-9]{6}')"
            printf "  %-20s %-20s verdict=%-20s score=%s\n" "$TIMESTAMP" "$AGENT" "$VERDICT" "$SCORE"
        done
        ;;

    --stats)
        echo "Review Statistics:"
        echo "=================="
        if [ -d "$REVIEW_DIR" ]; then
            TOTAL="$(ls "$REVIEW_DIR"/review-*.json 2>/dev/null | wc -l | tr -d ' ')"
            APPROVED="$(grep -l '"APPROVED"' "$REVIEW_DIR"/review-*.json 2>/dev/null | wc -l | tr -d ' ')"
            CHANGES="$(grep -l '"CHANGES_REQUESTED"' "$REVIEW_DIR"/review-*.json 2>/dev/null | wc -l | tr -d ' ')"
            REJECTED="$(grep -l '"REJECTED"' "$REVIEW_DIR"/review-*.json 2>/dev/null | wc -l | tr -d ' ')"
            echo "  Total reviews:       $TOTAL"
            echo "  Approved:            $APPROVED"
            echo "  Changes requested:   $CHANGES"
            echo "  Rejected:            $REJECTED"
            if [ "$TOTAL" -gt 0 ]; then
                PASS_RATE="$(python3 -c "print(f'{$APPROVED/$TOTAL*100:.1f}%')" 2>/dev/null || echo "N/A")"
                echo "  First-pass rate:     $PASS_RATE"
            fi
        else
            echo "  No reviews found."
        fi
        ;;

    --help|-h)
        echo "Usage: review-verdict.sh <agent-name> [--json|--check]"
        echo "       review-verdict.sh --list"
        echo "       review-verdict.sh --stats"
        ;;

    *)
        AGENT_NAME="$1"
        MODE="${2:---text}"

        # Find latest review for this agent
        LATEST="$(ls -t "$REVIEW_DIR"/review-"${AGENT_NAME}"-*.json 2>/dev/null | head -1)"

        if [ -z "$LATEST" ] || [ ! -f "$LATEST" ]; then
            echo "[review-verdict] No review found for agent '$AGENT_NAME'" >&2
            exit 3
        fi

        case "$MODE" in
            --json)
                cat "$LATEST"
                ;;
            --check)
                VERDICT="$(jq -r '.verdict' "$LATEST" 2>/dev/null)"
                case "$VERDICT" in
                    APPROVED)           exit 0 ;;
                    CHANGES_REQUESTED)  exit 1 ;;
                    REJECTED)           exit 2 ;;
                    *)                  exit 3 ;;
                esac
                ;;
            --text|*)
                VERDICT="$(jq -r '.verdict' "$LATEST" 2>/dev/null)"
                SCORE="$(jq -r '.weighted_total' "$LATEST" 2>/dev/null)"
                SUMMARY="$(jq -r '.summary' "$LATEST" 2>/dev/null)"
                FINDINGS="$(jq '.findings | length' "$LATEST" 2>/dev/null)"
                echo "Agent:    $AGENT_NAME"
                echo "Verdict:  $VERDICT"
                echo "Score:    $SCORE / 10.0"
                echo "Findings: $FINDINGS"
                echo "Summary:  $SUMMARY"
                echo "File:     $LATEST"
                ;;
        esac
        ;;
esac
