# Causal Analysis — Graph Traversal Patterns

How to walk the MyNextory causal graph to find root causes of metric breaches.

## Entity Relationship Map

```
clients (organizations)
  └── nx_users (members)
        ├── journeys (learning paths)
        │     └── chapters
        │           └── lessons
        │                 └── lesson_slides
        ├── coaching_sessions
        │     └── session_notes
        ├── activity_log (audit trail)
        ├── notifications
        └── personal_access_tokens
```

## Traversal Strategy

### Upstream Walk (Effect → Cause)

Start from the affected metric and walk upstream:

1. **Metric layer**: Which table/column shows the anomaly?
2. **Direct inputs**: What writes to this table? (Check `activity_log` subject_type)
3. **User layer**: Is it user-specific or system-wide?
4. **Organization layer**: Is it client-specific?
5. **Infrastructure layer**: Is it a platform issue?

### Example: Lesson Completion Rate Dropped

```
lesson_slides (completion status)
  ↑ written by: lesson progression logic
    ↑ triggered by: user interaction
      ↑ depends on: lessons (content availability)
        ↑ depends on: chapters (chapter unlock logic)
          ↑ depends on: journeys (journey assignment)
            ↑ depends on: nx_users (active user count)
              ↑ depends on: clients (organization status)
```

### Queries for Each Layer

```sql
-- Layer 1: Identify which specific metric changed
-- (Customize per metric type)

-- Layer 2: Check activity_log for the affected entity type
SELECT subject_type, event, COUNT(*) AS cnt
FROM activity_log
WHERE created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
  AND subject_type LIKE '%Lesson%'
GROUP BY subject_type, event
ORDER BY cnt DESC;

-- Layer 3: Is it user-segment specific?
SELECT u.status, COUNT(DISTINCT al.causer_id) AS users, COUNT(*) AS actions
FROM activity_log al
JOIN nx_users u ON al.causer_id = u.id
WHERE al.created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY u.status;

-- Layer 4: Is it client-specific?
SELECT c.name AS client, COUNT(*) AS activity
FROM activity_log al
JOIN nx_users u ON al.causer_id = u.id
JOIN clients c ON u.client_id = c.id
WHERE al.created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY c.name
ORDER BY activity DESC;
```

## Using Ownership Graph

```bash
# Find which agent owns the affected table
get_file_owner "path/to/model"

# Get blast radius from the affected concept
get_blast_radius "Lesson"

# Trace dependency path
get_dependency_path "content-agent" "identity-agent"
```

## Common Root Cause Patterns

| Pattern | Symptoms | Check |
|---------|----------|-------|
| User churn | Gradual decline across all metrics | `nx_users` status distribution over time |
| Content gap | Drop in specific journey metrics | Lessons with 0 slides or missing content |
| Coach inactivity | Session metrics drop | `coaching_sessions` by coach over time |
| Deployment break | Sudden cliff in all metrics | `activity_log` hourly pattern, look for gap |
| Data pipeline stall | Metrics freeze at a value | `MAX(created_at)` across key tables |
