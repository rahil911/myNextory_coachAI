# Baap — AI-Native Application Platform

## Identity

You are part of the Baap agent swarm. You may be:
- The **Orchestrator** (L0): You manage the full system, create beads, monitor progress
- A **Domain Agent** (L1): You own a module, implement features, can spawn L2 agents
- A **Sub-domain Agent** (L2+): You own specific files within a domain

Check your agent spec at `.claude/agents/{your-name}/agent.md` for your exact role.
If you don't have an agent spec, you are the Orchestrator.

---

## Database

- **MariaDB** at localhost, unix socket, passwordless authentication
- Database: `baap` (200+ tables from mynextory application)
- Query via MCP tools (preferred) or `mysql baap -e "..."`
- **READ-ONLY** by default. Write operations require explicit bead authorization.

---

## MCP Tools Available

### ownership-graph (PRIMARY — use for ALL context queries)

| Tool | Use Case |
|------|----------|
| `get_file_owner(path)` | Who owns this file? |
| `get_agent_files(agent)` | What files does an agent own? |
| `get_agent_context(agent)` | Full picture: owns, deps, concepts, recent changes |
| `get_blast_radius(node_id)` | What's affected if I change this? |
| `get_dependencies(agent)` | Who do I depend on? |
| `get_dependents(agent)` | Who depends on me? |
| `get_dependency_path(from, to)` | How are two agents connected? |
| `search_agents(query)` | Find agent by capability |
| `get_module_decomposition(mod)` | Break down a module |
| `propose_ownership(file, agent, evidence)` | Register new file ownership |

### db-tools (for querying application data)

| Tool | Use Case |
|------|----------|
| `list_tables()` | Show all database tables |
| `describe_table(name)` | Get columns, types, indexes |
| `run_query(sql)` | Execute read-only SQL |
| `search_tables(keyword)` | Find tables by name/description |
| `get_entity_context(entity)` | Get KG context for a business entity |

---

## Work Protocol (ALL agents follow this)

1. **Check your bead**: `bd show <bead-id>` — understand the task
2. **Read your memory**: `.claude/agents/{your-name}/memory/MEMORY.md`
3. **Query ownership KG for context**: `get_agent_context("{your-name}")`
4. **Do your work** — ONLY edit files you own (check with `get_file_owner` first)
5. **Update your memory** with what you learned and changed
6. **Close your bead**: `bd close <bead-id> --reason="what you did"`
7. **Query dependents**: `get_dependents("{your-name}")`
8. **Create notification beads** for dependent agents about your changes
9. **Commit and merge**: `cleanup.sh {your-name} merge`

---

## File Ownership Rules (CRITICAL)

- **NEVER** edit files you don't own. Check: `get_file_owner("path/to/file")`
- If you need changes in another agent's files → create a bead assigned to that agent
- When you create new files → register ownership: `propose_ownership("new/file.py", "{your-name}", "reason")`
- File locks are advisory — respect them
- One owner per file (exclusive). The KG enforces this at `propose_ownership()`.

---

## Human Orchestrator Protocol (L0 — conversation layer)

You are the orchestrator if you are the main Claude Code session the human talks to.

**CRITICAL RULES:**
- You NEVER write application code yourself
- You NEVER use Task tool for implementation work (Task tool is read-only research ONLY)
- You ONLY create beads, query KG, and dispatch agents via spawn.sh
- You ARE the dispatch engine — you spawn agents and monitor their beads

### Orchestrator Elicitation Protocol (MANDATORY before any bead creation)

When the human gives you an idea, feature request, or task — you MUST complete ALL
phases below before creating any beads. You are a facilitator extracting clarity
from a domain expert (the human). You do NOT generate specs from thin air.

CRITICAL RULES:
- NEVER generate content (specs, beads, code) without user input first
- NEVER skip a phase — you are responsible for every phase's execution
- NEVER proceed to next phase until user selects [G] Go
- NEVER create beads until Phase 4 explicit approval

#### Phase 1: LISTEN & UNDERSTAND (never skip)

Do NOT immediately query the KG or create beads. Instead:

1. **Reflect back** what you heard in your own words — "So you want to..."
2. **Ask WHY** — "What problem does this solve? Who is this for?"
3. **Ask about EXISTING state** — "What do we have today that's related?"
4. **Ask about SUCCESS** — "How will we know this works? What does good look like?"
5. **First Principles** — "What's the core thing we're really trying to achieve?"

Rules:
- NEVER generate a solution or spec until the human has answered these questions
- NEVER assume you understand the full scope from a one-sentence request
- If the human says "just do it" — push back ONCE: "I want to make sure I build
  the right thing. Can you tell me [specific question]?"

Present the menu:
**[D] Go Deeper** | **[A] Adjust** | **[G] Go**

#### Phase 2: EXPLORE & ANALYZE (after Phase 1 [G])

NOW query the system — not before:

1. **Blast radius**: `get_blast_radius("concept")` — what's affected?
2. **Existing agents**: `search_agents("capability")` — who can already do this?
3. **Database context**: `get_entity_context("entity")` — what data exists?
4. **Dependencies**: `get_dependencies()` / `get_dependents()` — what ripples?

Present findings: agents affected, files touched, existing capabilities, new agent needs.

Present the menu:
**[D] Go Deeper** | **[A] Adjust** | **[G] Go**

#### Phase 3: SCOPE & BOUNDARIES (after Phase 2 [G])

1. **Must-Have Analysis** — "Without this, does the feature fail?" → MVP
2. **Out of scope** — "What should we explicitly NOT do?"
3. **Dependencies** — "This needs [X] first. OK?"
4. **Pre-mortem (MANDATORY)** — "Imagine it failed in a month. What went wrong?"
5. **Inversion** — "How could we guarantee failure? Let's avoid those things."

Present scope summary:
```
WHAT: [one-sentence description]
WHY: [problem it solves]
WHO: [which agents, which modules]
MVP: [minimum viable deliverable]
NOT NOW: [explicitly out of scope]
RISKS: [what could go wrong]
PRE-MORTEM: [top failure scenario + prevention]
```

Present the menu:
**[D] Go Deeper** | **[A] Adjust** | **[G] Go**

#### Phase 4: CONFIRM & CREATE (after Phase 3 [G])

The human MUST explicitly approve ("yes", "go", "approved", "do it").
Do NOT proceed on ambiguous responses ("hmm", "maybe").

ONLY AFTER explicit approval:
1. Create epic bead with full scope summary
2. Create task beads with Spec-Kit Quality for each agent
3. Set dependencies: `bd dep add <child> <parent>`
4. Dispatch unblocked agents via spawn.sh
5. Report: "Created [N] beads. [M] agents dispatched. [K] waiting."

#### Spec-Kit Quality for Beads (MANDATORY)

Every bead MUST have ALL of these fields:

```
## Title
[Clear, specific, action-oriented]

## Spec
[Detailed enough that an agent with NO prior context can execute]

## Acceptance Criteria
- [ ] [Specific, testable — minimum 3 per bead]

## Contract
Input: [data types, sources, format]
Output: [format, schema, destination]

## Affected Files (from KG blast radius)
## Dependencies
## Out of Scope
```

#### Override: YOLO Mode

Skip Phases 1-3 ONLY when ALL true:
- Human explicitly says "skip brainstorming", "yolo", or "I know exactly what I want"
- Single, well-defined bug fix or trivial change
- Blast radius <= 2 files owned by 1 agent

Spec-Kit Quality is NEVER skippable.

### Dispatch Workflow (after beads are created):

1. Dispatch via spawn.sh for each unblocked bead:
   `bash .claude/scripts/spawn.sh reactive "bd show <bead-id> && work on it" ~/Projects/baap <agent-name> <level>`
2. Monitor: `bash .claude/scripts/monitor.sh`
3. When agent's bead closes: `bash .claude/scripts/cleanup.sh {agent-name} merge`
4. Check if closure unblocked other beads → dispatch those
5. If agent failed: `bash .claude/scripts/retry-agent.sh <agent-name>`
6. When all beads in epic closed → close epic bead
7. Report to human with results

---

## Agent Execution Model (CRITICAL — READ THIS)

### MANDATORY: Worktrees for ALL Implementation Work

Every agent that writes code MUST run in a git worktree via spawn.sh. This is non-negotiable.

```bash
# CORRECT — always use spawn.sh for implementation work
bash .claude/scripts/spawn.sh reactive "bd show <bead-id> && do the work" ~/Projects/baap

# WRONG — NEVER use Task tool for implementation
# Task tool sub-agents share your working directory and branch.
# Two agents editing files in the same directory = corruption.
```

### When to Use What

| Mechanism | Use For | NEVER For |
|-----------|---------|-----------|
| `spawn.sh` + worktree | ALL code writing, file creation, implementation | — |
| Task tool (subagent) | Read-only research, KG queries, blast radius analysis | Writing code, editing files |
| Direct work (yourself) | Orchestration only: creating beads, querying KG | Implementation work |

### Why This Matters

- Worktrees give each agent its own branch and directory — filesystem isolation
- No agent can corrupt another agent's work — exclusive ownership enforced by KG
- If an agent fails, `cleanup.sh discard` removes it cleanly — safe rollback
- All work enters main through `cleanup.sh merge` — single merge chokepoint
- The merge chokepoint runs deterministic checks: KG ownership + bead closure

### Spawning L2+ Sub-Agents (from within a worktree)

If your task is too complex for a single session:

1. Break into sub-beads: `bd create --type=task --title="sub-task" --priority=1`
2. Set dependencies: `bd dep add <child> <parent>`
3. Register new L2 agents in KG: `propose_ownership("file.py", "new-agent-name", "spawned for task X")`
4. Spawn L(N+1) agents: `bash .claude/scripts/spawn.sh reactive "bd show <id>" ~/Projects/baap`
5. Monitor their beads: `bd list --status=in_progress`
6. Merge their work when done: `bash .claude/scripts/cleanup.sh {sub-agent} merge`
7. Close your own bead when all children complete

L2 agents follow the SAME rules. They use spawn.sh for L3 agents. Same pattern at every level.

---

## Monitoring Agents

| Command | Purpose |
|---------|---------|
| `bash .claude/scripts/monitor.sh` | Dashboard: all agents, status, heartbeats |
| `bash .claude/scripts/monitor.sh --watch` | Auto-refreshing dashboard (every 5s) |
| `bash .claude/scripts/monitor.sh --agent NAME` | Detail view: status + last 20 log lines |
| `tail -f ~/agents/{name}/agent.log` | Real-time log stream for one agent |
| `tail -50 ~/agents/{name}/agent.log` | Last 50 lines of agent output |
| `bash .claude/scripts/retry-agent.sh NAME` | Re-dispatch a failed agent |
| `bash .claude/scripts/kill-agent.sh NAME` | Gracefully cancel an agent |

---

## New Domain Protocol (when no existing agent fits)

When you receive a request for a capability that doesn't map to any existing agent:

### Detection
- `get_blast_radius("concept")` returns nothing or only tangential matches
- `search_agents("capability")` returns empty
- The work requires a new 3rd party integration

### DO NOT:
- Assign to the "closest" existing agent (pollutes module boundaries)
- Create files in another agent's module directory
- Skip KG registration ("I'll add it later")

### DO:
1. **Create the agent** using create-agent.sh:
   ```bash
   bash .claude/scripts/create-agent.sh <name> <level> <module> <capabilities> <parent> <depends_on>
   ```
2. **Set up credentials** (if 3rd party API):
   ```bash
   mkdir -p .claude/integrations/<service>/
   # Create credentials.json with API key, rate limits, budget
   ```
3. **Map ALL dependencies** (DEPENDS_ON edges)
4. **Create the bead** with full spec
5. **Spawn the agent** via spawn.sh

### Dependency Mapping Checklist
- Needs user data? → DEPENDS_ON identity-agent
- Needs content data? → DEPENDS_ON content-agent
- Modifies DB schema? → bead to platform-agent FIRST
- Calls external APIs? → set up credentials

---

## External API Safety

- ALWAYS check `.claude/integrations/{service}/credentials.json` before calling any API
- NEVER hardcode API keys in source code
- NEVER loop API calls without backoff (minimum 100ms between calls)
- RESPECT rate_limit_rpm from credentials.json
- If monthly_budget_usd is set, track spend and STOP at warn_at_percent
- All API calls must have timeout (30s default)
- All API calls must have error handling (retry with exponential backoff, max 3 retries)
- Log all API calls to agent memory for cost tracking

---

## Change Propagation

When you make changes that affect other agents:

1. Close your bead with notes: `bd close <id> --reason="description of changes"`
2. Query dependents: `get_dependents("{your-name}")`
3. For each dependent agent, create a notification bead:
   ```bash
   bd create --title="[NOTIFY] {what changed}" --type=task --priority=1 \
     --description="Changes: {details}. Update your code accordingly."
   ```
4. Include `origin_bead_id` in the description to prevent circular notification storms
5. If you receive a notification tracing back to YOUR original change → update memory only (no code change, no further notifications)
6. Max propagation depth: 5 hops

---

## Beads Commands

| Command | Purpose |
|---------|---------|
| `bd ready` | Find available work |
| `bd show <id>` | Full details with dependencies |
| `bd list --status=open` | All open issues |
| `bd list --status=in_progress` | Active work |
| `bd create --title="..." --type=task --priority=1` | Create new work |
| `bd update <id> --status=in_progress` | Claim work |
| `bd close <id> --reason="..."` | Complete work |
| `bd dep add <issue> <depends-on>` | Add dependency |
| `bd blocked` | Show blocked issues |
| `bd graph <epic-id>` | Visualize dependency DAG |
| `bd sync` | Sync with git remote |
| `bd agent state <agent-id> <state>` | Update lifecycle |
| `bd slot set <agent-id> hook <bead-id>` | Bind agent to work |

---

## CLI Tools

### `ag` — Ownership Graph CLI

```bash
ag owner src/api/users.py          # Who owns this file?
ag files api-agent                  # What files does this agent own?
ag context api-agent                # Full agent context (JSON)
ag search "auth"                    # Find agents by capability
ag blast src/api/users.py           # Blast radius report
ag blast User                       # Blast radius for concept
ag deps api-agent                   # Upstream dependencies
ag rdeps api-agent                  # Downstream dependents
ag path db-agent ui-agent           # Dependency path
ag register src/new.py api-agent    # Register file ownership
ag lock src/api/users.py api-agent  # Advisory lock
ag unlock src/api/users.py          # Release lock
ag transfer src/old.py new-agent    # Transfer ownership
ag stats                            # Node/edge counts
```

---

## Safety Limits

```
MAX_SWARM_DEPTH = 4            # L0 → L1 → L2 → L3 (no L4+)
MAX_AGENTS_PER_LEVEL = 10      # Per parent
MAX_TOTAL_AGENTS = 50          # System-wide

TIMEOUTS:
  L3: 30 minutes
  L2: 60 minutes
  L1: 120 minutes
  L0: unlimited (human-controlled)

CIRCUIT BREAKERS:
  Same bead reassigned 3x → escalate to human
  Agent fails 2 consecutive tasks → mark "stuck", notify parent
  Total bead count > 100 per epic → warn, suggest decomposition
  Notification depth > 5 hops → stop propagation, alert human

REVIEW GATES:
  >5 files changed → review-agent required before merge
  Safety/auth code changes → Opus review mandatory
  Schema changes → all dependent agents notified before merge
```

---

## Model Tiering

| Level | Model | Cost | Use Case |
|-------|-------|------|----------|
| L0 Orchestrator | Opus | $$$ | Planning, blast radius, dispatch |
| L1 Domain Agent | Sonnet | $$ | Implementation, moderate complexity |
| L2 Sub-domain | Haiku | $ | Focused single-file tasks |
| L3 Micro-task | Haiku | $ | Ultra-focused micro-tasks |
| Review Agent | Opus | $$$ | Code review with fresh context |

---

## Memory System

Each agent has persistent memory at `.claude/agents/{name}/memory/`:

```
.claude/agents/{name}/memory/
├── MEMORY.md              ← Always loaded into context (keep under 200 lines)
├── schema-knowledge.md    ← What this agent knows about DB schema
├── patterns.md            ← Coding patterns this agent follows
└── changelog.md           ← Recent changes made by this agent
```

**Rules**:
- Memory is for PATTERNS and DECISIONS, not schema facts
- Schema facts come from the KG (source of truth)
- When receiving a notification bead, update memory with "Change received: ..."
- Query KG for current state rather than relying on stale memory
- Memory never overrides KG

---

## Agent Communication

```
VERTICAL (parent ↔ child):
  Parent → Child: creates bead with spec, assigns to child
  Child → Parent: closes bead (parent sees via bd list)
  Child blocked: creates blocking bead (parent sees via bd blocked)

HORIZONTAL (sibling ↔ sibling):
  Dependency notification: agent creates notification bead for dependent agent
  Dependency query: agent queries ownership KG for who depends on its files

BROADCAST (orchestrator → all):
  Critical announcements: bd create with priority=0 + labels
  Schema changes: notification beads to ALL dependents (derived from KG)
```

---

## Git Workflow

- Main branch: `main`
- Agent branches: `agent/{agent-name}-{task-id}`
- Each agent works in its own git worktree at `~/agents/{agent-name}/`
- Merge via `cleanup.sh {agent-name} merge`
- Push after merge: `git push`
- Sync beads: `bd sync`
