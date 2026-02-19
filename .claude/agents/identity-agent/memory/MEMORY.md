# Identity Agent Memory

## My Ownership
- `.claude/mcp/tory_engine.py` — Tory MCP intelligence engine (profile interpret, scoring, roadmap)
- `.claude/command-center/backend/routes/tory.py` — Tory API routes (profile CRUD, feedback)
- `.claude/command-center/backend/services/tory_service.py` — Tory service layer (DB access)
- `.claude/db/migrations/001_create_tory_tables.sql` — Tory schema migration (9 tables)

## Key Decisions
- Narrative uses second person ("You show strong...") per bead spec, 3-5 sentences
- Top 3 strengths + 2 growth areas highlighted in narrative
- Motivation drivers cleaned (stripped periods, lowered case) for natural reading
- API routes added to existing command-center FastAPI app (not a separate service)
- tory_engine functions imported directly in route handler (same process, avoids MCP overhead)
- tory_feedback table stores feedback type, comment, and links to profile + version

## Schema Knowledge
Key tables in my domain:
- nx_users: Core user table, hub with 20+ references. IDs start at 174 (not 1!)
- nx_user_onboardings: User onboarding data, EPP in assesment_result JSON, Q&A in separate fields
- clients, coaches, employees, nx_admin_users, departments, etc.
- tory_learner_profiles: Profile with EPP summary, strengths, gaps, narrative, confidence, version
- tory_feedback: Learner feedback (not_like_me, too_vague, etc.) linked to profile
- 7 other tory_* tables: pedagogy_config, content_tags, roadmaps, roadmap_items, reassessments, coach_overrides, progress_snapshots

## Patterns
- EPP scores parsed from `assesment_result` JSON: personality dims strip "EPP" prefix, job-fit dims get "_JobFit" suffix
- Q&A fields are JSON arrays stored as strings, need json.loads() on retrieval
- Unicode escaping in Q&A data: \u2019 appears as "u2019" in DB — pre-existing data issue
- Confidence: base 50 + 10 for Q&A + 15 for full EPP = 75 max
- Learning style heuristic: Extroversion>70→active, Openness>70→reflective, Conscientiousness>70→theoretical, else blended

## Dependents to Notify on Changes
- content-agent, engagement-agent, meetings-agent, comms-agent, platform-agent

## Recent Changes
- **baap-qkk.3** (2026-02-19): Completed learner profile generation
  - Created tory_feedback table
  - Fixed MCP narrative to second person with 3-5 sentences
  - Built 3 API endpoints: POST /api/tory/profile, GET /api/tory/profile/{id}, POST /api/tory/feedback
  - Created services/tory_service.py and routes/tory.py
  - Registered in main.py with service singleton pattern
  - All 7 e2e tests pass
