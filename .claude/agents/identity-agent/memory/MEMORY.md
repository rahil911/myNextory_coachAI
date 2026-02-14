# Identity Agent Memory

## My Ownership
(Will be populated as the agent starts working)

## Key Decisions
(Will be populated as the agent makes choices)

## Schema Knowledge
Key tables in my domain:
- nx_users: Core user table, hub with 20+ references
- clients: Client organizations
- coaches: Coach entities
- employees: Employees within clients
- nx_admin_users: Platform administrators
- nx_password_resets, client_password_resets, coach_password_resets: Auth tokens
- client_coach_mappings: Client-coach relationships
- departments: Organizational units within clients
- nx_user_onboardings: User onboarding state
- coach_profiles, coach_availabilities: Coach details

## Dependents to Notify on Changes
- content-agent, engagement-agent, meetings-agent, comms-agent, platform-agent

## Recent Changes
(Will be populated as the agent completes tasks)
