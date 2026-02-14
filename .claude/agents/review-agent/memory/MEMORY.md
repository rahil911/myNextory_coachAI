# Review Agent Memory

## My Ownership
(Will be populated as the agent starts working)
Review agent typically does not own application files.

## Key Decisions
(Will be populated as the agent makes choices)

## Review History
(Will track past reviews: bead-id, agent reviewed, verdict, key findings)

## Common Issues Found
(Will track recurring patterns to watch for)

## Schema Knowledge
Key tables to be aware of during reviews:
- nx_users: Hub table, 20+ references -- changes have massive blast radius
- activity_log: Largest table (57210 rows) -- performance-sensitive
- nx_chapter_details: Hub with 13 refs -- content hierarchy core
- nx_lessons: Hub with 13 refs -- content hierarchy core
- nx_journey_details: Hub with 10 refs -- top-level learning paths

## Security Patterns
(Will be populated with security patterns observed in the codebase)

## Recent Changes
(Will be populated as the agent completes reviews)
