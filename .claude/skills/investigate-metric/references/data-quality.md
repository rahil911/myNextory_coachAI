# Data Quality Validation Procedures

Detailed procedures for validating MyNextory data quality before root cause analysis.

## 1. Freshness Check

Data should be current within its expected SLA:

| Source | Expected Freshness | Query |
|--------|-------------------|-------|
| `activity_log` | < 1 hour | `SELECT MAX(created_at) FROM activity_log` |
| `nx_users` | < 4 hours | `SELECT MAX(updated_at) FROM nx_users` |
| `journeys` | < 24 hours | `SELECT MAX(updated_at) FROM journeys` |
| `notifications` | < 1 hour | `SELECT MAX(created_at) FROM notifications` |

**If stale**: Check if the application is writing correctly. Look for deployment events or database issues.

## 2. Completeness Check

Compare row counts across time windows to detect gaps:

```sql
-- Daily activity volume (should be consistent on weekdays)
SELECT DATE(created_at) AS day,
       COUNT(*) AS total,
       COUNT(DISTINCT causer_id) AS unique_users
FROM activity_log
WHERE created_at > DATE_SUB(NOW(), INTERVAL 14 DAY)
GROUP BY day
ORDER BY day;

-- Hourly pattern (detect gaps within a day)
SELECT DATE(created_at) AS day,
       HOUR(created_at) AS hr,
       COUNT(*) AS cnt
FROM activity_log
WHERE created_at > DATE_SUB(NOW(), INTERVAL 2 DAY)
GROUP BY day, hr
ORDER BY day, hr;
```

**Red flags**:
- Day with 0 rows (total outage)
- Day with < 50% of average (partial outage)
- Missing hours in a pattern that's normally continuous

## 3. Schema Integrity

Check for unexpected schema changes:

```sql
-- Check if table structure matches expectations
DESCRIBE activity_log;
DESCRIBE nx_users;

-- Check for NULL columns that shouldn't be NULL
SELECT COUNT(*) AS total,
       SUM(CASE WHEN causer_id IS NULL THEN 1 ELSE 0 END) AS null_causer,
       SUM(CASE WHEN subject_type IS NULL THEN 1 ELSE 0 END) AS null_subject
FROM activity_log
WHERE created_at > DATE_SUB(NOW(), INTERVAL 1 DAY);
```

## 4. Referential Integrity

Verify foreign key relationships are intact:

```sql
-- Orphaned activity_log entries (causer references non-existent user)
SELECT COUNT(*) AS orphaned
FROM activity_log al
LEFT JOIN nx_users u ON al.causer_id = u.id
WHERE al.causer_id IS NOT NULL AND u.id IS NULL
  AND al.created_at > DATE_SUB(NOW(), INTERVAL 7 DAY);

-- Journey references to non-existent users
SELECT COUNT(*) AS orphaned
FROM journeys j
LEFT JOIN nx_users u ON j.user_id = u.id
WHERE u.id IS NULL;
```

## 5. Distribution Check

Verify data distributions haven't shifted unexpectedly:

```sql
-- Activity type distribution (should be stable)
SELECT log_name, COUNT(*) AS cnt,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct
FROM activity_log
WHERE created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY log_name
ORDER BY cnt DESC;
```

## Decision Matrix

| Check | Pass | Investigate | Halt |
|-------|------|-------------|------|
| Freshness | Within SLA | 1-2x SLA | > 2x SLA |
| Completeness | > 95% of average | 80-95% | < 80% |
| Schema | No changes | New nullable columns | Dropped/renamed columns |
| Referential | < 0.1% orphans | 0.1-1% | > 1% |
| Distribution | < 10% shift | 10-25% shift | > 25% shift |
