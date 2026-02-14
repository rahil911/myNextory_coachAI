#!/usr/bin/env bash
# cleanup.sh — Merge agent results to main and remove worktree
#
# Usage:
#   cleanup.sh <agent_name> <merge|discard>
#
# Examples:
#   cleanup.sh reactive-20260210_143000 merge     # Merge to main + push
#   cleanup.sh reactive-20260210_143000 discard   # Throw away changes
set -euo pipefail

NAME="${1:?Usage: cleanup.sh <agent_name> <merge|discard>}"
ACTION="${2:?Missing action: merge or discard}"
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
WORKTREE="$AGENT_DIR/$NAME"
BRANCH="agent/$NAME"

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
    echo "Merging agent/$NAME to main..."

    # Commit any uncommitted changes in the worktree
    cd "$WORKTREE"
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
      git add -A
      git commit -m "Agent $NAME: final results [$(hostname -s)]" --no-verify
    fi

    # ── Deterministic KG Ownership Check ────────────────────────────────────
    # Every new file MUST have an owner in the KG before merging to main.
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
        echo "All new files already registered in KG ✓"
      fi
    else
      echo "Note: KG not yet available (ag CLI or cache missing). Skipping ownership check."
    fi
    # ── End KG Check ────────────────────────────────────────────────────────

    # ── Deterministic Bead Closure Check ────────────────────────────────────
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
    # ── End Bead Check ──────────────────────────────────────────────────────

    # Switch to main repo and merge
    cd "$PROJECT"
    git checkout "$MAIN_BRANCH" 2>/dev/null
    git merge "$BRANCH" --no-ff -m "Merge $BRANCH results" --no-verify

    # Push
    git push 2>/dev/null && echo "Pushed to remote." || echo "Warning: Push failed. Run 'git push' manually."

    echo "Merged: $BRANCH → $MAIN_BRANCH"
    ;;

  discard)
    echo "Discarding agent/$NAME changes..."
    ;;

  *)
    echo "Error: Unknown action '$ACTION'. Use: merge or discard" >&2
    exit 1
    ;;
esac

# ── Remove worktree and branch ──────────────────────────────────────────────
cd "$PROJECT"
git worktree remove "$WORKTREE" --force 2>/dev/null || {
  echo "Warning: Could not remove worktree. Trying manual cleanup..." >&2
  rm -rf "$WORKTREE"
  git worktree prune
}
git branch -D "$BRANCH" 2>/dev/null || true

echo "Cleaned up: $WORKTREE removed, branch $BRANCH deleted"
