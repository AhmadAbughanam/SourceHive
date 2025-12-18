-- ============================================================
--  AI Résumé Analyzer – Database Setup Script
--  Author: Ibrahim Harb
--  Purpose: Central storage for applicant data, parsed CVs,
--           HR feedback, and role-based JD matching.
--  Engine:  MySQL 8+ (InnoDB)
-- ============================================================

-- ------------------------------------------------------------
-- Create database (idempotent)
-- ------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS cv
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE cv;

-- ------------------------------------------------------------
-- Drop existing tables (optional safety for full re-init)
-- ------------------------------------------------------------
-- DROP TABLE IF EXISTS user_feedback, user_data, jd_keywords, jd_roles, synonyms, admin_users;

-- ------------------------------------------------------------
--  Admin accounts (for HR dashboard logins)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admin_users (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  username      VARCHAR(100) NOT NULL UNIQUE,
  email         VARCHAR(190) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  full_name     VARCHAR(190),
  role          ENUM('admin','hr','viewer') DEFAULT 'hr',
  is_active     TINYINT(1) DEFAULT 1,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Default admin (password: admin@resume-analyzer)
INSERT IGNORE INTO admin_users (username, email, password_hash, full_name, role)
VALUES ('admin', 'admin@resume-analyzer', SHA2('admin@resume-analyzer', 256), 'System Administrator', 'admin');

-- ------------------------------------------------------------
-- Main table: user_data (parsed CVs + applicant info)
-- ------------------------------------------------------------
-- ------------------------------------------------------------
-- 🔧 Safe rebuild of user_data  (removes old duplicate indexes)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS user_data;

CREATE TABLE user_data (
  id                BIGINT PRIMARY KEY AUTO_INCREMENT,
  created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  first_name        VARCHAR(100),
  last_name         VARCHAR(100),
  email             VARCHAR(190) NOT NULL,
  phone             VARCHAR(60),
  address           VARCHAR(255),
  selected_role     VARCHAR(120),
  parsed_role       VARCHAR(120),
  education_json    JSON,
  experience_years  DECIMAL(4,1) DEFAULT 0.0,
  skills_hard       JSON,
  skills_soft       JSON,
  skills_hard_raw   JSON NULL,
  skills_soft_raw   JSON NULL,
  skills_hard_canonical JSON NULL,
  skills_soft_canonical JSON NULL,
  full_text_clean   MEDIUMTEXT NULL,
  resume_sentences  JSON NULL,
  resume_embedding  JSON NULL,
  certifications_json JSON NULL,
  job_titles_json   JSON NULL,
  seniority_level   VARCHAR(32) NULL,
  resume_score      DECIMAL(5,2) DEFAULT 0.0,
  jd_match_score    DECIMAL(5,2) DEFAULT 0.0,
  status            ENUM('new','shortlisted','interviewed','hired','rejected') DEFAULT 'new',
  cv_filename       VARCHAR(255),
  es_doc_id         VARCHAR(64),
  notes             TEXT,

  CONSTRAINT uk_user_email_file UNIQUE (email, cv_filename),

  -- ✅ all index names are unique and new
  INDEX idx_ud_role_status (selected_role, status),
  INDEX idx_ud_exp_score (experience_years, resume_score),
  INDEX idx_ud_created (created_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------
-- HR feedback table (linked to user_data)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_feedback (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id       BIGINT NOT NULL,
  rated_score   TINYINT UNSIGNED DEFAULT NULL,   -- HR rating (0-10)
  favourite     TINYINT(1) DEFAULT 0,
  locked        TINYINT(1) DEFAULT 0,
  comment       TEXT,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id)
    REFERENCES user_data(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  INDEX idx_user (user_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Job Descriptions (JD library)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jd_roles (
  id            INT PRIMARY KEY AUTO_INCREMENT,
  role_name     VARCHAR(120) UNIQUE NOT NULL,
  jd_text       TEXT,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ------------------------------------------------------------
--  JD keywords (critical / preferred)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jd_keywords (
  id            INT PRIMARY KEY AUTO_INCREMENT,
  role_id       INT NOT NULL,
  keyword       VARCHAR(120) NOT NULL,
  importance    ENUM('critical','preferred') DEFAULT 'preferred',
  weight        DECIMAL(4,2) DEFAULT 1.0,        -- for fine-grained scoring
  FOREIGN KEY (role_id)
    REFERENCES jd_roles(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  UNIQUE KEY uk_role_keyword (role_id, keyword),
  INDEX idx_role (role_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Synonyms mapping table (keyword expansions)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS synonyms (
  id            INT PRIMARY KEY AUTO_INCREMENT,
  token         VARCHAR(120) NOT NULL,
  expands_to    VARCHAR(120) NOT NULL,
  category      ENUM('skill','certification','tool','other') DEFAULT 'skill',
  UNIQUE KEY uk_token_expand (token, expands_to),
  INDEX idx_token (token)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
--  Optional audit table (for analytics / HR actions history)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  admin_id      BIGINT,
  user_id       BIGINT,
  action_type   VARCHAR(120),
  details       TEXT,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (admin_id) REFERENCES admin_users(id) ON DELETE SET NULL,
  FOREIGN KEY (user_id)  REFERENCES user_data(id) ON DELETE CASCADE,
  INDEX idx_admin (admin_id),
  INDEX idx_user  (user_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- View: HR candidate summary (for dashboards)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW v_candidate_summary AS
SELECT
  u.id,
  CONCAT(u.first_name,' ',u.last_name) AS full_name,
  u.email,
  u.phone,
  u.selected_role,
  u.parsed_role,
  u.experience_years,
  u.resume_score,
  u.jd_match_score,
  u.status,
  COALESCE(f.rated_score,0) AS hr_rating,
  f.favourite,
  f.locked,
  f.comment,
  u.created_at
FROM user_data u
LEFT JOIN user_feedback f ON u.id = f.user_id;


-- ============================================================
-- JOB ROLE: AI Engineer
-- Location: Amman | Level: Junior | Hybrid
-- ============================================================
