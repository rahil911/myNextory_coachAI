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
