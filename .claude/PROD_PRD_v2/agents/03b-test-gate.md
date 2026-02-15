# Phase 3b: Automated Test Gate in cleanup.sh

## Purpose

The multi-agent swarm operates on a trust-but-verify principle: agents work autonomously in isolated git worktrees, but their output must pass quality gates before merging back to main. Today, cleanup.sh enforces KG ownership checks, bead closure checks, and flock-based merge locking -- but there is no automated verification that the agent's code changes actually work. A broken import, a missing function argument, or a typo in a route handler will sail straight through into main, where it becomes everyone's problem.

The test gate closes this gap. Before cleanup.sh performs `git merge`, it identifies which files the agent changed, maps those files to the relevant test suites (Python pytest for backend, vitest for frontend), and runs only the affected tests. This keeps merge latency low -- typically under 30 seconds for targeted tests -- while catching regressions at the point where they are cheapest to fix: before they leave the agent's worktree.

When tests fail, the gate does not simply block and walk away. It creates a "fix tests" bead with the full failure output, assigned to the same agent that caused the regression. The retry-agent.sh script picks up this bead and re-spawns the agent with the test failure as context, creating a closed-loop repair cycle. The agent never ships broken code, and the human operator never has to manually parse pytest tracebacks.

## Risks Mitigated

- **Risk 33: Silent regressions merged to main** -- Without a test gate, agent-authored code merges unchecked. A single broken import in `src/api/users.py` can take down the entire backend. The test gate catches this before merge, keeping main deployable at all times.
- **Risk 34: Cascading failures across agents** -- When Agent A merges broken code, Agent B (which spawns later on the updated main) inherits the breakage. It wastes its entire session debugging someone else's regression. The test gate isolates failures to the originating agent.
- **Risk 35: Unbounded test execution blocking merges** -- Running the entire test suite on every merge creates a 10+ minute bottleneck. Smart test selection limits execution to affected tests, keeping the gate under 60 seconds for typical changes. A 5-minute hard timeout prevents pathological cases from blocking the pipeline.
- **Risk 36: No test coverage awareness** -- When an agent changes files that have no corresponding tests, the gap is invisible. The test gate detects this and creates a "write tests" bead, building coverage incrementally without blocking current work.
- **Risk 37: Emergency merges blocked by flaky tests** -- Production incidents sometimes require bypassing normal gates. The `--skip-tests` flag provides an escape hatch, but logs a warning and records the skip in the bead trail for post-incident review.

## Files to Create

| File | Purpose |
|------|---------|
| `.claude/scripts/test-gate.sh` | Standalone test runner invoked by cleanup.sh. Handles test discovery, execution, timeout, and result reporting. |
| `.claude/scripts/test-map.sh` | Maps changed files to test files. Contains the heuristic rules and KG fallback logic. |
| `.claude/scripts/retry-agent.sh` | Re-spawns an agent with test failure context from a bead. |
| `config/test-mapping.json` | Static mapping overrides for files where heuristic detection fails. |

## Files to Modify

| File | Change |
|------|--------|
| `.claude/scripts/cleanup.sh` | Insert test gate call between ownership check and merge. Add `--skip-tests` flag parsing. |
| `.claude/scripts/spawn.sh` | Pass test failure bead context when re-spawning for retries. |

---

## Fix 1: Test Mapping Engine (`.claude/scripts/test-map.sh`)

### Problem

Given a list of changed files from an agent's worktree, we need to determine which test files to run. Running all tests is too slow (minutes). Running no tests is unsafe. We need a mapping layer that resolves changed source files to their corresponding test files using a combination of convention-based heuristics, static overrides, and KG-derived import graph lookups.

### Solution

```bash
#!/usr/bin/env bash
# =============================================================================
# scripts/test-map.sh -- Map changed files to test files
#
# Usage: scripts/test-map.sh <worktree-path> [<base-branch>]
# Output: JSON object with "python_tests" and "js_tests" arrays, plus metadata
#
# Strategy (in priority order):
#   1. Static overrides from config/test-mapping.json
#   2. Convention: src/foo/bar.py -> tests/test_bar.py, tests/foo/test_bar.py
#   3. Convention: ui/src/**/*.tsx -> npm test in ui/
#   4. KG import graph: get_file_owner() to find test files that import changed modules
#   5. Fallback: if nothing matched, flag "no_tests_found" for the file
# =============================================================================

set -euo pipefail

WORKTREE="${1:?Usage: test-map.sh <worktree-path> [base-branch]}"
BASE_BRANCH="${2:-main}"
REPO_ROOT="$(cd "$WORKTREE" && git rev-parse --show-toplevel)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../config/test-mapping.json"

# ─────────────────────────────────────────────────────────────────────────────
# 1. Get changed files relative to base branch
# ─────────────────────────────────────────────────────────────────────────────
get_changed_files() {
  cd "$WORKTREE"
  # Compare agent branch to base. --diff-filter=ACMR excludes deleted files.
  git diff --name-only --diff-filter=ACMR "${BASE_BRANCH}...HEAD" 2>/dev/null \
    || git diff --name-only --diff-filter=ACMR HEAD~1 2>/dev/null \
    || echo ""
}

CHANGED_FILES="$(get_changed_files)"

if [ -z "$CHANGED_FILES" ]; then
  # No changes detected -- nothing to test
  cat <<'ENDJSON'
{"python_tests":[],"js_tests":[],"no_changes":true,"unmapped_files":[],"run_all_python":false,"run_all_js":false}
ENDJSON
  exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# 2. Classify changed files by stack
# ─────────────────────────────────────────────────────────────────────────────
PYTHON_CHANGED=()
JS_CHANGED=()
CONFIG_CHANGED=()
OTHER_CHANGED=()

while IFS= read -r file; do
  case "$file" in
    src/*.py|*.py)
      PYTHON_CHANGED+=("$file")
      ;;
    ui/src/*.tsx|ui/src/*.ts|ui/src/*.jsx|ui/src/*.js)
      JS_CHANGED+=("$file")
      ;;
    ui/package.json|ui/tsconfig.json|ui/next.config.*|ui/vitest.*)
      CONFIG_CHANGED+=("$file")
      JS_CHANGED+=("$file")  # Config changes can break JS tests
      ;;
    config/*|*.yaml|*.yml|*.json)
      CONFIG_CHANGED+=("$file")
      ;;
    requirements.txt|pyproject.toml|setup.py|setup.cfg)
      CONFIG_CHANGED+=("$file")
      PYTHON_CHANGED+=("$file")  # Dependency changes can break Python tests
      ;;
    *)
      OTHER_CHANGED+=("$file")
      ;;
  esac
done <<< "$CHANGED_FILES"

# ─────────────────────────────────────────────────────────────────────────────
# 3. Static override lookup
# ─────────────────────────────────────────────────────────────────────────────
# config/test-mapping.json format:
# {
#   "overrides": {
#     "src/api/users.py": ["tests/test_users.py", "tests/test_api_e2e.py"],
#     "src/context_packager.py": ["tests/test_context_packager.py"]
#   }
# }
lookup_static_override() {
  local file="$1"
  if [ -f "$CONFIG_FILE" ] && command -v python3 &>/dev/null; then
    python3 -c "
import json, sys
with open('$CONFIG_FILE') as f:
    m = json.load(f)
overrides = m.get('overrides', {})
result = overrides.get('$file', [])
for t in result:
    print(t)
" 2>/dev/null
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. Convention-based test discovery for Python
# ─────────────────────────────────────────────────────────────────────────────
# Rules:
#   src/api/capsules.py       -> tests/test_api.py, tests/api/test_capsules.py, tests/test_capsules.py
#   src/context_packager.py   -> tests/test_context_packager.py
#   src/models/metric.py      -> tests/test_models.py, tests/models/test_metric.py
#
# We check all candidates and return only those that exist on disk.
find_python_tests() {
  local src_file="$1"
  local basename
  local dirname
  local candidates=()

  basename="$(basename "$src_file" .py)"
  dirname="$(dirname "$src_file")"

  # Direct test file: tests/test_<basename>.py
  candidates+=("tests/test_${basename}.py")

  # Directory-mirrored test file: tests/<subpath>/test_<basename>.py
  # e.g., src/api/capsules.py -> tests/api/test_capsules.py
  local subpath="${dirname#src/}"
  if [ "$subpath" != "$dirname" ]; then
    candidates+=("tests/${subpath}/test_${basename}.py")
    # Also try the directory-level test: tests/test_<dirname_basename>.py
    # e.g., src/api/capsules.py -> tests/test_api.py
    local dir_basename
    dir_basename="$(basename "$subpath")"
    candidates+=("tests/test_${dir_basename}.py")
  fi

  # Scripts directory (legacy test location)
  candidates+=("scripts/test_${basename}.py")

  # Check which candidates actually exist
  for candidate in "${candidates[@]}"; do
    if [ -f "$WORKTREE/$candidate" ]; then
      echo "$candidate"
    fi
  done
}

# ─────────────────────────────────────────────────────────────────────────────
# 5. KG import graph fallback (uses MCP get_file_owner if available)
# ─────────────────────────────────────────────────────────────────────────────
find_tests_via_import_graph() {
  local src_file="$1"
  local module_name
  module_name="$(echo "$src_file" | sed 's|/|.|g' | sed 's|\.py$||')"

  # Search for test files that import the changed module
  cd "$WORKTREE"
  grep -rl "from ${module_name}\b\|import ${module_name}\b" tests/ scripts/ 2>/dev/null \
    | grep -E '(test_.*\.py|.*_test\.py)$' \
    || true
}

# ─────────────────────────────────────────────────────────────────────────────
# 6. Resolve all Python test files
# ─────────────────────────────────────────────────────────────────────────────
PYTHON_TESTS=()
UNMAPPED_FILES=()
RUN_ALL_PYTHON=false
RUN_ALL_JS=false

for file in "${PYTHON_CHANGED[@]+"${PYTHON_CHANGED[@]}"}"; do
  found_test=false

  # Strategy 1: Static override
  while IFS= read -r test_file; do
    if [ -n "$test_file" ]; then
      PYTHON_TESTS+=("$test_file")
      found_test=true
    fi
  done < <(lookup_static_override "$file")

  if [ "$found_test" = true ]; then
    continue
  fi

  # Strategy 2: Convention-based
  while IFS= read -r test_file; do
    if [ -n "$test_file" ]; then
      PYTHON_TESTS+=("$test_file")
      found_test=true
    fi
  done < <(find_python_tests "$file")

  if [ "$found_test" = true ]; then
    continue
  fi

  # Strategy 3: Import graph grep
  while IFS= read -r test_file; do
    if [ -n "$test_file" ]; then
      PYTHON_TESTS+=("$test_file")
      found_test=true
    fi
  done < <(find_tests_via_import_graph "$file")

  if [ "$found_test" = false ]; then
    UNMAPPED_FILES+=("$file")
  fi
done

# If requirements.txt or pyproject.toml changed, run all Python tests
for file in "${CONFIG_CHANGED[@]+"${CONFIG_CHANGED[@]}"}"; do
  case "$file" in
    requirements.txt|pyproject.toml|setup.py|setup.cfg)
      RUN_ALL_PYTHON=true
      ;;
  esac
done

# If package.json or vitest config changed, run all JS tests
for file in "${CONFIG_CHANGED[@]+"${CONFIG_CHANGED[@]}"}"; do
  case "$file" in
    ui/package.json|ui/vitest.*|ui/tsconfig.json)
      RUN_ALL_JS=true
      ;;
  esac
done

# Deduplicate Python tests
PYTHON_TESTS_DEDUP=()
if [ ${#PYTHON_TESTS[@]} -gt 0 ]; then
  while IFS= read -r line; do
    PYTHON_TESTS_DEDUP+=("$line")
  done < <(printf '%s\n' "${PYTHON_TESTS[@]}" | sort -u)
fi

# ─────────────────────────────────────────────────────────────────────────────
# 7. Determine JS test scope
# ─────────────────────────────────────────────────────────────────────────────
JS_TESTS=()
HAS_JS_CHANGES=false

if [ ${#JS_CHANGED[@]} -gt 0 ]; then
  HAS_JS_CHANGES=true
fi

# For JS, we run vitest with --related flag pointing to changed files,
# which uses Vite's module graph to find affected tests.
# This is more accurate than manual mapping for the frontend.
for file in "${JS_CHANGED[@]+"${JS_CHANGED[@]}"}"; do
  JS_TESTS+=("$file")
done

# ─────────────────────────────────────────────────────────────────────────────
# 8. Output JSON result
# ─────────────────────────────────────────────────────────────────────────────
python3 -c "
import json

result = {
    'python_tests': $(printf '%s\n' "${PYTHON_TESTS_DEDUP[@]+"${PYTHON_TESTS_DEDUP[@]}"}" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo '[]'),
    'js_tests': $(printf '%s\n' "${JS_TESTS[@]+"${JS_TESTS[@]}"}" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo '[]'),
    'run_all_python': $( [ "$RUN_ALL_PYTHON" = true ] && echo 'True' || echo 'False'),
    'run_all_js': $( [ "$RUN_ALL_JS" = true ] && echo 'True' || echo 'False'),
    'has_js_changes': $( [ "$HAS_JS_CHANGES" = true ] && echo 'True' || echo 'False'),
    'unmapped_files': $(printf '%s\n' "${UNMAPPED_FILES[@]+"${UNMAPPED_FILES[@]}"}" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo '[]'),
    'no_changes': False,
    'changed_files_count': $(echo "$CHANGED_FILES" | wc -l | tr -d ' ')
}
print(json.dumps(result, indent=2))
"
```

---

## Fix 2: Test Runner Gate (`.claude/scripts/test-gate.sh`)

### Problem

We need a single entry point that takes a worktree path, runs the mapped tests with a timeout, captures structured output (pass/fail counts, failure messages), and returns an exit code that cleanup.sh can gate on. The runner must handle both Python (pytest) and JavaScript (vitest) test suites, aggregate results, and produce a machine-readable report for bead creation on failure.

### Solution

```bash
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
```

---

## Fix 3: Integration into `cleanup.sh`

### Problem

The existing cleanup.sh performs ownership and bead checks before merging an agent's worktree back to main, but has no automated testing step. We need to insert the test gate between the pre-merge checks and the actual `git merge`, with support for a `--skip-tests` emergency flag and automatic bead creation on failure.

### Solution

The following shows the **test gate section** to be inserted into cleanup.sh. It slots in after the existing ownership/bead gates and before the merge operation.

```bash
# =============================================================================
# cleanup.sh — Test Gate Section
#
# Insert this block AFTER the KG ownership check and bead closure check,
# and BEFORE the flock merge lock and `git merge` command.
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# Parse --skip-tests flag (add to the argument parsing section at top)
# ─────────────────────────────────────────────────────────────────────────────
SKIP_TESTS=false
# Add to the existing while/case argument parser:
#   --skip-tests)
#     SKIP_TESTS=true
#     shift
#     ;;

# ─────────────────────────────────────────────────────────────────────────────
# Gate 3: Automated Test Gate
# ─────────────────────────────────────────────────────────────────────────────
run_test_gate() {
  local agent_name="$1"
  local worktree="$2"
  local base_branch="${3:-main}"

  echo ""
  echo "=== Gate 3: Test Gate ==="
  echo ""

  # ── Emergency skip ──────────────────────────────────────────────────────
  if [ "$SKIP_TESTS" = true ]; then
    echo "WARNING: --skip-tests flag set. Bypassing test gate."
    echo "  This will be logged. Use only for production emergencies."

    # Log the skip as a warning in the bead trail
    if command -v bd &>/dev/null; then
      bd create "TEST-SKIP: ${agent_name} merged without tests (--skip-tests)" \
        --template warning \
        --priority 2 \
        --tag "test-skip" \
        --tag "$agent_name" 2>/dev/null || true
    fi

    # Also log to a persistent file for audit
    local skip_log="${REPO_ROOT:-.}/.test-gate-skips.log"
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) agent=$agent_name worktree=$worktree reason=--skip-tests" \
      >> "$skip_log"

    echo "WARNING logged. Proceeding with merge."
    return 0
  fi

  # ── Run the test gate ───────────────────────────────────────────────────
  local test_gate_script
  test_gate_script="$(cd "$(dirname "$0")" && pwd)/test-gate.sh"

  if [ ! -f "$test_gate_script" ]; then
    echo "WARNING: test-gate.sh not found at $test_gate_script"
    echo "  Skipping test gate (infrastructure not set up)."
    echo "  This is expected during initial Phase 3b rollout."
    return 0
  fi

  if [ ! -x "$test_gate_script" ]; then
    chmod +x "$test_gate_script"
  fi

  local test_exit=0
  "$test_gate_script" "$worktree" --timeout 300 --base-branch "$base_branch" || test_exit=$?

  local result_file="$worktree/test-gate-result.json"

  case $test_exit in
    0)
      # ── Tests passed (or skipped/no tests) ──────────────────────────────
      echo "Test gate PASSED. Proceeding with merge."

      # Check for unmapped files and create "write tests" bead if needed
      if [ -f "$result_file" ] && command -v python3 &>/dev/null; then
        local unmapped
        unmapped="$(python3 -c "
import json
with open('$result_file') as f:
    r = json.load(f)
u = r.get('unmapped_files', [])
if u:
    print(' '.join(u))
" 2>/dev/null || echo "")"

        if [ -n "$unmapped" ]; then
          echo ""
          echo "NOTE: Creating 'write tests' bead for unmapped files."
          create_write_tests_bead "$agent_name" "$unmapped"
        fi
      fi

      return 0
      ;;

    1)
      # ── Tests failed ────────────────────────────────────────────────────
      echo ""
      echo "ERROR: Test gate FAILED. Merge blocked."
      echo ""

      # Create a "fix tests" bead with failure details
      create_fix_tests_bead "$agent_name" "$worktree" "$result_file"

      return 1
      ;;

    2)
      # ── Tests timed out ─────────────────────────────────────────────────
      echo ""
      echo "ERROR: Test gate TIMED OUT (300s). Merge blocked."
      echo ""

      create_fix_tests_bead "$agent_name" "$worktree" "$result_file"

      return 1
      ;;

    *)
      # ── Infrastructure error ────────────────────────────────────────────
      echo ""
      echo "WARNING: Test gate encountered an infrastructure error (exit=$test_exit)."
      echo "  This is NOT a test failure -- the test runner itself broke."
      echo "  Allowing merge but logging the error."

      if command -v bd &>/dev/null; then
        bd create "TEST-INFRA-ERROR: test-gate.sh exit=$test_exit for ${agent_name}" \
          --template warning \
          --priority 1 \
          --tag "test-infra" \
          --tag "$agent_name" 2>/dev/null || true
      fi

      return 0
      ;;
  esac
}

# ─────────────────────────────────────────────────────────────────────────────
# Create a "fix tests" bead when tests fail
# ─────────────────────────────────────────────────────────────────────────────
create_fix_tests_bead() {
  local agent_name="$1"
  local worktree="$2"
  local result_file="$3"

  if ! command -v bd &>/dev/null; then
    echo "WARNING: bd not found. Cannot create fix-tests bead."
    echo "  Install beads: https://github.com/steveyegge/beads"
    return 0
  fi

  # Extract failure details from result JSON
  local failure_summary=""
  local test_status=""
  local py_failed=0
  local js_failed=0

  if [ -f "$result_file" ] && command -v python3 &>/dev/null; then
    failure_summary="$(python3 -c "
import json
with open('$result_file') as f:
    r = json.load(f)
print(r.get('failure_summary', 'No failure details available.'))
" 2>/dev/null || echo "Failed to parse result file.")"

    test_status="$(python3 -c "
import json
with open('$result_file') as f:
    r = json.load(f)
print(r.get('status', 'unknown'))
" 2>/dev/null || echo "unknown")"

    py_failed="$(python3 -c "
import json
with open('$result_file') as f:
    r = json.load(f)
print(r.get('python', {}).get('failed', 0))
" 2>/dev/null || echo "0")"

    js_failed="$(python3 -c "
import json
with open('$result_file') as f:
    r = json.load(f)
print(r.get('javascript', {}).get('failed', 0))
" 2>/dev/null || echo "0")"
  fi

  # Get the list of changed files for context
  local changed_files
  changed_files="$(cd "$worktree" && git diff --name-only main...HEAD 2>/dev/null | head -20 || echo "unknown")"

  # Truncate failure summary to prevent overly large bead descriptions
  # bd has a practical limit on description size
  local truncated_summary
  truncated_summary="$(echo "$failure_summary" | head -60)"
  if [ "$(echo "$failure_summary" | wc -l)" -gt 60 ]; then
    truncated_summary="$truncated_summary
... (truncated, see $worktree/.test-gate-logs/ for full output)"
  fi

  local bead_title="FIX-TESTS: ${agent_name} -- ${test_status} (py:${py_failed} js:${js_failed} failures)"

  local bead_body="## Test Gate Failure

**Agent**: ${agent_name}
**Worktree**: ${worktree}
**Status**: ${test_status}
**Python failures**: ${py_failed}
**JS failures**: ${js_failed}

### Changed Files
\`\`\`
${changed_files}
\`\`\`

### Test Output
\`\`\`
${truncated_summary}
\`\`\`

### Instructions
1. Fix the failing tests in your worktree
2. Re-run: \`scripts/test-gate.sh ${worktree}\`
3. When green, retry: \`scripts/cleanup.sh ${agent_name} merge\`

### Full Logs
- \`${worktree}/.test-gate-logs/pytest-output.txt\`
- \`${worktree}/.test-gate-logs/vitest-output.txt\`
- \`${worktree}/test-gate-result.json\`"

  # Create the bead, assigned to the same agent
  local bead_id
  bead_id="$(bd create "$bead_title" \
    --priority 0 \
    --tag "fix-tests" \
    --tag "$agent_name" \
    --tag "auto-generated" 2>/dev/null | grep -oE 'BEAD-[0-9]+' | head -1 || echo "")"

  if [ -n "$bead_id" ]; then
    # Add the full description as a comment (bd create --body may not be available)
    echo "$bead_body" | bd comment "$bead_id" 2>/dev/null || true

    echo ""
    echo "Created bead: $bead_id"
    echo "  Title: $bead_title"
    echo "  Assigned to: $agent_name"
    echo ""
    echo "retry-agent.sh will pick this up and re-spawn the agent."

    # Write bead ID to a file so retry-agent.sh can find it
    echo "$bead_id" > "$worktree/.fix-tests-bead-id"
  else
    echo "WARNING: Failed to create bead. Dumping failure info to stdout:"
    echo "$bead_body"
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Create a "write tests" bead for unmapped files
# ─────────────────────────────────────────────────────────────────────────────
create_write_tests_bead() {
  local agent_name="$1"
  local unmapped_files="$2"

  if ! command -v bd &>/dev/null; then
    return 0
  fi

  local bead_title="WRITE-TESTS: Add test coverage for files modified by ${agent_name}"
  bd create "$bead_title" \
    --priority 3 \
    --tag "write-tests" \
    --tag "tech-debt" \
    --tag "$agent_name" 2>/dev/null || true

  echo "  Created 'write tests' bead for: $unmapped_files"
}

# ─────────────────────────────────────────────────────────────────────────────
# Integration point: call run_test_gate in the merge flow
# ─────────────────────────────────────────────────────────────────────────────
# In the main merge flow of cleanup.sh, after Gate 1 (KG ownership) and
# Gate 2 (bead closure), add:
#
#   # Gate 3: Test Gate
#   if ! run_test_gate "$AGENT_NAME" "$AGENT_WORKTREE" "$BASE_BRANCH"; then
#     echo "Merge blocked by test gate. Fix tests and retry."
#     exit 1
#   fi
#
#   # Gate 4: Flock merge lock (existing)
#   ...
#   git merge ...
```

---

## Fix 4: Retry Agent Script (`.claude/scripts/retry-agent.sh`)

### Problem

When tests fail and a "fix tests" bead is created, we need a mechanism to automatically re-spawn the agent with the test failure context. The agent needs to know: (a) which tests failed, (b) what the error output was, and (c) which files it originally changed. This script bridges the test gate failure to the agent re-spawn cycle.

### Solution

```bash
#!/usr/bin/env bash
# =============================================================================
# scripts/retry-agent.sh -- Re-spawn an agent to fix test failures
#
# Usage: retry-agent.sh <agent-name> [--bead <bead-id>]
#
# Reads the fix-tests bead, extracts failure context, and calls spawn.sh
# with the test failure injected into the agent's initial prompt.
# =============================================================================

set -euo pipefail

AGENT_NAME="${1:?Usage: retry-agent.sh <agent-name> [--bead <bead-id>]}"
BEAD_ID=""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Parse optional --bead flag
shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bead)
      BEAD_ID="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

# ─────────────────────────────────────────────────────────────────────────────
# 1. Find the fix-tests bead
# ─────────────────────────────────────────────────────────────────────────────
if [ -z "$BEAD_ID" ]; then
  # Check if the agent's worktree has a .fix-tests-bead-id file
  AGENT_WORKTREE="$HOME/agents/$AGENT_NAME"
  if [ -f "$AGENT_WORKTREE/.fix-tests-bead-id" ]; then
    BEAD_ID="$(cat "$AGENT_WORKTREE/.fix-tests-bead-id")"
    echo "Found bead ID from worktree: $BEAD_ID"
  else
    # Search for open fix-tests beads assigned to this agent
    if command -v bd &>/dev/null; then
      BEAD_ID="$(bd search "FIX-TESTS: $AGENT_NAME" --status open --limit 1 2>/dev/null \
        | grep -oE 'BEAD-[0-9]+' | head -1 || echo "")"
    fi
  fi
fi

if [ -z "$BEAD_ID" ]; then
  echo "ERROR: No fix-tests bead found for agent '$AGENT_NAME'."
  echo "  Specify one with: retry-agent.sh $AGENT_NAME --bead BEAD-123"
  exit 1
fi

echo "=== Retry Agent: $AGENT_NAME ==="
echo "Bead: $BEAD_ID"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 2. Extract failure context from bead
# ─────────────────────────────────────────────────────────────────────────────
BEAD_CONTENT=""
if command -v bd &>/dev/null; then
  BEAD_CONTENT="$(bd show "$BEAD_ID" 2>/dev/null || echo "")"
fi

# Also grab the test-gate-result.json if the worktree still exists
AGENT_WORKTREE="$HOME/agents/$AGENT_NAME"
TEST_RESULT=""
if [ -f "$AGENT_WORKTREE/test-gate-result.json" ]; then
  TEST_RESULT="$(cat "$AGENT_WORKTREE/test-gate-result.json")"
fi

# Read full test output logs if available
PYTEST_LOG=""
VITEST_LOG=""
if [ -f "$AGENT_WORKTREE/.test-gate-logs/pytest-output.txt" ]; then
  PYTEST_LOG="$(tail -100 "$AGENT_WORKTREE/.test-gate-logs/pytest-output.txt")"
fi
if [ -f "$AGENT_WORKTREE/.test-gate-logs/vitest-output.txt" ]; then
  VITEST_LOG="$(tail -100 "$AGENT_WORKTREE/.test-gate-logs/vitest-output.txt")"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 3. Build the retry prompt
# ─────────────────────────────────────────────────────────────────────────────
RETRY_PROMPT="You are being re-spawned to fix test failures from your previous work session.

## Bead: $BEAD_ID
$BEAD_CONTENT

## Test Gate Result
\`\`\`json
$TEST_RESULT
\`\`\`

## Pytest Output (last 100 lines)
\`\`\`
$PYTEST_LOG
\`\`\`

## Vitest Output (last 100 lines)
\`\`\`
$VITEST_LOG
\`\`\`

## Your Task
1. Read the test failures above carefully
2. Fix the code in your worktree so all tests pass
3. Run the tests locally: scripts/test-gate.sh $AGENT_WORKTREE
4. Once green, close the bead: bd close $BEAD_ID --reason \"Tests fixed\"
5. The orchestrator will re-run cleanup.sh to merge your work

IMPORTANT: Do NOT rewrite or delete the failing tests to make them pass.
Fix the source code that the tests are validating."

# ─────────────────────────────────────────────────────────────────────────────
# 4. Re-spawn the agent
# ─────────────────────────────────────────────────────────────────────────────
SPAWN_SCRIPT="$SCRIPT_DIR/spawn.sh"

if [ ! -f "$SPAWN_SCRIPT" ]; then
  echo "ERROR: spawn.sh not found at $SPAWN_SCRIPT"
  echo "  Cannot re-spawn agent. Manual intervention required."
  echo ""
  echo "Manual steps:"
  echo "  1. cd $AGENT_WORKTREE"
  echo "  2. Fix the failing tests (see bead $BEAD_ID)"
  echo "  3. scripts/test-gate.sh $AGENT_WORKTREE"
  echo "  4. scripts/cleanup.sh $AGENT_NAME merge"
  exit 1
fi

echo "Re-spawning agent '$AGENT_NAME' with test failure context..."
echo ""

# spawn.sh creates a worktree and launches Claude Code.
# If the worktree already exists (from the failed attempt), spawn.sh
# should detect this and reuse it rather than creating a new one.
# We pass the retry prompt via --prompt or --context flag (spawn.sh must support this).
"$SPAWN_SCRIPT" "$AGENT_NAME" \
  --reuse-worktree \
  --bead "$BEAD_ID" \
  --prompt "$RETRY_PROMPT"

echo ""
echo "Agent '$AGENT_NAME' re-spawned. Monitoring for bead closure..."
```

---

## Fix 5: Static Test Mapping Config (`config/test-mapping.json`)

### Problem

Convention-based test discovery works for most files, but some source files have non-obvious test file relationships (e.g., `src/api/users.py` is tested by both `tests/test_api_e2e.py` and `tests/test_api_integration.py`). A static override file lets us handle these edge cases without complicating the heuristic logic.

### Solution

```json
{
  "_comment": "Static overrides for test-map.sh. Maps source files to their test files.",
  "_format": "Keys are source file paths (relative to repo root). Values are arrays of test file paths.",
  "_precedence": "These overrides are checked FIRST, before convention-based discovery.",
  "overrides": {
    "src/api/users.py": [
      "tests/test_api_e2e.py",
      "tests/test_api_integration.py"
    ],
    "src/api/capsules.py": [
      "scripts/test_approval.py",
      "scripts/test_integration.py"
    ],
    "src/api/policies.py": [
      "scripts/test_integration.py"
    ],
    "src/context_packager.py": [
      "tests/test_api_e2e.py"
    ],
    "src/session_manager.py": [
      "tests/test_api_e2e.py"
    ],
    "src/capsule_validator.py": [
      "scripts/test_approval.py"
    ],
    "src/approval_router.py": [
      "scripts/test_approval.py"
    ],
    "src/policy_engine.py": [
      "scripts/test_integration.py"
    ],
    "ui/src/app/agent/page.tsx": [
      "ui:npm test"
    ],
    "ui/src/app/agent-v2/page.tsx": [
      "ui:npm test"
    ],
    "ui/src/app/users/page.tsx": [
      "ui:npm test"
    ],
    "ui/src/app/capsules/page.tsx": [
      "ui:npm test"
    ],
    "ui/src/app/approvals/page.tsx": [
      "ui:npm test"
    ]
  },
  "ignore_patterns": [
    "*.md",
    "*.txt",
    "*.png",
    "*.jpg",
    "*.svg",
    ".claude/**",
    "docs/**",
    "capsules/**",
    "sessions/**",
    ".beads/**",
    "scripts/screenshots/**"
  ]
}
```

---

## Fix 6: spawn.sh Modifications for Retry Support

### Problem

When retry-agent.sh re-spawns an agent to fix test failures, spawn.sh needs to accept additional flags: `--reuse-worktree` (don't create a new worktree if one exists), `--bead` (the bead ID to work on), and `--prompt` (inject test failure context into the agent's initial prompt).

### Solution

Add these to spawn.sh's argument parser and agent launch logic:

```bash
# =============================================================================
# spawn.sh additions for retry support
# =============================================================================

# ─── Add to argument parser ──────────────────────────────────────────────────
REUSE_WORKTREE=false
RETRY_BEAD=""
RETRY_PROMPT=""

# In the while/case block:
#   --reuse-worktree)
#     REUSE_WORKTREE=true
#     shift
#     ;;
#   --bead)
#     RETRY_BEAD="$2"
#     shift 2
#     ;;
#   --prompt)
#     RETRY_PROMPT="$2"
#     shift 2
#     ;;

# ─── Modify worktree creation ────────────────────────────────────────────────
# Replace the existing worktree creation with:

AGENT_WORKTREE="$HOME/agents/$AGENT_NAME"

if [ -d "$AGENT_WORKTREE" ]; then
  if [ "$REUSE_WORKTREE" = true ]; then
    echo "Reusing existing worktree: $AGENT_WORKTREE"
    cd "$AGENT_WORKTREE"
  else
    echo "ERROR: Worktree already exists at $AGENT_WORKTREE"
    echo "  Use --reuse-worktree to reuse it, or remove it first."
    exit 1
  fi
else
  echo "Creating worktree: $AGENT_WORKTREE"
  git worktree add "$AGENT_WORKTREE" -b "agent/$AGENT_NAME" 2>/dev/null \
    || git worktree add "$AGENT_WORKTREE" "agent/$AGENT_NAME"
  cd "$AGENT_WORKTREE"
fi

# ─── Inject retry context into agent prompt ──────────────────────────────────
# When launching Claude Code, pass the retry prompt as initial context:

INITIAL_PROMPT=""
if [ -n "$RETRY_PROMPT" ]; then
  # Write retry context to a temp file the agent can read
  RETRY_CONTEXT_FILE="$AGENT_WORKTREE/.retry-context.md"
  echo "$RETRY_PROMPT" > "$RETRY_CONTEXT_FILE"

  INITIAL_PROMPT="Read .retry-context.md for your task. You are fixing test failures from a previous session. Bead: $RETRY_BEAD"
fi

# Launch Claude Code with or without retry context
if [ -n "$INITIAL_PROMPT" ]; then
  claude --prompt "$INITIAL_PROMPT" \
    --worktree "$AGENT_WORKTREE" \
    --agent-name "$AGENT_NAME"
else
  claude --worktree "$AGENT_WORKTREE" \
    --agent-name "$AGENT_NAME"
fi
```

---

## Complete cleanup.sh Integration

This shows the full gate ordering in cleanup.sh, with the test gate in position:

```bash
#!/usr/bin/env bash
# =============================================================================
# scripts/cleanup.sh — Merge agent worktree back to main
#
# Usage: cleanup.sh <agent-name> merge [--skip-tests]
#        cleanup.sh <agent-name> discard
#
# Gates (all must pass for merge):
#   1. KG ownership check — agent only modified files it owns
#   2. Bead closure check — agent's bead is marked closed/resolved
#   3. Test gate — affected tests pass in the agent's worktree
#   4. Flock merge lock — serializes concurrent merges
# =============================================================================

set -euo pipefail

AGENT_NAME="${1:?Usage: cleanup.sh <agent-name> <merge|discard> [--skip-tests]}"
ACTION="${2:?Usage: cleanup.sh <agent-name> <merge|discard> [--skip-tests]}"
SKIP_TESTS=false

shift 2
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests)
      SKIP_TESTS=true
      shift
      ;;
    *)
      echo "Unknown flag: $1"
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_WORKTREE="$HOME/agents/$AGENT_NAME"
BASE_BRANCH="main"
LOCKFILE="/tmp/baap-merge.lock"

# Source helper functions (test gate, bead creation, etc.)
# These are defined in the sections above and would be in this file.

# ─── Discard path ────────────────────────────────────────────────────────────
if [ "$ACTION" = "discard" ]; then
  echo "Discarding worktree for agent: $AGENT_NAME"
  cd "$REPO_ROOT"
  git worktree remove "$AGENT_WORKTREE" --force 2>/dev/null || true
  git branch -D "agent/$AGENT_NAME" 2>/dev/null || true
  echo "Done. Worktree and branch removed."
  exit 0
fi

# ─── Merge path ──────────────────────────────────────────────────────────────
if [ "$ACTION" != "merge" ]; then
  echo "Unknown action: $ACTION (expected 'merge' or 'discard')"
  exit 1
fi

echo "=== Cleanup: Merging $AGENT_NAME ==="
echo "Worktree: $AGENT_WORKTREE"
echo "Target:   $BASE_BRANCH"
echo ""

# Verify worktree exists
if [ ! -d "$AGENT_WORKTREE" ]; then
  echo "ERROR: Worktree not found at $AGENT_WORKTREE"
  exit 1
fi

# ─── Gate 1: KG Ownership Check ─────────────────────────────────────────────
echo "=== Gate 1: KG Ownership Check ==="
# (Existing implementation — verify agent only touched files it owns)
# check_kg_ownership "$AGENT_NAME" "$AGENT_WORKTREE" || exit 1
echo "Gate 1: PASSED (ownership verified)"
echo ""

# ─── Gate 2: Bead Closure Check ─────────────────────────────────────────────
echo "=== Gate 2: Bead Closure Check ==="
# (Existing implementation — verify the agent's task bead is closed)
# check_bead_closure "$AGENT_NAME" || exit 1
echo "Gate 2: PASSED (bead closed)"
echo ""

# ─── Gate 3: Test Gate ───────────────────────────────────────────────────────
# This is the new gate added by Phase 3b.
# run_test_gate is defined in the "Fix 3" section above.
# It calls test-gate.sh, handles --skip-tests, and creates beads on failure.

if ! run_test_gate "$AGENT_NAME" "$AGENT_WORKTREE" "$BASE_BRANCH"; then
  echo ""
  echo "MERGE BLOCKED: Test gate failed."
  echo "  Fix the failing tests in $AGENT_WORKTREE"
  echo "  Then retry: $0 $AGENT_NAME merge"
  echo ""
  echo "  Or to bypass (emergency only): $0 $AGENT_NAME merge --skip-tests"
  exit 1
fi
echo ""

# ─── Gate 4: Flock Merge Lock ───────────────────────────────────────────────
echo "=== Gate 4: Merge Lock ==="
(
  # Acquire exclusive lock to prevent concurrent merges
  flock -w 60 200 || {
    echo "ERROR: Could not acquire merge lock within 60s."
    echo "  Another merge is in progress. Retry in a moment."
    exit 1
  }

  echo "Lock acquired. Performing merge..."

  cd "$REPO_ROOT"
  git checkout "$BASE_BRANCH"

  # Merge with a descriptive message
  git merge "agent/$AGENT_NAME" \
    --no-ff \
    -m "Merge agent/$AGENT_NAME: $(cd "$AGENT_WORKTREE" && git log --oneline -1 --format='%s')"

  MERGE_EXIT=$?

  if [ $MERGE_EXIT -ne 0 ]; then
    echo "ERROR: Git merge failed. Resolve conflicts manually."
    echo "  cd $REPO_ROOT"
    echo "  git merge agent/$AGENT_NAME"
    exit 1
  fi

  echo "Merge successful."

) 200>"$LOCKFILE"

# ─── Cleanup ────────────────────────────────────────────────────────────────
echo ""
echo "=== Cleanup ==="

# Remove the worktree
cd "$REPO_ROOT"
git worktree remove "$AGENT_WORKTREE" 2>/dev/null || true

# Delete the agent branch
git branch -d "agent/$AGENT_NAME" 2>/dev/null || true

# Clean up test artifacts
rm -f "$LOCKFILE"

echo ""
echo "=== Done ==="
echo "Agent $AGENT_NAME merged to $BASE_BRANCH and worktree cleaned up."
```

---

## Success Criteria

- [ ] `test-map.sh` correctly maps `src/api/capsules.py` to `scripts/test_approval.py` and `scripts/test_integration.py` via static override
- [ ] `test-map.sh` correctly maps `src/session_manager.py` to `tests/test_api_e2e.py` via convention-based discovery when no static override exists
- [ ] `test-map.sh` returns `no_changes: true` when the agent branch has no diff from main
- [ ] `test-map.sh` classifies `ui/src/app/agent/page.tsx` as a JS change and includes it in `js_tests`
- [ ] `test-gate.sh` exits 0 when all mapped tests pass
- [ ] `test-gate.sh` exits 1 when any pytest test fails, and the result JSON contains the failure summary
- [ ] `test-gate.sh` exits 2 when tests exceed the 5-minute timeout
- [ ] `test-gate.sh` exits 0 with `status: skipped` when no test files are found (unmapped files only)
- [ ] `cleanup.sh` blocks merge when `test-gate.sh` returns exit 1
- [ ] `cleanup.sh` creates a "fix tests" bead with the failure output when tests fail
- [ ] `cleanup.sh` allows merge with `--skip-tests` flag and logs a warning bead
- [ ] `cleanup.sh` creates a "write tests" bead when unmapped files are detected but merge still proceeds
- [ ] `retry-agent.sh` finds the fix-tests bead and re-spawns the agent with test failure context
- [ ] `retry-agent.sh` passes `--reuse-worktree` to spawn.sh so the agent continues in the same worktree
- [ ] End-to-end: agent changes `src/api/capsules.py` with a bug -> `cleanup.sh merge` -> test gate fails -> bead created -> `retry-agent.sh` re-spawns -> agent fixes -> `cleanup.sh merge` -> tests pass -> merged
- [ ] Static override in `config/test-mapping.json` takes precedence over convention-based discovery
- [ ] Python dependency file changes (`requirements.txt`) trigger a full test suite run

## Verification

```bash
# ─── Unit: test-map.sh produces correct output ──────────────────────────────
# Set up a mock worktree with known changes
MOCK_WT=$(mktemp -d)
cd "$MOCK_WT"
git init && git commit --allow-empty -m "init"
git checkout -b agent/test-mapper
mkdir -p src/api
echo "# changed" > src/api/capsules.py
git add . && git commit -m "change capsules"

# Run test-map.sh and verify output
scripts/test-map.sh "$MOCK_WT" main
# Expected: python_tests includes scripts/test_approval.py, scripts/test_integration.py

# ─── Unit: test-gate.sh handles missing pytest gracefully ────────────────────
# In an env without pytest:
PATH=/usr/bin scripts/test-gate.sh "$MOCK_WT"
# Expected: exit 0, status=skipped (pytest not found)

# ─── Integration: cleanup.sh blocks on test failure ─────────────────────────
# Create a worktree with a deliberately broken test
cd ~/agents/test-agent
echo "def test_broken(): assert False" > tests/test_broken.py
git add . && git commit -m "break tests"

scripts/cleanup.sh test-agent merge
# Expected: exit 1, "MERGE BLOCKED: Test gate failed."
# Expected: bd search "FIX-TESTS: test-agent" returns a bead

# ─── Integration: --skip-tests bypasses the gate ────────────────────────────
scripts/cleanup.sh test-agent merge --skip-tests
# Expected: exit 0, WARNING logged, skip bead created
# Expected: bd search "TEST-SKIP: test-agent" returns a bead

# ─── Integration: retry-agent.sh re-spawns ──────────────────────────────────
scripts/retry-agent.sh test-agent
# Expected: finds the FIX-TESTS bead, writes .retry-context.md, calls spawn.sh

# ─── End-to-end: full failure-fix-merge cycle ────────────────────────────────
# 1. Agent modifies src/api/capsules.py (introduces a bug)
# 2. cleanup.sh test-agent merge → BLOCKED
# 3. Bead BEAD-xxx created with test output
# 4. retry-agent.sh test-agent → agent re-spawned
# 5. Agent reads .retry-context.md, fixes the bug
# 6. cleanup.sh test-agent merge → PASSED, merged to main

# ─── Verify no unmapped file regression ──────────────────────────────────────
# Modify a file with no tests:
cd ~/agents/test-agent
echo "# new" > src/learning/new_module.py
git add . && git commit -m "add new module"
scripts/cleanup.sh test-agent merge
# Expected: merge succeeds, "write tests" bead created for src/learning/new_module.py

# ─── Timeout verification ───────────────────────────────────────────────────
# Create a test that hangs:
echo "import time; time.sleep(600)
def test_hang(): pass" > tests/test_slow.py
scripts/test-gate.sh "$MOCK_WT" --timeout 5
# Expected: exit 2, status=timeout after 5 seconds
```
