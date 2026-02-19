-- Migration 007: Tory notification log and opt-out tables
-- Bead: baap-qkk.7 — comms integration for path notifications

-- Notification log: tracks every Tory notification sent per learner.
-- Used for 24-hour batch window enforcement and audit trail.
CREATE TABLE IF NOT EXISTS tory_notification_log (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    nx_user_id      BIGINT       NOT NULL,
    notification_type VARCHAR(30) NOT NULL COMMENT 'path_generated|reassessment_change|coach_change|reassessment_reminder',
    channel         VARCHAR(10)  NOT NULL COMMENT 'sms|email',
    path_event_id   INT          NULL     COMMENT 'FK to tory_path_events.id (NULL for reminders)',
    subject         VARCHAR(255) NULL,
    body            LONGTEXT     NULL,
    reason          LONGTEXT     NULL     COMMENT 'Copied from tory_path_events.reason',
    status          VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT 'pending|sent|failed|batched|skipped',
    batched_until   DATETIME     NULL     COMMENT 'If status=batched, when it becomes eligible',
    sent_at         DATETIME     NULL,
    error_detail    VARCHAR(500) NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      DATETIME     NULL,

    INDEX idx_tory_notif_user       (nx_user_id),
    INDEX idx_tory_notif_type       (notification_type),
    INDEX idx_tory_notif_status     (status),
    INDEX idx_tory_notif_batch      (nx_user_id, status, batched_until),
    INDEX idx_tory_notif_user_sent  (nx_user_id, sent_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Opt-out tracking: per learner, per notification type.
-- When a row exists and opted_out=1, that type is suppressed for that learner.
CREATE TABLE IF NOT EXISTS tory_notification_optouts (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    nx_user_id        BIGINT       NOT NULL,
    notification_type VARCHAR(30)  NOT NULL COMMENT 'path_generated|reassessment_change|coach_change|reassessment_reminder|all',
    opted_out         TINYINT(1)   NOT NULL DEFAULT 1,
    opted_out_at      DATETIME     NULL,
    opted_in_at       DATETIME     NULL     COMMENT 'If user re-opts-in later',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at        DATETIME     NULL,

    UNIQUE INDEX idx_tory_optout_user_type (nx_user_id, notification_type),
    INDEX idx_tory_optout_user            (nx_user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
