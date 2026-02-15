---
name: root-cause-analysis
description: |
  Walk the causal graph upstream to find root causes of issues in the MyNextory platform.
  Use when a symptom has been identified (metric breach, user complaint, system error) and
  you need to determine the underlying cause. Combines database queries, ownership graph
  traversal, and activity log forensics.

  Triggers: "root cause", "why is this happening", "what caused", "find the source of",
  "debug this issue", "trace the problem".
metadata:
  baap:
    requires:
      bins: [bd]
      config: [mcp.servers.db-tools, mcp.servers.ownership-graph]
---

# Root Cause Analysis

Systematic approach to finding root causes of issues on the MyNextory platform.

## When to Use

- A metric investigation has identified symptoms but not the cause
- A user or coach reports unexpected behavior
- System errors or anomalies detected in activity logs
- Post-incident review to prevent recurrence

## Five Whys Framework

For each symptom, ask "why?" at least 5 times, using data at each step:

```
Symptom: Lesson completion rate dropped 30%
  Why? → Fewer users are reaching lesson slides
    Why? → Chapter unlock logic is blocking progression
      Why? → A prerequisite lesson was accidentally deleted
        Why? → Content admin removed it thinking it was a draft
          Why? → No soft-delete or confirmation for published content
Root cause: Missing safeguard on content deletion
```

## Procedure

### Step 1: Define the Symptom

Document exactly what's wrong:
- **What**: Which metric/behavior is affected?
- **When**: When did it start? (Check activity_log timestamps)
- **Where**: Which users/clients/journeys are affected?
- **How much**: What's the magnitude of the issue?

### Step 2: Timeline Construction

Build a timeline of events around the symptom onset:

```sql
-- Activity around the time the issue started
SELECT created_at, log_name, event, subject_type, description
FROM activity_log
WHERE created_at BETWEEN '<start_time>' AND '<end_time>'
ORDER BY created_at DESC
LIMIT 100;

-- Check for deployment/config changes (look for admin actions)
SELECT created_at, causer_id, event, subject_type, description
FROM activity_log
WHERE causer_type LIKE '%Admin%'
  AND created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY created_at DESC;
```

### Step 3: Hypothesis Generation

Based on the timeline, generate candidate root causes:

| Hypothesis | Evidence For | Evidence Against | Test |
|-----------|-------------|-----------------|------|
| [Cause A] | [data point] | [counter-evidence] | [query to run] |
| [Cause B] | [data point] | [counter-evidence] | [query to run] |

### Step 4: Hypothesis Testing

For each candidate, run targeted queries:

```bash
# Check entity state
run_query "SELECT * FROM <table> WHERE id = <id>"

# Check ownership and dependencies
get_blast_radius "<entity>"

# Check if related agents reported issues
get_agent_context "<agent-name>"
```

### Step 5: Confirm Root Cause

A root cause is confirmed when:
- Changing it would have prevented the symptom
- The causal chain from cause to symptom is complete
- No simpler explanation exists

### Step 6: Document and Create Beads

```bash
# Document findings
bd update <investigation-bead> --notes="Root cause: [summary]. Evidence: [key queries]."

# Create fix bead
bd create --title="Fix: [root cause]" --type=task --priority=<severity>

# Create prevention bead
bd create --title="Prevent: [root cause class]" --type=task --priority=2
```

## Common Root Cause Categories

| Category | Examples | Check |
|----------|---------|-------|
| **Data** | Missing records, corrupt values, stale cache | Schema integrity, freshness |
| **Logic** | Wrong calculation, race condition, edge case | Activity log event sequence |
| **Config** | Wrong threshold, disabled feature, expired token | Config tables, env vars |
| **Content** | Deleted/unpublished content, broken links | Content tables, media |
| **Infrastructure** | DB connection limit, disk full, memory leak | System metrics |
| **Human** | Accidental deletion, wrong update, permission error | Admin actions in activity_log |

## Anti-patterns

- **Blaming the symptom**: "Users aren't completing lessons" is a symptom, not a cause
- **Stopping too early**: The first "why" answer is rarely the root cause
- **Correlation as causation**: Just because two things changed at the same time doesn't mean one caused the other
- **Scope creep**: Stay focused on the specific symptom being investigated
