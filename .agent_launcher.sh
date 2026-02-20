#!/bin/bash
# Prevent nested Claude Code detection
unset CLAUDECODE
# Export API keys so agent subprocesses (Python scripts) can access them.
# Claude Code uses subscription auth regardless.
export ANTHROPIC_API_KEY OPENAI_API_KEY GITHUB_TOKEN 2>/dev/null
cd "/home/rahil/agents/reactive-20260220_123442"
PROMPT=$(cat .agent_prompt.txt)
SYSPROMPT=$(cat .agent_sysprompt.txt)
claude -p "$PROMPT" --dangerously-skip-permissions --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' --mcp-config .mcp.json --append-system-prompt "$SYSPROMPT"
EXIT_CODE=$?
echo "$EXIT_CODE" > .agent_exit_code
echo ""
echo "=== AGENT DONE (exit $EXIT_CODE) ==="
echo "Type next prompt or press Ctrl+D to exit"
claude --continue --dangerously-skip-permissions
