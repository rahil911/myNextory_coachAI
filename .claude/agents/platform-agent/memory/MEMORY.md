# Platform Agent Memory

## My Ownership
- `.claude/command-center/backend/routes/tory_admin.py` — HR admin dashboard API
- `.claude/command-center/frontend/js/views/tory-admin.js` — HR dashboard frontend view
- `.claude/command-center/frontend/css/tory-admin.css` — HR dashboard styles

## Key Decisions
- departments table uses `department_title` column, NOT `name`
- tory_coach_flags can have multiple rows per user; always use MAX(id) subquery for dedup
- Phase determination: reassessments > 0 → "reassessed", has non-discovery lessons → "active", has discovery only → "discovery", else "profiled"
- Coach intervention rate = (locked + coach-sourced) / total recommendations

## Schema Knowledge
Key tables in my domain:
- activity_log: Polymorphic audit trail (57210 rows, 77% of all data, 30 log types)
- documents: General document uploads and management
- jobs: Laravel queue/job infrastructure for async processing
- client_coach_mappings: Client-coach M2M relationships
- departments: Organizational units within client companies (column: department_title)

Activity log uses Laravel Spatie polymorphic design (subject_type/subject_id, causer_type/causer_id).

Tory tables used by HR dashboard:
- tory_learner_profiles: 29 EPP dimensions, versioned, confidence 0-100
- tory_recommendations: Scored lessons per user, sequence ordered, batch_id groups
- tory_content_tags: Claude-analyzed trait tags, confidence gated, multi-pass
- tory_coach_flags: Coach-learner compatibility (green/yellow/red), multiple per user
- tory_path_events: Coach actions timeline (reorder/swap/lock)
- tory_reassessments: EPP retakes (mini/full), drift tracking
- tory_coach_overrides: Audit log of coach mutations

## Upstream Dependencies
- identity-agent: nx_users referenced via causer_id in activity_log

## Dependents to Notify on Changes
- None (leaf node in dependency graph)

## Recent Changes
- [baap-kfu] Created v_database_summary view
- [baap-qkk.9] Built HR/Admin dashboard: 4 API endpoints + frontend view with cohort table, individual drilldown, aggregate metrics, content gap heatmap, CSV export
