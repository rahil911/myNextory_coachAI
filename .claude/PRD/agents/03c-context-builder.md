# Phase 3c: Context Builder

## Purpose

Build the operational context for the agent swarm: agent spec files, agent memory directories, and verify that the agent-infra scripts (spawn.sh, cleanup.sh) and Claude Code reference doc are in place. This is the "connective tissue" that makes agents functional.

## Phase Info

- **Phase**: 3c (parallel with 3a, 3b, 3d — runs after Phase 2 gate)
- **Estimated time**: 30-45 minutes
- **Model tier**: Sonnet

## Input Contract

- **File**: `.claude/kg/agent_graph_cache.json` (from Phase 2a) — agent list
- **File**: `.claude/kg/seeds/agents.csv` (from Phase 2a) — agent definitions
- **File**: `.claude/CLAUDE.md` — ALREADY EXISTS (from PRD)
- **File**: `.claude/scripts/spawn.sh` — ALREADY EXISTS (from PRD)
- **File**: `.claude/scripts/cleanup.sh` — ALREADY EXISTS (from PRD)
- **File**: `.claude/references/claude-code-patterns.md` — ALREADY EXISTS (from PRD)

## Output Contract

- **Files**: `.claude/agents/{name}/agent.md` for each agent
- **Files**: `.claude/agents/{name}/memory/MEMORY.md` for each agent
- **Verification**: All pre-existing files confirmed present

## Step-by-Step Instructions

### 1. Verify Pre-Existing Files

These files were placed by the PRD writer and should already exist. Verify them:

```bash
echo "Checking pre-existing files..."
test -f .claude/CLAUDE.md && echo "  CLAUDE.md: OK" || echo "  ERROR: CLAUDE.md missing!"
test -f .claude/scripts/spawn.sh && echo "  spawn.sh: OK" || echo "  ERROR: spawn.sh missing!"
test -f .claude/scripts/cleanup.sh && echo "  cleanup.sh: OK" || echo "  ERROR: cleanup.sh missing!"
test -f .claude/references/claude-code-patterns.md && echo "  claude-code-patterns.md: OK" || echo "  ERROR: patterns doc missing!"
test -x .claude/scripts/spawn.sh && echo "  spawn.sh executable: OK" || chmod +x .claude/scripts/spawn.sh
test -x .claude/scripts/cleanup.sh && echo "  cleanup.sh executable: OK" || chmod +x .claude/scripts/cleanup.sh
```

If any are missing, that's a critical error — stop and report to the build orchestrator.

### 2. Read Agent List from KG

```bash
python3 -c "
import json
d = json.load(open('.claude/kg/agent_graph_cache.json'))
agents = [n for n in d['nodes'] if n['type'] == 'agent']
for a in agents:
    print(f\"{a['id']}: level={a['level']}, tier={a.get('model_tier', 'sonnet')}, module={a.get('module', 'none')}\")
"
```

### 3. Create Agent Directories and Specs

For EACH agent in the KG, create its directory structure and spec:

```bash
mkdir -p .claude/agents/{agent-name}/memory
```

#### Template: agent.md

```markdown
# {Agent Name}

## Identity
- **ID**: {agent-id}
- **Level**: {level} (L0=orchestrator, L1=domain, L2=sub-domain, L3=micro)
- **Parent**: {parent-agent-id}
- **Model Tier**: {model_tier}
- **Module**: {module-id}

## Capabilities
{comma-separated capabilities list}

## Owned Files
Query: `get_agent_files("{agent-id}")`
(Ownership is dynamic — always query the KG for current ownership)

## Dependencies
- **Depends on**: {list from KG edges where type=DEPENDS_ON}
- **Depended by**: {list from KG edges where this agent is the target}

## Work Protocol
1. Read this spec and your memory at `memory/MEMORY.md`
2. Check your bead: `bd show <bead-id>`
3. Query full context: `get_agent_context("{agent-id}")`
4. Do your work — ONLY edit files you own
5. Update memory with changes
6. Close bead, notify dependents

## Claude Code Reference
See `.claude/references/claude-code-patterns.md` for:
- How to spawn sub-agents (headless sessions or Task tool)
- Git worktree isolation patterns
- tmux session management
- Beads CLI commands

## Module Responsibility
{Description of what this agent's module covers}

## Safety
- Max children: {max_children}
- Timeout: {timeout_minutes} minutes
- Review required: {review_required}
- Can spawn sub-agents: {can_spawn}
```

#### Specific Agent Specs

Create these agent specs based on KG data:

**orchestrator/agent.md** — L0:
- Manages the full system, NEVER implements
- Creates beads with specs, sets dependencies
- Queries KG for blast radius
- Monitors via `bd list`, `bd graph`
- Reference: `.claude/references/claude-code-patterns.md` for spawning agents

**db-agent/agent.md** — L1 database:
- Owns database models, migrations, seeds
- MariaDB expertise (DDL, indexes, optimization)
- Creates notification beads on schema changes
- All other agents depend on this for schema

**api-agent/agent.md** — L1 API:
- Owns API endpoints (FastAPI)
- CRUD, auth, middleware
- Depends on db-agent, depended by ui-agent

**ui-agent/agent.md** — L1 frontend:
- Owns frontend (React/Next.js)
- Pages, components, styles
- Depends on api-agent

**test-agent/agent.md** — L1 testing:
- Owns test files
- Depends on api-agent and db-agent

**kg-agent/agent.md** — L1 knowledge graph:
- Owns KG infrastructure (.claude/kg/, .claude/mcp/)
- Maintains MCP servers, CLI, seeds

**review-agent/agent.md** — L1 reviewer (Opus tier):
- Reviews code before merge
- Fresh context, no shared hallucinations
- Can block merges

### 4. Create Initial Memory Files

For each agent, create `memory/MEMORY.md`:

```markdown
# {Agent Name} Memory

## My Ownership
(Will be populated as the agent starts working)

## Key Decisions
(Will be populated as the agent makes choices)

## Schema Knowledge
(Will be populated as the agent learns about the database)

## Recent Changes
(Will be populated as the agent completes tasks)
```

### 5. Verify Completeness

```bash
echo "=== Agent Infrastructure Verification ==="

AGENT_COUNT=$(ls -d .claude/agents/*/agent.md 2>/dev/null | wc -l)
MEMORY_COUNT=$(ls -d .claude/agents/*/memory/MEMORY.md 2>/dev/null | wc -l)

echo "Agent specs: $AGENT_COUNT"
echo "Memory files: $MEMORY_COUNT"

test $AGENT_COUNT -ge 5 || { echo "ERROR: Expected at least 5 agent specs"; exit 1; }
echo "Agent specs: PASS"

test -f .claude/CLAUDE.md && echo "CLAUDE.md: PASS"
test -x .claude/scripts/spawn.sh && echo "spawn.sh: PASS"
test -x .claude/scripts/cleanup.sh && echo "cleanup.sh: PASS"
test -f .claude/references/claude-code-patterns.md && echo "claude-code-patterns.md: PASS"

echo "=== All checks passed ==="
```

## Success Criteria

1. `.claude/agents/` has subdirectories for each agent in the KG
2. Each agent has `agent.md` with complete spec
3. Each agent has `memory/MEMORY.md` initialized
4. `.claude/CLAUDE.md` exists (verification)
5. `.claude/scripts/spawn.sh` exists and is executable (verification)
6. `.claude/scripts/cleanup.sh` exists and is executable (verification)
7. `.claude/references/claude-code-patterns.md` exists (verification)
8. Agent count matches KG agent node count
