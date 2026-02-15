---
name: forecast-impact
description: |
  Forecast the business impact of a detected issue, proposed change, or metric trend on the
  MyNextory coaching platform. Use when you need to quantify how an issue affects users,
  learning outcomes, or operations — or to predict the blast radius of a proposed change
  before implementing it.

  Triggers: "forecast impact", "what's the impact", "how many users affected",
  "project the effect", "estimate damage", "blast radius of this change".
metadata:
  baap:
    requires:
      bins: [bd]
      config: [mcp.servers.db-tools, mcp.servers.ownership-graph]
---

# Forecast Impact

Quantify the business impact of issues and changes on the MyNextory platform.

## When to Use

- After identifying a root cause, estimate its impact
- Before making a change, predict what it will affect
- During incident response, prioritize by severity
- For sprint planning, assess the value of a fix

## Impact Dimensions

### 1. User Impact

```sql
-- Active user base (denominator for all user impact calculations)
SELECT COUNT(*) AS total_active FROM nx_users WHERE status = 'active';

-- Users affected by a specific entity
SELECT COUNT(DISTINCT user_id) AS affected
FROM journeys
WHERE <condition>;

-- User segmentation of impact
SELECT
  CASE
    WHEN j.status = 'completed' THEN 'completed'
    WHEN j.status = 'in_progress' THEN 'active'
    ELSE 'other'
  END AS segment,
  COUNT(DISTINCT j.user_id) AS users
FROM journeys j
WHERE <condition>
GROUP BY segment;
```

### 2. Learning Impact

```sql
-- Lessons affected
SELECT COUNT(*) AS affected_lessons
FROM lessons l
JOIN chapters c ON l.chapter_id = c.id
WHERE <condition>;

-- Learning progress at risk
SELECT COUNT(*) AS in_progress_journeys
FROM journeys
WHERE status = 'in_progress'
  AND <condition>;
```

### 3. Operational Impact

Questions to quantify:
- How many coaching sessions are affected?
- Are any admin workflows blocked?
- Is content creation/editing impacted?

```sql
-- Upcoming coaching sessions at risk
SELECT COUNT(*) AS at_risk
FROM coaching_sessions
WHERE scheduled_at > NOW()
  AND <condition>;
```

### 4. Change Blast Radius

For proposed changes, use the ownership graph:

```bash
# What's affected by changing this entity?
get_blast_radius "<entity_or_file>"

# Which agents need to update their code?
get_dependents "<agent-name>"
```

## Trend Projection

For metrics trending in a direction:

```sql
-- Weekly trend (calculate week-over-week change)
SELECT
  YEARWEEK(created_at) AS week,
  COUNT(*) AS volume,
  COUNT(*) - LAG(COUNT(*)) OVER (ORDER BY YEARWEEK(created_at)) AS delta
FROM activity_log
WHERE created_at > DATE_SUB(NOW(), INTERVAL 8 WEEK)
GROUP BY week
ORDER BY week;
```

**Projection formula**:
```
If trend is linear:
  projected_value = current_value + (weekly_delta * weeks_ahead)

If trend is exponential:
  weekly_rate = current_week / previous_week
  projected_value = current_value * (weekly_rate ^ weeks_ahead)
```

## Severity Classification

| Severity | User Impact | Learning Impact | Operational Impact |
|----------|-------------|-----------------|-------------------|
| **Critical** | > 50% users | Active journeys blocked | Coaches/admins locked out |
| **High** | 20-50% users | Content inaccessible | Partial workflow disruption |
| **Medium** | 5-20% users | Degraded experience | Workaround available |
| **Low** | < 5% users | Cosmetic/minor | No operational impact |

## Output Template

```markdown
## Impact Forecast

**Issue/Change**: [description]
**Assessment Date**: [date]

### Scope
- Users affected: [N] ([%] of active base)
- Clients affected: [N] ([%] of organizations)
- Content affected: [N] lessons / [N] journeys

### Severity: [CRITICAL / HIGH / MEDIUM / LOW]

### Projection (if unresolved)
| Timeframe | Metric | Projected Value |
|-----------|--------|----------------|
| 1 week | [metric] | [value] |
| 1 month | [metric] | [value] |

### Blast Radius (for proposed changes)
- Files: [N] across [N] agents
- Agents: [list]
- Dependencies: [list]

### Recommendation
- Priority: P[0-3]
- Action: [immediate/short-term/long-term]
```
