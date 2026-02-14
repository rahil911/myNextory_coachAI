# Phase 1b: Harden cleanup.sh

## Purpose

cleanup.sh is the SINGLE MERGE CHOKEPOINT. All agent work enters main through it.
It already has KG ownership check and bead closure check. This phase adds merge locking
and epic integration branch support.

## Risks Mitigated

- Risk 5: Concurrent merge race condition (HIGH)
- Risk 10: Partial epic failure has no atomic rollback (MEDIUM)

## Current cleanup.sh Location

`.claude/scripts/cleanup.sh`

## Required Changes

Read the current cleanup.sh first, then apply these two fixes.

### Fix 1: flock Merge Lock (Risk 5)

Two agents finishing simultaneously both run `cleanup.sh merge`. Both do
`git checkout main && git merge`. The second one fails because main moved.

Wrap the entire merge section in a file lock:

```bash
LOCK_FILE="/tmp/baap-merge.lock"

(
  # Wait for lock (other agent might be merging)
  flock -w 300 200 || { echo "ERROR: Could not acquire merge lock after 5 minutes" >&2; exit 1; }

  echo "Acquired merge lock..."

  # --- existing merge logic goes here ---
  # git checkout main
  # git merge ...
  # git push

  echo "Released merge lock."

) 200>"$LOCK_FILE"
```

This ensures EXACTLY ONE merge happens at a time. The second agent waits up to 5 minutes
for the first to finish. Deterministic, no race.

The flock must wrap: git checkout, git merge, and git push. The KG check and bead check
can run BEFORE acquiring the lock (they don't need exclusive access to main).

### Fix 2: Epic Integration Branch (Risk 10)

Instead of merging each agent directly to main, support an optional integration branch
per epic. If an epic has 5 agents, all merge to `epic/<epic-id>` first. Once all pass,
that branch merges to main as a single merge commit. If any agent fails, discard the
integration branch — main is untouched.

Add an optional --epic flag:

```bash
EPIC_BRANCH="${3:-}"  # Optional: epic/baap-abc

# If epic branch specified, merge to that instead of main
if [ -n "$EPIC_BRANCH" ]; then
  TARGET_BRANCH="$EPIC_BRANCH"
  # Create epic branch from main if it doesn't exist
  git branch "$EPIC_BRANCH" "$MAIN_BRANCH" 2>/dev/null || true
else
  TARGET_BRANCH="$MAIN_BRANCH"
fi
```

Usage:
```bash
# Normal merge (direct to main)
cleanup.sh agent-name merge

# Epic merge (to integration branch)
cleanup.sh agent-name merge epic/baap-abc

# When all agents in epic are done, merge epic to main:
git checkout main && git merge epic/baap-abc --no-ff -m "EPIC: description"

# If epic failed, discard:
git branch -D epic/baap-abc
```

### Fix 3: Pull before merge

Before merging, pull latest main to avoid conflicts with agents that already merged:

```bash
git checkout "$TARGET_BRANCH" 2>/dev/null
git pull --rebase --autostash 2>/dev/null || true  # Get latest from other merges
git merge "$BRANCH" --no-ff -m "Merge $BRANCH results" --no-verify
```

### Fix 4: Remove symlinks before worktree removal

cleanup.sh removes the worktree at the end. But .beads/ and .venv/ are symlinks.
Remove them first to avoid `git worktree remove` errors:

```bash
# Remove symlinks before worktree removal (they point outside the worktree)
rm -f "$WORKTREE/.beads" 2>/dev/null || true
rm -f "$WORKTREE/.venv" 2>/dev/null || true
```

## Updated Usage

```
cleanup.sh <agent_name> <merge|discard> [epic_branch]
```

## Full Structure

```bash
#!/usr/bin/env bash
set -euo pipefail

NAME="${1:?Usage: cleanup.sh <agent_name> <merge|discard> [epic_branch]}"
ACTION="${2:?Missing action: merge or discard}"
EPIC_BRANCH="${3:-}"
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
WORKTREE="$AGENT_DIR/$NAME"
BRANCH="agent/$NAME"
LOCK_FILE="/tmp/baap-merge.lock"

# Validate worktree exists
[ -d "$WORKTREE" ] || { echo "Error: Worktree not found at $WORKTREE" >&2; exit 1; }

# Find main repo
PROJECT="$(cd "$WORKTREE" && git rev-parse --git-common-dir 2>/dev/null | sed 's|/\.git$||')"
[ -d "$PROJECT" ] || { echo "Error: Could not find parent repo" >&2; exit 1; }

case "$ACTION" in
  merge)
    echo "Merging agent/$NAME..."

    # Commit uncommitted changes
    cd "$WORKTREE"
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
      git add -A
      git commit -m "Agent $NAME: final results [$(hostname -s)]" --no-verify
    fi

    # KG ownership check (runs BEFORE acquiring merge lock — no exclusive access needed)
    # ... existing KG check code ...

    # Bead closure check (runs BEFORE acquiring merge lock)
    # ... existing bead check code ...

    # ── LOCKED MERGE SECTION ────────────────────────────────────────────────
    (
      flock -w 300 200 || { echo "ERROR: Merge lock timeout" >&2; exit 1; }
      echo "Merge lock acquired."

      cd "$PROJECT"
      MAIN_BRANCH="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo main)"

      # Determine merge target
      if [ -n "$EPIC_BRANCH" ]; then
        TARGET="$EPIC_BRANCH"
        git branch "$EPIC_BRANCH" "$MAIN_BRANCH" 2>/dev/null || true
      else
        TARGET="$MAIN_BRANCH"
      fi

      git checkout "$TARGET" 2>/dev/null
      git pull --rebase --autostash 2>/dev/null || true
      git merge "$BRANCH" --no-ff -m "Merge $BRANCH results" --no-verify

      if [ -z "$EPIC_BRANCH" ]; then
        git push 2>/dev/null && echo "Pushed." || echo "Warning: Push failed."
      fi

      echo "Merged: $BRANCH → $TARGET"
    ) 200>"$LOCK_FILE"
    # ── END LOCKED SECTION ──────────────────────────────────────────────────
    ;;

  discard)
    echo "Discarding agent/$NAME changes..."
    ;;
esac

# ── Cleanup ─────────────────────────────────────────────────────────────────
# Remove symlinks first (they point outside worktree)
rm -f "$WORKTREE/.beads" 2>/dev/null || true
rm -f "$WORKTREE/.venv" 2>/dev/null || true

cd "$PROJECT"
git worktree remove "$WORKTREE" --force 2>/dev/null || {
  rm -rf "$WORKTREE"
  git worktree prune
}
git branch -D "$BRANCH" 2>/dev/null || true

echo "Cleaned up: $NAME"
```

## Success Criteria

- [ ] flock wraps git checkout + merge + push (no concurrent merge race)
- [ ] Optional --epic flag merges to integration branch instead of main
- [ ] git pull before merge picks up prior agent merges
- [ ] Symlinks (.beads/, .venv/) removed before worktree removal
- [ ] KG check and bead check still run (before the locked section)
- [ ] Usage updated: cleanup.sh <name> <merge|discard> [epic_branch]

## Verification

```bash
# Test merge locking: simulate two concurrent merges
# Terminal 1:
bash .claude/scripts/cleanup.sh agent-a merge &

# Terminal 2 (immediately):
bash .claude/scripts/cleanup.sh agent-b merge &

# Expected: second merge waits for first to finish, then succeeds
# (not both failing with git checkout conflict)
```
