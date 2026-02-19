-- Performance indexes for Tory tables (baap-qkk.12)
-- Covering indexes for the most common query patterns

-- tory_content_tags: covering index for confidence-filter query
-- Query: WHERE deleted_at IS NULL AND review_status != 'rejected' AND (confidence >= 70 OR review_status = 'approved')
ALTER TABLE tory_content_tags
  ADD INDEX idx_tory_ct_eligible (deleted_at, review_status, confidence, nx_lesson_id);

-- tory_recommendations: covering index for active recs lookup (most frequent query)
-- Query: WHERE nx_user_id = ? AND deleted_at IS NULL ORDER BY sequence ASC
ALTER TABLE tory_recommendations
  ADD INDEX idx_tory_rec_active (nx_user_id, deleted_at, sequence);

-- tory_recommendations: covering index for batch lookups
-- Query: WHERE batch_id = ? AND deleted_at IS NULL ORDER BY sequence ASC
ALTER TABLE tory_recommendations
  ADD INDEX idx_tory_rec_batch_active (batch_id, deleted_at, sequence);

-- tory_path_events: covering index for user event history (ordered by time)
-- Query: WHERE nx_user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC
ALTER TABLE tory_path_events
  ADD INDEX idx_tory_pe_user_created (nx_user_id, deleted_at, created_at);

-- tory_reassessments: index for last-completed lookup
-- Query: WHERE nx_user_id = ? AND status = 'completed' AND deleted_at IS NULL ORDER BY completed_at DESC
ALTER TABLE tory_reassessments
  ADD INDEX idx_tory_reassess_completed (nx_user_id, status, deleted_at, completed_at);

-- tory_notification_log: covering index for user+type+status check
-- Query: WHERE nx_user_id = ? AND notification_type = ? AND status = 'sent'
ALTER TABLE tory_notification_log
  ADD INDEX idx_tory_notif_user_type_status (nx_user_id, notification_type, status, sent_at);

-- tory_learner_profiles: covering index for latest-profile lookup
-- Query: WHERE nx_user_id = ? AND deleted_at IS NULL ORDER BY version DESC LIMIT 1
ALTER TABLE tory_learner_profiles
  ADD INDEX idx_tory_profile_active (nx_user_id, deleted_at, version);

-- tory_progress_snapshots: index for aggregate dashboard query by date
-- Query: WHERE client_id = ? AND snapshot_date = CURDATE()
ALTER TABLE tory_progress_snapshots
  ADD INDEX idx_tory_snap_aggregate (client_id, snapshot_date, completion_pct, engagement_score);
