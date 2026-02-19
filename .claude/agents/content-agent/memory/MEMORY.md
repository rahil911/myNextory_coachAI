# Content Agent Memory

## My Ownership
- `.claude/mcp/tory_engine.py` — Tory MCP server (tory_engine tools)
- `.claude/db/migrations/001_create_tory_tables.sql` — Tory schema migration (original 10 tables)
- `.claude/db/migrations/002_coach_curation.sql` — Coach curation schema (tory_path_events + recommendation columns)
- `test_generate_path.py` — E2E test for generate_path
- `test_coach_curation.py` — E2E test for coach curation API

## Key Decisions
- `signal` is a reserved word in MariaDB — renamed to `compat_signal` in tory_coach_flags
- `message` renamed to `compat_message` for consistency
- Confidence threshold: >= 70 integer (not 0.7 float) since DB stores 0-100
- Default 20 recommendations (bead spec), not 30 (original code default)
- Rationale is template-based (no Claude API call) — cost-optimized per bead requirement
- `tory_recommendations` is separate from `tory_roadmap_items`: recs = raw scoring output, roadmap_items = curated path

## Schema Knowledge
Key tables in my domain:
- nx_journey_details: Top-level learning paths, hub with 10 refs
- nx_chapter_details: Mid-level units within journeys, hub with 13 refs
- nx_lessons: Atomic learning units, hub with 13 refs
- lesson_details: Detailed lesson content
- lesson_slides: Slides within lessons
- video_libraries: Video content library
- backpacks: User-collected learning materials (5833 rows)
- documents: Uploaded documents
- chatbot_documents: Knowledge base documents
- **tory_recommendations**: Raw scored recommendations per learner (has locked_by_coach, source columns)
- **tory_coach_flags**: Coach compatibility traffic light signals
- **tory_path_events**: Audit log for coach mutations (reordered/swapped/locked with reason)

Content hierarchy: Journey > Chapter > Lesson > Slide/Video

## Upstream Dependencies
- identity-agent: nx_users referenced via created_by in journey/chapter/lesson tables

## Dependents to Notify on Changes
- engagement-agent, comms-agent

## Key Patterns
- Locked recommendations (locked_by_coach=1) must be excluded from reorder and swap operations
- Divergence detection: % of coach-modified items vs total; >30% flags as "coach insight" (not blocked)
- All coach mutations create tory_path_events with reason text for audit trail
- `source` column on tory_recommendations: 'tory' = algorithm, 'coach' = manually modified

## Recent Changes
- baap-qkk.5: Built coach curation API for path management
  - Created tory_path_events table (11 tory tables now)
  - Added locked_by_coach and source columns to tory_recommendations
  - 4 new MCP tools: tory_coach_reorder, tory_coach_swap, tory_coach_lock, tory_get_path
  - Divergence detection >30% flagged as coach insight, not blocked
  - All 6 acceptance criteria verified via 50-test E2E suite
- baap-qkk.4: Implemented similarity scoring + path generation in tory_engine.py
  - Created tory_recommendations table (10 tory tables total now, was 8)
  - Created tory_coach_flags table
  - Added confidence filtering (>=70 or approved) to content tag queries
  - Added journey diversity rule (max 3 consecutive from same journey)
  - Added gap/strength interleaving for mixed learning
  - Added EPP-dimension-aware rationale generation with discovery framing
  - Added tory_generate_path tool as main entry point
  - All 6 acceptance criteria verified via E2E test
  - Seeded 25 test lessons + content tags for testing
