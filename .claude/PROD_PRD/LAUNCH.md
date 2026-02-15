# PROD_PRD — Production Hardening

## Purpose

The build phase (PRD/) created the infrastructure. This phase makes it production-grade.
30 risks identified. 10 agent specs. 3 phases.

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
| 16 | No log capture — agent output lost when tmux closes | HIGH | 01e |
| 17 | No real-time visibility into what agents are doing | MEDIUM-HIGH | 01e |
| 18 | No single-pane monitoring dashboard | MEDIUM | 01e |
| 19 | No automatic retry for transient failures (timeout, context exhaustion) | HIGH | 01f |
| 20 | Failed agent leaves dirty state (beads stuck, worktrees abandoned) | HIGH | 01f |
| 21 | Orchestrator has no structured failure info to act on | MEDIUM | 01f |
| 22 | Orchestrator assigns new-domain work to wrong existing agent | HIGH | 01g |
| 23 | API credentials not available in worktrees | HIGH | 01g |
| 24 | New agent created without KG registration (invisible to system) | HIGH | 01g |
| 25 | New agent created without dependency mapping (silent breakage) | HIGH | 01g |
| 26 | Cross-integration dependencies unmapped (no notifications) | MEDIUM-HIGH | 01g |
| 27 | Orchestrator skips brainstorming, creates beads from incomplete understanding | HIGH | 01h |
| 28 | Beads created with vague specs lead to agents producing wrong code | HIGH | 01h |
| 29 | Human's intent misunderstood due to lack of structured elicitation | HIGH | 01h |
| 30 | No scope boundary defined — agents build too much or too little | HIGH | 01h |

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
    ├── Phase 1b  │
    ├── Phase 1c  ├─ parallel (8 agents, all edit different files)
    ├── Phase 1d  │
    ├── Phase 1e  │
    ├── Phase 1f  │
    ├── Phase 1g  │
    └── Phase 1h ─┘
         │
         │  01a-harden-spawn.sh    (Risks: 1, 3, 6, 7, 11, 13)
         │  01b-harden-cleanup.sh  (Risks: 5, 10)
         │  01c-shared-state.md    (Risks: 4, 14, 15)
         │  01d-agent-lifecycle.md (Risks: 8, 9, 12)
         │  01e-observability.md   (Risks: 16, 17, 18)
         │  01f-retry-recovery.md  (Risks: 19, 20, 21)
         │  01g-new-domain-protocol.md (Risks: 22, 23, 24, 25, 26)
         │  01h-orchestrator-protocol.md (Risks: 27, 28, 29, 30)
         │
         │  GATE: All 8 agents pass their unit tests
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
              - Verify log capture works
              - Verify monitor.sh shows agent status
              - Verify retry-agent.sh re-dispatches failed work
              │
              GATE: All integration tests pass
```

## Execution Rules

1. Read each agent spec fully before starting work
2. Use Task tool (subagent_type="general-purpose") for each phase agent
3. Phase 0 MUST complete before Phase 1 starts
4. Phase 1 agents (01a through 01h) run in PARALLEL — they edit different files
5. Phase 2 MUST wait for ALL Phase 1 agents to complete
6. After Phase 2 passes: `git add -A && git commit -m "Production hardening complete" && git push`

## IMPORTANT: Dependencies Between Phase 1 Agents

While Phase 1 agents are parallel (they edit different FILES), some agents modify
spawn.sh (01a, 01e, 01f all touch spawn.sh). To avoid conflicts:

- **01a owns spawn.sh** — it does the full rewrite with all core fixes
- **01e adds to spawn.sh** — log capture (tee), status file creation
- **01f adds to spawn.sh** — exit code capture

**Resolution**: 01a runs FIRST and rewrites spawn.sh completely. Its spec includes
placeholders/hooks for 01e and 01f additions. Then 01e and 01f add their pieces.

Alternative: 01a's spec includes ALL spawn.sh changes (from 01e and 01f too),
and 01e/01f only create their NEW files (monitor.sh, retry-agent.sh) without
touching spawn.sh. This is PREFERRED to avoid merge conflicts.

**Recommended approach**: 01a rewrites spawn.sh with ALL fixes from 01a + 01e + 01f + 01g.
01e only creates monitor.sh. 01f only creates retry-agent.sh. 01g creates create-agent.sh
and the integrations directory, plus CLAUDE.md protocol additions. 01h only modifies
CLAUDE.md (adds orchestrator elicitation protocol — no conflict with 01e/01g CLAUDE.md
sections since they add to different sections).

## File Inventory

After completion, these files should be modified or created:

```
MODIFIED:
  .claude/scripts/spawn.sh          ← 01a: ALL spawn fixes (beads symlink, name, timeout,
                                            mcp-config, preflight, log tee, status file,
                                            exit code capture)
  .claude/scripts/cleanup.sh        ← 01b: flock merge lock, epic integration branch,
                                            symlink cleanup, log archive
  .claude/mcp/ownership_graph.py    ← 01c: shared KG path, file locking on writes
  .mcp.json                         ← 01c: absolute paths for KG cache
  .claude/CLAUDE.md                 ← 01e: monitoring commands section
                                            01h: orchestrator elicitation protocol
  .gitignore                        ← 01e: add .claude/logs/

CREATED:
  .claude/scripts/kill-agent.sh     ← 01d: graceful agent cancellation
  .claude/scripts/heartbeat.sh      ← 01d: background heartbeat wrapper
  .claude/scripts/monitor.sh        ← 01e: aggregated status dashboard
  .claude/scripts/retry-agent.sh    ← 01f: re-dispatch failed agent work
  .claude/scripts/create-agent.sh   ← 01g: atomic new agent creation
  .claude/integrations/.gitkeep     ← 01g: credentials directory
```
