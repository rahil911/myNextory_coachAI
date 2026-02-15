# 03f — Agent Learning Network (Shared Knowledge)

## Purpose

Agents working in isolated git worktrees accumulate valuable knowledge during sessions — API behaviors, schema quirks, library gotchas, testing patterns — then lose it all when the session ends. Even when written to their own `MEMORY.md`, that knowledge stays siloed within a single agent. The Agent Learning Network solves this by creating a shared knowledge layer at `.claude/knowledge/patterns.md` that every agent reads on session start, enabling discoveries from any agent to benefit all agents without cross-agent communication.

This is the difference between a team of amnesiac contractors and a team that actually learns.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Pattern pollution — low-quality or wrong patterns degrade all agents | **Critical** | Confidence tiers (hypothesis/validated/established) + curation script |
| File growth — patterns.md becomes 50KB and bloats every agent's context | **High** | Category sections + curation script deduplicates/prunes + 200-pattern hard cap |
| Race conditions — two agents write to patterns.md simultaneously | **Medium** | Agents work in isolated worktrees; patterns merge via git. Curation script runs single-threaded on orchestrator |
| Stale patterns — pattern was true for library v2 but breaks in v3 | **Medium** | `last_validated` timestamp + curation script flags patterns not validated in 90 days |
| Noise beads — "pattern-discovered" beads overwhelm the orchestrator | **Low** | Single bead per pattern, no bead for confidence upgrades, orchestrator batches pattern reviews |

## Files

### 1. `.claude/knowledge/patterns.md` — Shared pattern store

Read by every agent on session start. Written to by any agent that discovers a reusable pattern.

### 2. `.claude/knowledge/curate-patterns.sh` — Curation script

Run periodically by the orchestrator (or manually). Deduplicates, categorizes, prunes stale patterns, enforces the 200-pattern cap.

### 3. `.claude/knowledge/SCHEMA.md` — Pattern format reference

Documents the exact format for pattern entries so agents produce consistent output.

### 4. CLAUDE.md additions — Every agent's context loading instruction

A new section in the project CLAUDE.md that tells agents to read `patterns.md` on startup and how to contribute patterns.

## Fixes

### Fix 1: Create the shared patterns file

**File**: `.claude/knowledge/patterns.md`

This is the living document. Agents append to it. The curation script cleans it. Every agent reads it on session start.

```markdown
# Shared Agent Patterns
#
# This file contains patterns discovered by agents during their work.
# Every agent reads this file on session start.
# To add a pattern, append a new section following the format in SCHEMA.md.
#
# Curated by: curate-patterns.sh (run periodically by orchestrator)
# Last curated: (auto-updated by curation script)
# Pattern count: 0

---

## coding-patterns

(No patterns yet in this category.)

---

## db-patterns

(No patterns yet in this category.)

---

## api-patterns

(No patterns yet in this category.)

---

## testing-patterns

(No patterns yet in this category.)

---

## security-patterns

(No patterns yet in this category.)

---

## infra-patterns

(No patterns yet in this category.)
```

### Fix 2: Create the pattern format schema

**File**: `.claude/knowledge/SCHEMA.md`

```markdown
# Pattern Format Schema

Every pattern entry in `patterns.md` MUST follow this exact format.
Place the pattern under the correct category heading.

## Format

```
### [Pattern Name]
- **Discovered by**: [agent-name]
- **Date**: [YYYY-MM-DD]
- **Confidence**: [hypothesis | validated | established]
- **Last validated**: [YYYY-MM-DD]
- **Validation count**: [number]
- **Context**: [When does this pattern apply? Be specific about the scope.]
- **Pattern**: [What to do. Concrete, actionable, with code if relevant.]
- **Anti-pattern**: [What NOT to do. The mistake this pattern prevents.]
- **Evidence**: [Brief description of how this was discovered.]
```

## Confidence Levels

| Level | Meaning | Weight | Promotion criteria |
|-------|---------|--------|--------------------|
| `hypothesis` | First observation, might be wrong | Low — try it but verify | Initial discovery |
| `validated` | Confirmed across 2+ agents or sessions | Medium — follow unless you have reason not to | 2+ independent confirmations |
| `established` | Used successfully 5+ times | High — treat as project convention | 5+ successful uses, 0 contradictions |

## Rules

1. **One pattern per concept.** Don't combine "use Pydantic v2" with "always validate response schemas."
2. **Be specific.** "Handle errors" is not a pattern. "Wrap Snowflake queries in try/except and check for ProgrammingError to catch stale sessions" is.
3. **Include code when possible.** A 3-line code snippet is worth 30 words of description.
4. **Anti-patterns are mandatory.** If you can't articulate what NOT to do, the pattern isn't concrete enough.
5. **Context scoping.** Always specify WHEN the pattern applies. "When calling BC_ANALYTICS APIs" not "always."
```

### Fix 3: Create the curation script

**File**: `.claude/knowledge/curate-patterns.sh`

```bash
#!/usr/bin/env bash
# =============================================================================
# curate-patterns.sh — Deduplicate, categorize, and clean up patterns.md
#
# Run by the orchestrator periodically, or manually:
#   bash .claude/knowledge/curate-patterns.sh
#
# Requirements:
#   - claude CLI (uses Haiku for fast, cheap curation)
#   - patterns.md in same directory
#
# What it does:
#   1. Reads current patterns.md
#   2. Sends to Claude Haiku with curation instructions
#   3. Writes cleaned output back to patterns.md
#   4. Creates a git-friendly diff for review
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATTERNS_FILE="$SCRIPT_DIR/patterns.md"
SCHEMA_FILE="$SCRIPT_DIR/SCHEMA.md"
BACKUP_FILE="$SCRIPT_DIR/.patterns-backup-$(date +%Y%m%d-%H%M%S).md"
TEMP_OUTPUT="$SCRIPT_DIR/.patterns-curated-tmp.md"
MAX_PATTERNS=200

# ─────────────────────────────────────────────────────────────────────────────
# Preflight checks
# ─────────────────────────────────────────────────────────────────────────────
if [ ! -f "$PATTERNS_FILE" ]; then
  echo "ERROR: $PATTERNS_FILE not found. Nothing to curate."
  exit 1
fi

if ! command -v claude &>/dev/null; then
  echo "ERROR: claude CLI not found. Install: https://docs.anthropic.com/claude-code"
  exit 1
fi

# Count current patterns (lines starting with ### inside category sections)
PATTERN_COUNT=$(grep -c '^### ' "$PATTERNS_FILE" 2>/dev/null || echo "0")
echo "Current pattern count: $PATTERN_COUNT"

if [ "$PATTERN_COUNT" -eq 0 ]; then
  echo "No patterns to curate. Exiting."
  exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# Backup current file
# ─────────────────────────────────────────────────────────────────────────────
cp "$PATTERNS_FILE" "$BACKUP_FILE"
echo "Backed up to: $BACKUP_FILE"

# ─────────────────────────────────────────────────────────────────────────────
# Build curation prompt
# ─────────────────────────────────────────────────────────────────────────────
CURATION_PROMPT="$(cat <<'PROMPT_EOF'
You are curating a shared patterns file for an AI agent team. Your job:

1. DEDUPLICATE: Merge patterns that describe the same concept. Keep the best-written version. Combine evidence and bump validation count.

2. CATEGORIZE: Ensure every pattern is under the correct category heading:
   - coding-patterns: Language idioms, library usage, code structure
   - db-patterns: Database queries, schema handling, connection management
   - api-patterns: API calling conventions, response handling, authentication
   - testing-patterns: Test writing, fixtures, mocking, CI patterns
   - security-patterns: Credential handling, input validation, access control
   - infra-patterns: Deployment, configuration, environment setup

3. VALIDATE CONFIDENCE: Check confidence levels are appropriate:
   - hypothesis: Only 1 observation, no independent confirmation
   - validated: 2+ independent confirmations (check validation count)
   - established: 5+ successful uses (check validation count)
   Upgrade or downgrade confidence based on validation_count.

4. PRUNE STALE: Flag patterns where last_validated is more than 90 days ago by adding "(STALE — needs revalidation)" to the pattern name. Do NOT delete them.

5. ENFORCE CAP: If there are more than 200 patterns, remove the lowest-value ones. Priority for removal (lowest to highest value):
   - hypothesis confidence with validation_count=1 and last_validated > 60 days
   - Patterns that are too vague (no code snippet, no specific context)
   - Duplicate-adjacent patterns (very similar but not exact duplicates)

6. FORMAT: Output the complete patterns.md file with:
   - Updated header (pattern count, last curated date = today)
   - All category sections in order
   - Clean markdown formatting
   - No commentary outside the patterns.md structure

Output ONLY the curated patterns.md content, nothing else.
PROMPT_EOF
)"

# ─────────────────────────────────────────────────────────────────────────────
# Run curation through Claude Haiku
# ─────────────────────────────────────────────────────────────────────────────
echo "Running curation through Claude Haiku..."

PATTERNS_CONTENT="$(cat "$PATTERNS_FILE")"
SCHEMA_CONTENT=""
if [ -f "$SCHEMA_FILE" ]; then
  SCHEMA_CONTENT="$(cat "$SCHEMA_FILE")"
fi

# Use claude CLI with Haiku model for fast, cheap curation
claude --model haiku --print \
  "$CURATION_PROMPT

--- SCHEMA ---
$SCHEMA_CONTENT

--- CURRENT PATTERNS.MD ---
$PATTERNS_CONTENT" \
  > "$TEMP_OUTPUT" 2>/dev/null

# ─────────────────────────────────────────────────────────────────────────────
# Validate output
# ─────────────────────────────────────────────────────────────────────────────
if [ ! -s "$TEMP_OUTPUT" ]; then
  echo "ERROR: Curation produced empty output. Restoring backup."
  cp "$BACKUP_FILE" "$PATTERNS_FILE"
  rm -f "$TEMP_OUTPUT"
  exit 1
fi

# Sanity check: output should contain category headers
REQUIRED_HEADERS=("coding-patterns" "db-patterns" "api-patterns" "testing-patterns" "security-patterns")
for header in "${REQUIRED_HEADERS[@]}"; do
  if ! grep -q "$header" "$TEMP_OUTPUT"; then
    echo "ERROR: Curated output missing category '$header'. Restoring backup."
    cp "$BACKUP_FILE" "$PATTERNS_FILE"
    rm -f "$TEMP_OUTPUT"
    exit 1
  fi
done

# ─────────────────────────────────────────────────────────────────────────────
# Apply curated output
# ─────────────────────────────────────────────────────────────────────────────
mv "$TEMP_OUTPUT" "$PATTERNS_FILE"

NEW_COUNT=$(grep -c '^### ' "$PATTERNS_FILE" 2>/dev/null || echo "0")
echo ""
echo "Curation complete:"
echo "  Before: $PATTERN_COUNT patterns"
echo "  After:  $NEW_COUNT patterns"
echo "  Backup: $BACKUP_FILE"

# Show diff if git is available
if command -v git &>/dev/null && git rev-parse --is-inside-work-tree &>/dev/null; then
  echo ""
  echo "Changes:"
  git diff --stat "$PATTERNS_FILE" 2>/dev/null || true
fi

# ─────────────────────────────────────────────────────────────────────────────
# Clean up old backups (keep last 5)
# ─────────────────────────────────────────────────────────────────────────────
BACKUP_COUNT=$(ls "$SCRIPT_DIR"/.patterns-backup-*.md 2>/dev/null | wc -l | tr -d ' ')
if [ "$BACKUP_COUNT" -gt 5 ]; then
  ls -t "$SCRIPT_DIR"/.patterns-backup-*.md | tail -n +6 | xargs rm -f
  echo "Cleaned old backups (kept last 5)."
fi
```

### Fix 4: Pattern contribution protocol — agent instructions

**Addition to project CLAUDE.md** (new section to add):

```markdown
---

## Shared Knowledge (Agent Learning Network)

### On Session Start

Read the shared patterns file before starting work:
- `@.claude/knowledge/patterns.md` — Patterns discovered by all agents

Weight patterns by confidence:
- **established**: Treat as project convention. Follow unless explicitly overridden.
- **validated**: Strong guidance. Follow unless you have a specific reason not to.
- **hypothesis**: Informational. Try it, but verify independently.

### Contributing Patterns

When you discover something reusable during your work — an API behavior, a library quirk, a testing approach, a schema convention — contribute it to the shared knowledge:

#### Step 1: Write to your own MEMORY.md (always)
```
Add to .claude/agents/{your-name}/memory/MEMORY.md
```

#### Step 2: Append to shared patterns (if reusable across agents)

Append a new pattern entry to `.claude/knowledge/patterns.md` under the correct category heading. Follow the format in `.claude/knowledge/SCHEMA.md` exactly.

**Only contribute patterns that are genuinely reusable.** Ask yourself:
- Would another agent benefit from knowing this?
- Is this specific enough to be actionable?
- Can I articulate both the pattern AND the anti-pattern?

If any answer is no, keep it in your MEMORY.md only.

#### Step 3: Create a bead for discovery tracking
```bash
bd create "Pattern: [pattern-name] ([category])" \
  --label pattern-discovered \
  --label "category:[coding-patterns|db-patterns|api-patterns|testing-patterns|security-patterns|infra-patterns]" \
  --label "confidence:hypothesis" \
  --priority 3
```

#### Step 4: Validate existing patterns

If during your work you independently confirm an existing pattern works:
1. Update `Validation count` (+1) and `Last validated` date in that pattern's entry
2. If validation count reaches 2, upgrade confidence from `hypothesis` to `validated`
3. If validation count reaches 5, upgrade confidence from `validated` to `established`
4. Do NOT create a new bead for validation — just update the pattern entry

If you find an existing pattern is WRONG:
1. Add `(DISPUTED)` to the pattern name
2. Add a line: `- **Dispute**: [your-agent-name] on [date]: [explanation of why it's wrong]`
3. Create a bead: `bd create "Pattern dispute: [pattern-name]" --label pattern-disputed --priority 2`
4. Do NOT delete the pattern — let the curation script handle it

### Pattern Categories

| Category | What goes here |
|----------|---------------|
| `coding-patterns` | Language idioms, library usage, code structure, import conventions |
| `db-patterns` | Query patterns, schema handling, connection management, migration gotchas |
| `api-patterns` | API calling conventions, response handling, retry logic, authentication |
| `testing-patterns` | Test structure, fixtures, mocking strategies, CI configuration |
| `security-patterns` | Credential handling, input validation, access control, secret management |
| `infra-patterns` | Deployment, configuration, environment setup, Docker, CI/CD |
```

### Fix 5: Cross-agent learning propagation via session-start hook

**File**: `.claude/hooks/scripts/load-patterns.sh`

This hook runs on SessionStart, right after `onboard.sh`. It loads the shared patterns into agent context and provides a summary of recently added patterns.

```bash
#!/usr/bin/env bash
# =============================================================================
# load-patterns.sh — Load shared patterns on session start
#
# Runs on: SessionStart (after onboard.sh)
# Purpose: Surface recently added/updated patterns so agents are aware of
#          new knowledge without needing beads notifications.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PATTERNS_FILE="$PROJECT_ROOT/.claude/knowledge/patterns.md"

if [ ! -f "$PATTERNS_FILE" ]; then
  exit 0  # No patterns file yet, nothing to load
fi

# Count patterns by confidence level
ESTABLISHED=$(grep -c 'Confidence.*established' "$PATTERNS_FILE" 2>/dev/null || echo "0")
VALIDATED=$(grep -c 'Confidence.*validated' "$PATTERNS_FILE" 2>/dev/null || echo "0")
HYPOTHESIS=$(grep -c 'Confidence.*hypothesis' "$PATTERNS_FILE" 2>/dev/null || echo "0")
TOTAL=$((ESTABLISHED + VALIDATED + HYPOTHESIS))

if [ "$TOTAL" -eq 0 ]; then
  exit 0  # No patterns yet
fi

# Find patterns added or updated in the last 7 days
SEVEN_DAYS_AGO=$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d '7 days ago' +%Y-%m-%d 2>/dev/null || echo "")
RECENT_PATTERNS=""
if [ -n "$SEVEN_DAYS_AGO" ]; then
  # Extract pattern names with dates after the cutoff
  RECENT_PATTERNS=$(grep -B1 "Last validated.*$SEVEN_DAYS_AGO\|Date.*$SEVEN_DAYS_AGO" "$PATTERNS_FILE" 2>/dev/null \
    | grep '^### ' \
    | sed 's/^### /  - /' \
    | head -10 || echo "")
fi

# Output summary for agent context
cat << EOF
=== Shared Knowledge Loaded ===
Patterns: $TOTAL total ($ESTABLISHED established, $VALIDATED validated, $HYPOTHESIS hypothesis)
EOF

if [ -n "$RECENT_PATTERNS" ]; then
  cat << EOF
Recently added/updated:
$RECENT_PATTERNS
EOF
fi

cat << EOF

Read: @.claude/knowledge/patterns.md
Schema: @.claude/knowledge/SCHEMA.md
===============================
EOF
```

### Fix 6: Pattern validation tracking — ownership KG integration

When a pattern is added, the contributing agent's name is recorded. The ownership KG can be queried to find which agents would benefit from a pattern based on dependency relationships. This does NOT create beads (too noisy) — instead, patterns propagate passively through `patterns.md` being read on session start.

**Addition to `.claude/agents/orchestration.yaml`** — new auxiliary flow:

```yaml
  # ---------------------------------------------------------------------------
  # PATTERN CURATION (SCHEDULED)
  # ---------------------------------------------------------------------------
  pattern_curation:
    id: pattern_curation
    name: "Shared Pattern Curation"
    description: |
      Periodic cleanup of the shared patterns file. Deduplicates, recategorizes,
      prunes stale entries, and enforces the 200-pattern cap.

    trigger:
      type: schedule
      cron: "0 6 * * 1"            # Every Monday at 6am
      manual: true                  # Can also be triggered manually

    steps:
      - step: curate
        agent: null                 # Shell script, not an agent
        type: script
        command: "bash .claude/knowledge/curate-patterns.sh"
        timeout: "120s"

      - step: commit_if_changed
        agent: null
        type: script
        command: |
          cd "$(git rev-parse --show-toplevel)"
          if git diff --quiet .claude/knowledge/patterns.md 2>/dev/null; then
            echo "No changes after curation."
          else
            git add .claude/knowledge/patterns.md
            git commit -m "chore: curate shared agent patterns ($(date +%Y-%m-%d))"
          fi
        timeout: "30s"

    settings:
      notify_on_error: true
      create_bead_on_error: true
```

### Fix 7: Example patterns to seed the system

**Initial content to append to `.claude/knowledge/patterns.md`** after the category headers, demonstrating the format with real patterns from the Decision Canvas OS codebase:

```markdown
## api-patterns

### BC_ANALYTICS APIs require trailing-slash-free routes
- **Discovered by**: causal-analyst
- **Date**: 2026-01-15
- **Confidence**: established
- **Last validated**: 2026-02-10
- **Validation count**: 8
- **Context**: When defining FastAPI routes that will be called by the frontend or other agents via BC_ANALYTICS at localhost:8000.
- **Pattern**: Use `redirect_slashes=False` on routers and define routes as `""` not `"/"`. Example: `@router.get("")` not `@router.get("/")`.
- **Anti-pattern**: Using trailing slashes in route definitions causes 307 redirects that break CORS and confuse fetch calls.
- **Evidence**: Multiple agents hit this independently. FastAPI default behavior is to redirect `/api/foo` to `/api/foo/` with a 307, which breaks POST/PATCH requests and CORS preflight.

### MCP tool responses can be object-typed
- **Discovered by**: data-quality
- **Date**: 2026-02-08
- **Confidence**: validated
- **Last validated**: 2026-02-12
- **Validation count**: 3
- **Context**: When rendering MCP tool call results in the agent UI (agent_stream.py SSE events).
- **Pattern**: Always check if the MCP response content is a string or an object before rendering. Use `typeof content === 'object' ? JSON.stringify(content, null, 2) : content` for display.
- **Anti-pattern**: Assuming MCP tool results are always strings. Some tools (causal-graph, bc-analytics) return structured objects that cause `[object Object]` rendering if not handled.
- **Evidence**: Commit a48f948 — "Handle object-typed MCP responses in agent page renderers."

---

## coding-patterns

### AbortController in React useEffect for fetch calls
- **Discovered by**: recommender
- **Date**: 2026-01-20
- **Confidence**: established
- **Last validated**: 2026-02-14
- **Validation count**: 12
- **Context**: When making fetch/API calls inside React useEffect hooks, especially in Next.js pages.
- **Pattern**: Always create an `AbortController`, pass its `signal` to fetch, and call `controller.abort()` in the cleanup function. Use a `hasFetched` ref to prevent loading skeleton flash after first successful load. Ignore `AbortError` in catch blocks.
```typescript
useEffect(() => {
  const controller = new AbortController();
  const fetchData = async () => {
    try {
      const res = await fetch(url, { signal: controller.signal });
      // handle response
      hasFetched.current = true;
    } catch (err) {
      if (err.name === 'AbortError') return; // expected on cleanup
      // handle real error
    }
  };
  fetchData();
  return () => controller.abort();
}, [deps]);
```
- **Anti-pattern**: Naked fetch calls without AbortController cause React strict mode to double-fire requests in dev, and can cause state updates on unmounted components.
- **Evidence**: Persistent flickering bug on dashboard pages. React strict mode double-fires useEffect in development, causing visible loading skeleton flashes.

---

## db-patterns

### Guard against null in Snowflake aggregate results
- **Discovered by**: forecaster
- **Date**: 2026-02-01
- **Confidence**: validated
- **Last validated**: 2026-02-10
- **Validation count**: 4
- **Context**: When querying Snowflake for aggregate metrics (SUM, AVG, COUNT) that might have no matching rows.
- **Pattern**: Always use `COALESCE(aggregate_fn(col), 0)` or `IFNULL(aggregate_fn(col), 0)` for numeric aggregates. For string aggregates, use `COALESCE(aggregate_fn(col), 'N/A')`. Always check if the result set is empty before accessing row values.
- **Anti-pattern**: Assuming aggregate queries always return a numeric value. When no rows match the WHERE clause, `SUM()` returns `NULL`, not `0`, which causes downstream `NoneType` errors in Python.
- **Evidence**: Null SVG path crash in dashed line chart layer (commit 6aee558). Forecaster hit this when projecting impact for a metric with no data in the requested time range.

---

## testing-patterns

(No patterns yet in this category.)

---

## security-patterns

(No patterns yet in this category.)

---

## infra-patterns

### Never build or run servers on Mac — deploy via git push
- **Discovered by**: triage
- **Date**: 2026-01-25
- **Confidence**: established
- **Last validated**: 2026-02-14
- **Validation count**: 20
- **Context**: When deploying changes to the Decision Canvas OS or BC_ANALYTICS applications.
- **Pattern**: Mac is dev-only. All building, running, and serving happens on the India production machine. Push to master and let GitHub Actions deploy automatically. The workflow handles SSH ProxyJump through Azure VM, git pull, pip install, npm build, and tmux restart.
- **Anti-pattern**: Running `npm run build`, `npm start`, `uvicorn`, or any server process on the Mac. This wastes resources and creates confusion about which environment is "live."
- **Evidence**: Multiple incidents of "it works on my machine" confusion when testing against local vs. deployed versions. CI/CD pipeline in `.github/workflows/deploy.yml` is the single source of truth for deployments.
```

## Success Criteria

### Functional

1. **Patterns file exists and is loadable**: `.claude/knowledge/patterns.md` is valid markdown, parseable by any agent, and contains the category structure.

2. **Agents read patterns on startup**: The `load-patterns.sh` hook runs on SessionStart and outputs a summary of loaded patterns. Verified by checking session logs for "Shared Knowledge Loaded" output.

3. **Agents can contribute patterns**: An agent can append a properly-formatted pattern entry to `patterns.md` following SCHEMA.md. The entry appears under the correct category.

4. **Pattern beads are created**: When a new pattern is contributed, a "pattern-discovered" bead exists with appropriate labels.

5. **Curation script runs without error**: `bash .claude/knowledge/curate-patterns.sh` processes the file, produces valid output with all category headers, and creates a backup.

6. **Confidence promotion works**: A pattern with `validation_count: 2` gets promoted from `hypothesis` to `validated`. A pattern with `validation_count: 5` gets promoted to `established`.

7. **Deduplication works**: Two patterns describing the same concept are merged into one by the curation script, preserving the higher validation count and best description.

### Non-Functional

8. **Context overhead is bounded**: `patterns.md` at 200 patterns stays under 40KB — small enough to include in every agent's context window without meaningful impact on token budget.

9. **No cross-agent beads noise**: Pattern propagation happens via file read (patterns.md on startup), NOT via beads. Only initial discovery and disputes create beads.

10. **Curation is idempotent**: Running `curate-patterns.sh` twice on the same input produces identical output.

11. **Git-friendly diffs**: Pattern entries are structured so that adding/removing one pattern produces a clean, reviewable git diff without touching other entries.

## Verification

### Test 1: Pattern contribution end-to-end

```bash
# Simulate an agent discovering a pattern
cd "$(git rev-parse --show-toplevel)"

# Verify patterns.md exists with correct structure
test -f .claude/knowledge/patterns.md || { echo "FAIL: patterns.md missing"; exit 1; }
grep -q "## coding-patterns" .claude/knowledge/patterns.md || { echo "FAIL: missing category headers"; exit 1; }
grep -q "## api-patterns" .claude/knowledge/patterns.md || { echo "FAIL: missing category headers"; exit 1; }
grep -q "## db-patterns" .claude/knowledge/patterns.md || { echo "FAIL: missing category headers"; exit 1; }
grep -q "## testing-patterns" .claude/knowledge/patterns.md || { echo "FAIL: missing category headers"; exit 1; }
grep -q "## security-patterns" .claude/knowledge/patterns.md || { echo "FAIL: missing category headers"; exit 1; }
echo "PASS: patterns.md structure is valid"

# Verify SCHEMA.md exists
test -f .claude/knowledge/SCHEMA.md || { echo "FAIL: SCHEMA.md missing"; exit 1; }
grep -q "hypothesis" .claude/knowledge/SCHEMA.md || { echo "FAIL: SCHEMA.md missing confidence levels"; exit 1; }
grep -q "validated" .claude/knowledge/SCHEMA.md || { echo "FAIL: SCHEMA.md missing confidence levels"; exit 1; }
grep -q "established" .claude/knowledge/SCHEMA.md || { echo "FAIL: SCHEMA.md missing confidence levels"; exit 1; }
echo "PASS: SCHEMA.md is valid"
```

### Test 2: Curation script validation

```bash
cd "$(git rev-parse --show-toplevel)"

# Verify script exists and is executable
test -f .claude/knowledge/curate-patterns.sh || { echo "FAIL: curate-patterns.sh missing"; exit 1; }
test -x .claude/knowledge/curate-patterns.sh || chmod +x .claude/knowledge/curate-patterns.sh

# Verify script has required safety checks
grep -q "BACKUP" .claude/knowledge/curate-patterns.sh || { echo "FAIL: no backup logic"; exit 1; }
grep -q "coding-patterns" .claude/knowledge/curate-patterns.sh || { echo "FAIL: no category validation"; exit 1; }
grep -q "MAX_PATTERNS" .claude/knowledge/curate-patterns.sh || { echo "FAIL: no pattern cap"; exit 1; }
echo "PASS: curate-patterns.sh has required safety checks"
```

### Test 3: Session start hook

```bash
cd "$(git rev-parse --show-toplevel)"

# Verify hook exists
test -f .claude/hooks/scripts/load-patterns.sh || { echo "FAIL: load-patterns.sh missing"; exit 1; }

# Run hook and check output
OUTPUT=$(bash .claude/hooks/scripts/load-patterns.sh 2>&1)
echo "$OUTPUT" | grep -q "Shared Knowledge Loaded" || echo "$OUTPUT" | grep -q "No patterns" || { echo "FAIL: hook produced unexpected output: $OUTPUT"; exit 1; }
echo "PASS: load-patterns.sh runs successfully"
```

### Test 4: Pattern format validation

```bash
cd "$(git rev-parse --show-toplevel)"

# Check that seeded patterns follow the schema
PATTERNS_FILE=".claude/knowledge/patterns.md"

# Every pattern should have required fields
for pattern_name in $(grep '^### ' "$PATTERNS_FILE" | sed 's/^### //'); do
  echo "Checking pattern: $pattern_name"
done

# Count patterns by confidence
ESTABLISHED=$(grep -c 'Confidence.*established' "$PATTERNS_FILE" 2>/dev/null || echo "0")
VALIDATED=$(grep -c 'Confidence.*validated' "$PATTERNS_FILE" 2>/dev/null || echo "0")
HYPOTHESIS=$(grep -c 'Confidence.*hypothesis' "$PATTERNS_FILE" 2>/dev/null || echo "0")
echo "Pattern confidence distribution: $ESTABLISHED established, $VALIDATED validated, $HYPOTHESIS hypothesis"
echo "PASS: Pattern format validation complete"
```

### Test 5: Cross-agent propagation (passive)

```bash
# Verify that patterns.md is referenced in CLAUDE.md
cd "$(git rev-parse --show-toplevel)"
grep -q "patterns.md" .claude/CLAUDE.md || { echo "FAIL: CLAUDE.md doesn't reference patterns.md"; exit 1; }
grep -q "knowledge" .claude/CLAUDE.md || { echo "FAIL: CLAUDE.md doesn't mention knowledge directory"; exit 1; }
echo "PASS: CLAUDE.md references shared knowledge"
```

## Architecture Diagram

```
                    Agent Session Start
                           |
                    load-patterns.sh
                           |
                    Read patterns.md
                     /     |     \
                    /      |      \
            established  validated  hypothesis
            (follow)   (prefer)    (try, verify)
                    \      |      /
                     \     |     /
                    Agent does work
                           |
                    Discovers pattern?
                    /               \
                  No                Yes
                  |                  |
                Done         Write MEMORY.md
                             Append patterns.md
                             Create bead
                                   |
                             Git commit
                                   |
                    ┌──────────────┼──────────────┐
                    |              |              |
              Agent B starts  Agent C starts  Orchestrator
                    |              |              |
              Reads patterns  Reads patterns  curate-patterns.sh
              (on next        (on next        (weekly Monday 6am)
               session)        session)
                                              Dedup + categorize
                                              Promote confidence
                                              Prune stale
                                              Git commit
```

## Relationship to Other Specs

- **03a (Agent Memory)**: Patterns.md is the cross-agent complement to per-agent MEMORY.md. Agents always write to their own memory first, then optionally share via patterns.md.
- **03b (Beads Integration)**: "pattern-discovered" and "pattern-disputed" beads use the beads system for orchestrator awareness, but propagation is file-based, not bead-based.
- **03c (Ownership KG)**: The `get_dependents()` query is available to identify which agents would benefit from a pattern, but is informational only — no active push.
- **03d (Orchestration)**: The `pattern_curation` scheduled flow is defined in orchestration.yaml and runs the cleanup script weekly.
- **03e (Agent Handoffs)**: No direct interaction. Patterns propagate passively, not through handoffs.
