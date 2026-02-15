# Phase 1h: Orchestrator Elicitation Protocol

## Purpose

The orchestrator currently CAN jump straight from user request to bead creation to agent
dispatch. Nothing FORCES it to brainstorm, discuss, validate assumptions, or confirm
scope with the human first. This spec adds a mandatory elicitation phase — inspired by
BMAD Method's PM persona pattern (sequential step enforcement, "NEVER generate content
without user input", menu-based gates, validation loops) — that the orchestrator MUST
follow before creating any beads.

The principle: the orchestrator is a FACILITATOR, not a content generator. It asks WHY,
extracts requirements through conversation, validates assumptions, stress-tests the plan
with advanced techniques, and only creates beads when the human explicitly says "go."

### BMAD Patterns Adopted

From BMAD Method (bmad-code-org/BMAD-METHOD):

1. **Sequential Step Enforcement** — Steps execute in exact numerical order. No skipping.
   BMAD: "NEVER skip a step - YOU are responsible for every step's execution."
   Ours: 4 phases, each MUST complete before the next starts.

2. **NEVER Generate Without User Input** — The facilitator asks, never assumes.
   BMAD: "NEVER generate content without user input."
   Ours: No bead content generated until human has answered elicitation questions.

3. **Menu-Based Gates** — User must explicitly select to proceed.
   BMAD: "NEVER proceed until the user indicates to proceed."
   Ours: D/A/G menu after every phase. No advancement without G.

4. **Validation Loops** — "Does this sound right to you?" confirmations.
   BMAD: Explicit confirmation at every template-output checkpoint.
   Ours: Scope summary presented for explicit approval before bead creation.

5. **Advanced Elicitation** — Pre-mortem, inversion, first principles, socratic questioning.
   BMAD: 8 advanced techniques available on demand.
   Ours: Pre-mortem mandatory in Phase 3. Others available via [D] Go Deeper.

6. **MVP Philosophy** — Must-have vs nice-to-have with phased scoping.
   BMAD: "Without this, does the product fail?" gate.
   Ours: Phase 3 scoping with explicit MVP/NOT-NOW split.

## Risks Mitigated

- Risk 27: Orchestrator skips brainstorming and creates beads from incomplete understanding
- Risk 28: Beads created with vague specs lead to agents producing wrong code
- Risk 29: Human's intent misunderstood due to lack of structured elicitation
- Risk 30: No scope boundary defined → agents build too much or too little

## Files to Modify

- `.claude/CLAUDE.md` — Replace the orchestrator protocol workflow with the full
  elicitation protocol below

---

## The Protocol (add to CLAUDE.md)

Add this as the FIRST section under "Human Orchestrator Protocol", BEFORE the workflow
steps. This REPLACES the existing workflow steps 1-7.

```markdown
## Orchestrator Elicitation Protocol (MANDATORY before any bead creation)

When the human gives you an idea, feature request, or task — you MUST complete ALL
phases below before creating any beads. You are a facilitator extracting clarity
from a domain expert (the human). You do NOT generate specs from thin air.

CRITICAL RULES:
- NEVER generate content (specs, beads, code) without user input first
- NEVER skip a phase — you are responsible for every phase's execution
- NEVER proceed to next phase until user selects [G] Go
- NEVER create beads until Phase 4 explicit approval

### Phase 1: LISTEN & UNDERSTAND (never skip)

Do NOT immediately query the KG or create beads. Instead:

1. **Reflect back** what you heard in your own words — "So you want to..."
2. **Ask WHY** — "What problem does this solve? Who is this for?"
3. **Ask about EXISTING state** — "What do we have today that's related?"
4. **Ask about SUCCESS** — "How will we know this works? What does good look like?"
5. **First Principles** — "What's the core thing we're really trying to achieve,
   if we strip away all assumptions?"

Rules:
- NEVER generate a solution or spec until the human has answered these questions
- NEVER assume you understand the full scope from a one-sentence request
- If the human says "just do it" — push back ONCE: "I want to make sure I build
  the right thing. Can you tell me [specific question]?"
- Use **Socratic Questioning** — challenge vague claims with "why?" and "how?"

Present the menu:
**[D] Go Deeper** — "Want to explore any of these points further?"
**[A] Adjust** — "Want to change anything about what I heard?"
**[G] Go** — "Ready for me to analyze the system impact?"

### Phase 2: EXPLORE & ANALYZE (after Phase 1 [G])

NOW query the system — not before:

1. **Blast radius**: `get_blast_radius("concept")` — what's affected?
2. **Existing agents**: `search_agents("capability")` — who can already do this?
3. **Database context**: `get_entity_context("entity")` — what data exists?
4. **Dependencies**: `get_dependencies()` / `get_dependents()` — what ripples?
5. **Past work**: `bd search "keyword"` — have we done something similar before?

Present findings to the human:
- "This touches [N] agents and [M] files"
- "The most affected areas are [X, Y, Z]"
- "I see [existing capability] that we can build on"
- "This will require a new agent for [capability] because nothing exists today"
- "I found [N] related beads from past work: [brief summary]"

If new agent needed: "This doesn't map to any existing agent. I'll use
create-agent.sh to create one as part of the plan."

Present the menu:
**[D] Go Deeper** — "Want to explore any of these findings further?"
**[A] Adjust** — "Want to rethink the approach based on what I found?"
**[G] Go** — "Ready for me to define scope and boundaries?"

### Phase 3: SCOPE & BOUNDARIES (after Phase 2 [G])

Explicitly define with the human:

1. **Must-Have Analysis** — For each proposed feature, ask:
   - "Without this, does the feature fail?" → Must-have (MVP)
   - "Can this be manual initially?" → Nice-to-have (Phase 2)
   - "Is this a deal-breaker for first use?" → Must-have (MVP)

2. **Out of scope** — "What should we explicitly NOT do in this round?"

3. **Dependencies** — "This needs [X] to be done first. OK?"

4. **Pre-mortem (MANDATORY)** — "Imagine we built this and it failed in a month.
   What went wrong? What did we miss?"
   (This forces the human to think about failure modes BEFORE we start building.)

5. **Inversion** — "How could we guarantee this feature FAILS? Let's make sure
   we're not doing any of those things."

Present as a clear summary:
```
WHAT: [one-sentence description]
WHY: [problem it solves]
WHO: [which agents, which modules]
MVP (must-have): [minimum viable deliverable]
PHASE 2 (nice-to-have): [deferred to next round]
NOT NOW: [explicitly out of scope]
DEPENDS ON: [blockers]
RISKS: [what could go wrong]
PRE-MORTEM: [top failure scenario + how we prevent it]
```

Then ask: **"Does this capture it? Should I adjust anything before I create beads?"**

Present the menu:
**[D] Go Deeper** — "Want to stress-test any part of this plan?"
**[A] Adjust** — "Want to change the scope, add requirements, or reconsider?"
**[G] Go** — "Ready for me to create the beads?"

### Phase 4: CONFIRM & CREATE (after Phase 3 [G])

The human MUST explicitly approve before you create beads. Look for:
- "yes", "go", "looks good", "approved", "do it", "ship it"

Do NOT proceed on ambiguous responses like "hmm", "maybe", "I think so".
If ambiguous, ask: "I want to be sure — should I create the beads and dispatch agents?"

ONLY AFTER explicit approval:
1. Create epic bead with the full scope summary from Phase 3
2. Create task beads with Spec-Kit Quality (see below) for each agent
3. Set dependencies between beads: `bd dep add <child> <parent>`
4. Dispatch unblocked agents via spawn.sh
5. Report: "Created [N] beads. [M] agents dispatched. [K] waiting on dependencies."

### Spec-Kit Quality for Beads (MANDATORY — every bead, no exceptions)

When you DO create beads (after Phase 4 approval), every bead MUST have ALL of
these fields. A bead without these fields is INCOMPLETE and must not be created.

```
## Title
[Clear, specific, action-oriented — not vague like "Update stuff"]

## Spec
[What to build — detailed enough that an agent with NO prior context can execute.
 Include: what exists today, what needs to change, why, and how.
 Reference specific files, functions, schemas where applicable.]

## Acceptance Criteria
- [ ] [Specific, testable criterion — "User can search by name and email"]
- [ ] [Specific, testable criterion — "Search returns results in <200ms"]
- [ ] [Specific, testable criterion — "Empty query returns 400 error"]
(Minimum 3 criteria per bead. Each must be independently verifiable.)

## Contract
Input: [What this component receives — data types, sources, format]
Output: [What this component produces — format, schema, destination]

## Affected Files (from KG blast radius)
- file.py (owner-agent) — [what changes in this file]
- other.py (other-agent) — [what changes in this file]

## Dependencies
- Blocked by: [bead-id] — [reason this must complete first]
- Blocks: [bead-id] — [what is waiting on this]

## Out of Scope
- [Explicitly what this bead does NOT do]
- [This prevents agent from gold-plating or scope-creeping]
```

An agent should be able to read ONLY its bead and know exactly what to build,
what "done" looks like, and what NOT to do.

### Override: When to Skip Elicitation (YOLO Mode)

You MAY skip Phases 1-3 ONLY when ALL of these are true:
- The human explicitly says "skip brainstorming", "yolo", or "I know exactly what I want"
- The request is a single, well-defined bug fix or trivial change
- The blast radius is <=2 files owned by 1 agent

Even when skipping, Spec-Kit Quality (Phase 4) is NEVER skippable.
Every bead must have all fields regardless of how fast the human wants to go.

### State Tracking

After each phase, mentally track which phases are complete:
- [ ] Phase 1: Listen & Understand
- [ ] Phase 2: Explore & Analyze
- [ ] Phase 3: Scope & Boundaries
- [ ] Phase 4: Confirm & Create

If the conversation is interrupted (context limit, session restart), check
this state by reviewing conversation history before continuing.
```

---

## How This Changes the Orchestrator's Behavior

### Before (current):
```
Human: "Add user search"
Orchestrator: *immediately* get_blast_radius("User") → create 5 beads → dispatch
Result: 5 agents build something, but maybe not what the human wanted.
```

### After (with elicitation protocol):
```
Human: "Add user search"

═══ PHASE 1: LISTEN & UNDERSTAND ═══

Orchestrator: "So you want users to be able to search for other users in the app.
  A few questions before I plan this out:
  1. What kind of search? Name only, or also email, phone, location?
  2. Who needs this — end users, admins, coaches?
  3. Is there any search functionality today we're building on?
  4. What does 'good' look like — instant results, fuzzy matching, filters?
  5. At its core — is this about finding specific people, or browsing/discovery?

  [D] Go Deeper  [A] Adjust  [G] Go"
Human: "Name and email. End users. No search exists today. Fast, simple, no fuzzy."

Orchestrator: "Got it — focused, simple search. [G] Go"

---

PHASE 2: EXPLORE and ANALYZE

Orchestrator: *queries KG*
  get_blast_radius("User")
    -> api-agent (src/api/users.py), db-agent (src/models/user.py), ui-agent (ui/src/UserList.tsx)

  "Here's what I found:
  - This touches 3 agents: db-agent, api-agent, ui-agent
  - 5 files affected across those agents
  - The users table has 85k rows. Name and email are not indexed for search yet.
  - db-agent recently added last_login column (bead baap-3a7)
  - No existing search functionality in the codebase.

  [D] Go Deeper  [A] Adjust  [G] Go"
Human: "Go"

---

PHASE 3: SCOPE and BOUNDARIES

Orchestrator: "Let me define the scope with you:

  MUST-HAVE (MVP):
  - FULLTEXT index on users.name + users.email
  - GET /api/users/search?q=term endpoint
  - Basic search results display in UI

  NICE-TO-HAVE (Phase 2):
  - Pagination, filters, advanced search
  - Search history, recent searches

  NOT NOW:
  - Fuzzy matching, typo tolerance
  - Search analytics

  Now the pre-mortem: Imagine we shipped this and it failed.
  What could go wrong?
  - Search is too slow on 85k rows? FULLTEXT should handle it.
  - API returns too much data? We'll cap at 20 results.
  - SQL injection in search query? Parameterized queries mandatory.

  WHAT: Add user search by name and email
  WHY: End users need to find other users quickly
  WHO: db-agent (index), api-agent (endpoint), ui-agent (display)
  MVP: FULLTEXT index + search endpoint + basic UI
  PHASE 2: Pagination, filters, history
  NOT NOW: Fuzzy matching, analytics
  DEPENDS ON: Nothing (no blockers)
  RISKS: Slow query on large table (mitigated by FULLTEXT)
  PRE-MORTEM: Unparameterized SQL → injection. Prevention: use ORM.

  Does this capture it?

  [D] Go Deeper  [A] Adjust  [G] Go"
Human: "Go"

---

PHASE 4: CONFIRM and CREATE

Orchestrator: "Creating beads now..."
  - Epic: "Add user search" (baap-500)
  - Task: "Add FULLTEXT index on users.name+email" -> db-agent (baap-501)
  - Task: "Add GET /api/users/search endpoint" -> api-agent (baap-502, blocked by 501)
  - Task: "Add search UI to user list page" -> ui-agent (baap-503, blocked by 502)

  "Created 4 beads. 1 agent dispatched (db-agent). 2 waiting on dependencies."

Result: 3 agents build EXACTLY what the human wanted, in the right order,
with clear specs and boundaries. No wasted work.
```

---

## Success Criteria

- [ ] CLAUDE.md updated with the full Orchestrator Elicitation Protocol
- [ ] Protocol has 4 mandatory phases with menu gates between each
- [ ] Phase 1 includes reflect-back, WHY, existing state, success criteria, first principles
- [ ] Phase 2 queries KG (blast radius, agents, DB, dependencies, past beads)
- [ ] Phase 3 includes must-have analysis, pre-mortem (mandatory), inversion, scope summary
- [ ] Phase 4 requires explicit human approval before bead creation
- [ ] D/A/G menu presented after every phase (non-negotiable)
- [ ] Spec-Kit Quality template defined with all 7 mandatory fields
- [ ] YOLO mode override documented (explicit opt-in only, spec-kit still required)
- [ ] State tracking checklist included for session interruption recovery
- [ ] CRITICAL RULES block at the top (4 NEVER rules)
- [ ] Orchestrator cannot create beads without completing all phases

## Verification

Test the protocol by asking the orchestrator a vague request and verifying behavior:

```bash
# In a Claude Code session with the updated CLAUDE.md:

# Test 1: Vague request → should trigger Phase 1 questions
# Human: "Add notifications"
# Expected: Orchestrator asks WHY, what kind, who gets them, etc.
# NOT expected: Orchestrator immediately creates beads

# Test 2: "Just do it" → should push back once
# Human: "Just add it"
# Expected: "I want to make sure I build the right thing. Can you tell me..."
# NOT expected: Immediate bead creation

# Test 3: Ambiguous approval → should ask for confirmation
# Human: "Maybe looks ok"
# Expected: "I want to be sure — should I create the beads?"
# NOT expected: Bead creation on "maybe"

# Test 4: Explicit approval → should create with spec-kit quality
# Human: "Go"
# Expected: Epic bead + task beads, each with Title, Spec, AC, Contract,
#           Affected Files, Dependencies, Out of Scope
# NOT expected: Beads with vague descriptions or missing fields

# Test 5: D/A/G menu → should appear after every phase
# Verify the menu is presented 4 times during a full elicitation cycle.

# Test 6: YOLO mode → only on explicit request
# Human: "yolo, just add a column"
# Expected: Phases 1-3 skipped, but spec-kit quality still enforced
```

## Advanced Elicitation Techniques Reference

These techniques are available via [D] Go Deeper at any phase:

| Technique | When to Use | How |
|-----------|-------------|-----|
| **Pre-mortem** | Phase 3 (mandatory) | "Imagine it failed. What went wrong?" |
| **Inversion** | Phase 3 (recommended) | "How could we guarantee failure?" |
| **First Principles** | Phase 1 | "Strip away assumptions, what's the core need?" |
| **Socratic Questioning** | Any phase | "Why? How do you know? What if not?" |
| **Constraint Removal** | Phase 2 | "No constraints — what changes? Add back selectively" |
| **Stakeholder Mapping** | Phase 1 | "Who else cares? How would [role] view this?" |
| **Analogical Reasoning** | Phase 2 | "Where has this been solved before? Apply lessons" |
| **Red Team** | Phase 3 | "Attack the plan. What breaks?" |

Source: BMAD Method Advanced Elicitation (docs.bmad-method.org/explanation/advanced-elicitation/)
