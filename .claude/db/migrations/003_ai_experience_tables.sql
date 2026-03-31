-- Migration 003: AI Experience Tables
-- Bead: baap-d49
-- Date: 2026-02-20
-- Description: Expand tory_content_tags with 12 AI processing columns,
--              create tory_rag_chunks for RAG chunking, and
--              create tory_ai_sessions for AI session tracking.

-- ============================================================
-- 1. Expand tory_content_tags (12 new columns)
-- ============================================================
-- processed_at enables INCREMENTAL re-runs — Content Processor
-- skips lessons where processed_at > last slide modification.

ALTER TABLE tory_content_tags
  ADD COLUMN summary TEXT,
  ADD COLUMN learning_objectives LONGTEXT,
  ADD COLUMN key_concepts LONGTEXT,
  ADD COLUMN emotional_tone VARCHAR(50),
  ADD COLUMN target_seniority VARCHAR(20),
  ADD COLUMN estimated_minutes INT(11),
  ADD COLUMN coaching_prompts LONGTEXT,
  ADD COLUMN content_quality LONGTEXT,
  ADD COLUMN pair_recommendations LONGTEXT,
  ADD COLUMN slide_analysis LONGTEXT,
  ADD COLUMN rag_chunk_ids LONGTEXT,
  ADD COLUMN processed_at DATETIME DEFAULT NULL;

-- ============================================================
-- 2. Create tory_rag_chunks
-- ============================================================
CREATE TABLE IF NOT EXISTS tory_rag_chunks (
  id INT(11) NOT NULL AUTO_INCREMENT,
  lesson_detail_id INT(11) NOT NULL,
  chunk_index INT(11) NOT NULL,
  chunk_text TEXT NOT NULL,
  chunk_type VARCHAR(50),
  topic VARCHAR(200),
  slide_ids LONGTEXT,
  faiss_doc_id VARCHAR(100),
  embedding_model VARCHAR(100),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_rag_chunk_lesson (lesson_detail_id),
  KEY idx_rag_chunk_faiss (faiss_doc_id)
) ENGINE=InnoDB;

-- ============================================================
-- 3. Create tory_ai_sessions
-- ============================================================
-- session_state is LONGBLOB (not LONGTEXT) for gzip compression.
-- estimated_cost_usd tracks spend per session.
-- archived_at enables session archival (>90 days old).

CREATE TABLE IF NOT EXISTS tory_ai_sessions (
  id INT(11) NOT NULL AUTO_INCREMENT,
  nx_user_id INT(11) NOT NULL,
  role ENUM('curator', 'companion', 'creator') NOT NULL,
  initiated_by INT(11),
  session_state LONGBLOB,
  key_facts LONGTEXT,
  message_count INT(11) DEFAULT 0,
  model_tier VARCHAR(20) DEFAULT 'sonnet',
  total_input_tokens INT(11) DEFAULT 0,
  total_output_tokens INT(11) DEFAULT 0,
  estimated_cost_usd DECIMAL(10,4) DEFAULT 0,
  last_active_at DATETIME,
  archived_at DATETIME DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_ai_session_user (nx_user_id, role),
  KEY idx_ai_session_active (last_active_at),
  KEY idx_ai_session_archive (archived_at)
) ENGINE=InnoDB;
