---
name: recommend-action
description: |
  Synthesize investigation findings into actionable recommendations with prioritized beads.
  Use after completing an investigation (metric breach, root cause analysis, or impact forecast)
  to generate concrete next steps, create follow-up beads, and notify relevant agents and humans.

  Triggers: "recommend actions", "what should we do", "create fix beads",
  "next steps", "action plan", "remediation plan".
metadata:
  baap:
    requires:
      bins: [bd]
      config: [mcp.servers.ownership-graph]
---

# Recommend Action

Generate actionable recommendations from investigation findings and create follow-up beads.

## When to Use

- After completing a metric investigation
- After root cause analysis identifies the cause
- After impact forecasting quantifies severity
- When a human asks "what should we do about this?"

## Recommendation Framework

### Step 1: Classify the Issue

| Classification | Criteria | Response Time |
|---------------|----------|---------------|
| **P0 - Critical** | >50% users affected, data loss risk | Immediate (hours) |
| **P1 - High** | 20-50% users, feature broken | Within 24 hours |
| **P2 - Medium** | 5-20% users, degraded experience | Within 1 week |
| **P3 - Low** | <5% users, cosmetic | Next sprint |

### Step 2: Generate Recommendations

For each finding, generate recommendations in three time horizons:

**Immediate** (stop the bleeding):
- Can we revert a recent change?
- Can we disable the broken feature?
- Should we notify affected users?

**Short-term** (fix the root cause):
- What code/data needs to change?
- Which agent owns the fix?
- What tests need to be added?

**Long-term** (prevent recurrence):
- What monitoring should be added?
- What process change prevents this?
- What architectural improvement helps?

### Step 3: Identify Owners

Use the ownership graph to find the right agent for each action:

```bash
# Who owns the affected files?
get_file_owner "<affected_file>"

# Which agent has the relevant capability?
search_agents "<capability>"

# What are the dependencies?
get_dependencies "<agent-name>"
```

### Step 4: Create Beads

Create a bead for each actionable recommendation:

```bash
# Critical/immediate fix
bd create --title="[P0] Fix: [summary]" \
  --type=task --priority=0 \
  --description="## Spec
[What needs to change]

## Acceptance Criteria
- [ ] [Specific, testable criterion]
- [ ] [Another criterion]
- [ ] Tests pass

## Context
Investigation bead: [id]
Root cause: [summary]
Impact: [N users affected]"

# Monitoring/prevention
bd create --title="[P2] Monitor: [metric]" \
  --type=task --priority=2 \
  --description="Add alerting for [metric] with threshold [value].
Investigation bead: [id]"
```

### Step 5: Set Dependencies

```bash
# Fix must complete before monitoring setup
bd dep add <monitoring-bead> <fix-bead>

# Notification must happen immediately
# (no dependencies — unblocked)
```

### Step 6: Notify

For critical issues, use the notification router:

```bash
# The notification router handles routing based on priority
# Priority 3 → Telegram + Slack
# Agent events → Slack #baap-status
```

For agent-to-agent coordination, create notification beads:

```bash
bd create --title="[NOTIFY] [what changed]" \
  --type=task --priority=1 \
  --description="Changes from investigation [bead-id]: [summary].
Update your code/config accordingly."
```

## Output Template

```markdown
## Action Plan

**Investigation**: [bead-id] — [title]
**Root Cause**: [one sentence]
**Severity**: P[0-3]
**Generated**: [date]

### Immediate Actions
| # | Action | Owner | Bead | Status |
|---|--------|-------|------|--------|
| 1 | [action] | [agent] | [id] | Created |

### Short-term Fixes
| # | Action | Owner | Bead | Est. Effort |
|---|--------|-------|------|-------------|
| 1 | [action] | [agent] | [id] | [hours/days] |

### Long-term Prevention
| # | Action | Owner | Bead | Est. Effort |
|---|--------|-------|------|-------------|
| 1 | [action] | [agent] | [id] | [hours/days] |

### Dependencies
[bead-a] → [bead-b] → [bead-c]

### Notifications Sent
- [agent-name]: [notification summary]
```

## Anti-patterns

- **Vague recommendations**: "Fix the issue" — always specify what to change and how
- **Missing owners**: Every recommendation needs an assigned agent
- **No acceptance criteria**: Beads without testable criteria can't be verified
- **Skipping dependencies**: Beads created without proper ordering cause conflicts
- **Over-scoping**: Each bead should be completable by a single agent in one session
