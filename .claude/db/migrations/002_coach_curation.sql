-- =============================================================================
-- TORY: Coach Curation API — Schema Migration
-- Migration 002: Create tory_path_events, alter tory_recommendations
-- Bead: baap-qkk.5
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. tory_path_events
--    Audit log for all coach mutations on a learner's path.
--    Every reorder, swap, lock action creates an event with reason text.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tory_path_events (
    id              int(11)       NOT NULL AUTO_INCREMENT,
    nx_user_id      bigint(20)    NOT NULL COMMENT 'FK -> nx_users.id (learner)',
    coach_id        bigint(20)    NOT NULL COMMENT 'FK -> coaches.id (coach who acted)',
    event_type      varchar(20)   NOT NULL COMMENT 'reordered | swapped | locked',
    reason          longtext      NULL COMMENT 'Coach reason text for the mutation',
    details         longtext      NULL COMMENT 'JSON: mutation-specific payload',
    recommendation_ids longtext   NULL COMMENT 'JSON: list of tory_recommendations.id affected',
    divergence_pct  int(11)       NULL COMMENT 'Divergence percentage at time of event',
    flagged_for_review int(11)    NOT NULL DEFAULT 0 COMMENT '1 = divergence >30%, flagged as coach insight',
    created_at      datetime      NULL,
    updated_at      datetime      NULL,
    deleted_at      datetime      NULL,
    PRIMARY KEY (id),
    KEY idx_tory_pe_user (nx_user_id),
    KEY idx_tory_pe_coach (coach_id),
    KEY idx_tory_pe_type (event_type),
    KEY idx_tory_pe_user_type (nx_user_id, event_type)
) ENGINE=InnoDB ROW_FORMAT=Dynamic;

-- ---------------------------------------------------------------------------
-- 2. Add locked_by_coach and source columns to tory_recommendations
--    locked_by_coach: 1 = locked, excluded from future re-ranking
--    source: 'tory' (algorithm) or 'coach' (manually placed/modified)
-- ---------------------------------------------------------------------------
ALTER TABLE tory_recommendations
    ADD COLUMN locked_by_coach int(11) NOT NULL DEFAULT 0 COMMENT '1 = locked by coach, survives re-ranking'
    AFTER is_discovery;

ALTER TABLE tory_recommendations
    ADD COLUMN source varchar(10) NOT NULL DEFAULT 'tory' COMMENT 'tory = algorithm | coach = manually modified'
    AFTER locked_by_coach;

-- Index for filtering locked items during re-ranking
ALTER TABLE tory_recommendations
    ADD KEY idx_tory_rec_locked (nx_user_id, locked_by_coach);
