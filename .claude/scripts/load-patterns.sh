#!/usr/bin/env bash
# =============================================================================
# load-patterns.sh — Load shared patterns on session start
#
# Runs on: SessionStart (after onboard.sh)
# Purpose: Surface recently added/updated patterns so agents are aware of
#          new knowledge without needing beads notifications.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PATTERNS_FILE="$PROJECT_ROOT/.claude/knowledge/patterns.md"

if [ ! -f "$PATTERNS_FILE" ]; then
  exit 0  # No patterns file yet, nothing to load
fi

# Count patterns by confidence level
ESTABLISHED=$(grep -c 'Confidence.*established' "$PATTERNS_FILE" 2>/dev/null || echo "0")
VALIDATED=$(grep -c 'Confidence.*validated' "$PATTERNS_FILE" 2>/dev/null || echo "0")
HYPOTHESIS=$(grep -c 'Confidence.*hypothesis' "$PATTERNS_FILE" 2>/dev/null || echo "0")
TOTAL=$((ESTABLISHED + VALIDATED + HYPOTHESIS))

if [ "$TOTAL" -eq 0 ]; then
  exit 0  # No patterns yet
fi

# Find patterns added or updated in the last 7 days
SEVEN_DAYS_AGO=$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d '7 days ago' +%Y-%m-%d 2>/dev/null || echo "")
RECENT_PATTERNS=""
if [ -n "$SEVEN_DAYS_AGO" ]; then
  # Extract pattern names with dates after the cutoff
  RECENT_PATTERNS=$(grep -B1 "Last validated.*$SEVEN_DAYS_AGO\|Date.*$SEVEN_DAYS_AGO" "$PATTERNS_FILE" 2>/dev/null \
    | grep '^### ' \
    | sed 's/^### /  - /' \
    | head -10 || echo "")
fi

# Output summary for agent context
cat << EOF
=== Shared Knowledge Loaded ===
Patterns: $TOTAL total ($ESTABLISHED established, $VALIDATED validated, $HYPOTHESIS hypothesis)
EOF

if [ -n "$RECENT_PATTERNS" ]; then
  cat << EOF
Recently added/updated:
$RECENT_PATTERNS
EOF
fi

cat << EOF

Read: @.claude/knowledge/patterns.md
Schema: @.claude/knowledge/SCHEMA.md
===============================
EOF
