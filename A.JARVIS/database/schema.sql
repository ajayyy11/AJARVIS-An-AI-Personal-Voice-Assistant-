-- AJARVIS database schema
-- Run this script with a MySQL account allowed to create the database/tables.
-- If MYSQL_DB is changed in .env, change the database name below to match.

CREATE DATABASE IF NOT EXISTS ajarvis_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE ajarvis_db;

CREATE TABLE IF NOT EXISTS users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL,
  face_encoding BLOB NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_username (username)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS command_history (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL,
  command VARCHAR(2000) NOT NULL,
  response TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_command_history_username_id (username, id)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Explicit, editable user-owned facts and preferences for local personalization.
CREATE TABLE IF NOT EXISTS user_memories (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL,
  memory_key VARCHAR(80) NOT NULL,
  memory_value VARCHAR(1000) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_user_memories_username_key (username, memory_key),
  KEY idx_user_memories_username_updated (username, updated_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;


-- Minimal audit metadata for proposed and approved automation activity.
-- Raw tool arguments, URLs, prompts, and tool outputs are never stored here.
CREATE TABLE IF NOT EXISTS automation_activity (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL,
  plan_id CHAR(32) NOT NULL,
  step_number INT NULL,
  event_type VARCHAR(40) NOT NULL,
  tool_name VARCHAR(64) NULL,
  summary VARCHAR(240) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_automation_activity_user_id (username, id)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;


-- Durable metadata for workflow recovery. Sensitive prompts, URLs, and arguments
-- are deliberately not stored here; interrupted workflows require replanning.
CREATE TABLE IF NOT EXISTS automation_workflows (
  plan_id CHAR(32) NOT NULL,
  username VARCHAR(100) NOT NULL,
  status VARCHAR(32) NOT NULL,
  step_count INT NOT NULL DEFAULT 0,
  tools_summary VARCHAR(320) NOT NULL DEFAULT '',
  process_instance_id CHAR(32) NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  finished_at DATETIME NULL,
  PRIMARY KEY (plan_id),
  KEY idx_automation_workflows_user_updated (username, updated_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Reminder preferences are opt-in. Browser notifications require a second opt-in.
CREATE TABLE IF NOT EXISTS user_notification_preferences (
  username VARCHAR(100) NOT NULL,
  reminders_enabled TINYINT(1) NOT NULL DEFAULT 0,
  browser_notifications_enabled TINYINT(1) NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (username)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS assistant_reminders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL,
  title VARCHAR(180) NOT NULL,
  due_at DATETIME NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  PRIMARY KEY (id),
  KEY idx_assistant_reminders_user_status_due (username, status, due_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS assistant_notifications (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL,
  reminder_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(180) NOT NULL,
  body VARCHAR(240) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  presented_at DATETIME NULL,
  read_at DATETIME NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_assistant_notifications_user_reminder (username, reminder_id),
  KEY idx_assistant_notifications_user_read (username, read_at, id)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;


-- User-owned projects and tasks. Task ranking is calculated transparently at read time.
CREATE TABLE IF NOT EXISTS assistant_projects (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL,
  name VARCHAR(180) NOT NULL,
  objective VARCHAR(500) NOT NULL DEFAULT '',
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_assistant_projects_user_status_updated (username, status, updated_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS assistant_tasks (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL,
  project_id BIGINT UNSIGNED NULL,
  title VARCHAR(180) NOT NULL,
  details VARCHAR(500) NOT NULL DEFAULT '',
  priority VARCHAR(12) NOT NULL DEFAULT 'normal',
  due_at DATETIME NULL,
  effort_minutes SMALLINT UNSIGNED NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  PRIMARY KEY (id),
  KEY idx_assistant_tasks_user_status_due (username, status, due_at),
  KEY idx_assistant_tasks_user_project (username, project_id)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
