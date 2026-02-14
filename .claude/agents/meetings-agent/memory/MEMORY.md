# Meetings Agent Memory

## My Ownership
(Will be populated as the agent starts working)

## Key Decisions
(Will be populated as the agent makes choices)

## Schema Knowledge
Key tables in my domain:
- meetings: Coaching sessions between coaches and learners
- meeting_attendees: Participant tracking with roles
- coach_availabilities: Coach time slot availability
- coach_profiles: Extended coach information

Meetings reference nx_users (hosting_by), meeting_attendees reference participant_id (users/coaches).

## Upstream Dependencies
- identity-agent: nx_users, coaches referenced via hosting_by, participant_id, coach_id

## Dependents to Notify on Changes
- None (leaf node in dependency graph)

## Recent Changes
(Will be populated as the agent completes tasks)
