---
name: trace-lineage
description: |
  Trace data lineage through the MyNextory database schema. Use when you need to understand
  where a piece of data comes from, how it flows between tables, or what downstream entities
  are affected by a change to a specific table or column.

  Triggers: "trace lineage", "where does this data come from", "data flow",
  "what tables feed into", "upstream dependencies", "downstream impact".
metadata:
  baap:
    requires:
      bins: [bd]
      config: [mcp.servers.db-tools, mcp.servers.ownership-graph]
---

# Trace Lineage

Trace data lineage through MyNextory's database schema to understand data flow,
dependencies, and impact of changes.

## When to Use

- Investigating where a metric's data originates
- Understanding what's affected when a table/column changes
- Mapping data flow for a feature or business process
- Pre-change impact assessment

## Core Entity Hierarchy

```
clients (organizations)
  └── nx_users (members)
        ├── journeys
        │     └── chapters
        │           └── lessons
        │                 └── lesson_slides
        ├── coaching_sessions
        │     └── session_notes
        ├── activity_log (audit trail — polymorphic)
        ├── notifications
        ├── personal_access_tokens
        └── media (uploads via Spatie)
```

## Lineage Tracing Procedure

### Step 1: Identify the Target

What table/column are you tracing? Get its schema:

```bash
describe_table "<table_name>"
```

### Step 2: Find Upstream Sources

What writes to this table? Check foreign keys and the activity log:

```sql
-- Find tables that reference this table via FK
SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_NAME = '<target_table>'
  AND TABLE_SCHEMA = 'baap';

-- Find tables this table references
SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_NAME = '<target_table>'
  AND REFERENCED_TABLE_NAME IS NOT NULL
  AND TABLE_SCHEMA = 'baap';
```

### Step 3: Find Downstream Consumers

What reads from this table? Use the ownership graph:

```bash
get_blast_radius "<table_name>"
get_entity_context "<EntityName>"
```

### Step 4: Map the Flow

Document the lineage as a directed graph:

```
[Source A] --writes--> [Target Table] --read by--> [Consumer X]
[Source B] --writes--> [Target Table] --read by--> [Consumer Y]
```

### Step 5: Verify with Activity Log

The `activity_log` table records all changes (Spatie audit trail):

```sql
-- What operations happen on this entity type?
SELECT event, COUNT(*) AS cnt
FROM activity_log
WHERE subject_type LIKE '%<ModelName>%'
  AND created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY event
ORDER BY cnt DESC;

-- Who modifies this entity?
SELECT causer_type, COUNT(DISTINCT causer_id) AS actors, COUNT(*) AS actions
FROM activity_log
WHERE subject_type LIKE '%<ModelName>%'
  AND created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY causer_type;
```

## Output Format

```markdown
## Lineage Report: [table_name]

### Upstream (data sources)
| Source Table | Relationship | Column |
|-------------|--------------|--------|
| [table] | FK: [column] | [referenced_column] |

### Downstream (consumers)
| Consumer | Relationship | Impact of Change |
|----------|--------------|-----------------|
| [table/agent] | [how it uses data] | [what breaks] |

### Data Flow Diagram
[Source] -> [Target] -> [Consumer]

### Ownership
- Table owner: [agent-name]
- Upstream owners: [agent-names]
- Downstream owners: [agent-names]
```

## Common Lineage Patterns

| Starting Point | Typical Path |
|---------------|--------------|
| `nx_users` | clients -> nx_users -> journeys/sessions/activity |
| `lessons` | journeys -> chapters -> lessons -> lesson_slides |
| `activity_log` | any entity -> activity_log (audit sink) |
| `notifications` | system events -> notifications -> user |
| `coaching_sessions` | nx_users (coach+coachee) -> sessions -> notes |
