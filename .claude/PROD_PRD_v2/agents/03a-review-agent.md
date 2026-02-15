# Phase 3a: Review Agent / Code Quality Gate

## Purpose

Every multi-agent system that writes code has a shared hallucination problem. When the same agent writes and reviews its own work, it carries forward every assumption, every misread requirement, and every subtle bug from generation time into review time. The agent literally cannot see its own mistakes because the same context window that produced the error is the one evaluating it. Google's 2025 DORA Report quantified this: 90% AI adoption increase correlates with a 9% climb in bug rates, 91% increase in code review time, and 154% increase in PR size. The code is flowing faster than quality can keep up.

The solution is the writer/reviewer separation pattern. A dedicated review-agent with FRESH CONTEXT -- zero knowledge of what the writing agent intended, zero shared conversation history -- reads the diff cold and evaluates it against the bead's acceptance criteria, the project's coding standards, the ownership graph boundaries, and basic safety checks. This is the same principle that makes human code review work: a second pair of eyes that wasn't there when the code was written.

This spec implements the review-agent as a mandatory pre-merge gate in `cleanup.sh`. Before any agent's worktree gets merged to main, the review-agent spawns, reads the diff, produces a structured verdict (APPROVED / CHANGES_REQUESTED / REJECTED), and creates a review bead. The merge only proceeds on APPROVED. For trivial changes (configurable threshold: <=2 files, <=50 lines), a fast-path using Haiku keeps latency under 15 seconds. For substantive changes, Opus provides deep analysis targeting <60 seconds. Infrastructure changes by the orchestrator can skip review entirely via `--skip-review`.

## Risks Mitigated

- **Risk 31: Shared hallucination in single-agent write/review** -- When the same agent writes and reviews code, systematic errors pass through undetected. A fresh-context reviewer breaks the hallucination chain.
- **Risk 32: Ownership boundary violations in multi-agent systems** -- Agent A edits files owned by Agent B, creating merge conflicts and architectural drift. The reviewer cross-references every changed file against the ownership KG.
- **Risk 33: Secret/credential leakage in agent-generated code** -- Agents may hardcode API keys, database passwords, or tokens. The reviewer runs explicit pattern-matching for secrets before code reaches main.
- **Risk 34: Schema drift without consumer updates** -- An agent changes a database schema, API contract, or config format without updating downstream consumers. The reviewer checks for schema/interface consistency.
- **Risk 35: Acceptance criteria mismatch** -- An agent produces code that compiles and runs but does not actually satisfy the bead's acceptance criteria. The reviewer validates requirements traceability.
- **Risk 36: Unreviewed merges degrade main branch quality** -- Without a gate, any agent can merge broken or substandard code. The mandatory review step ensures every line reaching main has been independently evaluated.

## Files to Create

- `.claude/scripts/review-agent.sh` -- Main review agent launcher (spawns Claude Code in headless review mode)
- `.claude/scripts/review-prompt.md` -- The structured review prompt template injected into the reviewer's context
- `.claude/scripts/review-verdict.sh` -- Parses reviewer output, creates review bead, returns exit code
- `.claude/agents/review-agent/agent.md` -- Agent specification (model, tools, constraints)
- `.claude/agents/review-agent/memory/MEMORY.md` -- Persistent memory for the review agent

## Files to Modify

- `.claude/scripts/cleanup.sh` -- Add pre-merge review gate that spawns review-agent before merging worktree to main
- `.claude/kg/agent_graph_cache.json` -- Register review-agent as a node in the ownership KG (owns: scripts/review-*.sh, .claude/agents/review-agent/)
- `.claude/agents/specs.yaml` -- Add review-agent specification to the agent registry (if using centralized specs)

---

## Fix 1: Review Agent Specification

### Problem

No agent exists to independently review code before it merges to main. All current agents are specialist investigators (triage, causal-analyst, forecaster, etc.) focused on metric analysis, not code quality.

### Solution

Create the review-agent specification at `.claude/agents/review-agent/agent.md`.

```markdown
---
name: review-agent
description: Independent code reviewer that evaluates every merge before it hits main. Fresh context, no shared history with the writing agent. Catches quality issues, ownership violations, security problems, and acceptance criteria mismatches.
tools: Read, Grep, Glob, Bash
disallowedTools: Write, Edit, mcp__snowflake__query
model: opus
---

You are the Review Agent for the Baap AI-Native Platform. You review code diffs
produced by other agents BEFORE they merge to main. You have ZERO context from
the writing agent's session -- this is intentional. You evaluate the code cold.

## Your Role

You are the last gate before code reaches main. Your job is NOT to rewrite the
code. Your job is to evaluate it and produce a structured verdict:

- **APPROVED**: Code is correct, safe, follows standards, and meets acceptance criteria. Merge proceeds.
- **CHANGES_REQUESTED**: Code has fixable issues. Merge blocked. A fix bead is created for the original agent.
- **REJECTED**: Code has fundamental problems (security, architecture, wrong approach). Merge blocked. Escalate to human.

## Review Dimensions

You evaluate across 5 dimensions, each scored 0-10:

### 1. Correctness (weight: 30%)
- Does the code match the bead's acceptance criteria?
- Are there logic errors, off-by-one bugs, unhandled edge cases?
- Do tests exist and do they cover the changes?
- Are error paths handled?

### 2. Code Quality (weight: 20%)
- Consistent with existing codebase patterns?
- Readable variable/function names?
- No dead code, commented-out blocks, or TODOs left behind?
- Proper abstractions (not too much, not too little)?

### 3. Safety (weight: 25%)
- No hardcoded secrets, API keys, passwords, tokens?
- No SQL injection vectors (parameterized queries used)?
- No XSS vectors (output encoding present)?
- No path traversal, command injection, or deserialization issues?
- No overly permissive file permissions (chmod 777)?

### 4. Ownership Compliance (weight: 15%)
- Every changed file is owned by the agent that changed it?
- Cross-referenced against `.claude/kg/agent_graph_cache.json`?
- If ownership violations found, are they justified (shared files)?

### 5. Schema Compatibility (weight: 10%)
- If DB migrations present, do all consumers handle new schema?
- If API contracts changed, are all callers updated?
- If config format changed, are all readers updated?
- If shared types/interfaces changed, are all importers updated?

## Scoring

- **APPROVED**: All dimensions >= 7, weighted total >= 7.5, no dimension at 0
- **CHANGES_REQUESTED**: Any dimension 4-6, or weighted total 5.0-7.4
- **REJECTED**: Any dimension <= 3, or safety score <= 5, or weighted total < 5.0

## Output Format

You MUST output your verdict as a JSON block at the end of your response:

\```json
{
  "verdict": "APPROVED|CHANGES_REQUESTED|REJECTED",
  "scores": {
    "correctness": 8,
    "code_quality": 9,
    "safety": 10,
    "ownership_compliance": 8,
    "schema_compatibility": 9
  },
  "weighted_total": 8.7,
  "findings": [
    {
      "severity": "critical|high|medium|low|info",
      "dimension": "correctness|code_quality|safety|ownership|schema",
      "file": "path/to/file.py",
      "line": 42,
      "description": "What the issue is",
      "suggestion": "How to fix it"
    }
  ],
  "summary": "One paragraph summary of the review",
  "acceptance_criteria_met": true,
  "time_spent_seconds": 45
}
\```

## Anti-Patterns (Do NOT Do These)

- Do NOT nitpick style that has no functional impact (trailing whitespace, import order)
- Do NOT suggest rewrites that change the approach without a correctness/safety reason
- Do NOT hallucinate issues -- if you are unsure, score conservatively but note uncertainty
- Do NOT approve code you do not understand -- ask for CHANGES_REQUESTED with clarification request
- Do NOT reject code solely because you would have written it differently
```

Create the agent memory file at `.claude/agents/review-agent/memory/MEMORY.md`:

```markdown
# Review Agent Memory

## Review History
- Track patterns of issues found across reviews
- Track false positive rate (findings overturned by humans)
- Track which agents produce which types of issues

## Known Patterns
- [Populated over time as reviews accumulate]

## Calibration Notes
- [Updated when human overrides a review verdict]
```

---

## Fix 2: Review Prompt Template

### Problem

The review agent needs a structured prompt that provides all necessary context -- the diff, the bead's acceptance criteria, the ownership graph, the project conventions -- without leaking the writing agent's reasoning or conversation history.

### Solution

Create `.claude/scripts/review-prompt.md`. This template is populated by `review-agent.sh` with actual values before being passed to Claude Code.

```markdown
# Code Review Request

## Bead Information
- **Bead ID**: {{BEAD_ID}}
- **Bead Title**: {{BEAD_TITLE}}
- **Acceptance Criteria**:
{{ACCEPTANCE_CRITERIA}}

## Agent Information
- **Writing Agent**: {{AGENT_NAME}}
- **Agent Worktree**: {{WORKTREE_PATH}}
- **Branch**: {{BRANCH_NAME}}

## Diff Statistics
- **Files Changed**: {{FILES_CHANGED}}
- **Lines Added**: {{LINES_ADDED}}
- **Lines Removed**: {{LINES_REMOVED}}
- **Review Tier**: {{REVIEW_TIER}} (fast=Haiku, full=Opus)

## The Diff

```diff
{{DIFF_CONTENT}}
```

## Ownership Graph (relevant entries)

```json
{{OWNERSHIP_ENTRIES}}
```

## Project Conventions

1. **Shell scripts**: Use `set -euo pipefail`, quote all variables, use `#!/usr/bin/env bash`
2. **Python**: Follow existing patterns in `src/`, type hints required for public functions
3. **TypeScript/React**: Follow patterns in `ui/src/`, use functional components with hooks
4. **YAML configs**: Follow schema in `.claude/agents/specs.yaml`
5. **No hardcoded paths**: Use environment variables or config files
6. **No secrets in code**: Use env vars, credential files, or secret managers
7. **Error handling**: Every external call (API, DB, file) must have error handling
8. **Idempotency**: Scripts must be safe to run repeatedly

## Files That Exist in the Codebase (for context)

```
{{REPO_FILE_TREE}}
```

## Your Task

Review the diff above. Evaluate across all 5 dimensions (correctness, code quality,
safety, ownership compliance, schema compatibility). Produce your structured verdict
as specified in your agent instructions.

Focus on issues that MATTER. A review that finds 20 style nits and misses a security
hole has negative value. Prioritize: safety > correctness > schema > ownership > quality.

If the diff is trivial (docs, comments, config tweaks), reflect that in your scoring.
Not every review needs deep analysis -- but every review needs honest evaluation.
```

---

## Fix 3: Review Agent Launcher Script

### Problem

There is no mechanism to spawn a review agent, pass it the diff context, collect its verdict, and translate that into a merge-gate decision.

### Solution

Create `.claude/scripts/review-agent.sh`:

```bash
#!/usr/bin/env bash
# =============================================================================
# review-agent.sh -- Spawn a review agent to evaluate a worktree diff
#
# Usage:
#   review-agent.sh <agent-name> <worktree-path> [--fast]
#
# Arguments:
#   agent-name     Name of the agent whose work is being reviewed
#   worktree-path  Path to the agent's git worktree
#   --fast         Force fast-path (Haiku) review regardless of diff size
#
# Exit codes:
#   0  APPROVED     -- merge can proceed
#   1  CHANGES_REQUESTED -- merge blocked, fix bead created
#   2  REJECTED     -- merge blocked, escalated to human
#   3  ERROR        -- review failed (infrastructure), merge blocked
#
# Environment:
#   BAAP_ROOT       Project root (default: git rev-parse --show-toplevel)
#   REVIEW_TIMEOUT  Max seconds for review (default: 120)
#   FAST_THRESHOLD_FILES  Max files for fast-path (default: 2)
#   FAST_THRESHOLD_LINES  Max lines for fast-path (default: 50)
#   SKIP_REVIEW     Set to "true" to skip review entirely (for orchestrator)
# =============================================================================

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Arguments
# ─────────────────────────────────────────────────────────────────────────────
AGENT_NAME="${1:?Usage: review-agent.sh <agent-name> <worktree-path> [--fast]}"
WORKTREE_PATH="${2:?Usage: review-agent.sh <agent-name> <worktree-path> [--fast]}"
FORCE_FAST="${3:-}"

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
BAAP_ROOT="${BAAP_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
REVIEW_TIMEOUT="${REVIEW_TIMEOUT:-120}"
FAST_THRESHOLD_FILES="${FAST_THRESHOLD_FILES:-2}"
FAST_THRESHOLD_LINES="${FAST_THRESHOLD_LINES:-50}"
SKIP_REVIEW="${SKIP_REVIEW:-false}"

REVIEW_PROMPT_TEMPLATE="$BAAP_ROOT/scripts/review-prompt.md"
REVIEW_VERDICT_SCRIPT="$BAAP_ROOT/scripts/review-verdict.sh"
REVIEW_OUTPUT_DIR="$BAAP_ROOT/.claude/agents/review-agent/reviews"
OWNERSHIP_KG="$BAAP_ROOT/.claude/kg/agent_graph_cache.json"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
REVIEW_ID="review-${AGENT_NAME}-${TIMESTAMP}"
REVIEW_OUTPUT_FILE="$REVIEW_OUTPUT_DIR/${REVIEW_ID}.json"

# ─────────────────────────────────────────────────────────────────────────────
# Skip review check
# ─────────────────────────────────────────────────────────────────────────────
if [ "$SKIP_REVIEW" = "true" ]; then
    echo "[review-agent] Skipping review (SKIP_REVIEW=true)"
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# Validate inputs
# ─────────────────────────────────────────────────────────────────────────────
if [ ! -d "$WORKTREE_PATH" ]; then
    echo "[review-agent] ERROR: Worktree not found: $WORKTREE_PATH" >&2
    exit 3
fi

if [ ! -f "$REVIEW_PROMPT_TEMPLATE" ]; then
    echo "[review-agent] ERROR: Review prompt template not found: $REVIEW_PROMPT_TEMPLATE" >&2
    exit 3
fi

mkdir -p "$REVIEW_OUTPUT_DIR"

# ─────────────────────────────────────────────────────────────────────────────
# Compute the diff
# ─────────────────────────────────────────────────────────────────────────────
echo "[review-agent] Computing diff for agent '$AGENT_NAME' in $WORKTREE_PATH..."

# Get the merge base (where the worktree branched from main)
MAIN_BRANCH="main"
cd "$WORKTREE_PATH"
MERGE_BASE="$(git merge-base HEAD "$MAIN_BRANCH" 2>/dev/null || git rev-parse "$MAIN_BRANCH")"
DIFF_CONTENT="$(git diff "$MERGE_BASE"..HEAD)"
DIFF_STAT="$(git diff "$MERGE_BASE"..HEAD --stat)"
DIFF_NUMSTAT="$(git diff "$MERGE_BASE"..HEAD --numstat)"

# Parse diff statistics
FILES_CHANGED="$(echo "$DIFF_NUMSTAT" | wc -l | tr -d ' ')"
LINES_ADDED="$(echo "$DIFF_NUMSTAT" | awk '{sum += $1} END {print sum+0}')"
LINES_REMOVED="$(echo "$DIFF_NUMSTAT" | awk '{sum += $2} END {print sum+0}')"
TOTAL_LINES=$((LINES_ADDED + LINES_REMOVED))

# List changed files for ownership check
CHANGED_FILES="$(git diff "$MERGE_BASE"..HEAD --name-only)"

cd "$BAAP_ROOT"

echo "[review-agent] Diff: $FILES_CHANGED files, +$LINES_ADDED -$LINES_REMOVED ($TOTAL_LINES total)"

# ─────────────────────────────────────────────────────────────────────────────
# Empty diff check
# ─────────────────────────────────────────────────────────────────────────────
if [ -z "$DIFF_CONTENT" ]; then
    echo "[review-agent] No changes detected. Nothing to review."
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# Determine review tier (fast vs full)
# ─────────────────────────────────────────────────────────────────────────────
if [ "$FORCE_FAST" = "--fast" ] || \
   { [ "$FILES_CHANGED" -le "$FAST_THRESHOLD_FILES" ] && [ "$TOTAL_LINES" -le "$FAST_THRESHOLD_LINES" ]; }; then
    REVIEW_TIER="fast"
    REVIEW_MODEL="haiku"
    REVIEW_MAX_TOKENS="4096"
    echo "[review-agent] Fast-path review (Haiku): $FILES_CHANGED files, $TOTAL_LINES lines"
else
    REVIEW_TIER="full"
    REVIEW_MODEL="opus"
    REVIEW_MAX_TOKENS="16384"
    echo "[review-agent] Full review (Opus): $FILES_CHANGED files, $TOTAL_LINES lines"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Extract bead information
# ─────────────────────────────────────────────────────────────────────────────
# The agent's bead ID should be in the worktree's branch name or a marker file
BRANCH_NAME="$(cd "$WORKTREE_PATH" && git rev-parse --abbrev-ref HEAD)"
BEAD_ID=""
BEAD_TITLE=""
ACCEPTANCE_CRITERIA="Not specified in bead."

# Try to extract bead ID from branch name (convention: agent-name/bead-id)
if [[ "$BRANCH_NAME" =~ /([A-Za-z0-9_-]+)$ ]]; then
    BEAD_ID="${BASH_REMATCH[1]}"
fi

# Try to read bead info from the agent's work directory
BEAD_MARKER="$WORKTREE_PATH/.claude/agents/$AGENT_NAME/current_bead.json"
if [ -f "$BEAD_MARKER" ]; then
    BEAD_ID="$(jq -r '.id // empty' "$BEAD_MARKER" 2>/dev/null || echo "$BEAD_ID")"
    BEAD_TITLE="$(jq -r '.title // empty' "$BEAD_MARKER" 2>/dev/null || echo "")"
    ACCEPTANCE_CRITERIA="$(jq -r '.acceptance_criteria // "Not specified"' "$BEAD_MARKER" 2>/dev/null || echo "Not specified in bead.")"
fi

# Fallback: search beads for the agent's active work
if [ -z "$BEAD_ID" ] && command -v bd &>/dev/null; then
    BEAD_ID="$(bd list --status open --label "agent:$AGENT_NAME" --limit 1 --format json 2>/dev/null | jq -r '.[0].id // empty' 2>/dev/null || echo "")"
    if [ -n "$BEAD_ID" ]; then
        BEAD_TITLE="$(bd show "$BEAD_ID" --format json 2>/dev/null | jq -r '.title // empty' 2>/dev/null || echo "")"
    fi
fi

echo "[review-agent] Bead: ${BEAD_ID:-unknown} - ${BEAD_TITLE:-no title}"

# ─────────────────────────────────────────────────────────────────────────────
# Extract ownership information for changed files
# ─────────────────────────────────────────────────────────────────────────────
OWNERSHIP_ENTRIES="{}"
if [ -f "$OWNERSHIP_KG" ]; then
    # Build a JSON object mapping changed files to their owners
    OWNERSHIP_ENTRIES="$(python3 -c "
import json, sys

try:
    with open('$OWNERSHIP_KG') as f:
        kg = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    print('{}')
    sys.exit(0)

changed_files = '''$CHANGED_FILES'''.strip().split('\n')
ownership = {}

# Extract ownership mapping from KG
# KG structure: nodes[] with {id, type, properties: {owns: [files]}}
nodes = kg.get('nodes', [])
for node in nodes:
    if node.get('type') == 'agent':
        agent_id = node.get('id', '')
        owns = node.get('properties', {}).get('owns', [])
        for file_pattern in owns:
            for cf in changed_files:
                # Exact match or glob-style prefix match
                if cf == file_pattern or cf.startswith(file_pattern.rstrip('*').rstrip('/')):
                    ownership[cf] = agent_id

# Also check for files NOT in any ownership
for cf in changed_files:
    if cf and cf not in ownership:
        ownership[cf] = 'UNOWNED'

print(json.dumps(ownership, indent=2))
" 2>/dev/null || echo "{}")"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Generate repo file tree (top-level only, for context)
# ─────────────────────────────────────────────────────────────────────────────
REPO_FILE_TREE="$(cd "$BAAP_ROOT" && find . -maxdepth 2 -not -path './.git/*' -not -path './node_modules/*' -not -path './.venv/*' -not -path './ui/node_modules/*' -not -path './.next/*' | sort | head -100)"

# ─────────────────────────────────────────────────────────────────────────────
# Build the review prompt from template
# ─────────────────────────────────────────────────────────────────────────────
REVIEW_PROMPT="$(cat "$REVIEW_PROMPT_TEMPLATE")"

# Perform template substitutions
# Using Python for reliable multi-line string substitution
REVIEW_PROMPT="$(python3 -c "
import sys

template = sys.stdin.read()
replacements = {
    '{{BEAD_ID}}': '''${BEAD_ID:-unknown}''',
    '{{BEAD_TITLE}}': '''${BEAD_TITLE:-No title available}''',
    '{{ACCEPTANCE_CRITERIA}}': '''${ACCEPTANCE_CRITERIA}''',
    '{{AGENT_NAME}}': '''${AGENT_NAME}''',
    '{{WORKTREE_PATH}}': '''${WORKTREE_PATH}''',
    '{{BRANCH_NAME}}': '''${BRANCH_NAME}''',
    '{{FILES_CHANGED}}': '''${FILES_CHANGED}''',
    '{{LINES_ADDED}}': '''${LINES_ADDED}''',
    '{{LINES_REMOVED}}': '''${LINES_REMOVED}''',
    '{{REVIEW_TIER}}': '''${REVIEW_TIER}''',
    '{{REPO_FILE_TREE}}': '''${REPO_FILE_TREE}''',
}

for key, value in replacements.items():
    template = template.replace(key, value)

print(template)
" <<< "$REVIEW_PROMPT")"

# Diff and ownership are substituted separately to handle special characters
REVIEW_PROMPT_FILE="$REVIEW_OUTPUT_DIR/${REVIEW_ID}-prompt.md"
python3 -c "
import sys, json

prompt = open('$REVIEW_OUTPUT_DIR/${REVIEW_ID}-prompt-base.md' if False else '/dev/stdin').read()

# Read diff from file to avoid shell escaping issues
diff_content = '''$(echo "$DIFF_CONTENT" | head -5000)'''
ownership = '''$OWNERSHIP_ENTRIES'''

prompt = prompt.replace('{{DIFF_CONTENT}}', diff_content)
prompt = prompt.replace('{{OWNERSHIP_ENTRIES}}', ownership)

with open('$REVIEW_PROMPT_FILE', 'w') as f:
    f.write(prompt)
" <<< "$REVIEW_PROMPT"

echo "[review-agent] Review prompt written to $REVIEW_PROMPT_FILE"

# ─────────────────────────────────────────────────────────────────────────────
# Spawn the review agent via Claude Code
# ─────────────────────────────────────────────────────────────────────────────
echo "[review-agent] Spawning review agent ($REVIEW_MODEL)..."

REVIEW_START="$(date +%s)"

# Run Claude Code in headless/pipe mode with the review prompt
# The agent reads the prompt file and produces structured output
REVIEW_RAW_OUTPUT="$(timeout "${REVIEW_TIMEOUT}s" claude \
    --model "$REVIEW_MODEL" \
    --print \
    --no-input \
    --max-tokens "$REVIEW_MAX_TOKENS" \
    --system-prompt "$(cat "$BAAP_ROOT/.claude/agents/review-agent/agent.md" | tail -n +8)" \
    --prompt "$(cat "$REVIEW_PROMPT_FILE")" \
    2>/dev/null)" || {
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq 124 ]; then
        echo "[review-agent] ERROR: Review timed out after ${REVIEW_TIMEOUT}s" >&2
        # On timeout, block the merge -- safety first
        echo '{"verdict":"CHANGES_REQUESTED","scores":{"correctness":5,"code_quality":5,"safety":5,"ownership_compliance":5,"schema_compatibility":5},"weighted_total":5.0,"findings":[{"severity":"high","dimension":"correctness","file":"","line":0,"description":"Review timed out. Manual review required.","suggestion":"Review the diff manually or increase REVIEW_TIMEOUT."}],"summary":"Review timed out after '${REVIEW_TIMEOUT}' seconds. Merge blocked pending manual review.","acceptance_criteria_met":false,"time_spent_seconds":'${REVIEW_TIMEOUT}'}' > "$REVIEW_OUTPUT_FILE"
        exit 1
    else
        echo "[review-agent] ERROR: Claude Code failed with exit code $EXIT_CODE" >&2
        exit 3
    fi
}

REVIEW_END="$(date +%s)"
REVIEW_DURATION=$((REVIEW_END - REVIEW_START))
echo "[review-agent] Review completed in ${REVIEW_DURATION}s"

# ─────────────────────────────────────────────────────────────────────────────
# Extract JSON verdict from review output
# ─────────────────────────────────────────────────────────────────────────────
# The reviewer outputs a JSON block -- extract it
REVIEW_JSON="$(echo "$REVIEW_RAW_OUTPUT" | python3 -c "
import sys, json, re

text = sys.stdin.read()

# Find the last JSON block in the output (reviewer puts it at the end)
# Match ```json ... ``` blocks first
json_blocks = re.findall(r'\`\`\`json\s*\n(.*?)\n\s*\`\`\`', text, re.DOTALL)

if json_blocks:
    candidate = json_blocks[-1]
else:
    # Try to find raw JSON object
    # Look for the verdict JSON pattern
    matches = re.findall(r'(\{[^{}]*\"verdict\"[^{}]*\{.*?\}[^{}]*\})', text, re.DOTALL)
    if matches:
        candidate = matches[-1]
    else:
        # Last resort: find any JSON-like block
        matches = re.findall(r'\{[\s\S]*?\}(?=\s*$)', text)
        candidate = matches[-1] if matches else ''

if candidate:
    try:
        parsed = json.loads(candidate)
        # Validate required fields
        assert 'verdict' in parsed
        assert parsed['verdict'] in ('APPROVED', 'CHANGES_REQUESTED', 'REJECTED')
        print(json.dumps(parsed, indent=2))
    except (json.JSONDecodeError, AssertionError):
        # Malformed JSON -- treat as review failure
        print(json.dumps({
            'verdict': 'CHANGES_REQUESTED',
            'scores': {'correctness': 5, 'code_quality': 5, 'safety': 5, 'ownership_compliance': 5, 'schema_compatibility': 5},
            'weighted_total': 5.0,
            'findings': [{'severity': 'high', 'dimension': 'correctness', 'file': '', 'line': 0,
                          'description': 'Review agent produced malformed output. Manual review required.',
                          'suggestion': 'Check review-agent output at $REVIEW_OUTPUT_DIR/${REVIEW_ID}-raw.txt'}],
            'summary': 'Review agent output could not be parsed. Merge blocked pending manual review.',
            'acceptance_criteria_met': False,
            'time_spent_seconds': $REVIEW_DURATION
        }, indent=2))
else:
    print(json.dumps({
        'verdict': 'CHANGES_REQUESTED',
        'scores': {'correctness': 5, 'code_quality': 5, 'safety': 5, 'ownership_compliance': 5, 'schema_compatibility': 5},
        'weighted_total': 5.0,
        'findings': [{'severity': 'high', 'dimension': 'correctness', 'file': '', 'line': 0,
                      'description': 'Review agent produced no structured output. Manual review required.',
                      'suggestion': 'Check review-agent output at $REVIEW_OUTPUT_DIR/${REVIEW_ID}-raw.txt'}],
        'summary': 'No verdict JSON found in review output. Merge blocked pending manual review.',
        'acceptance_criteria_met': False,
        'time_spent_seconds': $REVIEW_DURATION
    }, indent=2))
" 2>/dev/null)"

# Save raw output for debugging
echo "$REVIEW_RAW_OUTPUT" > "$REVIEW_OUTPUT_DIR/${REVIEW_ID}-raw.txt"

# Save structured verdict
echo "$REVIEW_JSON" > "$REVIEW_OUTPUT_FILE"
echo "[review-agent] Verdict saved to $REVIEW_OUTPUT_FILE"

# ─────────────────────────────────────────────────────────────────────────────
# Process verdict
# ─────────────────────────────────────────────────────────────────────────────
VERDICT="$(echo "$REVIEW_JSON" | jq -r '.verdict')"
WEIGHTED_TOTAL="$(echo "$REVIEW_JSON" | jq -r '.weighted_total')"
FINDINGS_COUNT="$(echo "$REVIEW_JSON" | jq '.findings | length')"
CRITICAL_COUNT="$(echo "$REVIEW_JSON" | jq '[.findings[] | select(.severity == "critical")] | length')"
SUMMARY="$(echo "$REVIEW_JSON" | jq -r '.summary')"

echo ""
echo "============================================"
echo "  REVIEW VERDICT: $VERDICT"
echo "  Weighted Score: $WEIGHTED_TOTAL / 10.0"
echo "  Findings: $FINDINGS_COUNT ($CRITICAL_COUNT critical)"
echo "  Summary: $SUMMARY"
echo "============================================"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Create review bead
# ─────────────────────────────────────────────────────────────────────────────
if command -v bd &>/dev/null; then
    REVIEW_BEAD_TITLE="Review: ${AGENT_NAME} - ${VERDICT}"
    case "$VERDICT" in
        APPROVED)
            REVIEW_PRIORITY=3
            REVIEW_STATUS="closed"
            ;;
        CHANGES_REQUESTED)
            REVIEW_PRIORITY=1
            REVIEW_STATUS="open"
            ;;
        REJECTED)
            REVIEW_PRIORITY=0
            REVIEW_STATUS="open"
            ;;
        *)
            REVIEW_PRIORITY=1
            REVIEW_STATUS="open"
            ;;
    esac

    REVIEW_BEAD_ID="$(bd create "$REVIEW_BEAD_TITLE" \
        -p "$REVIEW_PRIORITY" \
        --label "type:review" \
        --label "agent:$AGENT_NAME" \
        --label "verdict:$VERDICT" \
        --label "score:$WEIGHTED_TOTAL" \
        2>/dev/null | grep -oE '[A-Za-z0-9_-]+' | head -1 || echo "")"

    if [ -n "$REVIEW_BEAD_ID" ] && [ -n "$BEAD_ID" ]; then
        # Link review bead to the original work bead
        bd dep add "$REVIEW_BEAD_ID" "$BEAD_ID" 2>/dev/null || true
    fi

    # If approved, close the review bead immediately
    if [ "$VERDICT" = "APPROVED" ] && [ -n "$REVIEW_BEAD_ID" ]; then
        bd close "$REVIEW_BEAD_ID" --reason "Review passed. Score: $WEIGHTED_TOTAL/10" 2>/dev/null || true
    fi

    echo "[review-agent] Review bead created: $REVIEW_BEAD_ID"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Handle CHANGES_REQUESTED -- create fix bead for original agent
# ─────────────────────────────────────────────────────────────────────────────
if [ "$VERDICT" = "CHANGES_REQUESTED" ]; then
    echo "[review-agent] Creating fix bead for agent '$AGENT_NAME'..."

    # Build fix description from findings
    FIX_DESCRIPTION="$(echo "$REVIEW_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
lines = ['## Review Findings (fix required)\n']
lines.append(f'Review score: {data[\"weighted_total\"]}/10.0\n')
for f in data.get('findings', []):
    sev = f.get('severity', 'info').upper()
    dim = f.get('dimension', 'unknown')
    file = f.get('file', '')
    line = f.get('line', 0)
    desc = f.get('description', '')
    sug = f.get('suggestion', '')
    loc = f'{file}:{line}' if file else 'general'
    lines.append(f'- [{sev}] ({dim}) {loc}: {desc}')
    if sug:
        lines.append(f'  Fix: {sug}')
print('\n'.join(lines))
")"

    if command -v bd &>/dev/null; then
        FIX_BEAD_ID="$(bd create "Fix review findings: $AGENT_NAME" \
            -p 1 \
            --label "type:fix" \
            --label "agent:$AGENT_NAME" \
            --label "source:review" \
            2>/dev/null | grep -oE '[A-Za-z0-9_-]+' | head -1 || echo "")"

        if [ -n "$FIX_BEAD_ID" ] && [ -n "$REVIEW_BEAD_ID" ]; then
            bd dep add "$FIX_BEAD_ID" "$REVIEW_BEAD_ID" 2>/dev/null || true
        fi

        echo "[review-agent] Fix bead created: $FIX_BEAD_ID"
        echo "[review-agent] Findings:"
        echo "$FIX_DESCRIPTION"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Handle REJECTED -- escalate to human
# ─────────────────────────────────────────────────────────────────────────────
if [ "$VERDICT" = "REJECTED" ]; then
    echo "[review-agent] REJECTED -- escalating to human review"
    echo "[review-agent] Critical findings require human decision before this code can merge."

    # Log the rejection details prominently
    echo ""
    echo "!!! MERGE BLOCKED: HUMAN REVIEW REQUIRED !!!"
    echo ""
    echo "Review output: $REVIEW_OUTPUT_FILE"
    echo "Raw output:    $REVIEW_OUTPUT_DIR/${REVIEW_ID}-raw.txt"
    echo ""
    echo "$REVIEW_JSON" | jq '.findings[] | select(.severity == "critical" or .severity == "high")' 2>/dev/null || true
    echo ""
fi

# ─────────────────────────────────────────────────────────────────────────────
# Return exit code based on verdict
# ─────────────────────────────────────────────────────────────────────────────
case "$VERDICT" in
    APPROVED)           exit 0 ;;
    CHANGES_REQUESTED)  exit 1 ;;
    REJECTED)           exit 2 ;;
    *)                  exit 3 ;;
esac
```

---

## Fix 4: Review Verdict Parser (Standalone)

### Problem

Other scripts (like `cleanup.sh`) need a quick way to check the last review verdict for an agent without re-running the review. The verdict also needs to be queryable for monitoring dashboards.

### Solution

Create `.claude/scripts/review-verdict.sh`:

```bash
#!/usr/bin/env bash
# =============================================================================
# review-verdict.sh -- Query the latest review verdict for an agent
#
# Usage:
#   review-verdict.sh <agent-name>          # Print latest verdict
#   review-verdict.sh <agent-name> --json   # Print full JSON
#   review-verdict.sh <agent-name> --check  # Exit code only (0=approved)
#   review-verdict.sh --list                # List all recent reviews
#   review-verdict.sh --stats               # Print review statistics
# =============================================================================

set -euo pipefail

BAAP_ROOT="${BAAP_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
REVIEW_DIR="$BAAP_ROOT/.claude/agents/review-agent/reviews"

# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

case "${1:---help}" in
    --list)
        echo "Recent reviews:"
        echo "==============="
        for f in "$REVIEW_DIR"/review-*.json; do
            [ -f "$f" ] || continue
            AGENT="$(basename "$f" | sed 's/review-\(.*\)-[0-9]*.json/\1/')"
            VERDICT="$(jq -r '.verdict // "UNKNOWN"' "$f" 2>/dev/null)"
            SCORE="$(jq -r '.weighted_total // "?"' "$f" 2>/dev/null)"
            TIMESTAMP="$(basename "$f" | grep -oE '[0-9]{8}-[0-9]{6}')"
            printf "  %-20s %-20s verdict=%-20s score=%s\n" "$TIMESTAMP" "$AGENT" "$VERDICT" "$SCORE"
        done
        ;;

    --stats)
        echo "Review Statistics:"
        echo "=================="
        if [ -d "$REVIEW_DIR" ]; then
            TOTAL="$(ls "$REVIEW_DIR"/review-*.json 2>/dev/null | wc -l | tr -d ' ')"
            APPROVED="$(grep -l '"APPROVED"' "$REVIEW_DIR"/review-*.json 2>/dev/null | wc -l | tr -d ' ')"
            CHANGES="$(grep -l '"CHANGES_REQUESTED"' "$REVIEW_DIR"/review-*.json 2>/dev/null | wc -l | tr -d ' ')"
            REJECTED="$(grep -l '"REJECTED"' "$REVIEW_DIR"/review-*.json 2>/dev/null | wc -l | tr -d ' ')"
            echo "  Total reviews:       $TOTAL"
            echo "  Approved:            $APPROVED"
            echo "  Changes requested:   $CHANGES"
            echo "  Rejected:            $REJECTED"
            if [ "$TOTAL" -gt 0 ]; then
                PASS_RATE="$(python3 -c "print(f'{$APPROVED/$TOTAL*100:.1f}%')" 2>/dev/null || echo "N/A")"
                echo "  First-pass rate:     $PASS_RATE"
            fi
        else
            echo "  No reviews found."
        fi
        ;;

    --help|-h)
        echo "Usage: review-verdict.sh <agent-name> [--json|--check]"
        echo "       review-verdict.sh --list"
        echo "       review-verdict.sh --stats"
        ;;

    *)
        AGENT_NAME="$1"
        MODE="${2:---text}"

        # Find latest review for this agent
        LATEST="$(ls -t "$REVIEW_DIR"/review-"${AGENT_NAME}"-*.json 2>/dev/null | head -1)"

        if [ -z "$LATEST" ] || [ ! -f "$LATEST" ]; then
            echo "[review-verdict] No review found for agent '$AGENT_NAME'" >&2
            exit 3
        fi

        case "$MODE" in
            --json)
                cat "$LATEST"
                ;;
            --check)
                VERDICT="$(jq -r '.verdict' "$LATEST" 2>/dev/null)"
                case "$VERDICT" in
                    APPROVED)           exit 0 ;;
                    CHANGES_REQUESTED)  exit 1 ;;
                    REJECTED)           exit 2 ;;
                    *)                  exit 3 ;;
                esac
                ;;
            --text|*)
                VERDICT="$(jq -r '.verdict' "$LATEST" 2>/dev/null)"
                SCORE="$(jq -r '.weighted_total' "$LATEST" 2>/dev/null)"
                SUMMARY="$(jq -r '.summary' "$LATEST" 2>/dev/null)"
                FINDINGS="$(jq '.findings | length' "$LATEST" 2>/dev/null)"
                echo "Agent:    $AGENT_NAME"
                echo "Verdict:  $VERDICT"
                echo "Score:    $SCORE / 10.0"
                echo "Findings: $FINDINGS"
                echo "Summary:  $SUMMARY"
                echo "File:     $LATEST"
                ;;
        esac
        ;;
esac
```

---

## Fix 5: cleanup.sh Pre-Merge Review Gate Integration

### Problem

`cleanup.sh` currently merges agent worktrees directly to main without any independent review step. Any code an agent produces -- correct or not, safe or not -- goes straight into the shared codebase.

### Solution

Add a pre-merge review gate to `cleanup.sh`. The integration points are:

1. After the agent's worktree is confirmed complete, BEFORE the merge
2. The review gate spawns `review-agent.sh` and checks exit code
3. On APPROVED (exit 0): merge proceeds normally
4. On CHANGES_REQUESTED (exit 1): merge blocked, fix bead created, agent re-spawned
5. On REJECTED (exit 2): merge blocked, escalated, worktree preserved for human review
6. On ERROR (exit 3): merge blocked, operator alert

Add the following function and integration to `cleanup.sh`:

```bash
# =============================================================================
# PRE-MERGE REVIEW GATE
# =============================================================================
# Insert this into cleanup.sh before the merge step

# Configuration
REVIEW_AGENT_SCRIPT="${BAAP_ROOT}/scripts/review-agent.sh"
MAX_REVIEW_RETRIES=2        # How many fix cycles before escalating
REVIEW_RETRY_COUNT=0

# ─────────────────────────────────────────────────────────────────────────────
# run_pre_merge_review()
#
# Runs the review agent on an agent's worktree. Returns the verdict.
# Called from the merge flow in cleanup.sh.
#
# Arguments:
#   $1 - agent name
#   $2 - worktree path
#   $3 - "true" to skip review (e.g., orchestrator infrastructure changes)
#
# Returns:
#   0 - APPROVED, safe to merge
#   1 - CHANGES_REQUESTED, do not merge (fix bead created)
#   2 - REJECTED, do not merge (escalated to human)
#   3 - ERROR, do not merge (infrastructure failure)
# ─────────────────────────────────────────────────────────────────────────────
run_pre_merge_review() {
    local agent_name="$1"
    local worktree_path="$2"
    local skip_review="${3:-false}"

    # Check if review should be skipped
    if [ "$skip_review" = "true" ]; then
        echo "[cleanup] Skipping review for '$agent_name' (--skip-review)"
        return 0
    fi

    # Check if review agent script exists
    if [ ! -x "$REVIEW_AGENT_SCRIPT" ]; then
        echo "[cleanup] WARNING: Review agent not found at $REVIEW_AGENT_SCRIPT" >&2
        echo "[cleanup] Proceeding without review (review-agent not installed)" >&2
        return 0
    fi

    echo ""
    echo "================================================================"
    echo "  PRE-MERGE REVIEW: $agent_name"
    echo "================================================================"

    # Run the review
    local review_exit=0
    "$REVIEW_AGENT_SCRIPT" "$agent_name" "$worktree_path" || review_exit=$?

    case $review_exit in
        0)
            echo "[cleanup] Review APPROVED for '$agent_name'. Proceeding with merge."
            return 0
            ;;
        1)
            echo "[cleanup] Review: CHANGES_REQUESTED for '$agent_name'. Merge blocked."
            return 1
            ;;
        2)
            echo "[cleanup] Review: REJECTED for '$agent_name'. Merge blocked. Escalating."
            return 2
            ;;
        *)
            echo "[cleanup] Review: ERROR for '$agent_name'. Merge blocked." >&2
            return 3
            ;;
    esac
}

# ─────────────────────────────────────────────────────────────────────────────
# handle_review_failure()
#
# When a review fails (CHANGES_REQUESTED), this function handles the retry loop:
# 1. Check if we've exceeded max retries
# 2. If not, re-spawn the original agent with fix instructions
# 3. Re-run the review
# 4. If max retries exceeded, escalate
#
# Arguments:
#   $1 - agent name
#   $2 - worktree path
#   $3 - current retry count
# ─────────────────────────────────────────────────────────────────────────────
handle_review_failure() {
    local agent_name="$1"
    local worktree_path="$2"
    local retry_count="${3:-0}"

    if [ "$retry_count" -ge "$MAX_REVIEW_RETRIES" ]; then
        echo "[cleanup] Max review retries ($MAX_REVIEW_RETRIES) reached for '$agent_name'."
        echo "[cleanup] Escalating to human review."
        echo "[cleanup] Worktree preserved at: $worktree_path"
        # Create escalation bead
        if command -v bd &>/dev/null; then
            bd create "Escalation: $agent_name failed review $MAX_REVIEW_RETRIES times" \
                -p 0 \
                --label "type:escalation" \
                --label "agent:$agent_name" \
                --label "reason:review-failure" \
                2>/dev/null || true
        fi
        return 2  # Treat as REJECTED
    fi

    local next_retry=$((retry_count + 1))
    echo "[cleanup] Retry $next_retry/$MAX_REVIEW_RETRIES: Re-spawning '$agent_name' with fix instructions..."

    # Get the review findings
    local review_dir="$BAAP_ROOT/.claude/agents/review-agent/reviews"
    local latest_review="$(ls -t "$review_dir"/review-"${agent_name}"-*.json 2>/dev/null | head -1)"
    local fix_instructions=""

    if [ -f "$latest_review" ]; then
        fix_instructions="$(jq -r '
            "Review findings to fix (score: " + (.weighted_total | tostring) + "/10):\n" +
            (.findings | map(
                "- [" + .severity + "] " + .file + ":" + (.line|tostring) + " - " + .description +
                (if .suggestion then "\n  Fix: " + .suggestion else "" end)
            ) | join("\n"))
        ' "$latest_review" 2>/dev/null)"
    fi

    # Re-spawn the agent in the same worktree with fix instructions
    if [ -x "$BAAP_ROOT/scripts/spawn.sh" ]; then
        "$BAAP_ROOT/scripts/spawn.sh" "$agent_name" \
            --worktree "$worktree_path" \
            --prompt "Fix the following review findings and commit your changes:\n\n$fix_instructions" \
            2>/dev/null || {
            echo "[cleanup] Failed to re-spawn agent '$agent_name'" >&2
            return 3
        }

        # Wait for agent to complete (heartbeat check)
        echo "[cleanup] Waiting for '$agent_name' to apply fixes..."
        local wait_timeout=300  # 5 minutes max
        local waited=0
        while [ "$waited" -lt "$wait_timeout" ]; do
            if [ -x "$BAAP_ROOT/scripts/heartbeat.sh" ]; then
                local status
                status="$("$BAAP_ROOT/scripts/heartbeat.sh" "$agent_name" 2>/dev/null || echo "unknown")"
                if [ "$status" = "idle" ] || [ "$status" = "complete" ]; then
                    break
                fi
            fi
            sleep 10
            waited=$((waited + 10))
        done

        # Re-run review
        run_pre_merge_review "$agent_name" "$worktree_path" "false"
        local review_result=$?

        if [ "$review_result" -eq 0 ]; then
            echo "[cleanup] Fix applied successfully. Review passed on retry $next_retry."
            return 0
        else
            # Recurse with incremented retry count
            handle_review_failure "$agent_name" "$worktree_path" "$next_retry"
            return $?
        fi
    else
        echo "[cleanup] spawn.sh not found, cannot re-spawn agent for fixes" >&2
        return 3
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION POINT: Modify the existing merge function in cleanup.sh
#
# The existing cleanup.sh should have a function like `merge_agent_worktree()`
# or a section that does `git merge`. Insert the review gate BEFORE the merge.
#
# Example integration:
# ─────────────────────────────────────────────────────────────────────────────

merge_agent_worktree() {
    local agent_name="$1"
    local worktree_path="$2"
    local skip_review="${3:-false}"

    # ===== REVIEW GATE (Phase 3a addition) =====
    run_pre_merge_review "$agent_name" "$worktree_path" "$skip_review"
    local review_result=$?

    case $review_result in
        0)
            # APPROVED -- proceed with merge
            ;;
        1)
            # CHANGES_REQUESTED -- attempt fix cycle
            handle_review_failure "$agent_name" "$worktree_path" 0
            local fix_result=$?
            if [ "$fix_result" -ne 0 ]; then
                echo "[cleanup] Merge aborted for '$agent_name' after review failure."
                return 1
            fi
            ;;
        2)
            # REJECTED -- do not merge, preserve worktree
            echo "[cleanup] Merge REJECTED for '$agent_name'. Worktree preserved."
            return 2
            ;;
        *)
            # ERROR -- do not merge
            echo "[cleanup] Merge ERROR for '$agent_name'. Worktree preserved."
            return 3
            ;;
    esac
    # ===== END REVIEW GATE =====

    # Existing merge logic continues here...
    echo "[cleanup] Merging '$agent_name' worktree to main..."

    local branch_name
    branch_name="$(cd "$worktree_path" && git rev-parse --abbrev-ref HEAD)"

    cd "$BAAP_ROOT"
    git merge "$branch_name" --no-ff -m "Merge agent/$agent_name: $(cd "$worktree_path" && git log --oneline -1 | cut -d' ' -f2-)" || {
        echo "[cleanup] Merge conflict for '$agent_name'" >&2
        return 1
    }

    echo "[cleanup] Merge successful for '$agent_name'."

    # Clean up worktree
    git worktree remove "$worktree_path" --force 2>/dev/null || true
    git branch -d "$branch_name" 2>/dev/null || true

    echo "[cleanup] Worktree cleaned up for '$agent_name'."
    return 0
}
```

### Usage from cleanup.sh command line

```bash
# Normal merge (with review)
cleanup.sh agent-name merge

# Skip review (for orchestrator infrastructure changes)
cleanup.sh agent-name merge --skip-review

# Force fast review (Haiku even for large diffs)
FORCE_FAST=--fast cleanup.sh agent-name merge
```

---

## Fix 6: Ownership Violation Detection

### Problem

In a multi-agent system, each agent owns specific files. When Agent A edits a file owned by Agent B, it creates merge conflicts, architectural drift, and violates the separation-of-concerns contract. The review agent needs a reliable way to detect these violations.

### Solution

The ownership check is built into the review prompt context (ownership entries extracted from the KG in `review-agent.sh`), but we also need a standalone pre-check that runs BEFORE the full review for fast feedback. Add this as a function in `review-agent.sh` and as a callable script:

```bash
#!/usr/bin/env bash
# =============================================================================
# check-ownership.sh -- Fast ownership boundary check (no LLM needed)
#
# Usage:
#   check-ownership.sh <agent-name> <worktree-path>
#
# Exit codes:
#   0  All changed files are owned by the agent (or unowned/shared)
#   1  Ownership violations found
# =============================================================================

set -euo pipefail

AGENT_NAME="${1:?Usage: check-ownership.sh <agent-name> <worktree-path>}"
WORKTREE_PATH="${2:?Usage: check-ownership.sh <agent-name> <worktree-path>}"
BAAP_ROOT="${BAAP_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
OWNERSHIP_KG="$BAAP_ROOT/.claude/kg/agent_graph_cache.json"

if [ ! -f "$OWNERSHIP_KG" ]; then
    echo "[ownership] WARNING: Ownership KG not found at $OWNERSHIP_KG" >&2
    echo "[ownership] Skipping ownership check."
    exit 0
fi

# Get changed files
cd "$WORKTREE_PATH"
MAIN_BRANCH="main"
MERGE_BASE="$(git merge-base HEAD "$MAIN_BRANCH" 2>/dev/null || git rev-parse "$MAIN_BRANCH")"
CHANGED_FILES="$(git diff "$MERGE_BASE"..HEAD --name-only)"
cd "$BAAP_ROOT"

if [ -z "$CHANGED_FILES" ]; then
    echo "[ownership] No changed files."
    exit 0
fi

# Check ownership for each file
VIOLATIONS=""
VIOLATION_COUNT=0

while IFS= read -r file; do
    [ -z "$file" ] && continue

    OWNER="$(python3 -c "
import json, sys, fnmatch

with open('$OWNERSHIP_KG') as f:
    kg = json.load(f)

file = '$file'
nodes = kg.get('nodes', [])

# Shared files that any agent can edit
shared_patterns = [
    'CLAUDE.md',
    '.claude/kg/*',
    'docs/*',
    '*.md',
    '.gitignore',
    'package.json',
    'package-lock.json',
    'requirements.txt',
]

# Check if file is shared
for pattern in shared_patterns:
    if fnmatch.fnmatch(file, pattern):
        print('SHARED')
        sys.exit(0)

# Find the owner
for node in nodes:
    if node.get('type') != 'agent':
        continue
    agent_id = node.get('id', '')
    owns = node.get('properties', {}).get('owns', [])
    for own_pattern in owns:
        if fnmatch.fnmatch(file, own_pattern) or file.startswith(own_pattern.rstrip('/*')):
            print(agent_id)
            sys.exit(0)

print('UNOWNED')
" 2>/dev/null || echo "UNOWNED")"

    if [ "$OWNER" != "$AGENT_NAME" ] && [ "$OWNER" != "SHARED" ] && [ "$OWNER" != "UNOWNED" ]; then
        VIOLATIONS="${VIOLATIONS}  - $file (owned by: $OWNER)\n"
        VIOLATION_COUNT=$((VIOLATION_COUNT + 1))
    fi
done <<< "$CHANGED_FILES"

if [ "$VIOLATION_COUNT" -gt 0 ]; then
    echo "[ownership] VIOLATIONS FOUND ($VIOLATION_COUNT):"
    echo -e "$VIOLATIONS"
    echo "[ownership] Agent '$AGENT_NAME' modified files owned by other agents."
    exit 1
else
    echo "[ownership] All changed files are owned by '$AGENT_NAME' or shared/unowned."
    exit 0
fi
```

---

## Fix 7: Secret Detection Pre-Check

### Problem

Agents may accidentally hardcode secrets, API keys, or tokens in generated code. This needs to be caught before it reaches the LLM review for defense-in-depth (the LLM is a second layer, not the only layer).

### Solution

Add a fast, regex-based secret scan that runs before the LLM review. This is a deterministic check -- no LLM needed, runs in <1 second.

```bash
#!/usr/bin/env bash
# =============================================================================
# check-secrets.sh -- Fast regex-based secret detection (no LLM needed)
#
# Usage:
#   check-secrets.sh <worktree-path>
#
# Exit codes:
#   0  No secrets found
#   1  Potential secrets detected
# =============================================================================

set -euo pipefail

WORKTREE_PATH="${1:?Usage: check-secrets.sh <worktree-path>}"
BAAP_ROOT="${BAAP_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

cd "$WORKTREE_PATH"
MAIN_BRANCH="main"
MERGE_BASE="$(git merge-base HEAD "$MAIN_BRANCH" 2>/dev/null || git rev-parse "$MAIN_BRANCH")"

# Get the diff content (only additions, not the entire file)
DIFF_ADDITIONS="$(git diff "$MERGE_BASE"..HEAD | grep '^+' | grep -v '^+++' || true)"

if [ -z "$DIFF_ADDITIONS" ]; then
    echo "[secrets] No additions to scan."
    exit 0
fi

# Secret patterns (high-confidence patterns that are almost always real secrets)
FINDINGS=""
FINDING_COUNT=0

check_pattern() {
    local name="$1"
    local pattern="$2"
    local matches
    matches="$(echo "$DIFF_ADDITIONS" | grep -nE "$pattern" 2>/dev/null || true)"
    if [ -n "$matches" ]; then
        FINDINGS="${FINDINGS}\n  [$name]:\n"
        while IFS= read -r match; do
            FINDINGS="${FINDINGS}    $match\n"
            FINDING_COUNT=$((FINDING_COUNT + 1))
        done <<< "$matches"
    fi
}

# AWS
check_pattern "AWS Access Key" "AKIA[0-9A-Z]{16}"
check_pattern "AWS Secret Key" "aws_secret_access_key\s*=\s*['\"][A-Za-z0-9/+=]{40}"

# Google
check_pattern "Google API Key" "AIza[0-9A-Za-z_-]{35}"
check_pattern "Google OAuth" "ya29\.[0-9A-Za-z_-]+"

# GitHub
check_pattern "GitHub Token" "gh[pousr]_[A-Za-z0-9_]{36,}"
check_pattern "GitHub Personal" "github_pat_[A-Za-z0-9_]{82}"

# Generic secrets
check_pattern "Private Key" "-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----"
check_pattern "Hardcoded Password" "(password|passwd|pwd)\s*=\s*['\"][^'\"]{8,}"
check_pattern "Hardcoded Secret" "(secret|token|api_key|apikey)\s*=\s*['\"][^'\"]{8,}"
check_pattern "Bearer Token" "Bearer\s+[A-Za-z0-9_-]{20,}"
check_pattern "Basic Auth" "Basic\s+[A-Za-z0-9+/=]{20,}"

# Database
check_pattern "Connection String" "(postgres|mysql|mongodb|redis)://[^@\s]+@"
check_pattern "Snowflake Password" "SNOWFLAKE_PASSWORD\s*=\s*['\"][^'\"]+['\"]"

# Slack
check_pattern "Slack Token" "xox[baprs]-[0-9A-Za-z-]{10,}"
check_pattern "Slack Webhook" "hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"

cd "$BAAP_ROOT"

if [ "$FINDING_COUNT" -gt 0 ]; then
    echo "[secrets] POTENTIAL SECRETS DETECTED ($FINDING_COUNT findings):"
    echo -e "$FINDINGS"
    echo ""
    echo "[secrets] MERGE BLOCKED until secrets are removed."
    echo "[secrets] Use environment variables or secret managers instead."
    exit 1
else
    echo "[secrets] No secrets detected in diff."
    exit 0
fi
```

---

## Fix 8: Fast-Path Review Configuration

### Problem

Not every change needs a full Opus review. Trivial changes (typo fixes, comment updates, 1-2 file configs) should get fast feedback via Haiku to keep velocity high. The threshold between fast and full review needs to be configurable per-project.

### Solution

The fast/full decision logic is already in `review-agent.sh` (Fix 3), controlled by environment variables. Create a configuration file that projects can customize:

```bash
# =============================================================================
# .claude/agents/review-agent/config.sh
# Review agent configuration -- sourced by review-agent.sh
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# Fast-path thresholds
# Changes below BOTH thresholds get Haiku review (fast, ~15s)
# Changes above EITHER threshold get Opus review (full, ~60s)
# ─────────────────────────────────────────────────────────────────────────────
export FAST_THRESHOLD_FILES=2       # Max files for fast-path
export FAST_THRESHOLD_LINES=50      # Max total lines (added + removed) for fast-path

# ─────────────────────────────────────────────────────────────────────────────
# Timeouts
# ─────────────────────────────────────────────────────────────────────────────
export REVIEW_TIMEOUT=120           # Max seconds for any review
export REVIEW_TIMEOUT_FAST=30       # Max seconds for fast-path review
export AGENT_FIX_TIMEOUT=300        # Max seconds for agent to apply fixes

# ─────────────────────────────────────────────────────────────────────────────
# Retry configuration
# ─────────────────────────────────────────────────────────────────────────────
export MAX_REVIEW_RETRIES=2         # Fix cycles before escalating to human
export RETRY_BACKOFF_SECONDS=30     # Pause between retries

# ─────────────────────────────────────────────────────────────────────────────
# Skip patterns
# Files matching these patterns bypass review entirely
# (useful for auto-generated files, lock files, etc.)
# ─────────────────────────────────────────────────────────────────────────────
REVIEW_SKIP_PATTERNS=(
    "package-lock.json"
    "*.lock"
    ".beads/*"
    "sessions/*"
    "capsules/*"
    "*.png"
    "*.jpg"
    "*.jpeg"
    "*.gif"
    "*.svg"
    "*.ico"
    "*.woff"
    "*.woff2"
    "*.ttf"
    "*.eot"
)

# ─────────────────────────────────────────────────────────────────────────────
# Infrastructure paths (orchestrator can skip review for these)
# ─────────────────────────────────────────────────────────────────────────────
INFRASTRUCTURE_PATHS=(
    "CLAUDE.md"
    ".claude/agents/*/memory/MEMORY.md"
    ".claude/kg/agent_graph_cache.json"
    "scripts/*.sh"
    ".github/workflows/*"
)

# ─────────────────────────────────────────────────────────────────────────────
# should_skip_review()
# Returns 0 (true) if all changed files match skip patterns
# ─────────────────────────────────────────────────────────────────────────────
should_skip_review() {
    local changed_files="$1"
    local all_skippable=true

    while IFS= read -r file; do
        [ -z "$file" ] && continue
        local is_skip=false
        for pattern in "${REVIEW_SKIP_PATTERNS[@]}"; do
            if [[ "$file" == $pattern ]]; then
                is_skip=true
                break
            fi
        done
        if [ "$is_skip" = "false" ]; then
            all_skippable=false
            break
        fi
    done <<< "$changed_files"

    if [ "$all_skippable" = "true" ]; then
        return 0
    else
        return 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# is_infrastructure_change()
# Returns 0 (true) if all changed files are infrastructure paths
# ─────────────────────────────────────────────────────────────────────────────
is_infrastructure_change() {
    local changed_files="$1"
    local all_infra=true

    while IFS= read -r file; do
        [ -z "$file" ] && continue
        local is_infra=false
        for pattern in "${INFRASTRUCTURE_PATHS[@]}"; do
            if [[ "$file" == $pattern ]]; then
                is_infra=true
                break
            fi
        done
        if [ "$is_infra" = "false" ]; then
            all_infra=false
            break
        fi
    done <<< "$changed_files"

    if [ "$all_infra" = "true" ]; then
        return 0
    else
        return 1
    fi
}
```

Add this sourcing to the top of `review-agent.sh` (after the configuration block):

```bash
# Source project-specific config if it exists
REVIEW_CONFIG="$BAAP_ROOT/.claude/agents/review-agent/config.sh"
if [ -f "$REVIEW_CONFIG" ]; then
    # shellcheck source=/dev/null
    source "$REVIEW_CONFIG"
fi
```

And add these checks before the diff computation:

```bash
# Check if all changed files should skip review
if should_skip_review "$CHANGED_FILES"; then
    echo "[review-agent] All changed files match skip patterns. Skipping review."
    exit 0
fi

# Check if this is an infrastructure-only change
if is_infrastructure_change "$CHANGED_FILES"; then
    echo "[review-agent] Infrastructure-only change detected."
    if [ "$SKIP_REVIEW" != "force" ]; then
        echo "[review-agent] Skipping review for infrastructure paths."
        exit 0
    fi
fi
```

---

## Fix 9: Handling Reviewer Hallucinations

### Problem

The review agent itself can hallucinate findings -- flagging issues that do not exist, misunderstanding code, or confusing file names. This is the "who watches the watchmen?" problem. A reviewer that produces too many false positives will be ignored, reducing the value of the entire system.

### Solution

Implement a calibration loop with three mechanisms:

1. **Structured output validation**: The verdict JSON is validated against a schema, and malformed output defaults to CHANGES_REQUESTED (conservative, not APPROVED)

2. **Finding verification**: For each finding, the reviewer must cite a specific file and line number. A post-review script can verify that the cited code actually exists

3. **Human feedback loop**: When humans override a review verdict, the feedback is stored in the review agent's memory for future calibration

Create `.claude/scripts/verify-findings.sh`:

```bash
#!/usr/bin/env bash
# =============================================================================
# verify-findings.sh -- Verify that review findings reference real code
#
# Checks that each finding's file:line reference actually exists and
# that the described issue is plausible (the line contains relevant code).
#
# Usage:
#   verify-findings.sh <review-json-file> <worktree-path>
#
# Exit codes:
#   0  All findings verified (or no findings to verify)
#   1  Some findings reference non-existent code (potential hallucination)
# =============================================================================

set -euo pipefail

REVIEW_FILE="${1:?Usage: verify-findings.sh <review-json-file> <worktree-path>}"
WORKTREE_PATH="${2:?Usage: verify-findings.sh <review-json-file> <worktree-path>}"

if [ ! -f "$REVIEW_FILE" ]; then
    echo "[verify] Review file not found: $REVIEW_FILE" >&2
    exit 1
fi

FINDINGS_COUNT="$(jq '.findings | length' "$REVIEW_FILE" 2>/dev/null || echo 0)"
if [ "$FINDINGS_COUNT" -eq 0 ]; then
    echo "[verify] No findings to verify."
    exit 0
fi

HALLUCINATION_COUNT=0
VERIFIED_COUNT=0

for i in $(seq 0 $((FINDINGS_COUNT - 1))); do
    FILE="$(jq -r ".findings[$i].file // \"\"" "$REVIEW_FILE")"
    LINE="$(jq -r ".findings[$i].line // 0" "$REVIEW_FILE")"
    DESC="$(jq -r ".findings[$i].description // \"\"" "$REVIEW_FILE")"

    # Skip findings without file references (general findings)
    if [ -z "$FILE" ] || [ "$FILE" = "null" ] || [ "$FILE" = "" ]; then
        continue
    fi

    FULL_PATH="$WORKTREE_PATH/$FILE"

    if [ ! -f "$FULL_PATH" ]; then
        echo "[verify] HALLUCINATION? Finding $i references non-existent file: $FILE"
        HALLUCINATION_COUNT=$((HALLUCINATION_COUNT + 1))
        continue
    fi

    if [ "$LINE" -gt 0 ]; then
        TOTAL_LINES="$(wc -l < "$FULL_PATH" | tr -d ' ')"
        if [ "$LINE" -gt "$TOTAL_LINES" ]; then
            echo "[verify] HALLUCINATION? Finding $i references line $LINE but $FILE has only $TOTAL_LINES lines"
            HALLUCINATION_COUNT=$((HALLUCINATION_COUNT + 1))
            continue
        fi
    fi

    VERIFIED_COUNT=$((VERIFIED_COUNT + 1))
done

echo "[verify] Results: $VERIFIED_COUNT verified, $HALLUCINATION_COUNT potential hallucinations out of $FINDINGS_COUNT findings"

if [ "$HALLUCINATION_COUNT" -gt 0 ]; then
    echo "[verify] WARNING: $HALLUCINATION_COUNT findings may be hallucinated."

    # If more than half the findings are hallucinated, the review itself is suspect
    if [ "$HALLUCINATION_COUNT" -gt $((FINDINGS_COUNT / 2)) ]; then
        echo "[verify] CRITICAL: Majority of findings appear hallucinated. Review quality is suspect."
        echo "[verify] Consider re-running the review or requesting human review."
    fi

    exit 1
else
    exit 0
fi
```

Add human feedback recording to the review agent's memory:

```bash
#!/usr/bin/env bash
# =============================================================================
# review-feedback.sh -- Record human override of a review verdict
#
# Usage:
#   review-feedback.sh <review-id> <override-verdict> <reason>
#
# Example:
#   review-feedback.sh review-agent-a-20260214-120000 APPROVED "False positive on SQL injection"
# =============================================================================

set -euo pipefail

REVIEW_ID="${1:?Usage: review-feedback.sh <review-id> <override-verdict> <reason>}"
OVERRIDE_VERDICT="${2:?Usage: review-feedback.sh <review-id> <override-verdict> <reason>}"
REASON="${3:?Usage: review-feedback.sh <review-id> <override-verdict> <reason>}"

BAAP_ROOT="${BAAP_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
REVIEW_DIR="$BAAP_ROOT/.claude/agents/review-agent/reviews"
MEMORY_FILE="$BAAP_ROOT/.claude/agents/review-agent/memory/MEMORY.md"

# Find the review
REVIEW_FILE="$REVIEW_DIR/${REVIEW_ID}.json"
if [ ! -f "$REVIEW_FILE" ]; then
    echo "Review not found: $REVIEW_FILE" >&2
    exit 1
fi

ORIGINAL_VERDICT="$(jq -r '.verdict' "$REVIEW_FILE")"

echo "[feedback] Recording override: $ORIGINAL_VERDICT -> $OVERRIDE_VERDICT"
echo "[feedback] Reason: $REASON"

# Add override metadata to the review JSON
jq --arg ov "$OVERRIDE_VERDICT" --arg reason "$REASON" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '. + {human_override: {original_verdict: .verdict, override_verdict: $ov, reason: $reason, timestamp: $ts}}' \
    "$REVIEW_FILE" > "${REVIEW_FILE}.tmp" && mv "${REVIEW_FILE}.tmp" "$REVIEW_FILE"

# Append to memory file for future calibration
{
    echo ""
    echo "### Override: $REVIEW_ID ($(date +%Y-%m-%d))"
    echo "- Original: $ORIGINAL_VERDICT -> Override: $OVERRIDE_VERDICT"
    echo "- Reason: $REASON"
    echo "- Findings that were wrong:"
    jq -r '.findings[] | "  - [\(.severity)] \(.dimension): \(.description)"' "$REVIEW_FILE" 2>/dev/null || true
} >> "$MEMORY_FILE"

echo "[feedback] Override recorded in $MEMORY_FILE"
```

---

## Success Criteria

- [ ] `review-agent.sh` spawns a Claude Code session with the correct model (Haiku for fast, Opus for full) and produces a structured JSON verdict
- [ ] Empty diffs exit immediately with code 0 (no review needed)
- [ ] Diffs with <=2 files AND <=50 total lines trigger fast-path (Haiku) review
- [ ] Diffs exceeding either threshold trigger full (Opus) review
- [ ] The verdict JSON contains all required fields: verdict, scores (5 dimensions), weighted_total, findings array, summary
- [ ] APPROVED verdict (exit 0) allows cleanup.sh to proceed with merge
- [ ] CHANGES_REQUESTED verdict (exit 1) blocks merge and creates a fix bead linked to the original work bead
- [ ] REJECTED verdict (exit 2) blocks merge and creates an escalation bead at priority 0
- [ ] Review timeout blocks merge (conservative -- never auto-approve on timeout)
- [ ] Ownership violations are detected by cross-referencing changed files against `agent_graph_cache.json`
- [ ] Secret patterns (AWS keys, GitHub tokens, private keys, hardcoded passwords) are caught by regex pre-check before LLM review
- [ ] `cleanup.sh agent merge --skip-review` bypasses the review gate for orchestrator infrastructure changes
- [ ] `review-verdict.sh --stats` shows aggregate review statistics (total, approved, changes_requested, rejected, first-pass rate)
- [ ] `verify-findings.sh` detects hallucinated findings (references to non-existent files or lines beyond EOF)
- [ ] `review-feedback.sh` records human overrides in the review agent's memory for calibration
- [ ] The fix retry loop runs up to MAX_REVIEW_RETRIES times before escalating
- [ ] All review artifacts (prompt, raw output, verdict JSON) are saved in `.claude/agents/review-agent/reviews/` for audit

## Verification

```bash
# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Verify all scripts exist and are executable
# ─────────────────────────────────────────────────────────────────────────────
test -x scripts/review-agent.sh && echo "PASS: review-agent.sh exists" || echo "FAIL"
test -x scripts/review-verdict.sh && echo "PASS: review-verdict.sh exists" || echo "FAIL"
test -x scripts/check-ownership.sh && echo "PASS: check-ownership.sh exists" || echo "FAIL"
test -x scripts/check-secrets.sh && echo "PASS: check-secrets.sh exists" || echo "FAIL"
test -x scripts/verify-findings.sh && echo "PASS: verify-findings.sh exists" || echo "FAIL"
test -x scripts/review-feedback.sh && echo "PASS: review-feedback.sh exists" || echo "FAIL"
test -f scripts/review-prompt.md && echo "PASS: review-prompt.md exists" || echo "FAIL"
test -f .claude/agents/review-agent/agent.md && echo "PASS: agent.md exists" || echo "FAIL"
test -f .claude/agents/review-agent/config.sh && echo "PASS: config.sh exists" || echo "FAIL"

# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Fast-path threshold detection
# ─────────────────────────────────────────────────────────────────────────────
# Create a test worktree with a small change
git worktree add /tmp/test-review-fast test-review-fast 2>/dev/null || true
echo "# test" >> /tmp/test-review-fast/README.md
cd /tmp/test-review-fast && git add -A && git commit -m "small change"
cd "$BAAP_ROOT"
# This should trigger fast-path (1 file, 1 line)
scripts/review-agent.sh test-agent /tmp/test-review-fast 2>&1 | grep -q "Fast-path" && echo "PASS: Fast-path detected" || echo "FAIL"
git worktree remove /tmp/test-review-fast --force 2>/dev/null || true

# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Skip review flag
# ─────────────────────────────────────────────────────────────────────────────
SKIP_REVIEW=true scripts/review-agent.sh any-agent /tmp 2>&1 | grep -q "Skipping review" && echo "PASS: Skip review works" || echo "FAIL"

# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Secret detection
# ─────────────────────────────────────────────────────────────────────────────
# Create a test file with a fake AWS key in a temp worktree
git worktree add /tmp/test-secrets test-secrets 2>/dev/null || true
echo 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"' >> /tmp/test-secrets/test.py
cd /tmp/test-secrets && git add -A && git commit -m "add secret"
cd "$BAAP_ROOT"
scripts/check-secrets.sh /tmp/test-secrets 2>&1 | grep -q "POTENTIAL SECRETS DETECTED" && echo "PASS: Secret detected" || echo "FAIL"
git worktree remove /tmp/test-secrets --force 2>/dev/null || true

# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Review verdict stats
# ─────────────────────────────────────────────────────────────────────────────
mkdir -p .claude/agents/review-agent/reviews
echo '{"verdict":"APPROVED","weighted_total":8.5}' > .claude/agents/review-agent/reviews/review-test-20260214-120000.json
echo '{"verdict":"CHANGES_REQUESTED","weighted_total":5.0}' > .claude/agents/review-agent/reviews/review-test-20260214-130000.json
scripts/review-verdict.sh --stats 2>&1 | grep -q "Total reviews" && echo "PASS: Stats command works" || echo "FAIL"

# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Finding verification (hallucination detection)
# ─────────────────────────────────────────────────────────────────────────────
echo '{"findings":[{"file":"nonexistent.py","line":1,"description":"test","severity":"high","dimension":"correctness"}]}' > /tmp/test-review.json
scripts/verify-findings.sh /tmp/test-review.json "$BAAP_ROOT" 2>&1 | grep -q "HALLUCINATION" && echo "PASS: Hallucination detected" || echo "FAIL"

# ─────────────────────────────────────────────────────────────────────────────
# Test 7: End-to-end review (requires Claude Code CLI)
# ─────────────────────────────────────────────────────────────────────────────
# This test requires a real Claude Code session -- run manually:
#   git worktree add /tmp/test-e2e agent/test-e2e
#   cd /tmp/test-e2e
#   echo 'def hello(): return "world"' > hello.py
#   git add -A && git commit -m "add hello"
#   cd $BAAP_ROOT
#   scripts/review-agent.sh test-agent /tmp/test-e2e
#   echo "Exit code: $?"
#   scripts/review-verdict.sh test-agent --json
#   git worktree remove /tmp/test-e2e --force
```
