"""Read-only preflight check for the configured AJARVIS MySQL schema.

This script never creates, alters, or deletes database objects or records.
Run from the A.JARVIS directory after configuring .env.
"""

import sys

from config import Config
from database.db import get_connection


REQUIRED_COLUMNS = {
    "users": {"username", "face_encoding"},
    "command_history": {"id", "username", "command", "response"},
    "user_memories": {"id", "username", "memory_key", "memory_value", "created_at", "updated_at"},
    "automation_activity": {"id", "username", "plan_id", "step_number", "event_type", "tool_name", "summary", "created_at"},
    "automation_workflows": {"plan_id", "username", "status", "step_count", "tools_summary", "process_instance_id", "created_at", "updated_at", "finished_at"},
    "user_notification_preferences": {"username", "reminders_enabled", "browser_notifications_enabled", "updated_at"},
    "assistant_reminders": {"id", "username", "title", "due_at", "status", "created_at", "updated_at", "completed_at"},
    "assistant_notifications": {"id", "username", "reminder_id", "title", "body", "created_at", "presented_at", "read_at"},
}


def verify_schema():
    connection = None
    cursor = None
    errors = []
    warnings = []

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s",
            (Config.MYSQL_DB,),
        )
        tables = {row[0] for row in cursor.fetchall()}

        for table_name, required_columns in REQUIRED_COLUMNS.items():
            if table_name not in tables:
                errors.append(f"Missing required table: {table_name}")
                continue

            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (Config.MYSQL_DB, table_name),
            )
            actual_columns = {row[0] for row in cursor.fetchall()}
            missing = sorted(required_columns - actual_columns)
            if missing:
                errors.append(
                    f"Table {table_name} is missing column(s): {', '.join(missing)}"
                )

        if "user_memories" in tables:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'user_memories' "
                "AND INDEX_NAME = 'uq_user_memories_username_key'",
                (Config.MYSQL_DB,),
            )
            if not cursor.fetchone()[0]:
                errors.append("user_memories is missing the unique username/key index.")

        if "automation_activity" in tables:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'automation_activity' "
                "AND INDEX_NAME = 'idx_automation_activity_user_id'",
                (Config.MYSQL_DB,),
            )
            if not cursor.fetchone()[0]:
                errors.append("automation_activity is missing the per-user activity index.")


        phase6_indexes = {
            "automation_workflows": ("idx_automation_workflows_user_updated", ("username", "updated_at")),
            "assistant_reminders": ("idx_assistant_reminders_user_status_due", ("username", "status", "due_at")),
            "assistant_notifications": ("idx_assistant_notifications_user_read", ("username", "read_at", "id")),
        }
        for table_name, (index_name, expected_columns) in phase6_indexes.items():
            if table_name in tables:
                cursor.execute(
                    "SELECT COLUMN_NAME FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND INDEX_NAME = %s "
                    "ORDER BY SEQ_IN_INDEX",
                    (Config.MYSQL_DB, table_name, index_name),
                )
                actual_columns = tuple(row[0] for row in cursor.fetchall())
                if actual_columns != expected_columns:
                    errors.append(f"{table_name} is missing or has an incorrect {index_name} index.")

        if "assistant_notifications" in tables:
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'assistant_notifications' "
                "AND INDEX_NAME = 'uq_assistant_notifications_user_reminder' "
                "ORDER BY SEQ_IN_INDEX",
                (Config.MYSQL_DB,),
            )
            if tuple(row[0] for row in cursor.fetchall()) != ("username", "reminder_id"):
                errors.append("assistant_notifications is missing its unique user/reminder index.")

        if "users" in tables:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users' "
                "AND COLUMN_NAME = 'username' AND NON_UNIQUE = 0",
                (Config.MYSQL_DB,),
            )
            if not cursor.fetchone()[0]:
                errors.append(
                    "users.username has no unique index. Check for duplicate usernames "
                    "before applying a unique constraint."
                )

        if "command_history" in tables:
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'command_history' "
                "AND COLUMN_NAME = 'username'",
                (Config.MYSQL_DB,),
            )
            if cursor.fetchone():
                cursor.execute(
                    "SELECT COUNT(*) FROM command_history WHERE username IS NULL"
                )
                unassigned_count = int(cursor.fetchone()[0])
                if unassigned_count:
                    warnings.append(
                        f"{unassigned_count} legacy history row(s) have no known owner "
                        "and are intentionally hidden from per-user views."
                    )

                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'command_history' "
                    "AND INDEX_NAME = 'idx_command_history_username_id'",
                    (Config.MYSQL_DB,),
                )
                if not cursor.fetchone()[0]:
                    warnings.append(
                        "Recommended index idx_command_history_username_id is missing."
                    )

    except Exception as exc:
        errors.append(
            f"Could not verify database '{Config.MYSQL_DB}': "
            f"{type(exc).__name__}: {exc}"
        )
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        print("AJARVIS database preflight FAILED. Review errors; for an existing database, preview database/migrate_database.py first.")
        return 1

    print(f"AJARVIS database schema is usable: {Config.MYSQL_DB}")
    if warnings:
        print("Review the warnings above before treating the database as fully migrated.")
    return 0


if __name__ == "__main__":
    sys.exit(verify_schema())
