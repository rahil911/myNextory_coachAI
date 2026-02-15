#!/usr/bin/env bash
# checkpoint.sh -- Commit worktree progress and update bead notes
#
# Usage:
#   checkpoint.sh <worktree_path> <summary> [bead_id]
#
# Called by agents via Bash tool, or manually.
# Performs: git add + commit + bead update in one atomic operation.
set -euo pipefail

WORKTREE="${1:?Usage: checkpoint.sh <worktree_path> <summary> [bead_id]}"
SUMMARY="${2:?Missing checkpoint summary}"
BEAD_ID="${3:-}"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

# -- Validate ----------------------------------------------------------------
if [ ! -d "$WORKTREE/.git" ] && [ ! -f "$WORKTREE/.git" ]; then
  echo "Error: $WORKTREE is not a git worktree" >&2
  exit 1
fi

cd "$WORKTREE"

# -- Git commit ---------------------------------------------------------------
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  git add -A
  git commit -m "checkpoint: $SUMMARY" --no-verify 2>/dev/null || {
    echo "Warning: git commit failed (possibly nothing to commit)" >&2
  }
  echo "Committed checkpoint: $SUMMARY"
else
  echo "No changes to commit."
fi

# -- Update bead notes --------------------------------------------------------
if [ -n "$BEAD_ID" ]; then
  bd update "$BEAD_ID" --notes="Checkpoint [$TIMESTAMP]: $SUMMARY" 2>/dev/null && {
    echo "Updated bead $BEAD_ID with checkpoint."
  } || {
    echo "Warning: Failed to update bead $BEAD_ID" >&2
  }
fi

# -- Report -------------------------------------------------------------------
COMMIT_HASH="$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")"
FILES_CHANGED="$(git diff --name-only HEAD~1 2>/dev/null | wc -l | tr -d ' ')"
echo ""
echo "Checkpoint saved:"
echo "  Time:    $TIMESTAMP"
echo "  Commit:  $COMMIT_HASH"
echo "  Files:   $FILES_CHANGED changed"
echo "  Bead:    ${BEAD_ID:-none}"
echo "  Summary: $SUMMARY"
