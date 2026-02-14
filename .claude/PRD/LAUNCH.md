# Baap — AI-Native Application Platform: Build Specification

## Vision

Build a fully AI-native software development platform where Claude Code IS the operating system. Every file is owned by an agent, every change is tracked via beads, every relationship lives in a knowledge graph. The human talks to an orchestrator; the orchestrator dispatches work through a multi-level agent swarm that builds, evolves, and maintains the entire application autonomously.

The 205MB MySQL dump (`app-mynextory-backup.sql`) is just the seed data. YOU are building the SYSTEM that will develop the application from this data.


## Prerequisites (Check Before Starting)

Before executing any phase, verify these are available:

```bash
# 1. Claude Code installed
which claude || echo "ERROR: Install Claude Code first"

# 2. Beads CLI installed
which bd || pip install beads-cli || echo "ERROR: Install beads CLI"

# 3. Python 3 available
python3 --version || echo "ERROR: Python 3 required"

# 4. MariaDB client (for Phase 0 onwards)
which mysql || echo "Will be installed by Phase 0"

# 5. Git initialized
test -d .git && echo "Git repo: OK" || echo "Phase 0 will initialize git"
```

## Key Reference Files (Already in Repo)

These were placed here by the PRD writer. Agents should read them as needed:

- **`.claude/CLAUDE.md`** — Operating system instructions for ALL agents
- **`.claude/references/claude-code-patterns.md`** — Claude Code CLI flags, worktree patterns, tmux, headless sessions
- **`.claude/scripts/spawn.sh`** — Spawn an agent in isolated worktree + tmux
- **`.claude/scripts/cleanup.sh`** — Merge agent work back to main + cleanup

## How to Use This File

You are the **build orchestrator**. Your job is to execute the phases below by spawning sub-agents (one per spec file). Each spec file in `.claude/PRD/agents/` contains everything a sub-agent needs: input contracts, output contracts, step-by-step instructions, and success criteria.

### Execution Rules

1. **Read ALL spec files first** before spawning any agents
2. **Respect the phase DAG** — never start a phase until its gate passes
3. **Spawn agents in parallel** within each phase where possible
4. **Validate gates** before proceeding to the next phase
5. **Use beads for tracking** once Phase 4 enables them (phases 0-3 use the task list)
6. **Never skip a phase** — each builds on the previous

### How to Spawn Sub-Agents

For each agent spec, spawn a sub-agent using Claude Code's Task tool:

```
Task(
  subagent_type="general-purpose",
  prompt="Read the spec at .claude/PRD/agents/XX-name.md and execute it completely. Follow every step. Validate all success criteria before reporting done.",
  mode="bypassPermissions"
)
```

For Haiku-tier tasks (simple, focused):
```
Task(
  subagent_type="general-purpose",
  model="haiku",
  prompt="...",
  mode="bypassPermissions"
)
```

---

## Phase DAG

```
PHASE 0: Database Setup (sequential, blocks ALL)
  └── 00-db-setup.md
  GATE: mysql baap -e "SHOW TABLES" returns 100+ tables

PHASE 1: Discovery (3 agents in parallel)
  ├── 01a-schema-extractor.md    → .claude/discovery/schema.json
  ├── 01b-relationship-mapper.md → .claude/discovery/relationships.json
  └── 01c-data-profiler.md       → .claude/discovery/profile.json
  GATE: All 3 JSON files exist and are valid

PHASE 2: Knowledge Graph (2 agents in parallel)
  ├── 02a-kg-builder.md          → .claude/kg/agent_graph_cache.json + seeds/*.csv
  └── 02b-domain-mapper.md       → .claude/kg/seeds/concepts.csv
  GATE: agent_graph_cache.json has nodes > 0 and edges > 0

PHASE 3: Infrastructure (4 agents in parallel)
  ├── 03a-mcp-builder.md         → .claude/mcp/ownership_graph.py
  ├── 03b-db-mcp-builder.md      → .claude/mcp/db_tools.py
  ├── 03c-context-builder.md     → .claude/CLAUDE.md + .claude/agents/*/
  └── 03d-cli-builder.md         → .claude/tools/ag
  GATE: MCP servers start without errors, ag stats works

PHASE 4: Integration (sequential, validation)
  └── 04-integrator.md           → .mcp.json, .beads/, integration tests
  GATE: Full cycle test passes (KG query → bead create → owner lookup → bead close)

PHASE 5: First Swarm (optional, end-to-end demo)
  └── 05-first-swarm.md          → Live agent spawned, task completed, merged
  GATE: git log shows agent merge commit, bead closed, memory updated
```

---

## Execution Procedure

### Phase 0 — Database Setup

```
1. Read .claude/PRD/agents/00-db-setup.md
2. Spawn ONE agent to execute it
3. Wait for completion
4. VALIDATE: mysql baap -e "SHOW TABLES" | wc -l  → should be 100+
5. VALIDATE: mysql baap -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='baap'"
```

### Phase 1 — Discovery (parallel)

```
1. Spawn THREE agents simultaneously:
   - Agent 1a: .claude/PRD/agents/01a-schema-extractor.md
   - Agent 1b: .claude/PRD/agents/01b-relationship-mapper.md
   - Agent 1c: .claude/PRD/agents/01c-data-profiler.md
2. Wait for ALL three to complete
3. VALIDATE each output file:
   python3 -c "import json; d=json.load(open('.claude/discovery/schema.json')); print(f'{len(d[\"tables\"])} tables discovered')"
   python3 -c "import json; d=json.load(open('.claude/discovery/relationships.json')); print(f'{len(d[\"relationships\"])} relationships found')"
   python3 -c "import json; d=json.load(open('.claude/discovery/profile.json')); print(f'{len(d[\"tables\"])} tables profiled')"
```

### Phase 2 — Knowledge Graph (parallel)

```
1. Spawn TWO agents simultaneously:
   - Agent 2a: .claude/PRD/agents/02a-kg-builder.md
   - Agent 2b: .claude/PRD/agents/02b-domain-mapper.md
2. Wait for BOTH to complete
3. VALIDATE:
   python3 -c "
   import json
   d = json.load(open('.claude/kg/agent_graph_cache.json'))
   m = d['metadata']
   print(f'{m[\"node_count\"]} nodes, {m[\"edge_count\"]} edges')
   assert m['node_count'] > 0, 'No nodes!'
   assert m['edge_count'] > 0, 'No edges!'
   print('KG validation passed')
   "
```

### Phase 3 — Infrastructure (parallel)

```
1. Spawn FOUR agents simultaneously:
   - Agent 3a: .claude/PRD/agents/03a-mcp-builder.md
   - Agent 3b: .claude/PRD/agents/03b-db-mcp-builder.md
   - Agent 3c: .claude/PRD/agents/03c-context-builder.md
   - Agent 3d: .claude/PRD/agents/03d-cli-builder.md
2. Wait for ALL four to complete
3. VALIDATE:
   - bash .claude/mcp/run_mcp.sh ownership_graph.py --test  (should start without errors)
   - bash .claude/mcp/run_mcp.sh db_tools.py --test
   - python3 .claude/tools/ag stats  (should show node/edge counts)
   - test -f .claude/CLAUDE.md  (should exist)
```

### Phase 4 — Integration

```
1. Spawn ONE agent: .claude/PRD/agents/04-integrator.md
2. This agent:
   - Initializes beads: bd init
   - Creates .mcp.json pointing to both MCP servers
   - Runs smoke tests for all MCP tools
   - Runs E2E test: query KG → create bead → find owner → close bead
3. VALIDATE: integration_passed.flag exists at project root
```

### Phase 5 — First Swarm (optional)

```
1. Spawn ONE agent: .claude/PRD/agents/05-first-swarm.md
2. This agent orchestrates a real multi-agent task:
   - Creates a bead for a simple database task
   - Spawns a domain agent via spawn.sh
   - Domain agent does the work, closes bead, merges
   - Validates the full lifecycle
3. VALIDATE: git log shows merge commit, bead is closed
```

---

## Reference Architecture

This system mirrors **Decision Canvas OS** (`~/Projects/decision-canvas-os/`):
- **Causal-graph MCP server**: `.claude/mcp/causal_graph.py` — dict-based graph, BFS, 7 tools, JSON cache
- **run_mcp.sh**: Venv setup, idempotent, cross-platform runner
- **Agent-infra skill**: `~/.claude/skills/agent-infra/` — spawn.sh, cleanup.sh, worktree isolation

Agents building the MCP servers SHOULD read the reference implementation for patterns. The ownership-graph MCP server should be structurally identical to the causal-graph MCP server.

---

## Safety Limits

```
MAX_SWARM_DEPTH = 4          # L0 → L1 → L2 → L3 (no L4+)
MAX_AGENTS_PER_LEVEL = 10    # No more than 10 agents per parent
MAX_TOTAL_AGENTS = 50        # System-wide limit
BUILD_BUDGET = $50           # Total cost ceiling for full build

TIMEOUTS:
  Phase 0: 30 minutes        # DB setup
  Phase 1: 30 minutes each   # Discovery agents
  Phase 2: 45 minutes each   # KG builders
  Phase 3: 60 minutes each   # Infrastructure
  Phase 4: 30 minutes        # Integration
  Phase 5: 60 minutes        # First swarm

MODEL TIERING:
  Build orchestrator (you): Opus
  Phase 0-1 agents: Sonnet (straightforward work)
  Phase 2 agents: Sonnet (moderate complexity)
  Phase 3 agents: Sonnet (requires careful implementation)
  Phase 4-5 agents: Sonnet (integration + swarm)
```

---

## Success State

When all phases complete, the repo should have:

```
~/Projects/baap/
├── .claude/
│   ├── CLAUDE.md                      ← Operating system for all agents
│   ├── PRD/                           ← These spec files (read-only after build)
│   ├── discovery/
│   │   ├── schema.json                ← Full database schema
│   │   ├── relationships.json         ← FK and naming convention relationships
│   │   └── profile.json               ← Data profiling results
│   ├── kg/
│   │   ├── seeds/
│   │   │   ├── agents.csv             ← Agent definitions
│   │   │   ├── files.csv              ← File ownership
│   │   │   ├── modules.csv            ← Module definitions
│   │   │   ├── concepts.csv           ← Business concepts
│   │   │   └── edges.csv              ← All relationships
│   │   ├── agent_graph_cache.json     ← Built graph (loaded by MCP)
│   │   └── proposals.json             ← Proposed new edges
│   ├── mcp/
│   │   ├── ownership_graph.py         ← Ownership KG MCP server (10 tools)
│   │   ├── db_tools.py                ← Database MCP server (5 tools)
│   │   └── run_mcp.sh                 ← Cross-platform venv runner
│   ├── tools/
│   │   └── ag                         ← Ownership CLI tool
│   └── agents/
│       ├── orchestrator/
│       │   ├── agent.md               ← Orchestrator spec
│       │   └── memory/MEMORY.md       ← Orchestrator memory
│       ├── db-agent/
│       │   ├── agent.md
│       │   └── memory/MEMORY.md
│       ├── api-agent/
│       │   ├── agent.md
│       │   └── memory/MEMORY.md
│       └── ... (one per domain)
├── .beads/                            ← Beads tracking (initialized)
├── .mcp.json                          ← MCP server configuration
├── .gitignore                         ← Ignores SQL dump, .venv, etc.
└── app-mynextory-backup.sql           ← Seed data (gitignored)
```

At this point, you can launch a NEW Claude Code session in this repo, and it will:
1. Read `.claude/CLAUDE.md` → know the full system
2. Query ownership KG via MCP → know who owns what
3. Create beads → track all work
4. Spawn agent swarms → build features autonomously
5. Self-evolve → agents update KG, memory, and code as the app grows

**The system builds the app. You just talk to it.**
