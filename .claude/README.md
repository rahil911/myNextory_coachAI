# Command Center Think Tank → Build Orchestration Spec

This is a narrative product specification for humans operating Command Center. It describes exactly what should happen after pressing Approve and Build, what the language model is responsible for, what the deterministic control plane is responsible for, and what must be visible in UI so operators are never blind.

This document is intentionally non-code and written as an operational fiction spec that mirrors real behavior.

## Product Promise

When a human approves a Think Tank session, the system must do three things at once:

- Preserve intent fidelity from conversation to executable tasks.
- Keep launch behavior deterministic and auditable.
- Keep the human continuously informed in the UI, from first click to terminal state.

The operator should never need to inspect logs to answer: what is happening, what happened, what failed, and what to do next.

## Runtime Story: What Happens After Approve

### Stage 0 — Readiness and Visibility Setup

Before any side effect starts, the UI obtains readiness status for dispatch prerequisites. The UI presents readiness checks in the Think Tank panel as a control-tower card.

If requirements are missing, the launch action is disabled and the missing checks are explicitly named.

### Stage 1 — Two-Step Approval Intent

The first click is a planning confirmation, not execution.

The system performs a dry-run to generate a build preview. The human sees phased tasks and intended agent mapping. This is the last non-destructive checkpoint.

The second click is explicit execution commitment.

### Stage 2 — Session-Scoped Approval

Approval is bound to an explicit session identity. The backend validates session existence and enforces idempotency semantics so repeated client calls do not accidentally duplicate launch intent.

If identical intent is replayed inside the idempotency window, the backend returns cached launch outcome.

### Stage 3 — Think Tank State Transition

For real execution, Think Tank transitions into building mode and emits real-time events.

For dry-run, session state remains conversational and side effects are suppressed.

### Stage 4 — Probabilistic Planning

A language model decomposes the spec-kit into phased tasks. This is probabilistic and can vary by run.

To make this production-safe, deterministic wrappers apply:

- strict output-format contract,
- parser validation,
- bounded retries,
- fallback plan if parsing or generation fails.

Probabilistic generation is never allowed to bypass deterministic validation gates.

### Stage 5 — Deterministic Materialization

After plan acceptance, deterministic operations create and wire execution artifacts:

- epic and task records,
- dependency relationships,
- assignee hints,
- persisted dispatch metadata,
- background dispatch scheduling.

These side effects are observable and recoverable.

### Stage 6 — Autonomous Dispatch Loop

The dispatcher continuously evaluates which tasks are unblocked and launches agents under concurrency limits.

Monitoring reconciles multiple deterministic signals:

- task state updates,
- agent exit artifacts,
- heartbeat freshness,
- timeout thresholds,
- retry counters,
- optional acceptance checks.

Failures trigger recovery routines with clear retry or escalation outcomes.

### Stage 7 — Completion Contract

Completion status is terminal only when every task is either completed or failed with explicit accounting.

The UI must show totals, completion percentage, current running count, and recent dispatch feed entries.

## Responsibility Map

### Probabilistic LLM Layer

The LLM layer is responsible for:

- semantic decomposition of goals into tasks,
- requirement interpretation,
- draft ordering hints,
- language-level quality variability.

The LLM layer is not trusted for correctness by default; it is trusted for proposal generation under constraints.

### Deterministic Control Plane Layer

The deterministic layer is responsible for:

- request validation,
- session routing,
- idempotency checks,
- readiness preflight,
- task/epic side effects,
- dependency wiring,
- process spawn parameters,
- retries and timeout policy,
- status persistence and recovery,
- event propagation,
- cancellation and cleanup.

This layer owns correctness and auditability.

## UI Visibility Contract (Never Blind)

The Think Tank UI must provide all of the following during build orchestration:

- launch readiness checks,
- dry-run preview before commit,
- explicit commit transition indicator,
- current dispatch status pill,
- completed/running/failed/total counters,
- progress bar percentage,
- live event feed entries,
- retry and failure context,
- clear disabled-state explanation when launch is blocked.

The operator should have enough information to make go/no-go decisions without opening terminal tools.

## Failure Semantics

The pipeline is considered resilient when:

- missing prerequisites block launch with actionable messages,
- duplicate clicks are harmless,
- websocket interruption does not erase status awareness,
- backend restart does not erase critical dispatch context,
- malformed LLM output yields fallback behavior rather than crash,
- each failure has a visible next action path.

## Think Tank Mode Evolution (Product Direction)

To harden product behavior, Think Tank should explicitly enforce five operational modes:

- Discovery mode, focused on understanding and evidence.
- Optioning mode, focused on alternatives and tradeoffs.
- Scoping mode, focused on constraints, boundaries, and dependencies.
- Preview mode, focused on deterministic dry-run visibility.
- Launch mode, focused on idempotent execution and continuous observability.

Each mode should have entry criteria, exit criteria, and anti-goals so the conversation cannot drift into ambiguous execution.

## Definition of Production Grade

Production grade means the system remains understandable and safe under normal human chaos:

- repeated clicks,
- reconnects,
- partial failures,
- timing races,
- imperfect model responses,
- restarts during active dispatch.

If the operator can always answer what is happening and why, the system is operating at production quality.

## Living Spec Rule

Any future change to approval routing, launch policy, dispatch behavior, retries, visibility surfaces, or mode semantics must update this document in the same change set.
