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
