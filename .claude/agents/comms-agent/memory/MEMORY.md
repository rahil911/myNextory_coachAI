# Comms Agent Memory

## My Ownership
(Will be populated as the agent starts working)

## Key Decisions
(Will be populated as the agent makes choices)

## Schema Knowledge
Key tables in my domain:
- sms_details: SMS message records (1323 rows)
- sms_schedules: Scheduled SMS delivery
- dynamic_sms_details: Dynamic SMS content tied to chapters/lessons
- notification_histories: Multi-stakeholder notification delivery
- mail_communication_details: Email system with threaded conversations (self-referencing)
- mail_transfers: Email transfer tracking
- chatbot_sessions: AI chatbot sessions
- chatbot_histories: Chatbot Q&A history with timing
- chatbot_documents: Chatbot knowledge base
- activity_log: Polymorphic activity log (57210 rows, 77% of all data)

## Upstream Dependencies
- identity-agent: nx_users/clients/coaches referenced for message recipients
- content-agent: chapters/lessons referenced for SMS scheduling and dynamic content

## Dependents to Notify on Changes
- None (leaf node in dependency graph)

## Recent Changes
(Will be populated as the agent completes tasks)
