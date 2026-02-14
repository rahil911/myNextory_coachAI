#!/usr/bin/env bash
# spawn.sh — Spawn a Claude agent in an isolated git worktree + tmux window
#
# Usage:
#   spawn.sh <type> <prompt> [project_path]
#
# Types:
#   reactive   — User-triggered investigation (stays open for interaction)
#   proactive  — Scheduled task (auto-cleanup on completion)
#   team       — Agent team with parallel teammates
#
# Examples:
#   spawn.sh reactive "Investigate ROAS breach" ~/Projects/my-repo
#   spawn.sh proactive "Run health check" ~/Projects/my-repo
#   spawn.sh team "Complex analysis with 3 specialists" ~/Projects/my-repo
set -euo pipefail

TYPE="${1:?Usage: spawn.sh <reactive|proactive|team> <prompt> [project_path]}"
PROMPT="${2:?Missing prompt}"
PROJECT="${3:-$(pwd)}"
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
TMUX_SESSION="${AGENT_TMUX_SESSION:-agents}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
NAME="${TYPE}-${TIMESTAMP}"

# ── Validate ─────────────────────────────────────────────────────────────────
if [ ! -d "$PROJECT/.git" ]; then
  echo "Error: $PROJECT is not a git repo" >&2
  exit 1
fi

# ── Ensure tmux session exists ───────────────────────────────────────────────
if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
  tmux new-session -d -s "$TMUX_SESSION" -n "monitor"
  echo "Created tmux session: $TMUX_SESSION"
fi

# ── Create git worktree ─────────────────────────────────────────────────────
mkdir -p "$AGENT_DIR"
cd "$PROJECT"
git worktree add "$AGENT_DIR/$NAME" -b "agent/$NAME" 2>/dev/null || {
  # Branch may already exist, try without -b
  git worktree add "$AGENT_DIR/$NAME" "agent/$NAME" 2>/dev/null || {
    echo "Error: Failed to create worktree at $AGENT_DIR/$NAME" >&2
    exit 1
  }
}
echo "Created worktree: $AGENT_DIR/$NAME (branch: agent/$NAME)"

# ── Build Claude command ─────────────────────────────────────────────────────
CLAUDE_CMD="cd $AGENT_DIR/$NAME"

# MCP config (use project's if exists)
if [ -f "$AGENT_DIR/$NAME/.mcp.json" ]; then
  MCP_FLAG="--mcp-config .mcp.json"
else
  MCP_FLAG=""
fi

case "$TYPE" in
  reactive)
    # Interactive mode — user can jump in and interact
    CLAUDE_CMD="$CLAUDE_CMD && claude -p '${PROMPT//\'/\\\'}' --yes --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' $MCP_FLAG"
    CLAUDE_CMD="$CLAUDE_CMD; echo ''; echo '=== AGENT DONE === Type next prompt or press Ctrl+D to exit'; claude --continue --yes"
    ;;
  proactive)
    # Headless — run, save results, auto-cleanup
    CLAUDE_CMD="$CLAUDE_CMD && claude -p '${PROMPT//\'/\\\'}' --yes --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' $MCP_FLAG --output-format text"
    CLAUDE_CMD="$CLAUDE_CMD && echo '=== AUTO-CLEANUP ===' && cd $PROJECT && git add $AGENT_DIR/$NAME && git stash 2>/dev/null; true"
    ;;
  team)
    # Agent team with parallel teammates
    CLAUDE_CMD="$CLAUDE_CMD && CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 claude -p '${PROMPT//\'/\\\'}' --yes --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' $MCP_FLAG --teammate-mode tmux"
    CLAUDE_CMD="$CLAUDE_CMD; echo ''; echo '=== TEAM DONE === Press enter to close'; read"
    ;;
  *)
    echo "Error: Unknown type '$TYPE'. Use: reactive, proactive, team" >&2
    exit 1
    ;;
esac

# ── Launch in tmux ───────────────────────────────────────────────────────────
tmux new-window -t "$TMUX_SESSION" -n "$NAME" "$CLAUDE_CMD"
echo "Launched agent: $NAME (tmux window in session '$TMUX_SESSION')"
echo ""
echo "Monitor:  tmux attach -t $TMUX_SESSION"
echo "Cleanup:  $(dirname "$0")/cleanup.sh $NAME merge"
