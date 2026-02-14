# Phase 1a: Harden spawn.sh

## Purpose

spawn.sh is the entry point for every agent. It must be bulletproof.
Currently it creates a worktree and launches claude, but has 6 critical gaps.

## Risks Mitigated

- Risk 1: .beads/ inaccessible from worktrees (SHOWSTOPPER)
- Risk 3: Agent doesn't know its own name (HIGH)
- Risk 6: No timeout enforcement (HIGH)
- Risk 7: MCP server cold start / venv per worktree (MEDIUM-HIGH)
- Risk 11: spawn.sh may not pass --mcp-config (HIGH)
- Risk 13: No pre-flight check for tool availability (HIGH)

## Current spawn.sh Location

`.claude/scripts/spawn.sh`

## Required Changes

Read the current spawn.sh first, then rewrite it with ALL of the following fixes.

### Fix 1: Symlink .beads/ from main repo into worktree

After `git worktree add`, before launching claude:

```bash
# .beads/ is gitignored — agents need it for bead communication
# Symlink from main repo so all agents share the same beads database
MAIN_REPO="$(git rev-parse --show-toplevel)"
if [ -d "$MAIN_REPO/.beads" ]; then
  ln -sfn "$MAIN_REPO/.beads" "$WORKTREE/.beads"
  echo "Symlinked .beads/ from main repo"
fi
```

This is the MOST CRITICAL fix. Without it, agents cannot read, update, or close beads.
The entire communication protocol depends on this.

### Fix 2: Pass agent name explicitly

The agent needs to know WHO it is. Add an AGENT_NAME parameter:

```bash
# Usage: spawn.sh <mode> <prompt> <repo_path> [agent_name]
AGENT_NAME="${4:-$NAME}"  # Default to generated name if not provided
```

Inject identity into the prompt:
```bash
FULL_PROMPT="You are agent '$AGENT_NAME'. $PROMPT"
```

And export as env var for scripts:
```bash
export AGENT_NAME="$AGENT_NAME"
```

### Fix 3: Pass --mcp-config with absolute path

MCP config must work from the worktree directory:

```bash
MCP_CONFIG="$MAIN_REPO/.mcp.json"
if [ -f "$MCP_CONFIG" ]; then
  CLAUDE_FLAGS="$CLAUDE_FLAGS --mcp-config $MCP_CONFIG"
fi
```

Use ABSOLUTE path to the main repo's .mcp.json, not relative. This ensures MCP servers
can find their Python scripts and KG cache regardless of CWD.

### Fix 4: Timeout enforcement

Add timeout based on agent level. Accept as optional parameter or default to L1:

```bash
# Usage: spawn.sh <mode> <prompt> <repo_path> [agent_name] [level]
LEVEL="${5:-1}"

case "$LEVEL" in
  0) TIMEOUT_SECS=0 ;;        # L0: no timeout (orchestrator)
  1) TIMEOUT_SECS=7200 ;;     # L1: 2 hours
  2) TIMEOUT_SECS=3600 ;;     # L2: 1 hour
  3) TIMEOUT_SECS=1800 ;;     # L3: 30 minutes
  *) TIMEOUT_SECS=3600 ;;     # Default: 1 hour
esac

# Wrap claude command with timeout (0 = no timeout)
if [ "$TIMEOUT_SECS" -gt 0 ]; then
  CLAUDE_CMD="timeout $TIMEOUT_SECS $CLAUDE_CMD"
fi
```

### Fix 5: Symlink .venv/ to avoid cold start

Each worktree creating its own venv = minutes of pip install. Share the main repo's venv:

```bash
if [ -d "$MAIN_REPO/.venv" ]; then
  ln -sfn "$MAIN_REPO/.venv" "$WORKTREE/.venv"
  echo "Symlinked .venv/ from main repo"
fi
```

### Fix 6: Pre-flight check

Before doing anything, verify tools exist:

```bash
preflight_check() {
  local MISSING=0
  for tool in claude bd git tmux; do
    if ! command -v "$tool" &>/dev/null; then
      echo "ERROR: $tool not found in PATH" >&2
      MISSING=$((MISSING + 1))
    fi
  done
  if [ "$MISSING" -gt 0 ]; then
    echo "Pre-flight check failed. Install missing tools." >&2
    exit 1
  fi
}

preflight_check
```

## Full Rewrite Template

The new spawn.sh should follow this structure:

```bash
#!/usr/bin/env bash
# spawn.sh — Spawn a Claude Code agent in an isolated git worktree
#
# Usage:
#   spawn.sh <mode> <prompt> <repo_path> [agent_name] [level]
#
# Arguments:
#   mode        - reactive|proactive|team
#   prompt      - The task prompt for the agent
#   repo_path   - Absolute path to the main repository
#   agent_name  - Agent identity (default: auto-generated from mode+timestamp)
#   level       - Agent level 0-3 for timeout enforcement (default: 1)
#
# Examples:
#   spawn.sh reactive "bd show baap-abc && work on it" ~/Projects/baap identity-agent 1
#   spawn.sh reactive "bd show baap-xyz" ~/Projects/baap db-agent 1
set -euo pipefail

MODE="${1:?Usage: spawn.sh <mode> <prompt> <repo_path> [agent_name] [level]}"
PROMPT="${2:?Missing prompt}"
REPO="${3:?Missing repo path}"
NAME="${4:-${MODE}-$(date +%Y%m%d_%H%M%S)}"
LEVEL="${5:-1}"
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
WORKTREE="$AGENT_DIR/$NAME"
BRANCH="agent/$NAME"
TMUX_SESSION="${TMUX_SESSION_NAME:-agents}"

# ── Pre-flight ───────────────────────────────────────────────────────────────
for tool in claude bd git tmux; do
  command -v "$tool" &>/dev/null || { echo "ERROR: $tool not in PATH" >&2; exit 1; }
done

# Resolve main repo root (handles both repo path and worktree path)
MAIN_REPO="$(cd "$REPO" && git rev-parse --show-toplevel)"

# ── Timeout ──────────────────────────────────────────────────────────────────
case "$LEVEL" in
  0) TIMEOUT_SECS=0 ;;
  1) TIMEOUT_SECS=7200 ;;
  2) TIMEOUT_SECS=3600 ;;
  3) TIMEOUT_SECS=1800 ;;
  *) TIMEOUT_SECS=3600 ;;
esac

# ── Create worktree ──────────────────────────────────────────────────────────
mkdir -p "$AGENT_DIR"
cd "$MAIN_REPO"
git worktree add "$WORKTREE" -b "$BRANCH" HEAD 2>/dev/null || {
  echo "Worktree or branch already exists. Cleaning up..."
  git worktree remove "$WORKTREE" --force 2>/dev/null || true
  git branch -D "$BRANCH" 2>/dev/null || true
  git worktree add "$WORKTREE" -b "$BRANCH" HEAD
}

# ── Symlinks (shared state) ─────────────────────────────────────────────────
# .beads/ — CRITICAL: agents need shared beads for communication
if [ -d "$MAIN_REPO/.beads" ]; then
  ln -sfn "$MAIN_REPO/.beads" "$WORKTREE/.beads"
fi

# .venv/ — avoid cold start (minutes of pip install per worktree)
if [ -d "$MAIN_REPO/.venv" ]; then
  ln -sfn "$MAIN_REPO/.venv" "$WORKTREE/.venv"
fi

# ── Build claude command ─────────────────────────────────────────────────────
MCP_CONFIG="$MAIN_REPO/.mcp.json"
FULL_PROMPT="You are agent '$NAME'. Your agent level is L${LEVEL}. ${PROMPT}"

CLAUDE_CMD="claude -p \"$FULL_PROMPT\" --dangerously-skip-permissions"

# MCP config (absolute path so it works from worktree)
if [ -f "$MCP_CONFIG" ]; then
  CLAUDE_CMD="$CLAUDE_CMD --mcp-config $MCP_CONFIG"
fi

# Model tiering
case "$LEVEL" in
  0) CLAUDE_CMD="$CLAUDE_CMD --model claude-opus-4-6" ;;
  1) CLAUDE_CMD="$CLAUDE_CMD --model claude-sonnet-4-5-20250929" ;;
  *) CLAUDE_CMD="$CLAUDE_CMD --model claude-haiku-4-5-20251001" ;;
esac

# Timeout wrapper
if [ "$TIMEOUT_SECS" -gt 0 ]; then
  CLAUDE_CMD="timeout ${TIMEOUT_SECS}s $CLAUDE_CMD"
fi

# ── Ensure tmux session ─────────────────────────────────────────────────────
tmux has-session -t "$TMUX_SESSION" 2>/dev/null || tmux new-session -d -s "$TMUX_SESSION"

# ── Launch in tmux window ───────────────────────────────────────────────────
tmux new-window -t "$TMUX_SESSION" -n "$NAME" "cd $WORKTREE && export AGENT_NAME=$NAME && export AGENT_LEVEL=$LEVEL && $CLAUDE_CMD; echo 'Agent $NAME finished. Press Enter to close.'; read"

echo "Spawned agent '$NAME' (L${LEVEL}) in worktree: $WORKTREE"
echo "Monitor: tmux attach -t $TMUX_SESSION"
echo "Timeout: ${TIMEOUT_SECS}s ($(( TIMEOUT_SECS / 60 ))min)"
```

## Success Criteria

- [ ] spawn.sh accepts 5 args: mode, prompt, repo_path, agent_name, level
- [ ] Pre-flight check validates claude, bd, git, tmux in PATH
- [ ] .beads/ symlinked from main repo into worktree
- [ ] .venv/ symlinked from main repo into worktree
- [ ] Agent name passed in prompt and as AGENT_NAME env var
- [ ] --mcp-config uses absolute path to main repo's .mcp.json
- [ ] Timeout applied based on agent level
- [ ] Model selected based on agent level (Opus/Sonnet/Haiku)
- [ ] tmux session created if not exists
- [ ] Agent launched in named tmux window

## Verification

```bash
# Dry run: spawn a test agent, verify worktree structure
bash .claude/scripts/spawn.sh reactive "echo test" ~/Projects/baap test-agent 2

# Check worktree
ls ~/agents/test-agent/.beads    # Should be symlink
ls ~/agents/test-agent/.venv     # Should be symlink
ls ~/agents/test-agent/.claude/  # Should have CLAUDE.md, mcp/, kg/, etc.

# Cleanup
bash .claude/scripts/cleanup.sh test-agent discard
```
