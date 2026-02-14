# Engagement Agent Memory

## My Ownership
(Will be populated as the agent starts working)

## Key Decisions
(Will be populated as the agent makes choices)

## Schema Knowledge
Key tables in my domain:
- nx_user_ratings: User ratings across all content levels (3657 rows)
- old_ratings: Legacy/historical rating data
- tasks: Tasks assigned within learning journeys (2829 rows)
- nx_journal_details: User journal entries for reflective learning
- backpacks: Saved/collected learning materials (5833 rows)

All tables reference nx_users (identity-agent) and journey/chapter/lesson tables (content-agent).

## Upstream Dependencies
- identity-agent: nx_users referenced via created_by
- content-agent: journey_details/chapter_details/lessons referenced via foreign keys

## Dependents to Notify on Changes
- None (leaf node in dependency graph)

## Recent Changes
(Will be populated as the agent completes tasks)
