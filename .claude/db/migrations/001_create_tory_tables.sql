-- =============================================================================
-- TORY: Personalized Learning Path Engine — Database Schema
-- Migration 001: Create all 8 Tory tables
-- =============================================================================
-- Convention: Follows existing baap schema patterns
--   - int(11) PKs with AUTO_INCREMENT
--   - bigint(20) for refs to nx_users.id, coaches.id
--   - longtext for JSON payloads (no native JSON type)
--   - varchar for enum-like fields
--   - datetime NULL for timestamps (created_at, updated_at, deleted_at)
--   - No explicit FK constraints (convention-based, matching existing 38 tables)
--   - InnoDB engine, Dynamic row format
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. tory_pedagogy_config
--    Client-company pedagogy preference (A/B/C + ratio)
--    Referenced by: tory_roadmaps (via client_id on nx_users)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_pedagogy_config (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    client_id       int(11)       NOT NULL COMMENT 'FK → clients.id',
    mode            varchar(20)   NOT NULL DEFAULT 'balanced' COMMENT 'gap_fill | strength_lead | balanced',
    gap_ratio       int(11)       NOT NULL DEFAULT 50 COMMENT 'Percentage 0-100 for gap-filling emphasis',
    strength_ratio  int(11)       NOT NULL DEFAULT 50 COMMENT 'Percentage 0-100 for strength-leading emphasis',
    configured_by   int(11)       NULL COMMENT 'FK → nx_users.id or admin who set this',
    configured_user_type varchar(20) NULL COMMENT 'admin | coach | system',
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_pedagogy_client (client_id)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- ---------------------------------------------------------------------------
-- 2. tory_content_tags
--    Claude-generated trait tags per lesson (multi-pass, confidence-gated)
--    Bootstrap layer — populated by content tagging pipeline
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_content_tags (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    nx_lesson_id    int(11)       NOT NULL COMMENT 'FK → nx_lessons.id',
    lesson_detail_id int(11)      NULL COMMENT 'FK → lesson_details.id (optional granularity)',
    trait_tags      longtext      NOT NULL COMMENT 'JSON: [{trait, relevance_score, direction}]',
    difficulty      int(11)       NULL COMMENT 'Difficulty level 1-5',
    learning_style  varchar(50)   NULL COMMENT 'visual | reflective | active | theoretical | blended',
    prerequisites   longtext      NULL COMMENT 'JSON: prerequisite trait thresholds',
    confidence      int(11)       NOT NULL DEFAULT 0 COMMENT 'Confidence score 0-100',
    review_status   varchar(20)   NOT NULL DEFAULT 'pending' COMMENT 'pending | approved | rejected | needs_review',
    pass1_tags      longtext      NULL COMMENT 'JSON: First pass Claude Opus output',
    pass2_tags      longtext      NULL COMMENT 'JSON: Second pass Claude Opus output (different prompt)',
    pass_agreement  int(11)       NULL COMMENT 'Agreement score 0-100 between pass1 and pass2',
    reviewed_by     int(11)       NULL COMMENT 'FK → nx_users.id (coach/admin who reviewed)',
    reviewed_at     datetime      NULL,
    review_notes    longtext      NULL COMMENT 'Coach/admin notes on tag corrections',
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_content_lesson (nx_lesson_id),
    KEY idx_tory_content_review (review_status),
    KEY idx_tory_content_confidence (confidence)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- ---------------------------------------------------------------------------
-- 3. tory_learner_profiles
--    Claude's interpreted personality summary per user
--    Intelligence layer — generated from EPP + Q&A
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_learner_profiles (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    nx_user_id      bigint(20)    NOT NULL COMMENT 'FK → nx_users.id',
    onboarding_id   int(11)       NULL COMMENT 'FK → nx_user_onboardings.id (source data)',
    epp_summary     longtext      NOT NULL COMMENT 'JSON: normalized 29-dimension EPP trait vector',
    motivation_cluster longtext   NOT NULL COMMENT 'JSON: motivation drivers derived from Q&A',
    strengths       longtext      NOT NULL COMMENT 'JSON: top traits with scores',
    gaps            longtext      NOT NULL COMMENT 'JSON: growth areas with scores and motivation alignment',
    learning_style  varchar(50)   NULL COMMENT 'Inferred learning style preference',
    profile_narrative longtext    NULL COMMENT 'Claude-generated human-readable profile summary (user-facing)',
    confidence      int(11)       NOT NULL DEFAULT 50 COMMENT 'Profile confidence 0-100 (grows with data)',
    version         int(11)       NOT NULL DEFAULT 1 COMMENT 'Profile version (increments on reassessment)',
    source          varchar(30)   NOT NULL DEFAULT 'epp_qa' COMMENT 'epp_qa | reassessment_mini | reassessment_full | discovery',
    feedback_flags  int(11)       NOT NULL DEFAULT 0 COMMENT 'Count of "doesnt sound like me" flags',
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_profile_user (nx_user_id),
    KEY idx_tory_profile_version (nx_user_id, version)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- ---------------------------------------------------------------------------
-- 4. tory_roadmaps
--    Active learning path per learner (versioned)
--    Intelligence layer — generated by Tory MCP Agent
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_roadmaps (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    nx_user_id      bigint(20)    NOT NULL COMMENT 'FK → nx_users.id',
    profile_id      int(11)       NOT NULL COMMENT 'FK → tory_learner_profiles.id (profile used to generate)',
    pedagogy_mode   varchar(20)   NOT NULL DEFAULT 'balanced' COMMENT 'gap_fill | strength_lead | balanced (snapshot from client config)',
    pedagogy_ratio  varchar(10)   NULL COMMENT 'e.g. 70/30 — snapshot of ratio used',
    version         int(11)       NOT NULL DEFAULT 1 COMMENT 'Roadmap version (increments on adaptation)',
    status          varchar(20)   NOT NULL DEFAULT 'discovery' COMMENT 'discovery | active | completed | paused | archived',
    total_lessons   int(11)       NOT NULL DEFAULT 0,
    completed_lessons int(11)     NOT NULL DEFAULT 0,
    completion_pct  int(11)       NOT NULL DEFAULT 0 COMMENT '0-100',
    generation_rationale longtext NULL COMMENT 'Claude-generated explanation of overall path strategy (user-facing)',
    trigger_source  varchar(30)   NOT NULL DEFAULT 'onboarding' COMMENT 'onboarding | discovery_complete | reassessment | coach_request | drift',
    is_current      int(11)       NOT NULL DEFAULT 1 COMMENT '1 = active roadmap, 0 = historical version',
    created_by      int(11)       NULL COMMENT 'FK → nx_users.id or system',
    created_user_type varchar(20) NULL COMMENT 'system | coach | admin',
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_roadmap_user (nx_user_id),
    KEY idx_tory_roadmap_current (nx_user_id, is_current),
    KEY idx_tory_roadmap_status (status)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- ---------------------------------------------------------------------------
-- 5. tory_roadmap_items
--    Individual lesson assignments within a roadmap
--    Intelligence layer — each item has rationale
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_roadmap_items (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    roadmap_id      int(11)       NOT NULL COMMENT 'FK → tory_roadmaps.id',
    nx_lesson_id    int(11)       NOT NULL COMMENT 'FK → nx_lessons.id',
    content_tag_id  int(11)       NULL COMMENT 'FK → tory_content_tags.id (tag used for matching)',
    sequence        int(11)       NOT NULL COMMENT 'Order in the roadmap (1-based)',
    status          varchar(20)   NOT NULL DEFAULT 'pending' COMMENT 'pending | active | completed | skipped | locked',
    is_critical     int(11)       NOT NULL DEFAULT 0 COMMENT '1 = cannot be removed by coach (guardrail)',
    is_discovery    int(11)       NOT NULL DEFAULT 0 COMMENT '1 = part of discovery phase (first 3-5)',
    match_score     int(11)       NULL COMMENT 'Cosine similarity score 0-100',
    match_rationale longtext      NULL COMMENT 'Claude-generated explanation: why this lesson for this learner (user-facing)',
    trait_targets   longtext      NULL COMMENT 'JSON: EPP traits this lesson targets [{trait, expected_impact}]',
    started_at      datetime      NULL,
    completed_at    datetime      NULL,
    learner_rating  int(11)       NULL COMMENT 'Learner rating of this lesson 1-5',
    original_sequence int(11)     NULL COMMENT 'Original position before coach reorder (for divergence tracking)',
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_item_roadmap (roadmap_id),
    KEY idx_tory_item_lesson (nx_lesson_id),
    KEY idx_tory_item_sequence (roadmap_id, sequence),
    KEY idx_tory_item_status (status)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- ---------------------------------------------------------------------------
-- 6. tory_reassessments
--    Periodic re-evaluation records (mini + full EPP)
--    Adaptive layer — tracks learner growth over time
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_reassessments (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    nx_user_id      bigint(20)    NOT NULL COMMENT 'FK → nx_users.id',
    profile_id      int(11)       NULL COMMENT 'FK → tory_learner_profiles.id (profile before reassessment)',
    type            varchar(20)   NOT NULL COMMENT 'mini | full_epp',
    trigger_reason  varchar(30)   NOT NULL COMMENT 'scheduled | progress_milestone | coach_initiated | drift_detected | learner_feedback',
    status          varchar(20)   NOT NULL DEFAULT 'pending' COMMENT 'pending | sent | in_progress | completed | expired | failed',
    assessment_data longtext      NULL COMMENT 'JSON: questions + answers (for mini) or full EPP scores (for full_epp)',
    previous_scores longtext      NULL COMMENT 'JSON: EPP/profile snapshot before this reassessment',
    new_scores      longtext      NULL COMMENT 'JSON: EPP/profile snapshot after this reassessment',
    result_delta    longtext      NULL COMMENT 'JSON: [{trait, old_score, new_score, change_pct}]',
    drift_detected  int(11)       NOT NULL DEFAULT 0 COMMENT '1 = significant profile drift triggered path adaptation',
    path_action     varchar(30)   NULL COMMENT 'none | minor_reorder | major_adaptation | full_regeneration',
    criteria_order_id longtext    NULL COMMENT 'Criteria Corp order ID (for full_epp type)',
    sent_at         datetime      NULL,
    completed_at    datetime      NULL,
    expires_at      datetime      NULL COMMENT 'Deadline for completion before expiry',
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_reassess_user (nx_user_id),
    KEY idx_tory_reassess_type (type),
    KEY idx_tory_reassess_status (status),
    KEY idx_tory_reassess_schedule (nx_user_id, type, status)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- ---------------------------------------------------------------------------
-- 7. tory_coach_overrides
--    When coaches curate the roadmap (reorder/swap/lock/unlock)
--    Tracks divergence between Tory recommendation and coach edits
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_coach_overrides (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    roadmap_id      int(11)       NOT NULL COMMENT 'FK → tory_roadmaps.id',
    roadmap_item_id int(11)       NULL COMMENT 'FK → tory_roadmap_items.id (item affected)',
    coach_id        bigint(20)    NOT NULL COMMENT 'FK → coaches.id',
    action          varchar(20)   NOT NULL COMMENT 'reorder | swap | lock | unlock',
    details         longtext      NULL COMMENT 'JSON: {from_sequence, to_sequence} or {swapped_with_item_id} etc.',
    reason          longtext      NULL COMMENT 'Coach explanation for the override',
    was_blocked     int(11)       NOT NULL DEFAULT 0 COMMENT '1 = action was blocked by guardrail (tried to remove critical lesson)',
    blocked_reason  longtext      NULL COMMENT 'System message if action was blocked',
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_override_roadmap (roadmap_id),
    KEY idx_tory_override_coach (coach_id),
    KEY idx_tory_override_action (action)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- ---------------------------------------------------------------------------
-- 8. tory_progress_snapshots
--    Aggregated data for HR dashboard (individual + team)
--    Generated periodically by background worker
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_progress_snapshots (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    nx_user_id      bigint(20)    NOT NULL COMMENT 'FK → nx_users.id',
    roadmap_id      int(11)       NULL COMMENT 'FK → tory_roadmaps.id (current roadmap at snapshot time)',
    snapshot_date   date          NOT NULL,
    completion_pct  int(11)       NOT NULL DEFAULT 0 COMMENT 'Roadmap completion 0-100',
    engagement_score int(11)      NULL COMMENT 'Engagement score 0-100 (derived from backpack frequency, ratings, task completion)',
    lessons_completed int(11)     NOT NULL DEFAULT 0,
    lessons_total   int(11)       NOT NULL DEFAULT 0,
    days_active     int(11)       NULL COMMENT 'Days with at least one interaction in this period',
    days_stalled    int(11)       NULL COMMENT 'Consecutive days with no activity',
    path_changes    int(11)       NOT NULL DEFAULT 0 COMMENT 'Number of roadmap adaptations to date',
    coach_overrides int(11)       NOT NULL DEFAULT 0 COMMENT 'Number of coach interventions to date',
    divergence_score int(11)      NULL COMMENT 'How much coach overrides diverge from Tory recs 0-100',
    tory_accuracy   int(11)       NULL COMMENT 'How well Tory predictions matched outcomes 0-100',
    reassessments_completed int(11) NOT NULL DEFAULT 0 COMMENT 'Total reassessments completed to date',
    profile_confidence int(11)    NULL COMMENT 'Current profile confidence at snapshot time 0-100',
    client_id       int(11)       NULL COMMENT 'FK → clients.id (denormalized for dashboard queries)',
    department_id   int(11)       NULL COMMENT 'FK → departments.id (denormalized for team aggregates)',
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_snap_user (nx_user_id),
    KEY idx_tory_snap_date (snapshot_date),
    KEY idx_tory_snap_client (client_id, snapshot_date),
    KEY idx_tory_snap_dept (department_id, snapshot_date),
    KEY idx_tory_snap_user_date (nx_user_id, snapshot_date)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- ---------------------------------------------------------------------------
-- 9. tory_recommendations
--    Raw scored recommendations per learner (output of similarity engine)
--    Written by tory_generate_path, consumed by roadmap generation
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_recommendations (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    nx_user_id      bigint(20)    NOT NULL COMMENT 'FK → nx_users.id',
    profile_id      int(11)       NOT NULL COMMENT 'FK → tory_learner_profiles.id (profile used for scoring)',
    nx_lesson_id    int(11)       NOT NULL COMMENT 'FK → nx_lessons.id',
    content_tag_id  int(11)       NULL COMMENT 'FK → tory_content_tags.id (tag used for matching)',
    nx_journey_detail_id int(11)  NULL COMMENT 'FK → nx_journey_details.id (denormalized for diversity rules)',
    match_score     decimal(8,4)  NOT NULL DEFAULT 0 COMMENT 'Similarity score 0-100',
    gap_contribution decimal(8,4) NULL COMMENT 'Gap-fill score contribution',
    strength_contribution decimal(8,4) NULL COMMENT 'Strength-lead score contribution',
    adjusted_score  decimal(8,4)  NULL COMMENT 'Score after diversity/diminishing returns adjustments',
    sequence        int(11)       NOT NULL DEFAULT 0 COMMENT 'Rank order (1 = best match)',
    match_rationale longtext      NULL COMMENT 'Human-readable explanation referencing EPP dimensions',
    matching_traits longtext      NULL COMMENT 'JSON: [{trait, type, direction}] traits this lesson targets',
    is_discovery    int(11)       NOT NULL DEFAULT 0 COMMENT '1 = part of discovery phase (first 3-5)',
    pedagogy_mode   varchar(20)   NULL COMMENT 'Pedagogy mode used for scoring',
    pedagogy_ratio  varchar(10)   NULL COMMENT 'Gap/strength ratio used',
    confidence      int(11)       NULL COMMENT 'Content tag confidence at time of scoring',
    batch_id        varchar(50)   NULL COMMENT 'Batch identifier for this scoring run',
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_rec_user (nx_user_id),
    KEY idx_tory_rec_lesson (nx_lesson_id),
    KEY idx_tory_rec_score (nx_user_id, match_score),
    KEY idx_tory_rec_batch (batch_id),
    KEY idx_tory_rec_sequence (nx_user_id, sequence)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- ---------------------------------------------------------------------------
-- 10. tory_coach_flags
--     Coach-learner compatibility flags (traffic light signals)
--     Computed from EPP heuristics when coach is assigned
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_coach_flags (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    nx_user_id      bigint(20)    NOT NULL COMMENT 'FK → nx_users.id (learner)',
    coach_id        bigint(20)    NOT NULL COMMENT 'FK → coaches.id',
    profile_id      int(11)       NULL COMMENT 'FK → tory_learner_profiles.id (profile used)',
    compat_signal   varchar(10)   NOT NULL DEFAULT 'green' COMMENT 'green | yellow | red',
    compat_message  varchar(255)  NULL COMMENT 'Summary message for the signal',
    warnings        longtext      NULL COMMENT 'JSON: list of warning strings',
    learner_low_traits longtext   NULL COMMENT 'JSON: traits below threshold',
    learner_high_traits longtext  NULL COMMENT 'JSON: traits above threshold',
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_flag_user (nx_user_id),
    KEY idx_tory_flag_coach (coach_id),
    KEY idx_tory_flag_signal (compat_signal),
    KEY idx_tory_flag_user_coach (nx_user_id, coach_id)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- ---------------------------------------------------------------------------
-- 11. tory_feedback
--    Learner feedback on their profile ('This doesn't sound like me')
--    Tracks profile accuracy signals for reassessment triggering
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_feedback (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    nx_user_id      bigint(20)    NOT NULL COMMENT 'FK → nx_users.id',
    profile_id      int(11)       NULL COMMENT 'FK → tory_learner_profiles.id',
    type            varchar(30)   NOT NULL COMMENT 'not_like_me | too_vague | incorrect_strength | other',
    comment         longtext      NULL COMMENT 'Optional learner comment',
    profile_version int(11)       NULL COMMENT 'Version of profile when feedback was given',
    resolved        int(11)       NOT NULL DEFAULT 0 COMMENT '1 = feedback addressed in subsequent profile version',
    resolved_at     datetime      NULL,
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_feedback_user (nx_user_id),
    KEY idx_tory_feedback_profile (profile_id),
    KEY idx_tory_feedback_type (type)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- =============================================================================
-- VERIFICATION
-- =============================================================================
-- After running, verify with:
-- SELECT TABLE_NAME, TABLE_ROWS, ENGINE, ROW_FORMAT
-- FROM information_schema.tables
-- WHERE table_schema = 'baap' AND table_name LIKE 'tory_%'
-- ORDER BY TABLE_NAME;
-- =============================================================================
