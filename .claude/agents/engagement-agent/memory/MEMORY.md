# Engagement Agent Memory

## Checkpoint 2026-02-19
- **Bead**: baap-qkk.6
- **Status**: completed
- **Completed**:
  - Reassessment scheduler + adaptive re-ranking worker (1062 lines in tory_engine.py)
  - Criteria Corp API client with 3-retry exponential backoff
  - Mini-assessment processor (weighted 70/30 blend)
  - Passive signal aggregator (backpack/ratings/tasks -> trait adjustment)
  - Profile drift detection engine
  - Adaptive re-ranking preserving coach-locked recommendations
  - Path event recording (type=reassessed with human-readable reason)
  - 4 MCP tools: tory_schedule_quarterly_epp, tory_mini_assessment, tory_check_passive_signals, tory_reassessment_status
- **All 6 acceptance criteria verified and passing**

## My Ownership
- `.claude/mcp/tory_engine.py` — Tory Engine MCP server (reassessment + re-ranking code, lines ~460-2970)

## Key Decisions
- Mini-assessment uses 70% existing / 30% new weighted blend (not full replacement)
- Passive signals use 10% weight boost (weak signal, light touch)
- Drift threshold: 15% average delta triggers path re-ranking
- Backpack signal threshold: 10 new interactions triggers reassessment check
- Coach-locked items interleaved at original positions in re-ranked list
- Criteria Corp API fallback: merge mini-assessment scores into old scores (partial overlay)

## Schema Knowledge
Key tables in my domain:
- tory_reassessments: Reassessment records (quarterly_epp, mini, backpack_derived)
- tory_path_events: Path change audit trail (type=reassessed)
- tory_recommendations: Personalized learning recs with locked_by_coach flag
- tory_learner_profiles: Versioned learner profiles (epp_summary, strengths, gaps)
- nx_user_ratings: User ratings (3657 rows)
- tasks: Tasks assigned within learning journeys (2829 rows)
- backpacks: Saved/collected learning materials (5833 rows)

All tables reference nx_users (identity-agent) and journey/chapter/lesson tables (content-agent).

## Upstream Dependencies
- identity-agent: nx_users referenced via created_by
- content-agent: journey_details/chapter_details/lessons referenced via foreign keys

## Dependents to Notify on Changes
- None (leaf node in dependency graph)

## Recent Changes
- baap-qkk.6: Built reassessment scheduler + adaptive re-ranking worker (2026-02-19)
