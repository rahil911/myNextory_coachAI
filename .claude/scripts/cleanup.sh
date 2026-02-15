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

    # ── LOCKED MERGE SECTION ──────────────────────────────────────────────────
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
