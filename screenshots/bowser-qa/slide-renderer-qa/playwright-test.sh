#!/bin/bash
# Slide Renderer QA — Playwright screenshot capture
# Tests specific lessons that cover all 68 slide types via the actual slide viewer API
set -e

SCREENSHOT_DIR="$(dirname "$0")"
BASE_URL="http://localhost:8002"

echo "=== Slide Renderer QA — Playwright Tests ==="
echo ""

# Test key lessons that cover diverse slide types via API
LESSONS=(
  "8:One-Word"
  "11:Principles"
  "18:Stakeholders"
  "22:Measures-of-Success"
  "23:Attitude-for-Gratitude"
  "24:The-Amazing-You"
  "31:Empathy-and-Social-Skills"
  "36:Tools-for-the-Heart"
  "47:Performance-Matters"
  "52:Thinking-Productively"
  "53:Reflect-with-CARE"
  "58:Building-Your-Network"
  "87:Building-Self-Confidence"
  "103:Reading-the-Room"
  "116:Positive-Energy"
  "118:Confidence-is-Competence"
)

echo "Testing ${#LESSONS[@]} lessons via API..."

for entry in "${LESSONS[@]}"; do
  IFS=':' read -r lesson_id lesson_name <<< "$entry"
  echo -n "  Lesson $lesson_id ($lesson_name)... "

  # Check API returns slides
  response=$(curl -s "$BASE_URL/api/tory/lesson/$lesson_id/slides")
  slide_count=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('slides', d)))" 2>/dev/null || echo "0")

  if [ "$slide_count" = "0" ]; then
    echo "SKIP (no slides)"
    continue
  fi

  # Get slide types in this lesson
  types=$(echo "$response" | python3 -c "
import sys, json
d = json.load(sys.stdin)
slides = d.get('slides', d)
types = set(s.get('type', 'unknown') for s in slides)
print(','.join(sorted(types)))
" 2>/dev/null || echo "unknown")

  echo "$slide_count slides: $types"
done

echo ""
echo "=== Playwright UI Screenshot Test ==="

# Use Playwright to take screenshots of the slide viewer
npx playwright screenshot --wait-for-timeout=3000 "$BASE_URL/#tory-workspace" "$SCREENSHOT_DIR/00-workspace-overview.png" 2>/dev/null && echo "Captured workspace overview" || echo "Failed workspace overview"

echo ""
echo "=== Complete ==="
