# PROD_PRD v2 — Quality & Safety Hardening

## Purpose

PROD_PRD v1 built the core infrastructure (spawn, cleanup, KG, lifecycle, monitoring, retry, domain protocol, orchestrator protocol). All 30 risks mitigated, 21/21 integration tests passed (commit cfe4890).

This phase adds **quality gates, safety nets, observability layers, and an interactive Command Center** on top of that foundation.
24 new risks identified. 9 agent specs. 3 phases.

## Prerequisites

- PROD_PRD v1 MUST be complete (all Phase 0-2 tests passing)
- These scripts MUST exist and work: spawn.sh, cleanup.sh, kill-agent.sh, heartbeat.sh, monitor.sh, retry-agent.sh, create-agent.sh
- Ownership KG MUST be operational (.claude/kg/agent_graph_cache.json)
- Beads MUST be initialized (.beads/ directory)

## Risks Being Mitigated

| # | Risk | Severity | Fix Agent |
|---|------|----------|-----------|
| 31 | Shared hallucination — same agent writes and reviews its own code | CRITICAL | 03a |
| 32 | Ownership boundary violations in multi-agent merges | HIGH | 03a |
| 33 | Silent regressions merged to main (no test gate) | CRITICAL | 03b |
| 34 | Cascading failures — Agent A merges broken code, Agent B inherits breakage | HIGH | 03b |
| 35 | Unbounded test execution blocking merges | MEDIUM | 03b |
| 36 | No test coverage awareness (invisible gaps) | MEDIUM | 03b |
| 37 | Cross-agent schema drift without consumer validation | CRITICAL | 03c |
| 38 | Contract extraction false positives blocking valid merges | MEDIUM | 03c |
| 39 | Contracts become stale (nobody updates them) | MEDIUM | 03c |
| 40 | Context exhaustion loses 80% completed work on retry | HIGH | 03d |
| 41 | Resume vs fresh session wrong choice corrupts agent state | HIGH | 03d |
| 42 | No remote visibility into swarm progress from Mac | HIGH | 03e |
| 43 | No event timeline for post-mortem analysis | MEDIUM | 03e |
| 44 | Invisible bead dependency bottlenecks | MEDIUM | 03e |
| 45 | Agents repeat mistakes other agents already solved | HIGH | 03f |
| 46 | Pattern pollution from unvalidated agent contributions | MEDIUM | 03f |
| 47 | Shared knowledge file grows unbounded | LOW | 03f |
| 48 | Hardcoded secrets/credentials in agent-generated code | CRITICAL | 03g |
| 49 | SQL injection / XSS vectors in agent-generated code | HIGH | 03g |
| 50 | Vulnerable/unlocked dependencies introduced by agents | MEDIUM | 03g |
| 51 | No interactive human control — can't move beads, comment, paste screenshots | HIGH | 03h, 03i |
| 52 | No brainstorming/elicitation UI for spec-kit creation (BMAD Think Tank) | HIGH | 03h, 03i |
| 53 | No approval-then-AFK workflow — human can't approve and walk away | MEDIUM | 03h, 03i |
| 54 | Command Center dashboard is a monolith — can't reuse across projects | MEDIUM | 03h, 03i |

## Phase DAG

```
Phase 3 (after PROD_PRD v1 Phase 2 passes)
    │
    │  PREREQUISITE: commit cfe4890 (PROD_PRD v1 complete)
    │
    │  ┌── 03a ──────┐
    │  │              │  03a runs FIRST (owns cleanup.sh modifications)
    │  │  GATE: cleanup.sh has all 3 gates (security → test → review)
    │  │              │
    │  ├── 03b ──┐    │
    │  ├── 03c   │    │
    │  ├── 03d   ├────┤  03b-03g run in PARALLEL after 03a
    │  ├── 03e   │    │  (they create NEW files, don't modify cleanup.sh)
    │  ├── 03f   │    │
    │  └── 03g ──┘    │
    │              │
    │  03a-harden-cleanup-gates.md  (Risks: 31, 32)
    │  03b-test-gate.md             (Risks: 33, 34, 35, 36)
    │  03c-contract-validation.md   (Risks: 37, 38, 39)
    │  03d-context-checkpointing.md (Risks: 40, 41)
    │  03e-progress-dashboard.md    (Risks: 42, 43, 44)
    │  03f-agent-learning.md        (Risks: 45, 46, 47)
    │  03g-security-scan.md         (Risks: 48, 49, 50)
    │
    │  GATE: All 7 agents pass their unit tests
    │
    Phase 3.5 (Command Center — runs AFTER 03e, can overlap with others)
    │
    │  03h + 03i run in PARALLEL (backend + frontend)
    │  They create files ONLY in .claude/command-center/ (zero conflicts)
    │  03h builds the backend API (FastAPI at :8002)
    │  03i builds the frontend UI (vanilla JS, served by FastAPI static mount)
    │
    │  03h-command-center-api.md    (Risks: 51, 52, 53, 54)
    │  03i-command-center-ui.md     (Risks: 51, 52, 53, 54)
    │
    │  DEPENDENCY: 03e must complete first (03h extends 03e's dashboard_api.py patterns)
    │  DEPENDENCY: API contracts between 03h and 03i are PRE-RECONCILED (no conflicts)
    │
    │  GATE: Command Center starts on :8002, WebSocket connects, Kanban renders
    │
    Phase 4 (sequential, integration test v2)
         │
         04-integration-test-v2.md
         - Verify security scan blocks merge with hardcoded secret
         - Verify test gate blocks merge with failing test
         - Verify review agent spawns and produces verdict
         - Verify contract validation catches schema drift
         - Verify checkpoint saves progress mid-session
         - Verify retry-agent.sh reads checkpoint and resumes
         - Verify dashboard API returns agent status from Mac
         - Verify patterns.md loads on agent session start
         - Verify scan-security.sh exit codes (0/1/2) correct
         - Verify cleanup.sh gate chain runs in order: security → test → review
         - Verify Command Center API at :8002 responds to /api/dashboard/health
         - Verify Command Center Kanban at /api/kanban returns bead columns
         - Verify Command Center WebSocket at /ws accepts connections
         - Verify Command Center frontend serves at :8002 (static mount)
         │
         GATE: All integration tests pass
```

## Execution Rules

1. Read each agent spec fully before starting work
2. Use Task tool (subagent_type="general-purpose") for each phase agent
3. **03a MUST complete before 03b-03g start** (03a modifies cleanup.sh with all gate insertion points)
4. 03b through 03g run in PARALLEL — they create different NEW files
5. Phase 3.5 (03h + 03i) can start after 03e completes — they are independent of 03a-03d/03f-03g
6. 03h and 03i run in PARALLEL — backend and frontend in isolated .claude/command-center/ directory
7. Phase 4 MUST wait for ALL agents (03a-03i) to complete
8. After Phase 4 passes: `git add -A && git commit -m "Quality, safety, and Command Center complete" && git push`

## IMPORTANT: Dependencies Between Phase 3 Agents

### cleanup.sh Coordination (same pattern as v1 spawn.sh)

Three agents need to add gates to cleanup.sh (03a review, 03b test, 03g security).
To avoid merge conflicts:

- **03a owns ALL cleanup.sh modifications** — adds all 3 gates in order:
  1. Security scan gate (calls `.claude/scripts/scan-security.sh`)
  2. Test gate (calls `.claude/scripts/test-gate.sh`)
  3. Review gate (calls `.claude/scripts/review-agent.sh`)
- **03b only creates** test-gate.sh, test-map.sh, config/test-mapping.json
- **03g only creates** scan-security.sh

**Recommended approach**: 03a reads the specs for 03b and 03g to understand the gate
interface (exit codes, arguments), then adds all three gate calls to cleanup.sh.
03b and 03g only create their standalone scripts and tests.

### spawn.sh Coordination

- **03d modifies spawn.sh** — adds `--append-system-prompt` for checkpoint injection,
  `--bead` flag for bead association, `--reuse-worktree` flag for retry cycles
- **No other Phase 3 agent touches spawn.sh**

### CLAUDE.md Coordination (additive, no conflicts)

Multiple agents add to CLAUDE.md in DIFFERENT sections:
- 03a: review commands section
- 03d: checkpoint protocol section
- 03e: dashboard commands section
- 03f: agent patterns loading protocol

These are all ADDITIVE and go to different sections. No conflicts expected.

## File Inventory

After completion, these files should be modified or created:

```
MODIFIED:
  .claude/scripts/cleanup.sh        ← 03a: security gate + test gate + review gate
                                           (3 new function calls before merge)
  .claude/scripts/spawn.sh          ← 03d: checkpoint injection, --bead, --reuse-worktree
  .claude/CLAUDE.md                 ← 03a: review commands
                                      03d: checkpoint protocol
                                      03e: dashboard commands
                                      03f: patterns loading protocol
  .gitignore                        ← 03e: add dashboard temp files

CREATED:
  .claude/scripts/review-agent.sh   ← 03a: headless review agent launcher
  .claude/scripts/review-prompt.md  ← 03a: review prompt template
  .claude/scripts/review-verdict.sh ← 03a: verdict parser + bead creator
  .claude/scripts/check-ownership.sh ← 03a: KG ownership violation check
  .claude/scripts/check-secrets.sh  ← 03a: regex secret detection (fast pre-check)
  .claude/scripts/verify-findings.sh ← 03a: verify review findings exist in code
  .claude/scripts/review-feedback.sh ← 03a: human override recording for calibration
  .claude/agents/review-agent/      ← 03a: agent spec + memory directory
  .claude/scripts/test-gate.sh      ← 03b: test runner with timeout
  .claude/scripts/test-map.sh       ← 03b: changed files → test files mapper
  .claude/config/test-mapping.json  ← 03b: static test mapping overrides
  .claude/contracts/                ← 03c: contract definition files (JSON Schema)
  .claude/scripts/validate-contracts.sh ← 03c: contract validation engine
  .claude/scripts/generate-contract.sh  ← 03c: draft contract generator
  .claude/scripts/extract-schema.py     ← 03c: AST-based schema extractor
  .claude/scripts/bump-contract.sh      ← 03c: contract version evolution
  .claude/scripts/checkpoint.sh     ← 03d: atomic checkpoint helper
  .claude/scripts/dashboard_api.py  ← 03e: single-file FastAPI dashboard backend
  .claude/scripts/dashboard.html    ← 03e: single-file HTML dashboard
  .claude/scripts/start-dashboard.sh ← 03e: dashboard launcher
  .claude/knowledge/patterns.md     ← 03f: shared cross-agent pattern store
  .claude/knowledge/SCHEMA.md       ← 03f: pattern format reference
  .claude/knowledge/curate-patterns.sh ← 03f: Haiku-powered pattern curation
  .claude/scripts/load-patterns.sh  ← 03f: SessionStart hook for pattern loading
  .claude/scripts/scan-security.sh  ← 03g: security scan engine

  .claude/command-center/backend/   ← 03h: Command Center API (15+ Python files)
    main.py                          FastAPI app entry point
    config.py                        Path-based configuration
    models.py                        Pydantic models
    services/                        Business logic (agent, bead, thinktank, event_bus, etc.)
    routes/                          API endpoints (agents, beads, kanban, thinktank, commands, etc.)
    start.sh                         Launcher script
    requirements.txt                 Python dependencies

  .claude/command-center/frontend/  ← 03i: Command Center UI (31 files)
    index.html                       App shell
    css/                             7 CSS files (theme, layout, kanban, thinktank, timeline, components, animations)
    js/                              Core infrastructure (state, api, router)
    js/views/                        6 views (dashboard, kanban, thinktank, timeline, agents, epics)
    js/components/                   9 components (command-palette, toast, clipboard, approval-card, etc.)
    js/utils/                        3 utilities (dom, format, fuzzy)
    assets/                          SVG icon sprite
```
