#!/usr/bin/env bash
# cleanup.sh — Merge agent results and remove worktree
#
# Usage:
#   cleanup.sh <agent_name> <merge|discard> [epic_branch]
#
# Examples:
#   cleanup.sh reactive-20260210_143000 merge                  # Merge to main + push
#   cleanup.sh reactive-20260210_143000 merge epic/baap-abc    # Merge to epic branch
#   cleanup.sh reactive-20260210_143000 discard                # Throw away changes
set -euo pipefail

NAME="${1:?Usage: cleanup.sh <agent_name> <merge|discard> [epic_branch]}"
ACTION="${2:?Missing action: merge or discard}"
EPIC_BRANCH="${3:-}"
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
WORKTREE="$AGENT_DIR/$NAME"
BRANCH="agent/$NAME"
LOCK_FILE="/tmp/baap-merge.lock"

# ── Validate ─────────────────────────────────────────────────────────────────
if [ ! -d "$WORKTREE" ]; then
  echo "Error: Worktree not found at $WORKTREE" >&2
  echo "Active worktrees:"
  git worktree list 2>/dev/null || true
  exit 1
fi

# Find the main repo (parent of worktree)
PROJECT="$(cd "$WORKTREE" && git rev-parse --git-common-dir 2>/dev/null | sed 's|/\.git$||')"
if [ -z "$PROJECT" ] || [ ! -d "$PROJECT" ]; then
  echo "Error: Could not find parent repo for worktree" >&2
  exit 1
fi

case "$ACTION" in
  merge)
    echo "Merging agent/$NAME..."

    # Commit any uncommitted changes in the worktree
    cd "$WORKTREE"
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
      git add -A
      git commit -m "Agent $NAME: final results [$(hostname -s)]" --no-verify
    fi

    # ── Deterministic KG Ownership Check (BEFORE merge lock) ───────────────
    # Every new file MUST have an owner in the KG before merging.
    # If unregistered, auto-register to the agent that created it.
    MAIN_BRANCH="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo main)"
    AG_CLI="$PROJECT/.claude/tools/ag"
    KG_CACHE="$PROJECT/.claude/kg/agent_graph_cache.json"

    if [ -x "$AG_CLI" ] && [ -f "$KG_CACHE" ]; then
      echo "Checking KG ownership for new files..."
      UNREGISTERED=0

      # Get new files added by this agent branch (not in main)
      NEW_FILES=$(cd "$WORKTREE" && git diff --name-only --diff-filter=A "$MAIN_BRANCH"..."$BRANCH" 2>/dev/null || true)

      for f in $NEW_FILES; do
        # Skip non-source files
        case "$f" in
          *.py|*.ts|*.tsx|*.js|*.jsx|*.sql|*.json) ;;
          *) continue ;;
        esac

        # Check if file has an owner in KG
        OWNER=$("$AG_CLI" owner "$f" 2>/dev/null | head -1 || true)
        if [ -z "$OWNER" ] || echo "$OWNER" | grep -qi "no owner\|not found\|error"; then
          echo "  Auto-registering: $f → $NAME"
          "$AG_CLI" register "$f" "$NAME" 2>/dev/null || true
          UNREGISTERED=$((UNREGISTERED + 1))
        fi
      done

      if [ "$UNREGISTERED" -gt 0 ]; then
        echo "Auto-registered $UNREGISTERED new file(s) to $NAME in KG"
      else
        echo "All new files already registered in KG"
      fi
    else
      echo "Note: KG not yet available (ag CLI or cache missing). Skipping ownership check."
    fi
    # ── End KG Check ──────────────────────────────────────────────────────────

    # ── Deterministic Bead Closure Check (BEFORE merge lock) ──────────────
    # Agent MUST close its assigned bead before merging. No silent merges.
    if command -v bd &>/dev/null; then
      echo "Checking bead closure for agent $NAME..."
      OPEN_BEADS=$(bd list --status=in_progress --json 2>/dev/null | python3 -c "
import json, sys
try:
    beads = json.load(sys.stdin)
    agent = '$NAME'
    open_ones = [b['id'] for b in beads if agent in str(b.get('assignee','')) or agent in str(b.get('title',''))]
    print(' '.join(open_ones))
except: pass
" 2>/dev/null || true)

      if [ -n "$OPEN_BEADS" ]; then
        echo "WARNING: Agent $NAME has unclosed beads: $OPEN_BEADS"
        echo "Auto-closing with merge reason..."
        for BEAD_ID in $OPEN_BEADS; do
          bd close "$BEAD_ID" --reason="Auto-closed by cleanup.sh merge for agent $NAME" 2>/dev/null || true
        done
        echo "Beads auto-closed. Proceeding with merge."
      else
        echo "All beads closed for $NAME"
      fi
    else
      echo "Note: bd not in PATH. Skipping bead closure check."
    fi
    # ── End Bead Check ────────────────────────────────────────────────────────

    # ── PRE-MERGE GATE 1: Security Scan ──────────────────────────────────────
    # Runs scan-security.sh (created by 03g) on the agent's diff.
    # Exit codes: 0=clean, 1=CRITICAL (block), 2=WARNING (allow with note)
    SCAN_SCRIPT="$PROJECT/.claude/scripts/scan-security.sh"
    SKIP_SECURITY="${SKIP_SECURITY:-false}"

    if [ "$SKIP_SECURITY" = "true" ]; then
      echo "[gate:security] Skipping security scan (SKIP_SECURITY=true)"
    elif [ -x "$SCAN_SCRIPT" ]; then
      echo "[gate:security] Running security scan..."
      scan_exit=0
      "$SCAN_SCRIPT" --diff "$MAIN_BRANCH" "$BRANCH" || scan_exit=$?
      case $scan_exit in
        0) echo "[gate:security] CLEAN — no issues found" ;;
        1) echo "[gate:security] CRITICAL issues found. Merge BLOCKED." >&2; exit 1 ;;
        2) echo "[gate:security] Warnings found. Proceeding (review recommended)." ;;
        *) echo "[gate:security] Scan error (exit $scan_exit). Merge BLOCKED." >&2; exit 1 ;;
      esac
    else
      echo "[gate:security] scan-security.sh not found. Skipping. (Install via Phase 3g)"
    fi
    # ── End Security Gate ────────────────────────────────────────────────────

    # ── PRE-MERGE GATE 2: Test Gate ──────────────────────────────────────────
    # Runs test-gate.sh (created by 03b) on the agent's worktree.
    # Exit codes: 0=passed, 1=failed, 2=timeout
    TEST_GATE_SCRIPT="$PROJECT/.claude/scripts/test-gate.sh"
    SKIP_TESTS="${SKIP_TESTS:-false}"

    if [ "$SKIP_TESTS" = "true" ]; then
      echo "[gate:test] Skipping test gate (SKIP_TESTS=true)"
    elif [ -x "$TEST_GATE_SCRIPT" ]; then
      echo "[gate:test] Running test gate..."
      test_exit=0
      "$TEST_GATE_SCRIPT" "$WORKTREE" || test_exit=$?
      case $test_exit in
        0) echo "[gate:test] PASSED — all tests green" ;;
        1) echo "[gate:test] FAILED — tests did not pass. Merge BLOCKED." >&2; exit 1 ;;
        2) echo "[gate:test] TIMEOUT — tests exceeded time limit. Merge BLOCKED." >&2; exit 1 ;;
        *) echo "[gate:test] Error (exit $test_exit). Merge BLOCKED." >&2; exit 1 ;;
      esac
    else
      echo "[gate:test] test-gate.sh not found. Skipping. (Install via Phase 3b)"
    fi
    # ── End Test Gate ────────────────────────────────────────────────────────

    # ── PRE-MERGE GATE 3: Review Gate ────────────────────────────────────────
    # Runs review-agent.sh (created by 03a) — spawns fresh-context reviewer.
    # Exit codes: 0=APPROVED, 1=CHANGES_REQUESTED, 2=REJECTED, 3=ERROR
    REVIEW_SCRIPT="$PROJECT/.claude/scripts/review-agent.sh"
    SKIP_REVIEW="${SKIP_REVIEW:-false}"

    if [ "$SKIP_REVIEW" = "true" ]; then
      echo "[gate:review] Skipping review gate (SKIP_REVIEW=true)"
    elif [ -x "$REVIEW_SCRIPT" ]; then
      echo "[gate:review] Running review gate..."
      review_exit=0
      "$REVIEW_SCRIPT" "$NAME" "$WORKTREE" || review_exit=$?
      case $review_exit in
        0) echo "[gate:review] APPROVED — review passed" ;;
        1) echo "[gate:review] CHANGES REQUESTED. Merge BLOCKED." >&2; exit 1 ;;
        2) echo "[gate:review] REJECTED. Merge BLOCKED. Escalating to human." >&2; exit 2 ;;
        *) echo "[gate:review] Error (exit $review_exit). Merge BLOCKED." >&2; exit 1 ;;
      esac
    else
      echo "[gate:review] review-agent.sh not found. Skipping. (Install via Phase 3a)"
    fi
    # ── End Review Gate ──────────────────────────────────────────────────────

    # ── LOCKED MERGE SECTION ──────────────────────────────────────────────────
    # NOTE: Gate 4 (Browser QA) runs AFTER the merge below because it needs
    # the latest code running on the dashboard. It does not block the merge —
    # it creates fix beads on failure. See post-merge section after the lock.
    (
      flock -w 300 200 || { echo "ERROR: Could not acquire merge lock after 5 minutes" >&2; exit 1; }
      echo "Merge lock acquired."

      cd "$PROJECT"
      MAIN_BRANCH="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo main)"

      # Determine merge target
      if [ -n "$EPIC_BRANCH" ]; then
        TARGET="$EPIC_BRANCH"
        # Create epic branch from main if it doesn't exist
        git branch "$EPIC_BRANCH" "$MAIN_BRANCH" 2>/dev/null || true
      else
        TARGET="$MAIN_BRANCH"
      fi

      git checkout "$TARGET" 2>/dev/null
      git pull --rebase --autostash 2>/dev/null || true
      git merge "$BRANCH" --no-ff -m "Merge $BRANCH results" --no-verify

      # Only push when merging directly to main (not to epic branch)
      if [ -z "$EPIC_BRANCH" ]; then
        git push 2>/dev/null && echo "Pushed to remote." || echo "Warning: Push failed. Run 'git push' manually."
      fi

      echo "Merged: $BRANCH → $TARGET"
      echo "Released merge lock."
    ) 200>"$LOCK_FILE"
    # ── END LOCKED SECTION ────────────────────────────────────────────────────

    # ── POST-MERGE GATE 4: Browser QA Gate ──────────────────────────────────
    # Runs AFTER merge because the dashboard needs the latest code.
    # Does NOT block the merge — creates fix beads on failure.
    BROWSER_QA_SCRIPT="$PROJECT/.claude/scripts/browser-qa-gate.sh"
    SKIP_BROWSER_QA="${SKIP_BROWSER_QA:-false}"

    if [ "$SKIP_BROWSER_QA" = "true" ]; then
      echo "[gate:browser-qa] Skipping (SKIP_BROWSER_QA=true)"
    elif [ -x "$BROWSER_QA_SCRIPT" ]; then
      echo "[gate:browser-qa] Running browser QA..."
      qa_exit=0
      "$BROWSER_QA_SCRIPT" "$NAME" "$WORKTREE" || qa_exit=$?
      case $qa_exit in
        0) echo "[gate:browser-qa] ALL PASSED" ;;
        1) echo "[gate:browser-qa] PARTIAL FAILURE — fix bead created" ;;
        2) echo "[gate:browser-qa] ALL FAILED — fix bead created" ;;
        3) echo "[gate:browser-qa] QA infra error — proceeding with warning" ;;
        4) echo "[gate:browser-qa] Skipped (no UI files in diff)" ;;
      esac
    else
      echo "[gate:browser-qa] browser-qa-gate.sh not found. Skipping. (Install via Bead 12)"
    fi
    # ── End Browser QA Gate ─────────────────────────────────────────────────
    ;;

  discard)
    echo "Discarding agent/$NAME changes..."
    ;;

  *)
    echo "Error: Unknown action '$ACTION'. Use: merge or discard" >&2
    exit 1
    ;;
esac

# ── Archive agent log before cleanup ─────────────────────────────────────────
LOG_FILE="$WORKTREE/agent.log"
ARCHIVE_DIR="$PROJECT/.claude/logs"
if [ -f "$LOG_FILE" ]; then
  mkdir -p "$ARCHIVE_DIR"
  cp "$LOG_FILE" "$ARCHIVE_DIR/${NAME}_$(date +%Y%m%d_%H%M%S).log"
  echo "Archived agent log to $ARCHIVE_DIR/"
fi

# Clean up status file
rm -f "/tmp/baap-agent-status/$NAME.json"
rm -f "/tmp/baap-agent-status/$NAME.retries"

# ── Cleanup: Remove worktree and branch ──────────────────────────────────────
# Remove symlinks first (they point outside the worktree and cause git worktree remove errors)
rm -f "$WORKTREE/.beads" 2>/dev/null || true
rm -f "$WORKTREE/.venv" 2>/dev/null || true
rm -f "$WORKTREE/.claude/integrations" 2>/dev/null || true

cd "$PROJECT"
git worktree remove "$WORKTREE" --force 2>/dev/null || {
  echo "Warning: Could not remove worktree. Trying manual cleanup..." >&2
  rm -rf "$WORKTREE"
  git worktree prune
}
git branch -D "$BRANCH" 2>/dev/null || true

echo "Cleaned up: $WORKTREE removed, branch $BRANCH deleted"
