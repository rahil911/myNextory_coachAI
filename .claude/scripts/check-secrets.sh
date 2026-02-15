#!/usr/bin/env bash
# =============================================================================
# check-secrets.sh -- Fast regex-based secret detection (no LLM needed)
#
# Usage:
#   check-secrets.sh <worktree-path>
#
# Exit codes:
#   0  No secrets found
#   1  Potential secrets detected
# =============================================================================

set -euo pipefail

WORKTREE_PATH="${1:?Usage: check-secrets.sh <worktree-path>}"
BAAP_ROOT="${BAAP_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

cd "$WORKTREE_PATH"
MAIN_BRANCH="main"
MERGE_BASE="$(git merge-base HEAD "$MAIN_BRANCH" 2>/dev/null || git rev-parse "$MAIN_BRANCH")"

# Get the diff content (only additions, not the entire file)
DIFF_ADDITIONS="$(git diff "$MERGE_BASE"..HEAD | grep '^+' | grep -v '^+++' || true)"

if [ -z "$DIFF_ADDITIONS" ]; then
    echo "[secrets] No additions to scan."
    exit 0
fi

# Secret patterns (high-confidence patterns that are almost always real secrets)
FINDINGS=""
FINDING_COUNT=0

check_pattern() {
    local name="$1"
    local pattern="$2"
    local matches
    matches="$(echo "$DIFF_ADDITIONS" | grep -nE "$pattern" 2>/dev/null || true)"
    if [ -n "$matches" ]; then
        FINDINGS="${FINDINGS}\n  [$name]:\n"
        while IFS= read -r match; do
            FINDINGS="${FINDINGS}    $match\n"
            FINDING_COUNT=$((FINDING_COUNT + 1))
        done <<< "$matches"
    fi
}

# AWS
check_pattern "AWS Access Key" "AKIA[0-9A-Z]{16}"
check_pattern "AWS Secret Key" "aws_secret_access_key\s*=\s*['\"][A-Za-z0-9/+=]{40}"

# Google
check_pattern "Google API Key" "AIza[0-9A-Za-z_-]{35}"
check_pattern "Google OAuth" "ya29\.[0-9A-Za-z_-]+"

# GitHub
check_pattern "GitHub Token" "gh[pousr]_[A-Za-z0-9_]{36,}"
check_pattern "GitHub Personal" "github_pat_[A-Za-z0-9_]{82}"

# Generic secrets
check_pattern "Private Key" "-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----"
check_pattern "Hardcoded Password" "(password|passwd|pwd)\s*=\s*['\"][^'\"]{8,}"
check_pattern "Hardcoded Secret" "(secret|token|api_key|apikey)\s*=\s*['\"][^'\"]{8,}"
check_pattern "Bearer Token" "Bearer\s+[A-Za-z0-9_-]{20,}"
check_pattern "Basic Auth" "Basic\s+[A-Za-z0-9+/=]{20,}"

# Database
check_pattern "Connection String" "(postgres|mysql|mongodb|redis)://[^@\s]+@"
check_pattern "Snowflake Password" "SNOWFLAKE_PASSWORD\s*=\s*['\"][^'\"]+['\"]"

# Slack
check_pattern "Slack Token" "xox[baprs]-[0-9A-Za-z-]{10,}"
check_pattern "Slack Webhook" "hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"

cd "$BAAP_ROOT"

if [ "$FINDING_COUNT" -gt 0 ]; then
    echo "[secrets] POTENTIAL SECRETS DETECTED ($FINDING_COUNT findings):"
    echo -e "$FINDINGS"
    echo ""
    echo "[secrets] MERGE BLOCKED until secrets are removed."
    echo "[secrets] Use environment variables or secret managers instead."
    exit 1
else
    echo "[secrets] No secrets detected in diff."
    exit 0
fi
