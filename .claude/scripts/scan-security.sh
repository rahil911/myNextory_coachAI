#!/usr/bin/env bash
# scan-security.sh -- Security scanner for Baap agent merge gate
#
# Scans a git diff (or directory) for security issues:
#   - Hardcoded secrets (API keys, passwords, private keys)
#   - SQL injection patterns (raw string formatting in queries)
#   - XSS vectors (dangerouslySetInnerHTML, eval, innerHTML)
#   - Dependency issues (new deps without lockfile, known vulnerable packages)
#
# Usage:
#   scan-security.sh --diff <base_branch> <head_branch>   # Scan diff between branches
#   scan-security.sh --file <path>                         # Scan a single file
#   scan-security.sh --dir <path>                          # Scan a directory recursively
#   scan-security.sh --staged                              # Scan staged changes (git diff --cached)
#
# Exit codes:
#   0 = clean (no issues or INFO only)
#   1 = CRITICAL issues found (merge must be blocked)
#   2 = WARNING issues found (merge allowed, review needed)
#
# Environment:
#   SECURITY_SCAN_STRICT=1    Treat WARNINGs as CRITICALs (block on everything)
#   SECURITY_SCAN_QUIET=1     Suppress INFO-level output

set -euo pipefail

# ── Color output ─────────────────────────────────────────────────────────────
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

# ── Counters ─────────────────────────────────────────────────────────────────
CRITICAL_COUNT=0
WARNING_COUNT=0
INFO_COUNT=0

# ── Result collection ────────────────────────────────────────────────────────
FINDINGS=""

record_finding() {
  local severity="$1"
  local category="$2"
  local file="$3"
  local line_num="${4:-0}"
  local detail="$5"

  case "$severity" in
    CRITICAL) CRITICAL_COUNT=$((CRITICAL_COUNT + 1)); COLOR="$RED" ;;
    WARNING)  WARNING_COUNT=$((WARNING_COUNT + 1));   COLOR="$YELLOW" ;;
    INFO)     INFO_COUNT=$((INFO_COUNT + 1));         COLOR="$BLUE" ;;
    *)        COLOR="$NC" ;;
  esac

  FINDINGS="${FINDINGS}${severity}|${category}|${file}|${line_num}|${detail}\n"

  if [ "$severity" = "INFO" ] && [ "${SECURITY_SCAN_QUIET:-0}" = "1" ]; then
    return
  fi

  printf "${COLOR}[%s]${NC} %s: ${BOLD}%s${NC}:%s -- %s\n" \
    "$severity" "$category" "$file" "$line_num" "$detail"
}

# ── Get diff content ─────────────────────────────────────────────────────────
# Returns the content to scan, one way or another.

SCAN_MODE=""
DIFF_CONTENT=""
SCAN_FILES=()

parse_args() {
  case "${1:-}" in
    --diff)
      SCAN_MODE="diff"
      BASE_BRANCH="${2:?Usage: scan-security.sh --diff <base> <head>}"
      HEAD_BRANCH="${3:?Usage: scan-security.sh --diff <base> <head>}"
      DIFF_CONTENT="$(git diff "$BASE_BRANCH...$HEAD_BRANCH" 2>/dev/null || git diff "$BASE_BRANCH..$HEAD_BRANCH" 2>/dev/null)"
      # Also get list of changed files for targeted scanning
      mapfile -t SCAN_FILES < <(git diff --name-only "$BASE_BRANCH...$HEAD_BRANCH" 2>/dev/null || git diff --name-only "$BASE_BRANCH..$HEAD_BRANCH" 2>/dev/null)
      ;;
    --staged)
      SCAN_MODE="staged"
      DIFF_CONTENT="$(git diff --cached)"
      mapfile -t SCAN_FILES < <(git diff --cached --name-only)
      ;;
    --file)
      SCAN_MODE="file"
      local target="${2:?Usage: scan-security.sh --file <path>}"
      [ -f "$target" ] || { echo "ERROR: File not found: $target" >&2; exit 1; }
      DIFF_CONTENT="$(cat "$target")"
      SCAN_FILES=("$target")
      ;;
    --dir)
      SCAN_MODE="dir"
      local target="${2:?Usage: scan-security.sh --dir <path>}"
      [ -d "$target" ] || { echo "ERROR: Directory not found: $target" >&2; exit 1; }
      mapfile -t SCAN_FILES < <(find "$target" -type f \
        \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \
           -o -name "*.json" -o -name "*.yaml" -o -name "*.yml" -o -name "*.toml" \
           -o -name "*.sh" -o -name "*.env" -o -name "*.env.*" \) \
        ! -path "*/node_modules/*" ! -path "*/.venv/*" ! -path "*/__pycache__/*" \
        ! -path "*/.git/*" ! -path "*/dist/*" ! -path "*/.next/*" 2>/dev/null)
      # Concatenate all files for pattern scanning
      DIFF_CONTENT=""
      for f in "${SCAN_FILES[@]}"; do
        DIFF_CONTENT="${DIFF_CONTENT}$(cat "$f" 2>/dev/null)"$'\n'
      done
      ;;
    *)
      echo "Usage: scan-security.sh <--diff base head | --staged | --file path | --dir path>"
      exit 1
      ;;
  esac
}

# ── Scan 1: Secret Detection ────────────────────────────────────────────────
#
# Grep the diff for patterns that indicate hardcoded secrets.
# Only scan added lines (lines starting with + in diffs, or all lines in file/dir mode).

scan_secrets() {
  echo ""
  echo "${BOLD}=== Secret Detection ===${NC}"

  local content="$1"

  if [ -z "$content" ]; then
    echo "  (no content to scan)"
    return
  fi

  # For diff mode, extract only added lines (+ prefix, not +++ file headers)
  local scan_text="$content"
  if [ "$SCAN_MODE" = "diff" ] || [ "$SCAN_MODE" = "staged" ]; then
    scan_text="$(echo "$content" | grep '^+' | grep -v '^+++' || true)"
  fi

  if [ -z "$scan_text" ]; then
    echo "  (no added lines to scan)"
    return
  fi

  # -- Pattern: AWS Access Key IDs --
  local aws_keys
  aws_keys="$(echo "$scan_text" | grep -nE 'AKIA[0-9A-Z]{16}' || true)"
  if [ -n "$aws_keys" ]; then
    while IFS= read -r match; do
      local lnum file_ctx
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SECRET" "(diff)" "$lnum" "AWS Access Key ID (AKIA...) found"
    done <<< "$aws_keys"
  fi

  # -- Pattern: Generic API key assignment --
  # Matches: api_key = "...", api_key="...", API_KEY = '...'
  # Excludes: api_key = os.environ, api_key = config., api_key = ""
  local api_keys
  api_keys="$(echo "$scan_text" | grep -niE 'api[_-]?key\s*[=:]\s*["\x27][a-zA-Z0-9_\-]{8,}' || true)"
  if [ -n "$api_keys" ]; then
    while IFS= read -r match; do
      # Skip if it's a config/env lookup pattern
      if echo "$match" | grep -qiE '(os\.environ|config\.|getenv|process\.env|settings\.|\.get\()'; then
        continue
      fi
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SECRET" "(diff)" "$lnum" "Hardcoded API key assignment: $(echo "$match" | head -c 120)"
    done <<< "$api_keys"
  fi

  # -- Pattern: Stripe keys --
  local stripe_keys
  stripe_keys="$(echo "$scan_text" | grep -nE '(sk_live_|pk_live_|sk_test_|rk_live_)[a-zA-Z0-9]{20,}' || true)"
  if [ -n "$stripe_keys" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SECRET" "(diff)" "$lnum" "Stripe key found: $(echo "$match" | head -c 80)"
    done <<< "$stripe_keys"
  fi

  # -- Pattern: GitHub personal access tokens --
  local gh_tokens
  gh_tokens="$(echo "$scan_text" | grep -nE '(ghp_|gho_|ghu_|ghs_|ghr_)[a-zA-Z0-9]{36,}' || true)"
  if [ -n "$gh_tokens" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SECRET" "(diff)" "$lnum" "GitHub token found: $(echo "$match" | head -c 80)"
    done <<< "$gh_tokens"
  fi

  # -- Pattern: OpenAI / Anthropic API keys --
  local ai_keys
  ai_keys="$(echo "$scan_text" | grep -nE '(sk-[a-zA-Z0-9]{32,}|sk-ant-[a-zA-Z0-9\-]{32,})' || true)"
  if [ -n "$ai_keys" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SECRET" "(diff)" "$lnum" "AI provider API key found: $(echo "$match" | head -c 80)"
    done <<< "$ai_keys"
  fi

  # -- Pattern: Hardcoded password assignment --
  # Matches: password = "...", password="...", PASSWORD: "..."
  # Excludes: test files, empty strings, variable references
  local passwords
  passwords="$(echo "$scan_text" | grep -niE 'password\s*[=:]\s*["\x27][^"\x27]{4,}' || true)"
  if [ -n "$passwords" ]; then
    while IFS= read -r match; do
      # Skip test files
      if echo "$match" | grep -qiE '(test_|_test\.|spec\.|\.test\.|mock|fixture|fake|example|placeholder)'; then
        continue
      fi
      # Skip env/config lookups
      if echo "$match" | grep -qiE '(os\.environ|config\.|getenv|process\.env|settings\.|\.get\()'; then
        continue
      fi
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SECRET" "(diff)" "$lnum" "Hardcoded password: $(echo "$match" | head -c 120)"
    done <<< "$passwords"
  fi

  # -- Pattern: Private keys --
  local privkeys
  privkeys="$(echo "$scan_text" | grep -nE 'BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY' || true)"
  if [ -n "$privkeys" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SECRET" "(diff)" "$lnum" "Private key found in source"
    done <<< "$privkeys"
  fi

  # -- Pattern: Connection strings with embedded passwords --
  # Matches: mysql://user:pass@host, postgresql://user:pass@host, redis://:pass@host
  local connstrings
  connstrings="$(echo "$scan_text" | grep -nE '(mysql|postgres(ql)?|redis|mongodb|amqp|mariadb)://[^:]+:[^@\s]+@' || true)"
  if [ -n "$connstrings" ]; then
    while IFS= read -r match; do
      # Skip if the password part is an env variable reference
      if echo "$match" | grep -qiE '(\$\{|\$[A-Z_]|%[A-Z_]|os\.environ|getenv)'; then
        continue
      fi
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SECRET" "(diff)" "$lnum" "Connection string with embedded password: $(echo "$match" | sed 's/:[^@]*@/:***@/' | head -c 120)"
    done <<< "$connstrings"
  fi

  # -- Pattern: .env files in the diff --
  if [ "$SCAN_MODE" = "diff" ] || [ "$SCAN_MODE" = "staged" ]; then
    local envfiles
    envfiles="$(echo "$content" | grep -E '^\+\+\+ b/.*\.env' | sed 's|^+++ b/||' || true)"
    if [ -n "$envfiles" ]; then
      while IFS= read -r envfile; do
        # .env.example and .env.template are OK
        if echo "$envfile" | grep -qE '\.(example|template|sample)$'; then
          record_finding "INFO" "SECRET" "$envfile" "0" ".env template file (OK if no real values)"
        else
          record_finding "CRITICAL" "SECRET" "$envfile" "0" ".env file committed -- secrets will be in git history"
        fi
      done <<< "$envfiles"
    fi
  fi

  # -- Pattern: credentials.json being committed --
  if [ "$SCAN_MODE" = "diff" ] || [ "$SCAN_MODE" = "staged" ]; then
    local credfiles
    credfiles="$(echo "$content" | grep -E '^\+\+\+ b/.*credentials\.json' | sed 's|^+++ b/||' || true)"
    if [ -n "$credfiles" ]; then
      while IFS= read -r credfile; do
        record_finding "CRITICAL" "SECRET" "$credfile" "0" "credentials.json committed -- must remain gitignored"
      done <<< "$credfiles"
    fi
  fi
}

# ── Scan 2: SQL Injection ───────────────────────────────────────────────────
#
# Look for raw string formatting in SQL queries (Python f-strings, concatenation).
# This stack uses FastAPI + SQLAlchemy/MariaDB, so parameterized queries or ORM
# should be the norm.

scan_sql_injection() {
  echo ""
  echo "${BOLD}=== SQL Injection Scan ===${NC}"

  # Only scan Python files
  local py_content=""

  if [ "$SCAN_MODE" = "diff" ] || [ "$SCAN_MODE" = "staged" ]; then
    # Extract added lines from Python file sections of the diff
    local in_python=0
    while IFS= read -r line; do
      if echo "$line" | grep -qE '^\+\+\+ b/.*\.py$'; then
        in_python=1
        continue
      elif echo "$line" | grep -qE '^\+\+\+ b/'; then
        in_python=0
        continue
      fi
      if [ "$in_python" -eq 1 ] && echo "$line" | grep -q '^+' && ! echo "$line" | grep -q '^+++'; then
        py_content="${py_content}${line}"$'\n'
      fi
    done <<< "$DIFF_CONTENT"
  else
    # File/dir mode: read Python files directly
    for f in "${SCAN_FILES[@]}"; do
      if echo "$f" | grep -qE '\.py$'; then
        py_content="${py_content}$(cat "$f" 2>/dev/null)"$'\n'
      fi
    done
  fi

  if [ -z "$py_content" ]; then
    echo "  (no Python content to scan)"
    return
  fi

  # -- Pattern: f-string SQL queries --
  # f"SELECT ... {variable}", f"INSERT ... {", f"UPDATE ... {", f"DELETE ... {"
  local fsql
  fsql="$(echo "$py_content" | grep -niE 'f"(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\s.*\{' || true)"
  if [ -n "$fsql" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SQL_INJECTION" "(python)" "$lnum" "f-string SQL query: $(echo "$match" | head -c 120)"
    done <<< "$fsql"
  fi

  # Also check f'...' single-quote variant
  local fsql_sq
  fsql_sq="$(echo "$py_content" | grep -niE "f'(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\s.*\{" || true)"
  if [ -n "$fsql_sq" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SQL_INJECTION" "(python)" "$lnum" "f-string SQL query (single-quote): $(echo "$match" | head -c 120)"
    done <<< "$fsql_sq"
  fi

  # -- Pattern: String concatenation in SQL --
  # "SELECT " + variable, query = query + ..., sql += ...
  local concat_sql
  concat_sql="$(echo "$py_content" | grep -niE '"(SELECT|INSERT|UPDATE|DELETE)\s.*"\s*\+' || true)"
  if [ -n "$concat_sql" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SQL_INJECTION" "(python)" "$lnum" "String-concatenated SQL: $(echo "$match" | head -c 120)"
    done <<< "$concat_sql"
  fi

  # -- Pattern: .format() on SQL strings --
  local format_sql
  format_sql="$(echo "$py_content" | grep -niE '"(SELECT|INSERT|UPDATE|DELETE)\s.*"\.format\(' || true)"
  if [ -n "$format_sql" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SQL_INJECTION" "(python)" "$lnum" ".format() SQL query: $(echo "$match" | head -c 120)"
    done <<< "$format_sql"
  fi

  # -- Pattern: % string formatting on SQL --
  local percent_sql
  percent_sql="$(echo "$py_content" | grep -niE '"(SELECT|INSERT|UPDATE|DELETE)\s.*"\s*%\s' || true)"
  if [ -n "$percent_sql" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SQL_INJECTION" "(python)" "$lnum" "%-formatted SQL query: $(echo "$match" | head -c 120)"
    done <<< "$percent_sql"
  fi

  # -- Pattern: execute() with non-parameterized query --
  # cursor.execute(f"...) or cursor.execute("..." + ...) or cursor.execute("..." % ...)
  local exec_raw
  exec_raw="$(echo "$py_content" | grep -niE '\.execute\(\s*f["\x27]' || true)"
  if [ -n "$exec_raw" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SQL_INJECTION" "(python)" "$lnum" "execute() with f-string: $(echo "$match" | head -c 120)"
    done <<< "$exec_raw"
  fi

  # -- Pattern: raw() or text() with f-string (SQLAlchemy) --
  local sa_raw
  sa_raw="$(echo "$py_content" | grep -niE '(text|raw)\(\s*f["\x27]' || true)"
  if [ -n "$sa_raw" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "SQL_INJECTION" "(python)" "$lnum" "SQLAlchemy text()/raw() with f-string: $(echo "$match" | head -c 120)"
    done <<< "$sa_raw"
  fi
}

# ── Scan 3: XSS Vectors ─────────────────────────────────────────────────────
#
# Scan TypeScript/React files for patterns that bypass React's built-in XSS
# protection or allow arbitrary code execution.

scan_xss() {
  echo ""
  echo "${BOLD}=== XSS Scan ===${NC}"

  # Only scan TS/TSX/JS/JSX files
  local ts_content=""

  if [ "$SCAN_MODE" = "diff" ] || [ "$SCAN_MODE" = "staged" ]; then
    local in_ts=0
    while IFS= read -r line; do
      if echo "$line" | grep -qE '^\+\+\+ b/.*\.(tsx?|jsx?)$'; then
        in_ts=1
        continue
      elif echo "$line" | grep -qE '^\+\+\+ b/'; then
        in_ts=0
        continue
      fi
      if [ "$in_ts" -eq 1 ] && echo "$line" | grep -q '^+' && ! echo "$line" | grep -q '^+++'; then
        ts_content="${ts_content}${line}"$'\n'
      fi
    done <<< "$DIFF_CONTENT"
  else
    for f in "${SCAN_FILES[@]}"; do
      if echo "$f" | grep -qE '\.(tsx?|jsx?)$'; then
        ts_content="${ts_content}$(cat "$f" 2>/dev/null)"$'\n'
      fi
    done
  fi

  if [ -z "$ts_content" ]; then
    echo "  (no TypeScript/React content to scan)"
    return
  fi

  # -- Pattern: dangerouslySetInnerHTML --
  local dangerous
  dangerous="$(echo "$ts_content" | grep -niE 'dangerouslySetInnerHTML' || true)"
  if [ -n "$dangerous" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      # Check if it's sanitized (DOMPurify, sanitize-html, etc.)
      if echo "$match" | grep -qiE '(DOMPurify|sanitize|purify|escaped|encode)'; then
        record_finding "INFO" "XSS" "(react)" "$lnum" "dangerouslySetInnerHTML with sanitization (verify manually)"
      else
        record_finding "WARNING" "XSS" "(react)" "$lnum" "dangerouslySetInnerHTML without visible sanitization: $(echo "$match" | head -c 120)"
      fi
    done <<< "$dangerous"
  fi

  # -- Pattern: eval() --
  local evals
  evals="$(echo "$ts_content" | grep -niE '\beval\s*\(' || true)"
  if [ -n "$evals" ]; then
    while IFS= read -r match; do
      # Skip comments
      if echo "$match" | grep -qE '^\s*(//|\*)'; then
        continue
      fi
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "WARNING" "XSS" "(react)" "$lnum" "eval() usage: $(echo "$match" | head -c 120)"
    done <<< "$evals"
  fi

  # -- Pattern: new Function() --
  local newfn
  newfn="$(echo "$ts_content" | grep -niE 'new\s+Function\s*\(' || true)"
  if [ -n "$newfn" ]; then
    while IFS= read -r match; do
      if echo "$match" | grep -qE '^\s*(//|\*)'; then
        continue
      fi
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "WARNING" "XSS" "(react)" "$lnum" "new Function() constructor: $(echo "$match" | head -c 120)"
    done <<< "$newfn"
  fi

  # -- Pattern: innerHTML direct assignment --
  local innerhtml
  innerhtml="$(echo "$ts_content" | grep -niE '\.innerHTML\s*=' || true)"
  if [ -n "$innerhtml" ]; then
    while IFS= read -r match; do
      if echo "$match" | grep -qE '^\s*(//|\*)'; then
        continue
      fi
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "WARNING" "XSS" "(react)" "$lnum" "Direct innerHTML assignment: $(echo "$match" | head -c 120)"
    done <<< "$innerhtml"
  fi

  # -- Pattern: outerHTML assignment --
  local outerhtml
  outerhtml="$(echo "$ts_content" | grep -niE '\.outerHTML\s*=' || true)"
  if [ -n "$outerhtml" ]; then
    while IFS= read -r match; do
      if echo "$match" | grep -qE '^\s*(//|\*)'; then
        continue
      fi
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "WARNING" "XSS" "(react)" "$lnum" "Direct outerHTML assignment: $(echo "$match" | head -c 120)"
    done <<< "$outerhtml"
  fi

  # -- Pattern: document.write() --
  local docwrite
  docwrite="$(echo "$ts_content" | grep -niE 'document\.write\s*\(' || true)"
  if [ -n "$docwrite" ]; then
    while IFS= read -r match; do
      if echo "$match" | grep -qE '^\s*(//|\*)'; then
        continue
      fi
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "WARNING" "XSS" "(react)" "$lnum" "document.write() usage: $(echo "$match" | head -c 120)"
    done <<< "$docwrite"
  fi

  # -- Pattern: Unescaped template literal in href/src (potential javascript: URL) --
  local js_url
  js_url="$(echo "$ts_content" | grep -niE "(href|src|action)\s*=\s*\{?\s*['\"\`]javascript:" || true)"
  if [ -n "$js_url" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "CRITICAL" "XSS" "(react)" "$lnum" "javascript: URL in attribute: $(echo "$match" | head -c 120)"
    done <<< "$js_url"
  fi
}

# ── Scan 4: Dependency Security ──────────────────────────────────────────────
#
# Check for new dependencies added without lockfile updates, and for
# known-vulnerable packages.

scan_dependencies() {
  echo ""
  echo "${BOLD}=== Dependency Scan ===${NC}"

  if [ "$SCAN_MODE" != "diff" ] && [ "$SCAN_MODE" != "staged" ]; then
    echo "  (dependency scan only runs in diff/staged mode)"
    return
  fi

  local content="$DIFF_CONTENT"

  # -- Check: package.json changed but package-lock.json not --
  local pkg_changed=0
  local lock_changed=0
  for f in "${SCAN_FILES[@]}"; do
    case "$f" in
      */package.json|package.json) pkg_changed=1 ;;
      */package-lock.json|package-lock.json) lock_changed=1 ;;
      */yarn.lock|yarn.lock) lock_changed=1 ;;
      */pnpm-lock.yaml|pnpm-lock.yaml) lock_changed=1 ;;
    esac
  done

  if [ "$pkg_changed" -eq 1 ] && [ "$lock_changed" -eq 0 ]; then
    record_finding "WARNING" "DEPS" "package.json" "0" \
      "package.json modified but no lockfile updated -- run npm install and commit the lockfile"
  fi

  # -- Check: pyproject.toml or requirements.txt changed but no lock --
  local pyreqs_changed=0
  local pylock_changed=0
  for f in "${SCAN_FILES[@]}"; do
    case "$f" in
      */requirements*.txt|requirements*.txt) pyreqs_changed=1 ;;
      */pyproject.toml|pyproject.toml) pyreqs_changed=1 ;;
      */poetry.lock|poetry.lock) pylock_changed=1 ;;
      */requirements*.txt|requirements*.txt) pylock_changed=1 ;;  # requirements.txt IS the lock for pip
    esac
  done

  if [ "$pyreqs_changed" -eq 1 ] && [ "$pylock_changed" -eq 0 ]; then
    # Only warn for pyproject.toml without poetry.lock (requirements.txt is its own lock)
    for f in "${SCAN_FILES[@]}"; do
      if echo "$f" | grep -qE 'pyproject\.toml$'; then
        record_finding "INFO" "DEPS" "pyproject.toml" "0" \
          "pyproject.toml modified -- verify poetry.lock or pip-compile output is up to date"
      fi
    done
  fi

  # -- Known vulnerable / risky packages blocklist --
  # These packages have had critical CVEs or are known supply-chain risks.
  # This is a basic, maintainable blocklist -- NOT a replacement for npm audit.
  local BLOCKED_NPM_PACKAGES=(
    "event-stream"        # Supply chain attack (2018, flatmap-stream)
    "ua-parser-js"        # Compromised (2021, cryptomining)
    "coa"                 # Compromised (2021)
    "rc"                  # Compromised (2021)
    "colors"              # Sabotaged by maintainer (2022, infinite loop)
    "faker"               # Sabotaged by maintainer (2022)
    "node-ipc"            # Sabotaged (2022, protestware/peacenotwar)
    "node-fetch@1"        # Deprecated, use v2+ or native fetch
  )

  local BLOCKED_PIP_PACKAGES=(
    "pyyaml<6"            # CVE-2020-14343 (arbitrary code execution)
    "jinja2<3"            # Multiple XSS CVEs
    "urllib3<1.26.5"      # CVE-2021-33503
    "cryptography<41"     # Multiple CVEs
    "setuptools<65.5.1"   # CVE-2022-40897
  )

  # Check npm blocklist against added lines in package.json
  if [ "$pkg_changed" -eq 1 ]; then
    local pkg_added
    pkg_added="$(echo "$content" | grep -A9999 '^\+\+\+ b/.*package\.json' | grep '^+' | grep -v '^+++' || true)"
    for blocked in "${BLOCKED_NPM_PACKAGES[@]}"; do
      local pkg_name="${blocked%%@*}"  # Strip version constraint
      if echo "$pkg_added" | grep -qi "\"$pkg_name\""; then
        record_finding "CRITICAL" "DEPS" "package.json" "0" \
          "Blocked package '$blocked' added -- known supply-chain risk or vulnerability"
      fi
    done
  fi

  # Check pip blocklist against added lines in requirements/pyproject
  if [ "$pyreqs_changed" -eq 1 ]; then
    local py_added
    py_added="$(echo "$content" | grep '^+' | grep -v '^+++' || true)"
    for blocked in "${BLOCKED_PIP_PACKAGES[@]}"; do
      local pkg_name="${blocked%%<*}"  # Strip version constraint
      pkg_name="${pkg_name%%=*}"
      if echo "$py_added" | grep -qi "$pkg_name"; then
        record_finding "WARNING" "DEPS" "(python deps)" "0" \
          "Package '$blocked' -- check version is not in vulnerable range"
      fi
    done
  fi
}

# ── Scan 5: Miscellaneous Security Hygiene ───────────────────────────────────

scan_misc() {
  echo ""
  echo "${BOLD}=== Security Hygiene ===${NC}"

  local content="$1"

  if [ -z "$content" ]; then
    echo "  (no content to scan)"
    return
  fi

  local scan_text="$content"
  if [ "$SCAN_MODE" = "diff" ] || [ "$SCAN_MODE" = "staged" ]; then
    scan_text="$(echo "$content" | grep '^+' | grep -v '^+++' || true)"
  fi

  if [ -z "$scan_text" ]; then
    echo "  (no added lines to scan)"
    return
  fi

  # -- Pattern: Disabled SSL verification --
  local nossl
  nossl="$(echo "$scan_text" | grep -niE '(verify\s*=\s*False|VERIFY_SSL\s*=\s*False|rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*["\x27]0)' || true)"
  if [ -n "$nossl" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "WARNING" "SECURITY" "(code)" "$lnum" "SSL verification disabled: $(echo "$match" | head -c 120)"
    done <<< "$nossl"
  fi

  # -- Pattern: Hardcoded IP addresses (non-localhost) --
  local hardcoded_ips
  hardcoded_ips="$(echo "$scan_text" | grep -nE '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}' | grep -vE '(127\.0\.0\.[01]|0\.0\.0\.0|localhost|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)' || true)"
  if [ -n "$hardcoded_ips" ]; then
    while IFS= read -r match; do
      # Skip comments and version numbers
      if echo "$match" | grep -qE '(version|Version|#|//|\*|semver)'; then
        continue
      fi
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "INFO" "SECURITY" "(code)" "$lnum" "Hardcoded non-private IP address: $(echo "$match" | head -c 120)"
    done <<< "$hardcoded_ips"
  fi

  # -- Pattern: subprocess.call/Popen with shell=True --
  local shell_true
  shell_true="$(echo "$scan_text" | grep -niE '(subprocess\.(call|run|Popen)|os\.system|os\.popen)\s*\(' | grep -i 'shell\s*=\s*True' || true)"
  if [ -n "$shell_true" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "WARNING" "SECURITY" "(python)" "$lnum" "subprocess with shell=True (command injection risk): $(echo "$match" | head -c 120)"
    done <<< "$shell_true"
  fi

  # -- Pattern: os.system() calls --
  local ossystem
  ossystem="$(echo "$scan_text" | grep -niE '\bos\.system\s*\(' || true)"
  if [ -n "$ossystem" ]; then
    while IFS= read -r match; do
      if echo "$match" | grep -qE '^\s*(#|//|\*)'; then
        continue
      fi
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "WARNING" "SECURITY" "(python)" "$lnum" "os.system() call (prefer subprocess with shell=False): $(echo "$match" | head -c 120)"
    done <<< "$ossystem"
  fi

  # -- Pattern: pickle.loads on untrusted data --
  local pickle_loads
  pickle_loads="$(echo "$scan_text" | grep -niE 'pickle\.loads?\s*\(' || true)"
  if [ -n "$pickle_loads" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "WARNING" "SECURITY" "(python)" "$lnum" "pickle.load() usage (arbitrary code execution if untrusted data): $(echo "$match" | head -c 120)"
    done <<< "$pickle_loads"
  fi

  # -- Pattern: CORS wildcard --
  local cors_star
  cors_star="$(echo "$scan_text" | grep -niE '(allow_origins\s*=\s*\[\s*"\*"|Access-Control-Allow-Origin.*\*)' || true)"
  if [ -n "$cors_star" ]; then
    while IFS= read -r match; do
      local lnum
      lnum="$(echo "$match" | cut -d: -f1)"
      record_finding "WARNING" "SECURITY" "(code)" "$lnum" "CORS wildcard (*) -- restrict to specific origins in production: $(echo "$match" | head -c 120)"
    done <<< "$cors_star"
  fi
}

# ── Summary & Exit ───────────────────────────────────────────────────────────

print_summary() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if [ "$CRITICAL_COUNT" -eq 0 ] && [ "$WARNING_COUNT" -eq 0 ] && [ "$INFO_COUNT" -eq 0 ]; then
    printf "${GREEN}${BOLD}SCAN CLEAN${NC} -- No security issues found.\n"
  else
    printf "${BOLD}SCAN RESULTS:${NC}  "
    [ "$CRITICAL_COUNT" -gt 0 ] && printf "${RED}%d CRITICAL${NC}  " "$CRITICAL_COUNT"
    [ "$WARNING_COUNT" -gt 0 ]  && printf "${YELLOW}%d WARNING${NC}  " "$WARNING_COUNT"
    [ "$INFO_COUNT" -gt 0 ]     && printf "${BLUE}%d INFO${NC}  " "$INFO_COUNT"
    echo ""
  fi

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # Write findings to a report file for bead creation
  if [ -n "$FINDINGS" ]; then
    REPORT_FILE="/tmp/baap-security-scan-$(date +%Y%m%d_%H%M%S).txt"
    printf "$FINDINGS" > "$REPORT_FILE"
    echo "Report saved: $REPORT_FILE"
  fi
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
  echo "${BOLD}Baap Security Scanner${NC}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  parse_args "$@"

  echo "Mode: $SCAN_MODE"
  echo "Files to scan: ${#SCAN_FILES[@]}"

  scan_secrets "$DIFF_CONTENT"
  scan_sql_injection
  scan_xss
  scan_dependencies
  scan_misc "$DIFF_CONTENT"
  print_summary

  # ── Exit code ──────────────────────────────────────────────────────────────
  if [ "$CRITICAL_COUNT" -gt 0 ]; then
    exit 1
  fi

  if [ "$WARNING_COUNT" -gt 0 ]; then
    if [ "${SECURITY_SCAN_STRICT:-0}" = "1" ]; then
      exit 1  # Strict mode: warnings are treated as critical
    fi
    exit 2
  fi

  exit 0
}

main "$@"
