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

## Known Issues
- 18 of original 38 tables are empty (content/coach data redacted from dump) -- production data needed before Month 1 end
- `trigger` is a MySQL reserved word -- used `trigger_source` instead
