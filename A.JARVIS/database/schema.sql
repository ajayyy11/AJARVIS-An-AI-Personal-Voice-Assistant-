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
  command VARCHAR(2000) NOT NULL,
  response TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_command_history_created_at (created_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
