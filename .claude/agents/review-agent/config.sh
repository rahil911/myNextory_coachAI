# =============================================================================
# .claude/agents/review-agent/config.sh
# Review agent configuration -- sourced by review-agent.sh
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# Fast-path thresholds
# Changes below BOTH thresholds get Haiku review (fast, ~15s)
# Changes above EITHER threshold get Opus review (full, ~60s)
# ─────────────────────────────────────────────────────────────────────────────
export FAST_THRESHOLD_FILES=2       # Max files for fast-path
export FAST_THRESHOLD_LINES=50      # Max total lines (added + removed) for fast-path

# ─────────────────────────────────────────────────────────────────────────────
# Timeouts
# ─────────────────────────────────────────────────────────────────────────────
export REVIEW_TIMEOUT=120           # Max seconds for any review
export REVIEW_TIMEOUT_FAST=30       # Max seconds for fast-path review
export AGENT_FIX_TIMEOUT=300        # Max seconds for agent to apply fixes

# ─────────────────────────────────────────────────────────────────────────────
# Retry configuration
# ─────────────────────────────────────────────────────────────────────────────
export MAX_REVIEW_RETRIES=2         # Fix cycles before escalating to human
export RETRY_BACKOFF_SECONDS=30     # Pause between retries

# ─────────────────────────────────────────────────────────────────────────────
# Skip patterns
# Files matching these patterns bypass review entirely
# (useful for auto-generated files, lock files, etc.)
# ─────────────────────────────────────────────────────────────────────────────
REVIEW_SKIP_PATTERNS=(
    "package-lock.json"
    "*.lock"
    ".beads/*"
    "sessions/*"
    "capsules/*"
    "*.png"
    "*.jpg"
    "*.jpeg"
    "*.gif"
    "*.svg"
    "*.ico"
    "*.woff"
    "*.woff2"
    "*.ttf"
    "*.eot"
)

# ─────────────────────────────────────────────────────────────────────────────
# Infrastructure paths (orchestrator can skip review for these)
# ─────────────────────────────────────────────────────────────────────────────
INFRASTRUCTURE_PATHS=(
    "CLAUDE.md"
    ".claude/agents/*/memory/MEMORY.md"
    ".claude/kg/agent_graph_cache.json"
    "scripts/*.sh"
    ".github/workflows/*"
)

# ─────────────────────────────────────────────────────────────────────────────
# should_skip_review()
# Returns 0 (true) if all changed files match skip patterns
# ─────────────────────────────────────────────────────────────────────────────
should_skip_review() {
    local changed_files="$1"
    local all_skippable=true

    while IFS= read -r file; do
        [ -z "$file" ] && continue
        local is_skip=false
        for pattern in "${REVIEW_SKIP_PATTERNS[@]}"; do
            if [[ "$file" == $pattern ]]; then
                is_skip=true
                break
            fi
        done
        if [ "$is_skip" = "false" ]; then
            all_skippable=false
            break
        fi
    done <<< "$changed_files"

    if [ "$all_skippable" = "true" ]; then
        return 0
    else
        return 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# is_infrastructure_change()
# Returns 0 (true) if all changed files are infrastructure paths
# ─────────────────────────────────────────────────────────────────────────────
is_infrastructure_change() {
    local changed_files="$1"
    local all_infra=true

    while IFS= read -r file; do
        [ -z "$file" ] && continue
        local is_infra=false
        for pattern in "${INFRASTRUCTURE_PATHS[@]}"; do
            if [[ "$file" == $pattern ]]; then
                is_infra=true
                break
            fi
        done
        if [ "$is_infra" = "false" ]; then
            all_infra=false
            break
        fi
    done <<< "$changed_files"

    if [ "$all_infra" = "true" ]; then
        return 0
    else
        return 1
    fi
}
