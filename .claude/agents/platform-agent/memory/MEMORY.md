# Platform Agent Memory

## My Ownership
(Will be populated as the agent starts working)

## Key Decisions
(Will be populated as the agent makes choices)

## Schema Knowledge
Key tables in my domain:
- activity_log: Polymorphic audit trail (57210 rows, 77% of all data, 30 log types)
- documents: General document uploads and management
- jobs: Laravel queue/job infrastructure for async processing
- client_coach_mappings: Client-coach M2M relationships
- departments: Organizational units within client companies

Activity log uses Laravel Spatie polymorphic design (subject_type/subject_id, causer_type/causer_id).

## Upstream Dependencies
- identity-agent: nx_users referenced via causer_id in activity_log

## Dependents to Notify on Changes
- None (leaf node in dependency graph)

## Recent Changes
(Will be populated as the agent completes tasks)
