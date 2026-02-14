# PROD_PRD — Production Hardening

## Purpose

The build phase (PRD/) created the infrastructure. This phase makes it production-grade.
15 risks identified. 6 agent specs. 3 phases.

## Risks Being Mitigated

| # | Risk | Severity | Fix Agent |
|---|------|----------|-----------|
| 1 | .beads/ inaccessible from worktrees (gitignored, not symlinked) | SHOWSTOPPER | 01a |
| 2 | .claude/ directory not committed to git (worktrees would be empty) | SHOWSTOPPER | 00 |
| 3 | Agent doesn't know its own name (can't call get_agent_context) | HIGH | 01a |
| 4 | KG cache is per-worktree, not shared (agents diverge) | HIGH | 01c |
| 5 | Concurrent merge race condition (no lock on git checkout main) | HIGH | 01b |
| 6 | No timeout enforcement (stuck agents run forever) | HIGH | 01a |
| 7 | MCP server cold start (each worktree creates its own venv) | MEDIUM-HIGH | 01a |
| 8 | No heartbeat / stuck-agent detection | MEDIUM-HIGH | 01d |
| 9 | No graceful agent cancellation (kill tmux = dirty state) | MEDIUM | 01d |
| 10 | Partial epic failure has no atomic rollback | MEDIUM | 01b |
| 11 | spawn.sh may not pass --mcp-config correctly | HIGH | 01a |
| 12 | Agent memory directory may not exist on first run | MEDIUM | 01d |
| 13 | No pre-flight check for claude CLI / bd / ag availability | HIGH | 01a |
| 14 | KG cache concurrent write safety (no file locking) | HIGH | 01c |
| 15 | Beads SQLite concurrent writes from parallel agents | MEDIUM-HIGH | 01c |

## Phase DAG

```
Phase 0 (sequential, must pass first)
    │
    │  00-validate-git-state.md
    │  - Verify .claude/ is committed to git
    │  - Verify .gitignore covers SQL dumps, agents/, .beads/
    │  - Verify claude CLI, bd, ag, python3 all available
    │  - Commit any uncommitted .claude/ files
    │
    │  GATE: git status shows .claude/ tracked, all tools in PATH
    │
    ├── Phase 1a ─┐
    ├── Phase 1b  ├─ parallel (4 agents)
    ├── Phase 1c  │
    └── Phase 1d ─┘
         │
         │  01a-harden-spawn.md    (Risks: 1, 3, 6, 7, 11, 13)
         │  01b-harden-cleanup.md  (Risks: 5, 10)
         │  01c-shared-state.md    (Risks: 4, 14, 15)
         │  01d-agent-lifecycle.md (Risks: 8, 9, 12)
         │
         │  GATE: All 4 scripts pass their unit tests
         │
         Phase 2 (sequential, integration test)
              │
              02-integration-test.md
              - Spawn a real agent in a worktree
              - Verify beads accessible from worktree
              - Verify KG shared state
              - Verify merge lock prevents concurrent merges
              - Verify timeout kills stuck agent
              - Verify heartbeat detectable
              - Verify kill-agent.sh cleans up properly
              │
              GATE: All integration tests pass
```

## Execution Rules

1. Read each agent spec fully before starting work
2. Use Task tool (subagent_type="general-purpose") for each phase agent
3. Phase 0 MUST complete before Phase 1 starts
4. Phase 1 agents (01a, 01b, 01c, 01d) run in PARALLEL — they edit different files
5. Phase 2 MUST wait for ALL Phase 1 agents to complete
6. After Phase 2 passes: `git add -A && git commit -m "Production hardening complete" && git push`

## File Inventory

After completion, these files should be modified or created:

```
MODIFIED:
  .claude/scripts/spawn.sh          ← 01a: beads symlink, agent name, timeout, mcp-config, preflight
  .claude/scripts/cleanup.sh        ← 01b: flock merge lock, epic integration branch
  .claude/mcp/ownership_graph.py    ← 01c: shared KG path, file locking on writes
  .mcp.json                         ← 01c: absolute paths for KG cache

CREATED:
  .claude/scripts/kill-agent.sh     ← 01d: graceful agent cancellation
  .claude/scripts/heartbeat.sh      ← 01d: background heartbeat wrapper
  .claude/scripts/preflight.sh      ← 01a: pre-spawn tool availability check
```
