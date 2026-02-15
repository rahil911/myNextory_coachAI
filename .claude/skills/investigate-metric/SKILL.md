---
name: investigate-metric
description: |
  Full investigation protocol for metric breaches in MyNextory data. Use when a metric
  crosses a threshold or shows an anomaly — user engagement drops, lesson completion rates
  change, coaching session patterns shift, or activity log volumes spike/dip unexpectedly.
  Walks causal graph, checks data quality, forecasts impact, recommends actions.

  Triggers: "investigate metric", "metric breach", "anomaly detected", "why did X drop",
  "engagement declining", "completion rate changed".
metadata:
  baap:
    requires:
      bins: [bd]
      config: [mcp.servers.db-tools, mcp.servers.ownership-graph]
---

# Investigate Metric

Full investigation protocol for metric breaches on the MyNextory coaching/learning platform.

## Quick Reference

1. Validate data quality -> [references/data-quality.md](references/data-quality.md)
2. Walk causal graph -> [references/causal-analysis.md](references/causal-analysis.md)
3. Forecast impact -> [references/impact-forecasting.md](references/impact-forecasting.md)
4. Recommend actions -> [references/action-recommendations.md](references/action-recommendations.md)

## Core Workflow

### Phase 1: Triage

1. **Identify the metric** — What exactly changed? Get the metric name, current value, expected value, and time window.
2. **Quantify the breach** — How far off threshold? Is it a spike or a trend?
3. **Check scope** — Is it global (all users) or segmented (specific client, journey, coach)?

```bash
# Check recent activity patterns
run_query "SELECT DATE(created_at) as day, COUNT(*) as cnt FROM activity_log WHERE created_at > DATE_SUB(NOW(), INTERVAL 14 DAY) GROUP BY day ORDER BY day"

# Check user engagement
run_query "SELECT status, COUNT(*) FROM nx_users GROUP BY status"
```

### Phase 2: Data Quality Validation

Before investigating root cause, confirm the data is trustworthy.

**See [references/data-quality.md](references/data-quality.md) for detailed procedures.**

Quick checks:
- **Freshness**: Is the data current? Check `activity_log` max timestamp.
- **Completeness**: Are there gaps? Compare daily row counts.
- **Schema**: Any recent migrations? Check table structure.

```bash
# Data freshness check
run_query "SELECT MAX(created_at) as latest FROM activity_log"

# Daily completeness
run_query "SELECT DATE(created_at) as day, COUNT(*) FROM activity_log WHERE created_at > DATE_SUB(NOW(), INTERVAL 7 DAY) GROUP BY day ORDER BY day"
```

### Phase 3: Causal Analysis

Walk the causal graph upstream from the affected metric to find the root cause.

**See [references/causal-analysis.md](references/causal-analysis.md) for graph traversal patterns.**

Key relationships in MyNextory:
- `nx_users` -> `journeys` -> `chapters` -> `lessons` -> `lesson_slides`
- `nx_users` -> `coaching_sessions` -> `session_notes`
- `nx_users` -> `activity_log` (polymorphic audit trail)
- `clients` -> `nx_users` (organization membership)

```bash
# Use ownership graph to find related tables
get_blast_radius "User"

# Check entity context
get_entity_context "Journey"
```

### Phase 4: Impact Forecasting

Estimate the business impact of the metric breach.

**See [references/impact-forecasting.md](references/impact-forecasting.md) for formulas.**

Dimensions to assess:
- **User impact**: How many users are affected?
- **Revenue impact**: Does this affect paid features?
- **Operational impact**: Does this block coaches or admins?
- **Data impact**: Is data being lost or corrupted?

### Phase 5: Recommendations

Synthesize findings into actionable recommendations.

**See [references/action-recommendations.md](references/action-recommendations.md) for templates.**

Output format:
```
## Investigation Summary

**Metric**: [name]
**Breach**: [current] vs [expected] ([% deviation])
**Root Cause**: [one sentence]
**Impact**: [severity: low/medium/high/critical]

## Recommendations

1. [Immediate action]
2. [Short-term fix]
3. [Long-term prevention]

## Evidence

- [Query results supporting findings]
- [Timeline of events]
```

## Platform Context

### Key Tables
| Table | Metric Source | Typical Checks |
|-------|--------------|----------------|
| `activity_log` | All engagement metrics | Volume, frequency, type distribution |
| `nx_users` | User counts, status | Active/inactive ratio, new registrations |
| `journeys` | Learning progress | Completion rates, drop-off points |
| `lessons` | Content engagement | View counts, time-on-page |
| `coaching_sessions` | Session metrics | Frequency, duration, cancellation rate |
| `notifications` | Communication health | Delivery rates, open rates |

### MCP Tools Used
- `run_query(sql)` — Execute read-only SQL against MyNextory database
- `get_entity_context(entity)` — Get KG context for business entities
- `get_blast_radius(node)` — Find affected components
- `describe_table(name)` — Get table schema details

## Bead Integration

When investigation is triggered by a bead:
```bash
bd update <bead-id> --status=in_progress
# ... run investigation ...
bd close <bead-id> --reason="Investigation complete: [summary]"
```

Create follow-up beads for recommended actions:
```bash
bd create --title="[ACTION] Fix: [root cause]" --type=task --priority=<severity>
```
