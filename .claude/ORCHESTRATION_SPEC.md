# Command Center Build Orchestration Spec (Fictional, Narrative)

This document is a product-facing, narrative specification of how the Think Tank to Build pipeline works in Baap Command Center today, why it works, where it is probabilistic, where it is deterministic, and what production-grade behaviors are expected at each stage.

The scope of this spec is the journey from a user pressing “Approve & Start Building” in Think Tank through autonomous dispatch, monitoring, retries, and completion reporting. It is intentionally written as an operational story and not as implementation code.

## 1) System Intent

The system intent is to convert an approved product conversation into executable work with minimal manual coordination while preserving operator control, traceability, and failure containment.

From a systems perspective, this means blending two classes of computation:

- Probabilistic intelligence steps, where language-model output may vary between runs and must be bounded by contracts and fallback behavior.
- Deterministic control-plane steps, where every side effect should be explicit, observable, and recoverable.

The production quality bar is reached only when probabilistic steps are constrained and deterministic steps are auditable.

## 2) End-to-End Runtime Sequence

### Phase A: Human Approval Intent

A human operating in Think Tank reaches confirm mode and triggers build intent. The user interface first asks the backend for dispatch readiness and then invokes a dry-run approval flow to preview planned tasks. If preview exists, the UI requires a second confirmation click. Only then does it trigger real dispatch.

This creates a two-stage commitment:

- “Show me what will happen.”
- “Now execute it.”

The design objective is to avoid accidental launches and give operators a chance to inspect decomposition quality before side effects begin.

### Phase B: API Validation and Idempotent Gatekeeping

The backend approval route validates the target session by explicit session ID, performs readiness checks for required runtime dependencies, and applies idempotency semantics to reduce duplicate processing risk for repeated client calls.

If prerequisites are missing, the route should refuse execution with a service-unavailable style response that names what is missing, so the operator can fix environment state before retrying.

### Phase C: Think Tank State Transition

For non-dry-run calls, session state transitions from conversational confirmation to build-approved execution mode. The event bus emits progression events so real-time clients can update status surfaces.

For dry-run calls, no build side effects should occur; the user receives preview data only.

### Phase D: Plan Synthesis

The dispatch engine requests a plan from bead generation.

This stage contains probabilistic behavior:

- The model interprets spec-kit material and proposes phased tasks.
- Output quality may vary due to model behavior, context shape, and prompt adherence.

To preserve reliability, this stage must be wrapped by deterministic controls:

- strict output format expectations,
- parse validation,
- retry strategy,
- bounded fallback plan generation when model output is malformed or unavailable.

### Phase E: Deterministic Task Materialization

Once a plan exists, the system performs deterministic side effects:

- create epic and task beads,
- assign dependencies,
- assign candidate agents,
- persist dispatch state for recovery,
- schedule background dispatch loop.

At this point, observable state should be enough for postmortem reconstruction even if the process restarts.

### Phase F: Agent Dispatch and Monitoring

A background loop dispatches ready task beads only, obeying concurrency limits, dependency constraints, and retry policy. Each dispatch spawns an agent process with explicit identity context and captures metadata for monitoring.

Status reconciliation combines deterministic checks such as:

- bead lifecycle state from tracking system,
- agent exit artifacts,
- heartbeat freshness,
- timeout windows,
- optional acceptance criteria verification.

When failures occur, failure-recovery routines handle cleanup, annotation, retry decisions, and escalation events.

### Phase G: Completion and Hand-off

When all tasks resolve to complete or failed terminal states, the system emits completion events with totals and disposition summary. Session-level dispatch status remains queryable for dashboards and operator follow-up.

## 3) Probabilistic vs Deterministic Responsibility Map

### Probabilistic Components

- spec understanding and task decomposition,
- natural-language requirement interpretation,
- semantic routing hints from generated task descriptors,
- optional confidence judgments tied to output quality.

### Deterministic Components

- request routing and input validation,
- session lookup and state transitions,
- environment readiness checks,
- idempotency cache checks,
- bead creation/update side effects,
- dependency DAG wiring,
- spawn command construction,
- polling, timeouts, retry counts,
- persistence of dispatch metadata,
- websocket event fan-out,
- cancellation and cleanup actions.

Production reliability requires deterministic layers to compensate for probabilistic variability, never the reverse.

## 4) Failure Semantics (Operational Expectations)

The system should be considered healthy only when all of the following are true:

- Missing dependencies are caught before launch.
- Duplicate client submissions do not produce duplicate dispatches for the same intent window.
- Restart does not erase critical execution history.
- Operator can explain “what happened” from persisted and streamed evidence.
- LLM malformation does not crash the pipeline; fallback path remains valid.

## 5) Think Tank Mode Improvements (Product Direction)

Inspired by orchestrated product-delivery frameworks that emphasize clear role boundaries and quality gates, Think Tank can become more robust by introducing explicit mode contracts:

- Discovery Mode: maximize problem understanding and evidence collection, no execution proposals.
- Optioning Mode: generate alternatives with explicit tradeoffs and confidence bands.
- Scoping Mode: force boundary commitments, reject ambiguous ownership.
- Execution Preview Mode: deterministic dry-run artifact and cost/risk summary.
- Launch Mode: idempotent, observable, reversible dispatch trigger.

Each mode should have entry criteria, exit criteria, and anti-goals. This prevents conversational drift and reduces hidden state assumptions.

## 6) Recommended Production Guardrails

- Persist idempotency records with session scoping and bounded retention.
- Add replay-safe execution audit events with correlation IDs across route, dispatch, and agent layers.
- Introduce explicit “plan quality score” before allowing launch from preview.
- Add end-to-end chaos drills for dependency outage, stuck agent, malformed model output, and restart during active dispatch.
- Add operator-facing “why blocked” and “why retried” explanations in timeline.
- Add session isolation assertions in websocket pathways to prevent cross-session bleed.

## 7) Operator Mental Model

A practical operator mental model is:

- Dry-run is proposal.
- Confirm-build is commitment.
- Dispatch is asynchronous orchestration.
- Event stream is near-real-time narrative.
- Dispatch status endpoint is source-of-truth snapshot.
- Bead records are canonical task state.

If those six statements are consistently true in production, the system behavior remains legible even under stress.

## 8) Definition of “Prod Grade” for This Pipeline

Prod grade means this pipeline remains correct and understandable when people double-click, refresh mid-run, lose websocket connection, restart backend, or receive imperfect LLM output.

In other words: resilience under ordinary operator chaos.

---

This specification should be kept current whenever approval routing, dispatch semantics, failure handling, or Think Tank mode behavior changes.
