#!/bin/bash
# Prevent nested Claude Code detection
unset CLAUDECODE
# Strip API keys so Claude Code uses subscription auth, not API billing.
# App code (tag_content.py etc.) loads .env directly when it needs API keys.
unset ANTHROPIC_API_KEY OPENAI_API_KEY 2>/dev/null
cd "/home/rahil/agents/reactive-20260219_221707"
PROMPT=$(cat .agent_prompt.txt)
SYSPROMPT=$(cat .agent_sysprompt.txt)
claude -p "$PROMPT" --dangerously-skip-permissions --allowedTools 'Read,Edit,Bash,Glob,Grep,mcp__*' --mcp-config .mcp.json --append-system-prompt "$SYSPROMPT"
EXIT_CODE=$?
echo "$EXIT_CODE" > .agent_exit_code
echo ""
echo "=== AGENT DONE (exit $EXIT_CODE) ==="
echo "Type next prompt or press Ctrl+D to exit"
claude --continue --dangerously-skip-permissions
