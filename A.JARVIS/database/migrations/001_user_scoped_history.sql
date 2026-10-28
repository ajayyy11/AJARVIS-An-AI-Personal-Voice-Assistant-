-- Apply once to an existing AJARVIS database after backing it up.
-- Existing rows have no reliable owner; keep username NULL rather than exposing
-- another user's historical commands. New app writes include the authenticated username.
-- If the database/table name differs, select the correct database first.

ALTER TABLE command_history
  ADD COLUMN username VARCHAR(100) NULL AFTER id;

CREATE INDEX idx_command_history_username_id
  ON command_history (username, id);
