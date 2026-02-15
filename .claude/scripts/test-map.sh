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
