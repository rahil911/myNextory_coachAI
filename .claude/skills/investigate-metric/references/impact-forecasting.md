# Impact Forecasting

Estimate the business impact of a metric breach on the MyNextory platform.

## Impact Dimensions

### 1. User Impact

```sql
-- Total affected users (customize WHERE clause per breach)
SELECT COUNT(DISTINCT causer_id) AS affected_users,
       (SELECT COUNT(*) FROM nx_users WHERE status = 'active') AS total_active,
       ROUND(100.0 * COUNT(DISTINCT causer_id) /
         (SELECT COUNT(*) FROM nx_users WHERE status = 'active'), 1) AS pct_affected
FROM activity_log
WHERE created_at > DATE_SUB(NOW(), INTERVAL 7 DAY);
```

**Severity scale**:
| % Users Affected | Severity | Action |
|-----------------|----------|--------|
| < 5% | Low | Monitor, fix in next sprint |
| 5-20% | Medium | Fix within 48 hours |
| 20-50% | High | Fix within 24 hours |
| > 50% | Critical | Immediate response |

### 2. Learning Impact

```sql
-- Journey progression impact
SELECT j.title AS journey,
       COUNT(DISTINCT j.user_id) AS enrolled,
       SUM(CASE WHEN j.status = 'completed' THEN 1 ELSE 0 END) AS completed,
       ROUND(100.0 * SUM(CASE WHEN j.status = 'completed' THEN 1 ELSE 0 END) /
         COUNT(*), 1) AS completion_rate
FROM journeys j
GROUP BY j.title
ORDER BY enrolled DESC;
```

### 3. Operational Impact

Questions to answer:
- Are coaches blocked from delivering sessions?
- Are admins unable to manage content?
- Is the notification system down (users can't receive reminders)?

```sql
-- Coaching session health
SELECT DATE(scheduled_at) AS day,
       COUNT(*) AS sessions,
       SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled
FROM coaching_sessions
WHERE scheduled_at > DATE_SUB(NOW(), INTERVAL 14 DAY)
GROUP BY day ORDER BY day;
```

## Projection Formula

For trending metrics (not sudden breaks):

```
current_rate = metric_value / time_window
projected_impact = current_rate * projection_period

Example:
  - Daily active users dropping 5% per week
  - Current: 1000 DAU
  - 4-week projection: 1000 * (0.95^4) = 815 DAU
  - Impact: 185 fewer daily active users
```

## Output Template

```markdown
## Impact Assessment

**Metric**: [name]
**Current**: [value] (expected: [threshold])
**Deviation**: [amount] ([%])

### Affected Scope
- Users: [N] ([%] of active base)
- Organizations: [N] ([%] of clients)
- Features: [list affected features]

### Severity: [LOW / MEDIUM / HIGH / CRITICAL]

### Projection (if not fixed)
- 1 week: [projected value]
- 1 month: [projected value]
- Trend: [improving / stable / worsening]
```
