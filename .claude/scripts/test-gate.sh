#!/usr/bin/env bash
# =============================================================================
# scripts/test-gate.sh -- Run affected tests for an agent's worktree
#
# Usage: scripts/test-gate.sh <worktree-path> [--timeout <seconds>] [--base-branch <branch>]
# Exit codes:
#   0 = all tests passed (or no tests to run)
#   1 = one or more tests failed
#   2 = tests timed out
#   3 = test infrastructure error (missing pytest, vitest, etc.)
#
# Output: writes test-gate-result.json to <worktree-path>/
# =============================================================================

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Parse arguments
# ─────────────────────────────────────────────────────────────────────────────
WORKTREE=""
TIMEOUT=300  # 5 minutes default
BASE_BRANCH="main"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --timeout)
      TIMEOUT="$2"
      shift 2
      ;;
    --base-branch)
      BASE_BRANCH="$2"
      shift 2
      ;;
    *)
      WORKTREE="$1"
      shift
      ;;
  esac
done

if [ -z "$WORKTREE" ]; then
  echo "ERROR: worktree path required"
  echo "Usage: test-gate.sh <worktree-path> [--timeout <seconds>] [--base-branch <branch>]"
  exit 3
fi

WORKTREE="$(cd "$WORKTREE" && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULT_FILE="$WORKTREE/test-gate-result.json"
LOG_DIR="$WORKTREE/.test-gate-logs"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$LOG_DIR"

echo "=== Test Gate: $(date) ==="
echo "Worktree: $WORKTREE"
echo "Timeout:  ${TIMEOUT}s"
echo "Base:     $BASE_BRANCH"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 1. Run test-map.sh to discover affected tests
# ─────────────────────────────────────────────────────────────────────────────
echo "--- Discovering affected tests ---"

TEST_MAP_OUTPUT="$("$SCRIPT_DIR/test-map.sh" "$WORKTREE" "$BASE_BRANCH" 2>&1)"
TEST_MAP_EXIT=$?

if [ $TEST_MAP_EXIT -ne 0 ]; then
  echo "ERROR: test-map.sh failed (exit $TEST_MAP_EXIT)"
  echo "$TEST_MAP_OUTPUT"
  cat > "$RESULT_FILE" <<ENDJSON
{
  "status": "error",
  "error": "test-map.sh failed",
  "detail": "$(echo "$TEST_MAP_OUTPUT" | head -20 | sed 's/"/\\"/g' | tr '\n' ' ')",
  "timestamp": "$TIMESTAMP"
}
ENDJSON
  exit 3
fi

echo "$TEST_MAP_OUTPUT" > "$LOG_DIR/test-map-output.json"

# Parse the test map
NO_CHANGES="$(echo "$TEST_MAP_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('no_changes', False))" 2>/dev/null || echo "False")"

if [ "$NO_CHANGES" = "True" ]; then
  echo "No file changes detected. Skipping tests."
  cat > "$RESULT_FILE" <<ENDJSON
{
  "status": "skipped",
  "reason": "no_changes",
  "timestamp": "$TIMESTAMP"
}
ENDJSON
  exit 0
fi

PYTHON_TESTS="$(echo "$TEST_MAP_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(d.get('python_tests',[])))" 2>/dev/null || echo "")"
RUN_ALL_PYTHON="$(echo "$TEST_MAP_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_all_python', False))" 2>/dev/null || echo "False")"
HAS_JS_CHANGES="$(echo "$TEST_MAP_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('has_js_changes', False))" 2>/dev/null || echo "False")"
RUN_ALL_JS="$(echo "$TEST_MAP_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_all_js', False))" 2>/dev/null || echo "False")"
JS_TESTS="$(echo "$TEST_MAP_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(d.get('js_tests',[])))" 2>/dev/null || echo "")"
UNMAPPED_FILES="$(echo "$TEST_MAP_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(d.get('unmapped_files',[])))" 2>/dev/null || echo "")"

echo "Python tests: ${PYTHON_TESTS:-none}"
echo "JS changes:   $HAS_JS_CHANGES"
echo "Run all py:   $RUN_ALL_PYTHON"
echo "Run all js:   $RUN_ALL_JS"
echo "Unmapped:     ${UNMAPPED_FILES:-none}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 2. Track overall results
# ─────────────────────────────────────────────────────────────────────────────
PYTHON_STATUS="skipped"
PYTHON_EXIT=0
PYTHON_OUTPUT=""
PYTHON_PASSED=0
PYTHON_FAILED=0
PYTHON_ERRORS=0

JS_STATUS="skipped"
JS_EXIT=0
JS_OUTPUT=""
JS_PASSED=0
JS_FAILED=0

OVERALL_STATUS="passed"
TIMED_OUT=false

# ─────────────────────────────────────────────────────────────────────────────
# 3. Run Python tests
# ─────────────────────────────────────────────────────────────────────────────
run_python_tests() {
  cd "$WORKTREE"

  # Activate venv if it exists
  if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
  fi

  # Verify pytest is available
  if ! command -v pytest &>/dev/null; then
    if python3 -m pytest --version &>/dev/null; then
      PYTEST_CMD="python3 -m pytest"
    else
      echo "WARNING: pytest not found. Skipping Python tests."
      PYTHON_STATUS="skipped"
      return 0
    fi
  else
    PYTEST_CMD="pytest"
  fi

  local pytest_args=("-v" "--tb=short" "--no-header" "-q")
  local test_targets=()

  if [ "$RUN_ALL_PYTHON" = "True" ]; then
    echo "--- Running ALL Python tests (dependency file changed) ---"
    # Run everything in tests/ and scripts/test_*.py
    if [ -d "tests" ]; then
      test_targets+=("tests/")
    fi
    for f in scripts/test_*.py; do
      [ -f "$f" ] && test_targets+=("$f")
    done
  elif [ -n "$PYTHON_TESTS" ]; then
    echo "--- Running targeted Python tests ---"
    for test_file in $PYTHON_TESTS; do
      if [ -f "$test_file" ]; then
        test_targets+=("$test_file")
      else
        echo "WARNING: mapped test file not found: $test_file"
      fi
    done
  fi

  if [ ${#test_targets[@]} -eq 0 ]; then
    echo "No Python test targets to run."
    PYTHON_STATUS="skipped"
    return 0
  fi

  echo "Running: $PYTEST_CMD ${pytest_args[*]} ${test_targets[*]}"
  echo ""

  # Run with timeout
  local output_file="$LOG_DIR/pytest-output.txt"
  set +e
  timeout "$TIMEOUT" $PYTEST_CMD "${pytest_args[@]}" "${test_targets[@]}" \
    2>&1 | tee "$output_file"
  local exit_code=${PIPESTATUS[0]}
  set -e

  PYTHON_OUTPUT="$(cat "$output_file")"
  PYTHON_EXIT=$exit_code

  # Parse exit code
  case $exit_code in
    0)
      PYTHON_STATUS="passed"
      ;;
    1)
      PYTHON_STATUS="failed"
      ;;
    2)
      PYTHON_STATUS="error"
      ;;
    5)
      # pytest exit code 5 = no tests collected
      PYTHON_STATUS="skipped"
      PYTHON_EXIT=0
      echo "No Python tests were collected."
      ;;
    124)
      # timeout exit code
      PYTHON_STATUS="timeout"
      TIMED_OUT=true
      ;;
    *)
      PYTHON_STATUS="error"
      ;;
  esac

  # Parse pass/fail counts from pytest output
  # pytest summary line looks like: "5 passed, 2 failed, 1 error in 3.45s"
  if [ -f "$output_file" ]; then
    PYTHON_PASSED=$(grep -oE '[0-9]+ passed' "$output_file" | grep -oE '[0-9]+' || echo "0")
    PYTHON_FAILED=$(grep -oE '[0-9]+ failed' "$output_file" | grep -oE '[0-9]+' || echo "0")
    PYTHON_ERRORS=$(grep -oE '[0-9]+ error' "$output_file" | grep -oE '[0-9]+' || echo "0")
  fi

  echo ""
  echo "Python tests: status=$PYTHON_STATUS passed=$PYTHON_PASSED failed=$PYTHON_FAILED errors=$PYTHON_ERRORS"
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. Run JavaScript tests
# ─────────────────────────────────────────────────────────────────────────────
run_js_tests() {
  cd "$WORKTREE"

  if [ ! -d "ui" ]; then
    echo "No ui/ directory found. Skipping JS tests."
    JS_STATUS="skipped"
    return 0
  fi

  cd ui

  # Verify vitest is available
  if [ ! -f "node_modules/.bin/vitest" ] && ! command -v vitest &>/dev/null; then
    echo "WARNING: vitest not found in ui/. Skipping JS tests."
    echo "  Run 'npm install' in ui/ to set up test dependencies."
    JS_STATUS="skipped"
    return 0
  fi

  local vitest_cmd="npx vitest run"
  local output_file="$LOG_DIR/vitest-output.txt"

  if [ "$RUN_ALL_JS" = "True" ]; then
    echo "--- Running ALL JS tests (config file changed) ---"
  elif [ -n "$JS_TESTS" ]; then
    echo "--- Running related JS tests ---"
    # vitest --related uses Vite's module graph to find affected tests
    # This is more accurate than manual file mapping for the frontend
    local related_files=""
    for f in $JS_TESTS; do
      # Convert to path relative to ui/ for vitest
      local rel_path="${f#ui/}"
      related_files="$related_files ../$f"
    done
    vitest_cmd="npx vitest run --related $related_files"
  else
    echo "No JS test targets. Skipping."
    JS_STATUS="skipped"
    return 0
  fi

  echo "Running: $vitest_cmd"
  echo ""

  set +e
  timeout "$TIMEOUT" bash -c "$vitest_cmd" 2>&1 | tee "$output_file"
  local exit_code=${PIPESTATUS[0]}
  set -e

  JS_OUTPUT="$(cat "$output_file")"
  JS_EXIT=$exit_code

  case $exit_code in
    0)
      JS_STATUS="passed"
      ;;
    1)
      JS_STATUS="failed"
      ;;
    124)
      JS_STATUS="timeout"
      TIMED_OUT=true
      ;;
    *)
      JS_STATUS="error"
      ;;
  esac

  # Parse vitest output for counts
  # vitest summary: "Tests  5 passed | 2 failed (7)"
  if [ -f "$output_file" ]; then
    JS_PASSED=$(grep -oE '[0-9]+ passed' "$output_file" | head -1 | grep -oE '[0-9]+' || echo "0")
    JS_FAILED=$(grep -oE '[0-9]+ failed' "$output_file" | head -1 | grep -oE '[0-9]+' || echo "0")
  fi

  echo ""
  echo "JS tests: status=$JS_STATUS passed=$JS_PASSED failed=$JS_FAILED"
}

# ─────────────────────────────────────────────────────────────────────────────
# 5. Execute test suites
# ─────────────────────────────────────────────────────────────────────────────
HAS_PYTHON_TESTS=false
HAS_JS_TESTS=false

if [ -n "$PYTHON_TESTS" ] || [ "$RUN_ALL_PYTHON" = "True" ]; then
  HAS_PYTHON_TESTS=true
  run_python_tests
fi

if [ "$HAS_JS_CHANGES" = "True" ] || [ "$RUN_ALL_JS" = "True" ]; then
  HAS_JS_TESTS=true
  run_js_tests
fi

# ─────────────────────────────────────────────────────────────────────────────
# 6. Determine overall status
# ─────────────────────────────────────────────────────────────────────────────
if [ "$TIMED_OUT" = true ]; then
  OVERALL_STATUS="timeout"
elif [ "$PYTHON_STATUS" = "failed" ] || [ "$PYTHON_STATUS" = "error" ] || \
     [ "$JS_STATUS" = "failed" ] || [ "$JS_STATUS" = "error" ]; then
  OVERALL_STATUS="failed"
elif [ "$PYTHON_STATUS" = "passed" ] || [ "$JS_STATUS" = "passed" ]; then
  OVERALL_STATUS="passed"
else
  OVERALL_STATUS="skipped"
fi

# Collect failure messages for bead creation
FAILURE_SUMMARY=""
if [ "$OVERALL_STATUS" = "failed" ] || [ "$OVERALL_STATUS" = "timeout" ]; then
  if [ "$PYTHON_STATUS" = "failed" ] || [ "$PYTHON_STATUS" = "error" ]; then
    # Extract the FAILURES section from pytest output
    FAILURE_SUMMARY="$(echo "$PYTHON_OUTPUT" | sed -n '/^FAILED\|^=.*FAILURES/,/^=.*short test summary/p' | head -80)"
    if [ -z "$FAILURE_SUMMARY" ]; then
      # Fallback: last 40 lines of output
      FAILURE_SUMMARY="$(echo "$PYTHON_OUTPUT" | tail -40)"
    fi
  fi
  if [ "$JS_STATUS" = "failed" ] || [ "$JS_STATUS" = "error" ]; then
    JS_FAILURES="$(echo "$JS_OUTPUT" | grep -A 5 'FAIL\|AssertionError\|Error:' | head -80)"
    if [ -z "$JS_FAILURES" ]; then
      JS_FAILURES="$(echo "$JS_OUTPUT" | tail -40)"
    fi
    FAILURE_SUMMARY="$FAILURE_SUMMARY
--- JavaScript Test Failures ---
$JS_FAILURES"
  fi
  if [ "$OVERALL_STATUS" = "timeout" ]; then
    FAILURE_SUMMARY="TIMEOUT: Tests did not complete within ${TIMEOUT}s.
$FAILURE_SUMMARY"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# 7. Handle unmapped files (no tests exist)
# ─────────────────────────────────────────────────────────────────────────────
UNMAPPED_WARNING=""
if [ -n "$UNMAPPED_FILES" ]; then
  UNMAPPED_WARNING="WARNING: No test files found for: $UNMAPPED_FILES"
  echo ""
  echo "$UNMAPPED_WARNING"
  echo "Consider writing tests for these files."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 8. Write result JSON
# ─────────────────────────────────────────────────────────────────────────────
python3 -c "
import json

result = {
    'status': '$OVERALL_STATUS',
    'timestamp': '$TIMESTAMP',
    'timeout_seconds': $TIMEOUT,
    'python': {
        'status': '$PYTHON_STATUS',
        'exit_code': $PYTHON_EXIT,
        'passed': int('${PYTHON_PASSED:-0}' or 0),
        'failed': int('${PYTHON_FAILED:-0}' or 0),
        'errors': int('${PYTHON_ERRORS:-0}' or 0),
        'tests_run': $([ "$HAS_PYTHON_TESTS" = true ] && echo 'True' || echo 'False')
    },
    'javascript': {
        'status': '$JS_STATUS',
        'exit_code': $JS_EXIT,
        'passed': int('${JS_PASSED:-0}' or 0),
        'failed': int('${JS_FAILED:-0}' or 0),
        'tests_run': $([ "$HAS_JS_TESTS" = true ] && echo 'True' || echo 'False')
    },
    'unmapped_files': '${UNMAPPED_FILES}'.split() if '${UNMAPPED_FILES}'.strip() else [],
    'failure_summary': '''$(echo "$FAILURE_SUMMARY" | sed "s/'''/\\\\'\\\\'\\\\'/" | head -100)'''
}

with open('$RESULT_FILE', 'w') as f:
    json.dump(result, f, indent=2)

print(json.dumps(result, indent=2))
" 2>/dev/null || {
  # Fallback if python3 JSON generation fails
  cat > "$RESULT_FILE" <<ENDJSON
{
  "status": "$OVERALL_STATUS",
  "timestamp": "$TIMESTAMP",
  "error": "Failed to generate detailed result JSON"
}
ENDJSON
}

# ─────────────────────────────────────────────────────────────────────────────
# 9. Print summary and exit
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "=================================="
echo " Test Gate Result: $OVERALL_STATUS"
echo "=================================="
echo " Python: $PYTHON_STATUS (${PYTHON_PASSED:-0} passed, ${PYTHON_FAILED:-0} failed)"
echo " JS:     $JS_STATUS (${JS_PASSED:-0} passed, ${JS_FAILED:-0} failed)"
if [ -n "$UNMAPPED_FILES" ]; then
  echo " Unmapped: $UNMAPPED_FILES"
fi
echo "=================================="
echo ""

case "$OVERALL_STATUS" in
  passed|skipped)
    exit 0
    ;;
  failed)
    exit 1
    ;;
  timeout)
    exit 2
    ;;
  *)
    exit 3
    ;;
esac
