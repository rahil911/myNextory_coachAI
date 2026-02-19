# Comms Agent Memory

## Checkpoint 2026-02-19 02:40:00
- **Bead**: baap-qkk.7
- **Status**: completed
- **Completed**:
  - Created tory_notification_log and tory_notification_optouts tables (migration 007)
  - Built ToryNotificationService with 4 notification triggers
  - Implemented 24-hour batch window enforcement (batch-exempt: path_generated, reassessment_reminder)
  - Implemented opt-out tracking per learner per notification type (including 'all')
  - All 69 tests passing covering all 6 acceptance criteria
- **Files created**:
  - tory_notification_service.py — Main service with triggers, templates, delivery, batch window, opt-out
  - test_tory_notifications.py — 69 tests covering all 6 acceptance criteria
  - migrations/007_tory_notifications.sql — tory_notification_log + tory_notification_optouts tables

## My Ownership
- tory_notification_service.py — Tory notification service
- test_tory_notifications.py — Notification tests
- migrations/007_tory_notifications.sql — Schema migration

## Key Decisions
- Notification types: path_generated, reassessment_change, coach_change, reassessment_reminder
- Event type mapping: reassessed → reassessment_change; reordered/swapped/locked → coach_change
- Batch-exempt types: path_generated (first-time welcome), reassessment_reminder (time-sensitive)
- Delivery via existing infrastructure: sms_details (sms_type='tory_notification'), mail_communication_details (query_type='tory_notification')
- Contact info: email from nx_users, mobile/name from nx_user_onboardings
- Coach name: from coach_profiles table, falls back to "your coach"
- Multiline email bodies stored via escape_sql; mysql CLI tab-separated parsing truncates them (known limitation, tested via template builders instead)

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
- **tory_notification_log**: Tracks every Tory notification sent (batch window + audit)
- **tory_notification_optouts**: Per-learner per-type opt-out tracking

## Upstream Dependencies
- identity-agent: nx_users/clients/coaches referenced for message recipients
- content-agent: chapters/lessons referenced for SMS scheduling and dynamic content
- tory_path_events: event source for reassessment/coach change notifications
- tory_reassessments: source for reassessment reminder scheduling

## Dependents to Notify on Changes
- None (leaf node in dependency graph)

## Recent Changes
- baap-qkk.7: Implemented comms integration for Tory path notifications
