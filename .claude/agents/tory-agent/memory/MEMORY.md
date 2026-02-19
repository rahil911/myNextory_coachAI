# Tory Agent Memory

## Session Log

### 2026-02-18: Initial Setup
- Created 8 Tory database tables in baap MariaDB
- Tables: tory_pedagogy_config, tory_content_tags, tory_learner_profiles, tory_roadmaps, tory_roadmap_items, tory_reassessments, tory_coach_overrides, tory_progress_snapshots
- Total: 132 columns across 8 tables
- Migration: `.claude/db/migrations/001_create_tory_tables.sql`
- Updated discovery files (schema.json, relationships.json, profile.json) -- now 46 tables, 604 columns, 84 relationships
- Updated KG seeds (agents.csv, edges.csv, modules.csv, concepts.csv) -- now 50 nodes, 257 edges, 32 concepts
- Reserved word fix: `trigger` column renamed to `trigger_source` in tory_roadmaps

## Key Decisions
- Following existing baap DB conventions: int(11) PKs, longtext for JSON, no explicit FKs, InnoDB Dynamic
- Coach compatibility flag (traffic light) in V1 instead of full coach matching (V2)
- Pedagogy config is client-level, not learner-level
- Discovery phase: 3-5 exploratory lessons for cold-start learners before full roadmap

### 2026-02-19: Content Tagging Pipeline (baap-qkk.2)
- Built `tag_content.py` -- full L1-L3 content tagging pipeline
- L1: Extracts text from lesson_slides JSON (slide_title, content, questions, etc.)
- L2: Two-pass tagging (Claude API mode + keyword heuristic fallback)
- L3: Confidence gating (auto-approve >= 75, needs_review < 50, pending otherwise)
- Checkpoint resumption via tag_checkpoint.json
- **Results**: 79 lessons tagged total (25 existing + 54 new from heuristic mode)
- 8 lessons skipped (video-only, no parseable text content)
- 4 lesson_detail_ids unmapped (83, 120, 121, 122 -- no nx_lesson_id found)
- All 79 rows pass JSON_VALID validation
- Pipeline file: `.claude/mcp/tag_content.py`

## Data Architecture
- nx_lessons table is EMPTY (redacted from dump)
- lesson_detail_id -> nx_lesson_id mapping derived from backpacks + nx_user_ratings tables
- lesson_slides has actual content (450 rows, 73 distinct lesson_detail_ids)
- slide_content is JSON with fields: slide_title, content, short_description, questions, greetings, etc.
- Use `--xml` output format when querying multiline JSON content from MySQL

## Key Decisions
- Following existing baap DB conventions: int(11) PKs, longtext for JSON, no explicit FKs, InnoDB Dynamic
- Coach compatibility flag (traffic light) in V1 instead of full coach matching (V2)
- Pedagogy config is client-level, not learner-level
- Discovery phase: 3-5 exploratory lessons for cold-start learners before full roadmap
- Content tagging uses review_status in tory_content_tags (not separate tory_review_queue table)
- Heuristic tagging gets -15 confidence penalty (keyword-based is less reliable than Claude API)
- Two-pass system uses different keyword weights (0.6/0.4 vs 0.4/0.6) for diversity

## Known Issues
- 18 of original 38 tables are empty (content/coach data redacted from dump) -- production data needed before Month 1 end
- `trigger` is a MySQL reserved word -- used `trigger_source` instead
- 8 lessons with video-only content can't be tagged without transcripts
- 4 orphan lesson_detail_ids (83, 120, 121, 122) have no mapping in any table
