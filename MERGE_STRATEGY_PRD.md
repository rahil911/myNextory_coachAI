# PRD: Agent Worktree Branch Divergence Resolution

**Author**: Orchestrator (L0)
**Date**: 2026-02-19
**Status**: Draft
**Priority**: P0 (Blocks scaling beyond 3 concurrent agents)

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Current State Analysis](#2-current-state-analysis)
3. [Research Findings](#3-research-findings)
4. [Proposed Solutions](#4-proposed-solutions)
5. [Recommended Approach](#5-recommended-approach)
6. [Implementation Plan](#6-implementation-plan)
7. [Risk Analysis](#7-risk-analysis)
8. [Decision Log](#8-decision-log)

---

## 1. Problem Statement

### 1.1 Core Issue

The baap multi-agent system spawns parallel agents in git worktrees, each branched from `main` at spawn time. When agents complete work at different times, the `main` branch advances with each merge, causing later-finishing agents to have stale base commits. This creates merge conflicts that require manual intervention, breaking the autonomous agent pipeline.

### 1.2 Concrete Example from Production

The `tory_engine.py` file (4,937 lines, owned by `content-agent`) was modified by at least **8 different beads** across a single epic (`baap-qkk`):

| Bead | Agent | What Changed | Merge Order |
|------|-------|-------------|-------------|
| baap-qkk.2 | tory-agent | Content tagging pipeline | 1st |
| baap-qkk.3 | identity-agent | Learner profile generation | 2nd |
| baap-qkk.4 | content-agent | Scoring & path generation engine | 3rd |
| baap-qkk.5 | content-agent | Coach curation API | 4th |
| baap-qkk.6 | engagement-agent | Reassessment scheduler | 5th |
| baap-qkk.10 | content-agent | Coach review queue | 6th |
| baap-qkk.11-12 | platform-agent | Production hardening + E2E tests | 7th |
| baap-1hu | content-agent | User status + lesson impact tools | 8th |

Each agent branched from `main` at its spawn time. Agent 3 saw none of agent 2's changes. Agent 5 saw none of agents 2-4's changes. The result: cascading merge conflicts on a single 4,937-line file, each requiring the orchestrator to manually extract new functions and commit them to `main`.

### 1.3 Failure Modes Observed

**Mode 1: Additive-only conflicts (most common)**
Two agents both append new functions to the end of `tory_engine.py`. Git cannot auto-merge because both branches extend the same end-of-file region. These are semantically safe (no logical conflict) but textually unresolvable by git.

**Mode 2: Shared-section modifications**
Two agents modify the same `mysql_query()` helper or add imports to the same import block. These are true logical conflicts requiring semantic understanding to resolve.

**Mode 3: Cascading rebase failures**
After merging Agent A, rebasing Agent B onto new `main` succeeds. But rebasing Agent C (which also diverged from the original `main`) fails because the rebase encounters conflicts introduced by both A and B's merged changes.

**Mode 4: Schema drift**
Agent A adds a column to `tory_recommendations` and updates the INSERT statements in `tory_engine.py`. Agent B, unaware of the new column, writes INSERT statements that are now missing a field. This is a semantic conflict that no textual merge tool can detect.

### 1.4 Impact

| Metric | Current | Target |
|--------|---------|--------|
| Max parallel agents without conflicts | 2-3 | 8-10 |
| Manual merge interventions per epic | 3-5 | 0 |
| Time spent on merge resolution | 20-40 min/merge | <2 min (automated) |
| Agent idle time waiting for sequential merge | 10-30 min | 0 (agents never block on merge) |

---

## 2. Current State Analysis

### 2.1 spawn.sh (Agent Creation)

**Location**: `/home/rahil/Projects/baap/.claude/scripts/spawn.sh`

The spawn script creates worktrees with a simple branch from wherever `main` currently is:

```bash
git worktree add "$AGENT_DIR/$NAME" -b "agent/$NAME"
```

**Key characteristics**:
- Branch is created from `HEAD` of `main` at spawn time
- No mechanism to track what `main` commit an agent branched from
- No pre-spawn check for potential conflicts with in-flight agent branches
- No mechanism to notify running agents that `main` has moved forward

### 2.2 cleanup.sh (Agent Merge)

**Location**: `/home/rahil/Projects/baap/.claude/scripts/cleanup.sh`

The merge operation uses a file lock for serialization and a simple `--no-ff` merge:

```bash
(
  flock -w 300 200 || { echo "ERROR: Could not acquire merge lock" >&2; exit 1; }
  git checkout "$TARGET"
  git pull --rebase --autostash
  git merge "$BRANCH" --no-ff -m "Merge $BRANCH results" --no-verify
) 200>"$LOCK_FILE"
```

**Key characteristics**:
- File-based lock (`/tmp/baap-merge.lock`) ensures only one merge at a time (good)
- Pre-merge gates: KG ownership check, bead closure check, security scan, test gate, review gate
- No pre-merge rebase of the agent branch onto latest `main`
- No conflict detection before attempting the merge
- If `git merge` fails (conflict), the entire cleanup.sh exits with error, requiring manual intervention
- No fallback strategy (no automatic rebase, no AI-assisted resolution, no partial merge)

### 2.3 Ownership KG (Conflict Prevention)

The Knowledge Graph enforces exclusive file ownership:

```
tory_engine.py -> owned by content-agent (exclusive)
```

**The gap**: While the KG prevents two *agents* from owning the same file, it does NOT prevent multiple *beads* assigned to the same agent from modifying the same file in parallel worktrees. In our case, `content-agent` is responsible for `tory_engine.py`, but beads baap-qkk.4, baap-qkk.5, and baap-qkk.10 all modified it independently.

Additionally, agent ownership is not always respected in practice. The commit history shows `identity-agent`, `engagement-agent`, `tory-agent`, and `platform-agent` all modifying `tory_engine.py` despite it being owned by `content-agent`. The blast radius analysis confirms 10 agents are affected by changes to this file.

### 2.4 The Monolithic File Problem

`tory_engine.py` at 4,937 lines contains 13 distinct sections:

| Section | Lines (approx) | Purpose |
|---------|----------------|---------|
| Constants | 1-81 | EPP dimensions, config values |
| Rate Limiting | 82-113 | Token bucket rate limiter |
| Logging | 114-136 | Structured logging |
| Input Validation | 137-191 | Parameter validators |
| Circuit Breaker | 192-242 | External API protection |
| MySQL Helpers | 243-307 | DB query layer |
| Vector Math | 308-341 | Cosine similarity |
| Data Access Layer | 342-583 | 25+ query functions |
| Criteria Corp API | 584-661 | External EPP API client |
| Reassessment Engine | 662-1087 | Profile drift, re-ranking |
| EPP Parser | 1088-1172 | Score parsing |
| Scoring Engine | 1173-1434 | Content scoring, sequencing |
| MCP Server + Tools | 1435-4937 | Tool definitions, dispatch |

These sections have different change frequencies. The MCP Server section (lines 1435-4937, ~3,500 lines) is where most bead-driven additions happen -- each new MCP tool adds a tool definition and a handler function. This is the primary conflict zone.

### 2.5 Current Workaround (Manual Extraction)

When merge conflicts occur, the orchestrator:
1. Reads the agent's worktree to identify new functions/code
2. Manually copies those additions to `main`
3. Commits directly to `main`
4. Discards the agent's worktree

This works when agents only ADD new functions (no modifications). It fails when agents modify existing functions, change shared infrastructure, or when the additions depend on changes made in the same commit (e.g., a new constant + a function using it).

---

## 3. Research Findings

### 3.1 Merge Queue Systems

#### GitHub Merge Queue
[GitHub's native merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) ensures each PR is compatible with the target branch before merging. It processes PRs sequentially by default, rebasing each onto the latest target branch and re-running CI before merging. However, it does not support batching multiple PRs into a single merge and operates strictly FIFO. Not suitable for our local-only workflow.

#### Mergify
[Mergify](https://docs.mergify.com/merge-queue/) supports batching PRs, multiple queues with priorities, parallel checks via speculative execution, and custom queue rules. Key innovation: it creates draft PRs that speculatively combine changes and tests them in parallel. If the batch passes, all PRs in the batch merge together.

#### Trunk Merge Queue
[Trunk](https://trunk.io/merge-queue) introduces **parallel queues** based on "impacted targets" -- if two PRs affect different parts of the codebase, they run in independent testing lanes. It also supports **optimistic merging**: when a PR later in the queue passes, all PRs ahead of it can be safely merged.

#### Aviator MergeQueue
[Aviator](https://www.aviator.co/merge-queue) creates dynamic parallel queues based on **affected targets** in distributed builds. PRs with non-overlapping targets merge independently. PRs with overlapping targets are stacked and tested together. This is the closest model to what we need.

**Key takeaway**: All production merge queue systems solve the "main moved forward" problem by rebasing/testing against the latest `main` before merge. The differentiation is in parallelism strategies.

### 3.2 Monorepo Tools

#### Google Piper
[Google's Piper](https://qeunit.com/blog/how-google-does-monorepo/) uses trunk-based development where developers commit directly to `main` (trunk). There are no long-lived branches. Changes are atomic, cross-project commits. Conflicts are detected at commit time, not merge time. Google's scale (billions of LOC) is supported by custom tooling that simply rejects conflicting commits and asks the developer to rebase.

#### Meta Sapling
[Meta's Sapling](https://engineering.fb.com/2025/10/16/developer-tools/branching-in-a-sapling-monorepo/) uses two branching modes: (1) non-mergeable full-repo branches for release cutting, and (2) mergeable directory-scoped branches. At the monorepo commit graph level, all merges appear as linear commits, solving scalability issues with merge commit graphs. The key insight is that **directory-level isolation** maps perfectly to our **module-level isolation via the KG**.

#### Graphite (Stacked PRs)
[Graphite](https://graphite.com/docs/graphite-merge-queue) introduces **stack-aware merge queues** that treat dependent PRs as atomic units. When a stack of PRs is queued, the system validates the entire stack by running CI on the top-most PR (which contains all downstream changes). After merging, Graphite [automatically rebases](https://graphite.com/blog/automatic-rebase-after-merge) all partially-merged stacks.

**Key takeaway**: Monorepo tools succeed by making changes smaller and more linear. Directory/module isolation is a proven pattern for avoiding conflicts.

### 3.3 Conflict Detection Tools

#### Clash
[Clash](https://github.com/clash-sh/clash) is a purpose-built tool for detecting merge conflicts across git worktrees for parallel AI coding agents. Written in Rust, it uses `git merge-tree` (via the gix library) to perform **read-only three-way merges** between worktree pairs without modifying the repository.

Key features:
- `clash check <file>` -- analyzes a single file for conflicts across all worktrees
- `clash status` -- conflict matrix showing all worktree pairs
- `clash watch` -- live monitoring with auto-refresh on file changes
- JSON output for programmatic integration
- Claude Code plugin for pre-write conflict checks

**Key takeaway**: Clash solves early detection but not resolution. It is exactly what we need as a building block for conflict prevention.

#### git merge-tree
The built-in `git merge-tree` command performs three-way merges between tree objects and outputs conflicts without modifying the working directory. The `--early-exit` flag allows it to abort as soon as a conflict is found, making it efficient for conflict checking in tight loops.

### 3.4 AI-Assisted Merge Resolution

#### LLMinus (Linux Kernel)
[LLMinus](https://lwn.net/Articles/1053714/) by NVIDIA's Sasha Levin builds a searchable database of historical conflict resolutions from git history, uses semantic embeddings to find similar past conflicts, and constructs rich prompts for LLMs to resolve current conflicts.

#### CHATMERGE (Academic)
[CHATMERGE](https://ieeexplore.ieee.org/document/10366637/) uses ML to predict resolution strategies and leverages ChatGPT for complex resolutions. It classifies conflicts by type (additive, deletive, rewrite, etc.) and applies strategy-specific resolution.

#### Rizzler
[Rizzler](https://github.com/ghuntley/rizzler) sends conflicting code snippets to LLMs (GPT-4 or Claude) and the AI analyzes changes to generate a semantically correct merged version.

**Key takeaway**: AI-assisted merge resolution is viable for our use case. Our agents already use Claude, and our conflicts are well-structured (we know what each bead was supposed to do). The combination of bead specs + conflict markers gives Claude excellent context for resolution.

### 3.5 OpenAI Codex Approach
[OpenAI Codex](https://developers.openai.com/codex/app/worktrees/) uses the same worktree-per-agent model. Their documented strategies for resolution:
- **Strategy A**: Merge branches one at a time, resolving conflicts sequentially
- **Strategy B**: Apply as patches (cleaner history but more fragile)
- **Limitation acknowledged**: Codex does not auto-fix merge conflicts; users resolve manually or rerun tasks

**Key takeaway**: Even OpenAI has not solved this problem automatically. Manual/sequential merge is the industry standard. Our opportunity is to build something better using the KG ownership data and bead specs that other systems lack.

---

## 4. Proposed Solutions

### 4.1 Quick Wins (Hours to Implement)

#### QW-1: Pre-Merge Rebase in cleanup.sh

**What**: Before attempting `git merge`, automatically rebase the agent branch onto latest `main`.

**Change to cleanup.sh**:
```bash
# Inside the flock section, BEFORE merge:
cd "$PROJECT"
git checkout "$TARGET"
git pull --rebase --autostash

# Rebase agent branch onto latest target
git checkout "$BRANCH"
REBASE_EXIT=0
git rebase "$TARGET" || REBASE_EXIT=$?

if [ "$REBASE_EXIT" -ne 0 ]; then
  git rebase --abort
  echo "REBASE FAILED: Agent branch has conflicts with current $TARGET"
  echo "Falling back to merge attempt..."
  git checkout "$TARGET"
  git merge "$BRANCH" --no-ff -m "Merge $BRANCH results" || {
    echo "MERGE ALSO FAILED. Manual intervention required."
    exit 1
  }
else
  git checkout "$TARGET"
  git merge "$BRANCH" --ff-only -m "Merge $BRANCH results (rebased)"
fi
```

**Impact**: Eliminates conflicts from "additive-only" cases (the most common type) where two agents append to different parts of the same file. The rebase cleanly replays commits on top of the merged changes.

**Effort**: 1-2 hours.

**Limitation**: Does not help when the rebase itself conflicts (true overlapping edits).

---

#### QW-2: Conflict Detection Before Merge (using git merge-tree)

**What**: Before acquiring the merge lock, run `git merge-tree` to detect conflicts. If conflicts exist, report them instead of failing mid-merge.

**New helper in cleanup.sh**:
```bash
detect_conflicts() {
  local BASE TARGET BRANCH
  BASE=$(git merge-base "$1" "$2")
  RESULT=$(git merge-tree "$BASE" "$1" "$2" 2>&1)
  if echo "$RESULT" | grep -q "^<<<<<<<"; then
    echo "$RESULT"
    return 1
  fi
  return 0
}

# Before merge lock:
if ! detect_conflicts "$TARGET" "$BRANCH"; then
  echo "CONFLICT DETECTED between $BRANCH and $TARGET"
  echo "Conflicting regions:"
  detect_conflicts "$TARGET" "$BRANCH" 2>&1 | head -50
  # Option: invoke AI-assisted resolution here
fi
```

**Impact**: Immediate feedback on conflicts without partially completing a merge. Enables routing to different resolution strategies based on conflict type.

**Effort**: 1-2 hours.

---

#### QW-3: Sequential Merge Ordering via Bead Dependencies

**What**: Instead of merging agents in whatever order they finish, enforce merge ordering based on bead dependency chains. If bead B depends on bead A, do not merge B until A is merged.

**Implementation**: Already partially supported via `bd dep add`. Enhancement: `cleanup.sh` should check if the agent's bead has unmerged dependencies before proceeding.

```bash
# Check dependency order before merge
if command -v bd &>/dev/null; then
  BEAD_ID=$(cat "$WORKTREE/.agent_bead_id" 2>/dev/null || true)
  if [ -n "$BEAD_ID" ]; then
    DEPS=$(bd show "$BEAD_ID" --json 2>/dev/null | python3 -c "
import json, sys
try:
    bead = json.load(sys.stdin)
    deps = bead.get('depends_on', [])
    # Check if all dependencies are closed
    for dep in deps:
        status = ... # query status
        if status != 'closed':
            print(dep)
except: pass
" 2>/dev/null || true)
    if [ -n "$DEPS" ]; then
      echo "BLOCKED: Bead $BEAD_ID depends on unmerged beads: $DEPS"
      echo "Merge those first, then retry this agent."
      exit 1
    fi
  fi
fi
```

**Impact**: Prevents the cascading rebase failure problem (Mode 3). Agents that build on other agents' work always merge in the right order.

**Effort**: 2-3 hours.

---

### 4.2 Medium-Term Improvements (Days to Implement)

#### MT-1: Integrate Clash for Real-Time Conflict Detection

**What**: Install [Clash](https://github.com/clash-sh/clash) and integrate it into the agent lifecycle.

**Architecture**:
```
spawn.sh                     agent runtime                  cleanup.sh
   |                              |                              |
   +-- clash check at spawn  --> clash watch during work  --> clash status before merge
   |   (warn if conflicts         (notify agent if             (block merge if
   |    with in-flight agents)     new conflicts arise)         conflicts exist)
```

**Integration points**:

1. **At spawn time** (`spawn.sh`): Run `clash status --json` to check if the new worktree will conflict with existing worktrees. Warn the orchestrator.

2. **During agent work**: Add to the agent system prompt:
   ```
   Before editing any file, run: clash check <filepath>
   If conflicts detected, adapt your approach to avoid conflicting lines.
   ```

3. **At merge time** (`cleanup.sh`): Run `clash status --json` and parse for conflicts with `main`. If conflicts exist, attempt automated resolution before manual escalation.

**Effort**: 2-3 days (install, integrate, test).

**Impact**: Shifts conflict detection from merge-time to work-time. Agents can self-correct during development.

---

#### MT-2: AI-Assisted Merge Conflict Resolution

**What**: When merge/rebase fails, invoke Claude to semantically resolve the conflicts using bead specs as context.

**Architecture**:
```bash
resolve_conflicts_with_ai() {
  local BRANCH="$1" TARGET="$2" BEAD_ID="$3"

  # 1. Get conflict diff
  git merge "$BRANCH" --no-commit || true
  CONFLICTS=$(git diff --name-only --diff-filter=U)

  for FILE in $CONFLICTS; do
    # 2. Get the three versions
    OURS=$(git show "$TARGET:$FILE")
    THEIRS=$(git show "$BRANCH:$FILE")
    BASE=$(git merge-base "$TARGET" "$BRANCH")
    ANCESTOR=$(git show "$BASE:$FILE")

    # 3. Get the bead spec for context
    BEAD_SPEC=$(bd show "$BEAD_ID" 2>/dev/null || echo "No bead context")

    # 4. Build resolution prompt
    PROMPT="You are resolving a git merge conflict.

The base version (common ancestor) is:
$ANCESTOR

The main branch version (ours) is:
$OURS

The agent branch version (theirs) is:
$THEIRS

The agent was working on this task:
$BEAD_SPEC

Produce the correctly merged version that:
1. Preserves ALL changes from main (ours)
2. Incorporates ALL changes from the agent (theirs)
3. Resolves any true conflicts using the bead spec as intent
4. Maintains code correctness (no duplicate functions, proper imports)

Output ONLY the final merged file content, no explanations."

    # 5. Call Claude for resolution
    RESOLVED=$(claude -p "$PROMPT" --output-format text)

    # 6. Apply resolution
    echo "$RESOLVED" > "$FILE"
    git add "$FILE"
  done

  git commit -m "AI-resolved merge: $BRANCH -> $TARGET"
}
```

**Impact**: Handles Mode 1 (additive conflicts) and Mode 2 (shared-section modifications) automatically. Reduces manual intervention from 20-40 min to ~2 min (AI resolution + human review).

**Risks**:
- AI may introduce subtle bugs in complex resolution
- Cost: ~$0.50-2.00 per conflict resolution (Opus for accuracy)
- Requires human review gate after AI resolution

**Mitigation**: Run test gate AFTER AI resolution. If tests fail, discard and escalate to human.

**Effort**: 3-5 days.

---

#### MT-3: Main-Tracking Agent Branches (Periodic Rebase)

**What**: While agents are working, periodically rebase their worktree branches onto the latest `main`. This keeps divergence small and surfaces conflicts early.

**Architecture**:
```bash
# New script: .claude/scripts/sync-agents.sh
# Run after each cleanup.sh merge

for WORKTREE in ~/agents/*/; do
  AGENT_NAME=$(basename "$WORKTREE")
  BRANCH="agent/$AGENT_NAME"

  cd "$WORKTREE"

  # Stash agent's uncommitted changes
  git stash push -m "sync-stash" 2>/dev/null || true

  # Attempt rebase onto latest main
  REBASE_EXIT=0
  git fetch origin main 2>/dev/null || true
  git rebase main || REBASE_EXIT=$?

  if [ "$REBASE_EXIT" -ne 0 ]; then
    git rebase --abort
    echo "WARN: $AGENT_NAME cannot rebase cleanly onto main. Conflict detected."
    # Notify orchestrator via bead
  else
    echo "OK: $AGENT_NAME rebased onto latest main"
  fi

  # Restore agent's uncommitted changes
  git stash pop 2>/dev/null || true
done
```

**Trigger**: Run this after every `cleanup.sh merge` completes.

**Impact**: Keeps agent branches within 1-2 commits of `main`. Conflicts are detected immediately after the first merge, not after 5 merges.

**Risks**:
- Rebasing while an agent is actively editing files can cause confusion
- Agent's uncommitted changes may conflict with the rebase
- Must coordinate with agent checkpoints

**Mitigation**: Only rebase between agent checkpoints (check `.agent_exit_code` or heartbeat). Never rebase an actively running agent.

**Effort**: 2-3 days.

---

#### MT-4: Bead-Aware Merge Queue

**What**: Build a local merge queue that processes agent merges in dependency order, automatically rebasing each pending agent branch after each merge.

**Architecture**:
```
Merge Queue Manager (new script: merge-queue.sh)
  |
  +-- Input: List of agent branches ready to merge
  |
  +-- Step 1: Topological sort by bead dependencies
  |
  +-- Step 2: For each agent (in order):
  |     a. Rebase agent branch onto current main
  |     b. If rebase fails: attempt AI resolution
  |     c. If AI fails: skip agent, queue for manual resolution
  |     d. Run gates (security, test, review)
  |     e. Merge to main
  |     f. Rebase ALL remaining queued agents onto new main
  |
  +-- Step 3: Report results
```

**Impact**: Fully automated sequential merge with dependency awareness. Handles all four failure modes except Mode 4 (schema drift, which requires semantic validation).

**Effort**: 5-7 days.

---

### 4.3 Long-Term Architecture Changes (Weeks to Implement)

#### LT-1: Decompose Monolithic Files into Module Packages

**What**: Split `tory_engine.py` (4,937 lines) into a Python package with separate files per logical section. Apply the same decomposition to any file over 500 lines.

**Proposed structure**:
```
.claude/mcp/tory_engine/
  __init__.py           # Package entry, MCP server setup
  constants.py          # EPP dimensions, config (lines 1-81)
  db.py                 # MySQL helpers, circuit breaker (lines 192-307)
  data_access.py        # 25+ query functions (lines 342-583)
  vector_math.py        # Cosine similarity (lines 308-341)
  validators.py         # Input validation (lines 137-191)
  logging.py            # Structured logging (lines 114-136)
  rate_limiter.py       # Token bucket (lines 82-113)
  criteria_api.py       # Criteria Corp API client (lines 584-661)
  reassessment.py       # Reassessment engine (lines 662-1087)
  epp_parser.py         # EPP score parsing (lines 1088-1172)
  scoring.py            # Content scoring, sequencing (lines 1173-1434)
  rationale.py          # Rationale generation (lines 1435-1600)
  tools/
    __init__.py         # Tool registry
    learner_tools.py    # Learner data, profile, roadmap tools
    content_tools.py    # Content tagging, scoring tools
    coach_tools.py      # Coach curation, review queue tools
    workspace_tools.py  # Workspace data tools
    path_tools.py       # Path generation, reorder, swap tools
```

**Ownership mapping**: Each file gets its own KG owner:
```
tory_engine/constants.py     -> content-agent
tory_engine/criteria_api.py  -> identity-agent
tory_engine/reassessment.py  -> engagement-agent
tory_engine/scoring.py       -> content-agent
tory_engine/tools/coach_tools.py -> content-agent
tory_engine/tools/workspace_tools.py -> platform-agent
```

**Impact**: Eliminates 80%+ of merge conflicts on `tory_engine.py` because different agents now edit different files. This is the single highest-impact change possible.

**Effort**: 1-2 weeks (decomposition + updating all imports + testing).

---

#### LT-2: Trunk-Based Development with Feature Flags

**What**: Instead of agent branches, agents commit directly to `main` behind feature flags. Each bead gets a flag like `TORY_FEATURE_BAAP_QKK_5=true`.

**How it works**:
```python
# In tory_engine.py
if os.getenv("TORY_FEATURE_COACH_CURATION"):
    @server.tool("tory_coach_reorder")
    async def handle_coach_reorder(...):
        ...
```

Agents commit to `main` frequently (every checkpoint). Feature flags ensure unfinished work is not exposed. When the bead is closed, the flag guard is removed.

**Impact**: Eliminates branches entirely. No merge conflicts possible. Mimics Google's trunk-based development model.

**Risks**:
- Agents committing to `main` directly eliminates the safety of worktree isolation
- A broken commit on `main` blocks all agents
- Feature flag accumulation creates technical debt
- Requires very strong test gates on `main`

**Effort**: 2-3 weeks.

**Verdict**: Too risky for our current maturity. Requires CI/CD that we do not have. Revisit when we have a full test suite.

---

#### LT-3: Epic Branches with Stacked Merges (Graphite Model)

**What**: Instead of merging each agent directly to `main`, merge to an **epic branch** first. The epic branch collects all agent work for a single epic, then merges to `main` as one atomic unit.

**Architecture**:
```
main ──────────────────────────────────────────── main (after epic merge)
  \                                                /
   epic/baap-qkk ─────────────────────────────────
     \      \      \      \
      A1     A2     A3     A4  (agent branches, merged sequentially to epic)
```

**How it works**:
1. `spawn.sh` takes an optional `--epic` flag: `spawn.sh reactive "..." ~/Projects/baap --epic epic/baap-qkk`
2. Agent branches are created from the epic branch, not `main`
3. `cleanup.sh` merges to the epic branch (narrower scope = fewer conflicts)
4. When all beads in the epic are closed, merge the epic branch to `main`

This is already partially supported: `cleanup.sh` accepts an `[epic_branch]` argument but it is never used in practice.

**Impact**: Reduces the divergence window. Agent branches only need to be compatible with sibling agents in the same epic, not with all changes across all epics.

**Effort**: 1 week.

---

#### LT-4: File-Level Locking with Bead-Scoped Reservations

**What**: Extend the KG's advisory locking to enforce bead-scoped file reservations. When a bead is created that will modify a file, that file is "reserved" for that bead. Other beads that need the same file must wait or negotiate.

**Implementation**:
```bash
# At bead creation time:
ag lock tory_engine.py content-agent --bead baap-qkk.5

# At spawn time, check:
ag owner tory_engine.py
# Returns: "content-agent (locked by bead baap-qkk.5)"

# If another bead needs the same file:
# Option A: Queue (wait for lock release)
# Option B: Split work (decompose file first)
# Option C: Declare dependency (bd dep add new-bead baap-qkk.5)
```

**Impact**: Prevents the root cause -- multiple beads modifying the same file in parallel. Forces the orchestrator to think about file contention during Phase 3 (SCOPE & BOUNDARIES).

**Effort**: 1-2 weeks.

---

## 5. Recommended Approach

### 5.1 Phased Implementation Plan

Based on impact/effort analysis and the principle of "solve the pain now, build for scale later":

#### Phase A: Immediate (Do Today) -- 4-6 hours

1. **QW-1**: Pre-merge rebase in `cleanup.sh`
2. **QW-2**: Conflict detection before merge (git merge-tree)
3. **QW-3**: Dependency-ordered merge checking

These three changes make `cleanup.sh` significantly more robust with minimal risk.

#### Phase B: This Week -- 3-5 days

4. **MT-2**: AI-assisted merge conflict resolution
5. **MT-4**: Bead-aware merge queue (`merge-queue.sh`)

These eliminate manual intervention for 90% of conflicts.

#### Phase C: Next Sprint -- 1-2 weeks

6. **LT-1**: Decompose `tory_engine.py` into a package (HIGHEST LONG-TERM IMPACT)
7. **LT-3**: Epic branches with stacked merges

These prevent conflicts from occurring in the first place.

#### Phase D: Future -- As Needed

8. **MT-1**: Clash integration (useful if agent count grows to 5+)
9. **LT-4**: File-level locking with bead-scoped reservations
10. **MT-3**: Main-tracking agent branches (periodic rebase, only if Phase B is insufficient)

### 5.2 Rationale for Ordering

**Phase A first** because it is zero-risk, low-effort, and immediately reduces the failure rate of `cleanup.sh` from ~30% (on conflict-prone epics) to ~10%.

**Phase B second** because AI-assisted resolution + merge queue together handle the remaining 90% of that 10% -- bringing manual intervention close to zero.

**Phase C is the strategic move**: Decomposing monolithic files eliminates the root cause. After LT-1, most agents edit different files, and the merge queue rarely encounters conflicts. Epic branches further reduce the divergence window.

**Phase D is insurance**: These solutions address edge cases that only matter at scale (5+ concurrent agents) or in adversarial scenarios.

---

## 6. Implementation Plan

### 6.1 Phase A: Immediate Changes to cleanup.sh

**File**: `/home/rahil/Projects/baap/.claude/scripts/cleanup.sh`

**Change 1: Add conflict detection function**

Add before the `LOCKED MERGE SECTION`:
```bash
# ── PRE-MERGE: Conflict Detection ─────────────────────────────────────────
detect_merge_conflicts() {
  local TARGET_REF="$1" BRANCH_REF="$2"
  local BASE
  BASE=$(git merge-base "$TARGET_REF" "$BRANCH_REF" 2>/dev/null) || return 2

  local RESULT EXIT_CODE=0
  RESULT=$(git merge-tree "$BASE" "$TARGET_REF" "$BRANCH_REF" 2>&1) || EXIT_CODE=$?

  if echo "$RESULT" | grep -q "CONFLICT\|merged"; then
    echo "$RESULT"
    return 1
  fi
  return 0
}

echo "[pre-merge] Checking for conflicts..."
CONFLICT_OUTPUT=""
if ! CONFLICT_OUTPUT=$(detect_merge_conflicts "$TARGET" "$BRANCH" 2>&1); then
  echo "[pre-merge] WARNING: Potential conflicts detected"
  echo "$CONFLICT_OUTPUT" | head -20
  echo "[pre-merge] Attempting rebase-first strategy..."
fi
```

**Change 2: Add rebase-before-merge inside the flock section**

Replace the simple `git merge` with:
```bash
# Try rebase first (cleaner history, handles additive conflicts)
git checkout "$BRANCH" 2>/dev/null
REBASE_OK=true
git rebase "$TARGET" 2>/dev/null || {
  REBASE_OK=false
  git rebase --abort 2>/dev/null || true
}

git checkout "$TARGET" 2>/dev/null

if [ "$REBASE_OK" = true ]; then
  git merge "$BRANCH" --no-ff -m "Merge $BRANCH results (rebased)" --no-verify
else
  echo "[merge] Rebase failed. Attempting direct merge..."
  git merge "$BRANCH" --no-ff -m "Merge $BRANCH results" --no-verify || {
    echo "[merge] DIRECT MERGE FAILED. Manual resolution required."
    git merge --abort 2>/dev/null || true
    exit 1
  }
fi
```

**Change 3: Add dependency check before merge**

Add before the flock section:
```bash
# ── PRE-MERGE: Dependency Order Check ─────────────────────────────────────
BEAD_ID_FILE="$WORKTREE/.agent_bead_id"
if [ -f "$BEAD_ID_FILE" ] && command -v bd &>/dev/null; then
  CURRENT_BEAD=$(cat "$BEAD_ID_FILE")
  if [ -n "$CURRENT_BEAD" ]; then
    UNMERGED_DEPS=$(bd show "$CURRENT_BEAD" 2>/dev/null | grep -oP 'depends_on.*' || true)
    if [ -n "$UNMERGED_DEPS" ]; then
      echo "[pre-merge] NOTE: This bead has dependencies: $UNMERGED_DEPS"
      echo "[pre-merge] Ensure parent beads are merged first for cleanest results."
    fi
  fi
fi
```

### 6.2 Phase B: AI Resolution + Merge Queue

**New file**: `/home/rahil/Projects/baap/.claude/scripts/merge-queue.sh`

Core logic:
```bash
#!/usr/bin/env bash
# merge-queue.sh -- Process multiple agent merges in dependency order
# with automatic rebase and AI conflict resolution.
#
# Usage: merge-queue.sh [agent1] [agent2] ... [agentN]
#        merge-queue.sh --all    (merge all completed agents)

# 1. Discover agents ready to merge
# 2. Topological sort by bead dependencies
# 3. For each agent:
#    a. Rebase onto current main
#    b. If rebase fails: invoke AI resolution
#    c. If AI fails: skip, log, continue
#    d. Run gates
#    e. Merge
#    f. Notify remaining agents
# 4. Report results
```

**New file**: `/home/rahil/Projects/baap/.claude/scripts/resolve-conflicts-ai.sh`

Core logic:
```bash
#!/usr/bin/env bash
# resolve-conflicts-ai.sh -- Use Claude to resolve merge conflicts
#
# Usage: resolve-conflicts-ai.sh <branch> <target> [bead-id]
#
# Reads conflict markers from failed merge, sends to Claude with
# bead context, applies resolution, runs tests.

# 1. Identify conflicting files
# 2. For each file:
#    a. Extract ours/theirs/base versions
#    b. Get bead spec for context
#    c. Call Claude for resolution
#    d. Apply resolution
#    e. git add resolved file
# 3. Run test gate on resolved state
# 4. If tests pass: commit
# 5. If tests fail: abort and escalate
```

### 6.3 Phase C: File Decomposition

**Task**: Create a bead for `content-agent` to decompose `tory_engine.py` into a package.

**Acceptance criteria**:
1. All 13 sections in separate files under `.claude/mcp/tory_engine/`
2. MCP server still loads and all 30+ tools register correctly
3. All existing tests pass
4. KG ownership updated for each new file
5. No single file exceeds 500 lines

---

## 7. Risk Analysis

### 7.1 Risk Matrix

| Solution | Risk | Probability | Impact | Mitigation |
|----------|------|------------|--------|------------|
| QW-1 (Pre-merge rebase) | Rebase introduces subtle code changes | Low | Medium | Test gate runs after rebase |
| QW-2 (Conflict detection) | False positives block merges unnecessarily | Low | Low | Advisory only, does not block |
| QW-3 (Dependency ordering) | Beads without explicit deps merged in wrong order | Medium | Medium | Orchestrator reviews merge order |
| MT-2 (AI resolution) | AI introduces bugs in merged code | Medium | High | Mandatory test gate + human review for >5 files |
| MT-4 (Merge queue) | Queue bottleneck if one agent blocks | Low | Medium | Skip-and-continue logic |
| LT-1 (File decomposition) | Import breakage during split | Medium | High | Comprehensive test suite before split |
| LT-3 (Epic branches) | Epic branch itself diverges from main | Low | Medium | Keep epics short-lived (<1 week) |

### 7.2 Worst Case Scenarios

**Scenario A: AI resolution produces silently wrong code**
The AI merges two functions that look compatible but have a subtle semantic conflict (e.g., both change a default parameter value differently). The merged code passes tests but produces wrong results at runtime.

*Mitigation*: Always run test gate after AI resolution. For safety-critical code (auth, payments), require Opus-level review gate. Track AI resolution accuracy over time -- if success rate drops below 90%, disable and escalate.

**Scenario B: File decomposition breaks MCP server loading**
Splitting `tory_engine.py` changes the import paths. If any tool registration breaks, the entire MCP server fails and all agents lose their tools.

*Mitigation*: Create a dedicated integration test that starts the MCP server, lists all tools, and invokes each tool with a smoke-test input. Run this test before and after decomposition. Make the decomposition bead a P0 with a dedicated review-agent pass.

**Scenario C: Merge queue enters infinite loop**
Agent A conflicts with Agent B. AI resolves A->B. But B's resolution changes break Agent C. AI resolves B->C. But C's resolution changes break A's original merge. The queue cycles.

*Mitigation*: Track resolution attempts per agent. If an agent's merge is attempted 3 times, escalate to human. Set a max queue cycle count of 2 (each agent gets at most 2 resolution attempts per queue run).

---

## 8. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-19 | Reject LT-2 (trunk-based development) | Too risky without CI/CD. Worktree isolation is a safety feature we need. |
| 2026-02-19 | Prioritize LT-1 (file decomposition) as highest strategic impact | Root cause is monolithic files, not merge tooling. Decomposition eliminates 80%+ of conflicts. |
| 2026-02-19 | Choose rebase-before-merge over cherry-pick | Rebase preserves commit history and is idempotent. Cherry-pick creates duplicate commits and complicates history. |
| 2026-02-19 | Choose Claude for AI resolution over specialized tools | We already have Claude in the pipeline. Bead specs provide unique context that generic merge tools lack. |
| 2026-02-19 | Adopt Phase A immediately, defer Phase D | Quick wins have near-zero risk and immediate payoff. Phase D solutions are insurance for scale we have not yet hit. |

---

## Appendix A: Comparison of External Tools

| Tool | Type | Local/Cloud | Cost | Fits Our Model? |
|------|------|-------------|------|-----------------|
| [GitHub Merge Queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) | Merge queue | Cloud (GitHub) | Free w/ GitHub | No -- requires PRs, cloud CI |
| [Mergify](https://docs.mergify.com/merge-queue/) | Merge queue | Cloud | $499+/mo | No -- GitHub/GitLab only |
| [Trunk Merge Queue](https://trunk.io/merge-queue) | Merge queue | Cloud | $$ | No -- requires cloud CI |
| [Aviator](https://www.aviator.co/merge-queue) | Merge queue | Cloud | $$ | Concepts applicable, tool not |
| [Graphite](https://graphite.com/docs/graphite-merge-queue) | Stacked PRs | Cloud | $$ | Concepts applicable (stack-aware) |
| [Clash](https://github.com/clash-sh/clash) | Conflict detection | Local | Free (OSS) | **YES** -- perfect fit |
| [Rizzler](https://github.com/ghuntley/rizzler) | AI merge resolution | Local | API costs | Possible, but we can build our own |
| [git merge-tree](https://git-scm.com/docs/git-merge-tree) | Conflict detection | Local | Free (built-in) | **YES** -- already available |

---

## Appendix B: Git Commands Reference

```bash
# Detect conflicts without modifying working directory
git merge-tree $(git merge-base main agent/foo) main agent/foo

# Rebase agent branch onto latest main
git checkout agent/foo && git rebase main

# Three-way merge with ours/theirs strategy hints
git merge agent/foo -X patience      # patience diff algorithm (better for additive)
git merge agent/foo -X diff-algorithm=histogram  # even better for large files

# Show which files would conflict
git merge --no-commit --no-ff agent/foo && git diff --name-only --diff-filter=U

# Abort a failed merge
git merge --abort

# Cherry-pick specific commits (alternative to full merge)
git cherry-pick <commit-hash>

# Apply agent's changes as a patch (alternative to merge)
git diff main...agent/foo | git apply --3way
```

---

## Appendix C: Sources

- [What is a Merge Queue? (Aviator)](https://www.aviator.co/blog/what-is-a-merge-queue/)
- [Managing a merge queue (GitHub Docs)](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
- [Merge Queue (Mergify Docs)](https://docs.mergify.com/merge-queue/)
- [The Origin Story of Merge Queues (Mergify)](https://mergify.com/blog/the-origin-story-of-merge-queues)
- [Outgrowing GitHub Merge Queue (Trunk)](https://trunk.io/blog/outgrowing-github-merge-queue)
- [Branching in a Sapling Monorepo (Meta Engineering)](https://engineering.fb.com/2025/10/16/developer-tools/branching-in-a-sapling-monorepo/)
- [How Google Does Monorepo (QE Unit)](https://qeunit.com/blog/how-google-does-monorepo/)
- [Version Control and Branch Management (Abseil / Google SWE Book)](https://abseil.io/resources/swe-book/html/ch16.html)
- [Branching strategies for monorepo development (Graphite)](https://graphite.com/guides/branching-strategies-monorepo)
- [How we built the first stack-aware merge queue (Graphite)](https://graphite.com/blog/the-first-stack-aware-merge-queue)
- [Graphite automatic rebase after merge](https://graphite.com/blog/automatic-rebase-after-merge)
- [Merge Queues for Large Monorepos (Aviator)](https://www.aviator.co/blog/merge-queues-for-large-monorepos/)
- [Clash: Git worktree conflict detection (GitHub)](https://github.com/clash-sh/clash)
- [LLMinus: LLM-Assisted Merge Conflict Resolution (LWN.net)](https://lwn.net/Articles/1053714/)
- [Git Merge Conflict Resolution Leveraging Strategy Classification and LLM (IEEE)](https://ieeexplore.ieee.org/document/10366637/)
- [Rizzler: AI merge conflict resolver (GitHub)](https://github.com/ghuntley/rizzler)
- [Using Pre-trained Language Models to Resolve Merge Conflicts (Yale)](https://www.cs.yale.edu/homes/piskac/papers/2022ZhangETALmerge.pdf)
- [Resolve Git Merge Conflicts with AI (ARCAD)](https://www.arcadsoftware.com/discover/resources/blog/resolve-git-merge-conflicts-faster-with-artificial-intelligence-ai/)
- [OpenAI Codex App Worktrees](https://developers.openai.com/codex/app/worktrees/)
- [Codex App Worktrees Explained (Verdent)](https://www.verdent.ai/guides/codex-app-worktrees-explained)
- [Using Git Worktrees for Parallel AI Development (Steve Kinney)](https://stevekinney.com/courses/ai-development/git-worktrees)
- [Parallel AI Development with Git Worktrees (Medium)](https://medium.com/@ooi_yee_fei/parallel-ai-development-with-git-worktrees-f2524afc3e33)
- [Git Worktrees and Claude Code (Geeky Gadgets)](https://www.geeky-gadgets.com/how-to-use-git-worktrees-with-claude-code-for-seamless-multitasking/)
- [Rebase and resolve merge conflicts (GitLab Docs)](https://docs.gitlab.com/topics/git/git_rebase/)
- [Merging vs. Rebasing (Atlassian)](https://www.atlassian.com/git/tutorials/merging-vs-rebasing)
- [git merge-tree Documentation](https://git-scm.com/docs/git-merge-tree)
- [Affected Targets (Aviator Docs)](https://docs.aviator.co/mergequeue/concepts/affected-targets)
- [Parallel Mode (Aviator Docs)](https://docs.aviator.co/mergequeue/concepts/parallel-mode)
- [Parallel Checks (Mergify Docs)](https://docs.mergify.com/merge-queue/parallel-checks/)
- [Migrating from Bors-NG to GitHub Merge Queues (Lobsters)](https://lobste.rs/s/exhcza/migrating_from_bors_ng_github_merge)
