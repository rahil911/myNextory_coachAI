#!/usr/bin/env bash
# spawn.sh -- Spawn a Claude agent in an isolated git worktree + tmux window
#
# Usage:
#   spawn.sh <type> <prompt> [project_path] [--bead BEAD_ID]
#
# Types:
#   reactive   -- User-triggered investigation (stays open for interaction)
#   proactive  -- Scheduled task (auto-cleanup on completion)
#   team       -- Agent team with parallel teammates
#
# Examples:
#   spawn.sh reactive "Investigate ROAS breach" ~/Projects/my-repo --bead BC-a7x
#   spawn.sh proactive "Run health check" ~/Projects/my-repo
set -euo pipefail

TYPE="${1:?Usage: spawn.sh <reactive|proactive|team> <prompt> [project_path] [--bead BEAD_ID]}"
PROMPT="${2:?Missing prompt}"
PROJECT="${3:-$(pwd)}"
BEAD_ID=""
AGENT_NAME=""

# Parse optional flags
shift 3 2>/dev/null || shift $#
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bead) BEAD_ID="$2"; shift 2 ;;
    --agent-name) AGENT_NAME="$2"; shift 2 ;;
    *) shift ;;
  esac
done

AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
TMUX_SESSION="${AGENT_TMUX_SESSION:-agents}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
# Use provided agent name or default to type-timestamp
if [ -n "$AGENT_NAME" ]; then
  NAME="${AGENT_NAME}"
else
  NAME="${TYPE}-${TIMESTAMP}"
fi
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"

# -- Validate ----------------------------------------------------------------
if [ ! -d "$PROJECT/.git" ]; then
  echo "Error: $PROJECT is not a git repo" >&2
  exit 1
fi

# -- Ensure tmux session exists (works non-interactively from subprocess) ----
export TERM="${TERM:-xterm-256color}"
if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
  tmux new-session -d -s "$TMUX_SESSION" -n "monitor" 2>/dev/null || {
    echo "Warning: Could not create tmux session '$TMUX_SESSION'. Is tmux installed?" >&2
    exit 1
  }
  echo "Created tmux session: $TMUX_SESSION"
fi

# -- Create git worktree ----------------------------------------------------
mkdir -p "$AGENT_DIR"
cd "$PROJECT"
git worktree add "$AGENT_DIR/$NAME" -b "agent/$NAME" 2>/dev/null || {
  git worktree add "$AGENT_DIR/$NAME" "agent/$NAME" 2>/dev/null || {
    echo "Error: Failed to create worktree at $AGENT_DIR/$NAME" >&2
    exit 1
  }
}
echo "Created worktree: $AGENT_DIR/$NAME (branch: agent/$NAME)"

# -- Checkpoint system prompt injection --------------------------------------
CHECKPOINT_INSTRUCTION="IMPORTANT: You MUST checkpoint your progress periodically. After completing each major subtask, after every ~15 minutes of work, and before risky operations: (1) Write a structured checkpoint to your memory file (.claude/agents/*/memory/MEMORY.md) with Completed/Next/Files/Decisions sections. (2) Update the bead notes with a condensed version: bd update BEAD_ID --notes=\"Checkpoint: summary\". (3) Commit your work: git add -A && git commit -m \"checkpoint: summary\" --no-verify. This ensures your progress survives if the session times out or hits context limits."

if [ -n "$BEAD_ID" ]; then
  CHECKPOINT_INSTRUCTION="You are working on bead $BEAD_ID. $CHECKPOINT_INSTRUCTION"
fi

# -- Agent identity injection -----------------------------------------------
AGENT_IDENTITY=""
if [ -n "$AGENT_NAME" ]; then
  AGENT_SPEC="$PROJECT/.claude/agents/$AGENT_NAME/agent.md"
  AGENT_MEMORY="$PROJECT/.claude/agents/$AGENT_NAME/memory/MEMORY.md"
  if [ -f "$AGENT_SPEC" ]; then
    AGENT_IDENTITY="You are $AGENT_NAME. Your agent spec follows:\n\n$(cat "$AGENT_SPEC")\n\n"
  fi
  if [ -f "$AGENT_MEMORY" ]; then
    AGENT_IDENTITY="${AGENT_IDENTITY}Your persistent memory follows:\n\n$(cat "$AGENT_MEMORY")\n\n"
  fi
fi

# -- Build Claude command ----------------------------------------------------
CLAUDE_CMD="cd $AGENT_DIR/$NAME"

# MCP config (use project's if exists)
if [ -f "$AGENT_DIR/$NAME/.mcp.json" ]; then
  MCP_FLAG="--mcp-config .mcp.json"
else
  MCP_FLAG=""
fi

# Escape prompt for shell embedding
ESCAPED_PROMPT="${PROMPT//\'/\\\'}"
ESCAPED_CHECKPOINT="${CHECKPOINT_INSTRUCTION//\'/\\\'}"
ESCAPED_IDENTITY="${AGENT_IDENTITY//\'/\\\'}"

# Combine system prompt: identity + checkpoint instructions
SYSTEM_PROMPT="${ESCAPED_IDENTITY}${ESCAPED_CHECKPOINT}"

case "$TYPE" in
  reactive)
    CLAUDE_CMD="$CLAUDE_CMD && claude -p '$ESCAPED_PROMPT' --yes --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' $MCP_FLAG --append-system-prompt '$SYSTEM_PROMPT'"
    CLAUDE_CMD="$CLAUDE_CMD; EXIT_CODE=\$?; echo ''; echo '=== AGENT DONE (exit \$EXIT_CODE) ==='"
    # Store exit code and metadata for retry-agent.sh
    CLAUDE_CMD="$CLAUDE_CMD; echo \"\$EXIT_CODE\" > $AGENT_DIR/$NAME/.agent_exit_code"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$BEAD_ID' > $AGENT_DIR/$NAME/.agent_bead_id"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$ESCAPED_PROMPT' > $AGENT_DIR/$NAME/.agent_original_prompt"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$TYPE' > $AGENT_DIR/$NAME/.agent_type"
    CLAUDE_CMD="$CLAUDE_CMD; echo 'Type next prompt or press Ctrl+D to exit'; claude --continue --yes"
    ;;
  proactive)
    CLAUDE_CMD="$CLAUDE_CMD && claude -p '$ESCAPED_PROMPT' --yes --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' $MCP_FLAG --output-format text --append-system-prompt '$SYSTEM_PROMPT'"
    CLAUDE_CMD="$CLAUDE_CMD; EXIT_CODE=\$?; echo \"\$EXIT_CODE\" > $AGENT_DIR/$NAME/.agent_exit_code"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$BEAD_ID' > $AGENT_DIR/$NAME/.agent_bead_id"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$ESCAPED_PROMPT' > $AGENT_DIR/$NAME/.agent_original_prompt"
    CLAUDE_CMD="$CLAUDE_CMD; echo '$TYPE' > $AGENT_DIR/$NAME/.agent_type"
    # Auto-retry if timed out with checkpoint
    CLAUDE_CMD="$CLAUDE_CMD; if [ \"\$EXIT_CODE\" = '124' ] && [ -f '.claude/agents/*/memory/MEMORY.md' ]; then echo '=== TIMEOUT WITH CHECKPOINT -- AUTO-RETRYING ==='; $SCRIPTS_DIR/retry-agent.sh $AGENT_DIR/$NAME; fi"
    CLAUDE_CMD="$CLAUDE_CMD && echo '=== AUTO-CLEANUP ===' && cd $PROJECT && git add $AGENT_DIR/$NAME && git stash 2>/dev/null; true"
    ;;
  team)
    CLAUDE_CMD="$CLAUDE_CMD && CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 claude -p '$ESCAPED_PROMPT' --yes --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' $MCP_FLAG --teammate-mode tmux --append-system-prompt '$SYSTEM_PROMPT'"
    CLAUDE_CMD="$CLAUDE_CMD; EXIT_CODE=\$?; echo \"\$EXIT_CODE\" > $AGENT_DIR/$NAME/.agent_exit_code"
    CLAUDE_CMD="$CLAUDE_CMD; echo ''; echo '=== TEAM DONE (exit \$EXIT_CODE) === Press enter to close'; read"
    ;;
  *)
    echo "Error: Unknown type '$TYPE'. Use: reactive, proactive, team" >&2
    exit 1
    ;;
esac

# -- Launch in tmux ----------------------------------------------------------
tmux new-window -t "$TMUX_SESSION" -n "$NAME" "$CLAUDE_CMD"
echo "Launched agent: $NAME (tmux window in session '$TMUX_SESSION')"
echo ""
echo "Monitor:  tmux attach -t $TMUX_SESSION"
echo "Retry:    $(dirname "$0")/retry-agent.sh $AGENT_DIR/$NAME"
echo "Cleanup:  $(dirname "$0")/cleanup.sh $NAME merge"
