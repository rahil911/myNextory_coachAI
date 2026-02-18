# PROD_PRD_v4 — The Dispatch Engine

## Vision

This is the **ignition wire** — the critical missing piece that connects Think Tank approval to autonomous multi-agent execution. Everything upstream (brainstorming, spec-kit, approval UI) and everything downstream (spawn.sh, agents, cleanup.sh, quality gates, monitoring) is built and hardened. This PRD wires them together.

After this PRD is complete, the full pipeline works end-to-end:
```
Human idea → Think Tank → Spec-Kit → Approve → Beads → Agents → Code → Review → Merge → Done
```

## What Exists (DO NOT rebuild these)

- **Think Tank service**: `backend/services/thinktank_service.py` — 4-phase brainstorming with Claude, spec-kit accumulation, session persistence
- **Approval endpoint**: `POST /api/thinktank/approve` — sets status="approved", broadcasts events
- **Ownership KG**: `.claude/mcp/ownership_graph.py` — 10 tools for querying agent ownership, blast radius, dependencies
- **Beads CLI**: `bd create`, `bd update`, `bd close`, `bd dep add`, `bd ready`, `bd list`, `bd show`
- **Agent infrastructure**: `.claude/scripts/spawn.sh`, `cleanup.sh`, `heartbeat.sh`, `retry-agent.sh`, `monitor.sh`, `kill-agent.sh`
- **9 agent specs**: `.claude/agents/{orchestrator,platform-agent,identity-agent,comms-agent,content-agent,engagement-agent,meetings-agent,kg-agent,review-agent}/agent.md`
- **Quality gates**: `review-agent.sh`, `test-gate.sh`, `scan-security.sh`, `validate-contracts.sh`
- **Event bus**: `backend/services/event_bus.py` — WebSocket broadcasting to Command Center UI
- **Dashboard API**: `.claude/scripts/dashboard_api.py` — progress monitoring

## Architecture

```
thinktank_service.approve()
  │
  ▼
DispatchEngine.dispatch_approved_session(session)    ← NEW (02a)
  │
  ├── BeadGenerator.spec_to_beads(spec_kit)           ← NEW (01a)
  │     Creates epic + task beads with dependency DAG
  │     Returns: epic_id, [task_beads]
  │
  ├── AgentAssigner.assign_beads(task_beads)           ← NEW (01b)
  │     Queries KG for ownership + capabilities
  │     Returns: [{bead_id, agent_name}]
  │
  ├── BeadsBridge.link_session(session, epic_id)       ← NEW (01c)
  │     Syncs Think Tank session ↔ Beads epic
  │
  ▼
DispatchEngine._dispatch_loop()                       ← NEW (02a)
  │
  │ LOOP:
  │   1. bd ready → find unblocked beads
  │   2. For each: spawn.sh reactive "bd show <id>" ~/agents/<agent>
  │   3. Monitor heartbeats
  │   4. On bead closed → check if dependents unblocked → repeat
  │   5. On failure → FailureRecovery.handle(bead_id)
  │   6. Stream progress → event_bus → WebSocket → UI
  │
  ├── ProgressBridge.stream_status(agent, bead)       ← NEW (03a)
  │
  └── FailureRecovery.handle(bead_id, error)          ← NEW (03b)
```

## File Map

All new files go in `backend/services/` alongside existing thinktank_service.py:

```
backend/services/
  ├── thinktank_service.py      ← MODIFY: approve() triggers dispatch
  ├── bead_generator.py          ← NEW: spec-kit → beads
  ├── agent_assigner.py          ← NEW: KG-based routing
  ├── beads_bridge.py            ← NEW: session ↔ beads sync
  ├── dispatch_engine.py         ← NEW: the core dispatch loop
  ├── progress_bridge.py         ← NEW: agent → WebSocket streaming
  ├── failure_recovery.py        ← NEW: cleanup + retry
  ├── event_bus.py               ← EXISTS (no changes needed)
  ├── agent_service.py           ← EXISTS (may need minor additions)
  └── bead_service.py            ← EXISTS (may need minor additions)
```

## Phase DAG

```
Phase 0 ──────────────────────────────────────────────▶ GATE: all prerequisites validated
    │
    ├── Phase 1a (bead generator)    ─┐
    ├── Phase 1b (agent assigner)     ├─ parallel ──▶ GATE: all 3 services importable, unit tests pass
    └── Phase 1c (beads bridge)      ─┘
         │
         Phase 2a (dispatch engine)  ─── sequential ─▶ GATE: dispatch_engine.py runs, can process mock beads
              │
              ├── Phase 3a (progress bridge) ─┐
              └── Phase 3b (failure recovery) ┴─ parallel ─▶ GATE: WebSocket events flow, retry works
                   │
                   Phase 4 (integration wiring) ── sequential ─▶ GATE: approve() triggers full dispatch
                        │
                        Phase 5 (integration test) ── sequential ─▶ GATE: end-to-end succeeds
```

## Execution

**This PRD creates 8 agent specs. The orchestrator (you, reading LAUNCH.md) executes them in phase order.**

For each phase:
1. Read the agent spec(s) for that phase
2. Execute ALL agents in a parallel phase simultaneously (they touch different files)
3. Verify the gate condition before proceeding to next phase
4. If a gate fails, fix the issue before continuing

**IMPORTANT**: All code lives in `~/Projects/baap/.claude/command-center/backend/services/`. The existing code in that directory is the ground truth — read it before writing anything. Do NOT duplicate functionality that already exists.

**CRITICAL**: Use the Claude Agent SDK (`claude_agent_sdk`) for any AI calls, not the `anthropic` SDK. Pattern:
```python
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

async for msg in query(prompt=..., options=ClaudeAgentOptions(
    permission_mode="bypassPermissions",
    cwd=str(Path.home() / "Projects" / "baap"),
    max_turns=1,
)):
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                text += block.text
```

**CRITICAL**: All subprocess calls to `bd` (beads CLI) must use `asyncio.create_subprocess_exec` with proper error handling. The `bd` binary is in PATH on the India machine.

## Agent Specs

| Phase | Agent Spec | File Created | Dependencies |
|-------|-----------|-------------|--------------|
| 0 | `00-validate-prerequisites.md` | (validation only) | None |
| 1a | `01a-bead-generator.md` | `bead_generator.py` | Phase 0 |
| 1b | `01b-agent-assigner.md` | `agent_assigner.py` | Phase 0 |
| 1c | `01c-beads-bridge.md` | `beads_bridge.py` | Phase 0 |
| 2a | `02a-dispatch-engine.md` | `dispatch_engine.py` | Phase 1a, 1b, 1c |
| 3a | `03a-progress-bridge.md` | `progress_bridge.py` | Phase 2a |
| 3b | `03b-failure-recovery.md` | `failure_recovery.py` | Phase 2a |
| 4 | `04-integration-wiring.md` | (modifies thinktank_service.py + routes) | Phase 3a, 3b |
| 5 | `05-integration-test.md` | (validation only) | Phase 4 |
