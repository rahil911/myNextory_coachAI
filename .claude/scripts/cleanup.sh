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

    # Switch to main repo and merge
    cd "$PROJECT"
    MAIN_BRANCH="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo main)"
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
