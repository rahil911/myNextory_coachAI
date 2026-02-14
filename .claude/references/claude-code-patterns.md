# Claude Code CLI Patterns Reference

This document contains everything agents need to know about using Claude Code CLI for spawning sub-agents, headless sessions, and multi-agent coordination.

---

## Claude Code CLI Flags

| Flag | Short | Purpose |
|------|-------|---------|
| `-p "prompt"` | | Headless mode — run prompt and exit |
| `--dangerously-skip-permissions` | `--yes` | Skip all permission prompts (required for unattended agents) |
| `--allowedTools "Read,Edit,Bash,Glob,Grep,mcp__*"` | | Auto-approve specific tools |
| `--output-format json\|stream-json\|text` | | Output format |
| `--mcp-config .mcp.json` | | Load MCP servers from config file |
| `--model claude-opus-4-6` | | Select model (opus, sonnet, haiku) |
| `--resume SESSION_ID` | | Resume a previous session |
| `--resume SESSION_ID --fork-session` | | Fork a session (branch investigation) |
| `--append-system-prompt "..."` | | Add instructions to system prompt |
| `--continue` | `-c` | Continue the last conversation |
| `--permissionMode bypassPermissions` | | Skip all permission checks |

---

## Session Modes

### Interactive (human-in-the-loop)
```bash
claude --dangerously-skip-permissions --mcp-config .mcp.json
```

### Headless (scripted, unattended)
```bash
claude -p "Your task here" --yes --mcp-config .mcp.json --output-format text
```

### Piped (Unix pipeline)
```bash
echo "Fix the bug in src/main.py" | claude -p - --yes
```

### Resume (continue previous session)
```bash
claude --resume SESSION_ID --yes
```

---

## Git Worktree Isolation Pattern

Each agent gets its own git worktree so agents never interfere with each other or main.

### Create Worktree
```bash
# From the main repo:
cd ~/Projects/baap
git worktree add ~/agents/agent-name -b agent/agent-name

# Now ~/agents/agent-name/ is a full copy of the repo on its own branch
```

### Work in Worktree
```bash
cd ~/agents/agent-name
# Edit files, run commands — changes only affect this branch
git add -A
git commit -m "Agent work: description"
```

### Merge Back to Main
```bash
cd ~/Projects/baap
git merge agent/agent-name --no-ff -m "Merge agent/agent-name work"
```

### Cleanup
```bash
cd ~/Projects/baap
git worktree remove ~/agents/agent-name --force
git branch -D agent/agent-name
```

---

## tmux Session Management

All agents run in tmux so they persist if SSH drops and can be monitored.

### Create tmux Session
```bash
# Create session (if not exists)
tmux new-session -d -s baap-agents -n monitor

# Add a window for a new agent
tmux new-window -t baap-agents -n agent-name "cd ~/agents/agent-name && claude -p 'task' --yes"
```

### Monitor
```bash
# Attach to see all agent windows
tmux attach -t baap-agents

# Navigate: Ctrl+B then window number (0, 1, 2...)
# Detach: Ctrl+B then d
```

### Kill an Agent Window
```bash
tmux send-keys -t baap-agents:agent-name C-c Enter
```

---

## Spawning a Headless Agent (Full Pattern)

```bash
#!/usr/bin/env bash
# Complete pattern for spawning an isolated agent

AGENT_NAME="db-agent-001"
PROMPT="Read your spec and work on bead XYZ"
PROJECT="$HOME/Projects/baap"
AGENT_DIR="$HOME/agents/$AGENT_NAME"

# 1. Create isolated worktree
cd "$PROJECT"
git worktree add "$AGENT_DIR" -b "agent/$AGENT_NAME"

# 2. Ensure tmux session exists
tmux has-session -t baap-agents 2>/dev/null || tmux new-session -d -s baap-agents -n monitor

# 3. Build Claude command
MCP_FLAG=""
[ -f "$AGENT_DIR/.mcp.json" ] && MCP_FLAG="--mcp-config .mcp.json"

CLAUDE_CMD="cd $AGENT_DIR && claude -p '$PROMPT' --yes --allowedTools 'Read,Edit,Bash,Glob,Grep,Write,mcp__*' $MCP_FLAG"

# 4. Launch in tmux window
tmux new-window -t baap-agents -n "$AGENT_NAME" "$CLAUDE_CMD"

echo "Agent launched: $AGENT_NAME"
echo "Monitor: tmux attach -t baap-agents"
```

---

## Model Selection

```bash
# Opus — for orchestration, planning, code review
claude -p "..." --model claude-opus-4-6 --yes

# Sonnet — default, for implementation
claude -p "..." --yes

# Haiku — for focused, simple tasks (fastest, cheapest)
claude -p "..." --model claude-haiku-4-5-20251001 --yes
```

---

## Sub-Agents Within Claude Code (Task Tool)

When running INSIDE a Claude Code session, you can spawn sub-agents using the built-in Task tool. These run as child processes within your session — no worktrees or tmux needed.

```
Task(
  subagent_type="general-purpose",
  prompt="Read the spec at .claude/PRD/agents/01a.md and execute it",
  mode="bypassPermissions"
)
```

This is simpler than headless sessions and is the RIGHT choice for:
- Build-phase agents (Phases 0-4)
- Short-lived tasks (< 30 minutes)
- Tasks that don't need file isolation

Use headless sessions + worktrees for:
- Runtime agents that work in parallel
- Long-running tasks
- Tasks that might conflict with each other's file edits

---

## Beads CLI (bd) — Task Tracking

```bash
# Install (if not already)
pip install beads-cli  # or: cargo install beads

# Initialize in repo
bd init

# Find work
bd ready

# Create task
bd create --title="Task description" --type=task --priority=2

# Claim and work
bd update BEAD_ID --status=in_progress

# Complete
bd close BEAD_ID --reason="What was done"

# Sync with git
bd sync
```

---

## Cross-Machine Agent Dispatch

```bash
# From Mac, dispatch work to India:
ssh india-linux "cd ~/Projects/baap && bash .claude/scripts/spawn.sh reactive 'Task prompt here' ~/Projects/baap"
```

---

## Cost Awareness

| Mode | Relative Cost |
|------|---------------|
| Single headless session (`claude -p`) | 1x |
| Task tool sub-agent (within session) | 0.5-1x |
| 3-agent team | ~4x |
| 5+ agent swarm | ~7x |

Claude Max subscription handles substantial usage. Default to single sessions and Task tool sub-agents. Use headless multi-agent swarms only for parallel work that justifies the cost.
