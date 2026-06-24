-- Run this SQL in your MySQL database to add persistent command history
-- mysql -u ajarvis_user -p ajarvis_db < create_history_table.sql

CREATE TABLE IF NOT EXISTS command_history (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    command    TEXT NOT NULL,
    response   TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
