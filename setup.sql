-- ============================================================
--  AI Résumé Analyzer – Database Setup Script
--  Author: Ibrahim Harb
--  Purpose: Central storage for applicant data, parsed CVs,
--           HR feedback, and role-based JD matching.
--  Engine:  MySQL 8+ (InnoDB)
-- ============================================================
SET FOREIGN_KEY_CHECKS = 0;

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
DROP TABLE IF EXISTS user_feedback;
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
  is_open       TINYINT(1) NOT NULL DEFAULT 1,
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
-- Seed: AI Engineer role + keywords (desktop setup.sql)
-- ------------------------------------------------------------
INSERT IGNORE INTO jd_roles (role_name, jd_text)
VALUES
(
  'AI Engineer',
  'We are building cutting-edge AI systems, including large language models (LLMs) and autonomous agents, to deliver real-time AI services solving real-world problems. As a Junior AI Engineer, you will actively contribute to developing and optimizing AI-powered applications, working hands-on with state-of-the-art tools and frameworks such as PyTorch, Hugging Face Transformers, and Docker. This role offers a unique opportunity to grow your machine learning skills, collaborate with a passionate team, and help bring innovative AI products to life.\n\n  JOB RESPONSIBILITIES:\n  • Building AI-powered applications using LLMs, Retrieval-Augmented Generation (RAG), and Model Context Protocol (MCP)\n  • Implementing advanced capabilities like function calling, agent orchestration, and tool use\n  • Benchmarking models using LLM-as-a-Judge, few-shot evaluations, and custom test pipelines\n  • Optimizing models through quantization techniques\n  • Containerizing applications with Docker and Docker Compose\n  • Leveraging Hugging Face Transformers for NLP tasks\n  • Working with vector databases for semantic search\n  • Applying image processing techniques using OpenCV\n  • Fine-tuning ML/DL models\n  • Integrating with databases such as MariaDB, PostgreSQL\n  • Working with queuing frameworks for task orchestration\n\n  QUALIFICATIONS:\n  • Bachelor’s degree in AI, Computer Science, or Engineering\n  • Strong Python skills\n  • Familiarity with PyTorch or TensorFlow\n  • Understanding of ML/NLP and RAG\n  • Docker, Linux, FastAPI, Git\n  • Optional: Quantization, Transformers, Vector DBs, OpenCV, Queuing systems, LangChain'
);

INSERT IGNORE INTO jd_keywords (role_id, keyword, importance) VALUES
-- === Core AI Foundations ===
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'python', 'critical'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'machine learning', 'critical'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'deep learning', 'critical'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'natural language processing', 'critical'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'llm', 'critical'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'rag', 'critical'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'model context protocol', 'preferred'),

-- === Frameworks ===
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'pytorch', 'critical'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'tensorflow', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'hugging face transformers', 'critical'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'langchain', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'llamaindex', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'haystack', 'preferred'),

-- === DevOps / Deployment ===
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'docker', 'critical'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'docker compose', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'linux', 'critical'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'fastapi', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'asyncio', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'git', 'critical'),

-- === Optimization / Performance ===
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'quantization', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'gptq', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'awq', 'preferred'),

-- === Data Handling / Infrastructure ===
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'vector database', 'critical'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'qdrant', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'chromadb', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'mariadb', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'postgresql', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'sqlite', 'preferred'),

-- === Computer Vision ===
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'opencv', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'object detection', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'image segmentation', 'preferred'),

-- === Systems / Architecture ===
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'redis queue', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'rabbitmq', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'background processing', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'agent orchestration', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'function calling', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'benchmarking', 'preferred'),
((SELECT id FROM jd_roles WHERE role_name='AI Engineer'), 'evaluation pipeline', 'preferred');

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
-- Seed: Synonyms Expansion (for semantic coverage)
-- ------------------------------------------------------------
INSERT IGNORE INTO synonyms (token, expands_to, category) VALUES
('llm', 'large language model', 'skill'),
('rag', 'retrieval augmented generation', 'skill'),
('mcp', 'model context protocol', 'skill'),
('transformers', 'hugging face transformers', 'tool'),
('hf', 'hugging face', 'tool'),
('cv', 'computer vision', 'skill'),
('docker compose', 'containerization', 'tool'),
('asyncio', 'asynchronous framework', 'tool'),
('quantization', 'model optimization', 'skill'),
('mlops', 'machine learning operations', 'skill'),
('ai', 'artificial intelligence', 'skill'),
('vector db', 'vector database', 'tool'),
('chroma', 'chromadb', 'tool'),
('llama index', 'llamaindex', 'tool'),
('lang chain', 'langchain', 'tool'),
('redis', 'redis queue', 'tool'),
('postgres', 'postgresql', 'tool'),
('mariadb', 'sql database', 'tool');

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
-- AI interview sessions (invites + status tracking)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS interview_sessions (
  session_id        VARCHAR(64) PRIMARY KEY,
  user_id           BIGINT NOT NULL,
  candidate_name    VARCHAR(255),
  email             VARCHAR(190),
  invite_email      VARCHAR(190),
  interview_role    VARCHAR(120),
  interview_status  ENUM('invited','in_progress','completed','expired','canceled') DEFAULT 'invited',
  interview_score   DECIMAL(5,2) DEFAULT 0.0,
  token_hash        CHAR(64),
  invite_last_error TEXT,
  invite_sent_at    TIMESTAMP NULL,
  expires_at        TIMESTAMP NULL,
  started_at        TIMESTAMP NULL,
  completed_at      TIMESTAMP NULL,
  created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES user_data(id) ON DELETE CASCADE,
  INDEX idx_is_user (user_id),
  INDEX idx_is_status (interview_status),
  INDEX idx_is_role (interview_role),
  INDEX idx_is_created (created_at),
  UNIQUE KEY uk_is_token_hash (token_hash)
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
SET FOREIGN_KEY_CHECKS = 1;
