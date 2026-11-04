"""Safely plan/apply local AJARVIS user-history and personalization migrations.

Default mode is read-only. Apply mode prompts for MIGRATE after a verified backup.
"""
import argparse
import sys

from config import Config
from database.db import get_connection

REQUIRED_COLUMNS = {
    "users": {"username", "face_encoding"},
    "command_history": {"id", "command", "response"},
}
USER_MEMORY_COLUMNS = {
    "id", "username", "memory_key", "memory_value", "created_at", "updated_at"
}
AUTOMATION_ACTIVITY_COLUMNS = {
    "id", "username", "plan_id", "step_number", "event_type",
    "tool_name", "summary", "created_at"
}
AUTOMATION_ACTIVITY_INDEX = "idx_automation_activity_user_id"
HISTORY_INDEX_NAME = "idx_command_history_username_id"
HISTORY_INDEX_COLUMNS = ("username", "id")

WORKFLOW_COLUMNS = {
    "plan_id", "username", "status", "step_count", "tools_summary",
    "process_instance_id", "created_at", "updated_at", "finished_at"
}
PREFERENCE_COLUMNS = {
    "username", "reminders_enabled", "browser_notifications_enabled", "updated_at"
}
REMINDER_COLUMNS = {
    "id", "username", "title", "due_at", "status", "created_at",
    "updated_at", "completed_at"
}
NOTIFICATION_COLUMNS = {
    "id", "username", "reminder_id", "title", "body", "created_at",
    "presented_at", "read_at"
}
PHASE6_INDEXES = {
    "automation_workflows": ("idx_automation_workflows_user_updated", ("username", "updated_at")),
    "assistant_reminders": ("idx_assistant_reminders_user_status_due", ("username", "status", "due_at")),
    "assistant_notifications": ("idx_assistant_notifications_user_read", ("username", "read_at", "id")),
}

PROJECT_COLUMNS = {
    "id", "username", "name", "objective", "status", "created_at", "updated_at"
}
TASK_COLUMNS = {
    "id", "username", "project_id", "title", "details", "priority", "due_at",
    "effort_minutes", "status", "created_at", "updated_at", "completed_at"
}
PHASE7_INDEXES = {
    "assistant_projects": ("idx_assistant_projects_user_status_updated", ("username", "status", "updated_at")),
    "assistant_tasks": ("idx_assistant_tasks_user_status_due", ("username", "status", "due_at")),
}


def plan_migration(tables, columns, indexes):
    """Return planned actions and errors without making schema changes."""
    actions, errors = [], []
    for table_name in REQUIRED_COLUMNS:
        if table_name not in tables:
            errors.append(f"Missing required table: {table_name}")
    if errors:
        return actions, errors

    for table_name, required in REQUIRED_COLUMNS.items():
        missing = sorted(required - columns.get(table_name, set()))
        if missing:
            errors.append(f"Table {table_name} is missing required column(s): {', '.join(missing)}")
    if errors:
        return actions, errors

    history_columns = columns.get("command_history", set())
    if "username" not in history_columns:
        actions.append("add_nullable_username_column")

    history_indexes = indexes.get("command_history", {})
    existing_index = history_indexes.get(HISTORY_INDEX_NAME)
    if existing_index is None:
        actions.append("add_user_history_index")
    elif tuple(existing_index) != HISTORY_INDEX_COLUMNS:
        errors.append(
            f"Index {HISTORY_INDEX_NAME} exists with columns {tuple(existing_index)!r}; "
            f"expected {HISTORY_INDEX_COLUMNS!r}. Inspect it manually; no changes were planned."
        )

    if "user_memories" not in tables:
        actions.append("create_user_memories_table")
    else:
        missing = sorted(USER_MEMORY_COLUMNS - columns.get("user_memories", set()))
        if missing:
            errors.append(
                "Table user_memories is missing required column(s): " + ", ".join(missing)
            )
        memory_indexes = indexes.get("user_memories", {})
        memory_unique = memory_indexes.get("uq_user_memories_username_key")
        if memory_unique is None:
            errors.append("user_memories is missing unique index uq_user_memories_username_key.")
        elif tuple(memory_unique) != ("username", "memory_key"):
            errors.append(
                "Index uq_user_memories_username_key must cover (username, memory_key); "
                "inspect the existing index manually."
            )
    if "automation_activity" not in tables:
        actions.append("create_automation_activity_table")
    else:
        missing = sorted(AUTOMATION_ACTIVITY_COLUMNS - columns.get("automation_activity", set()))
        if missing:
            errors.append(
                "Table automation_activity is missing required column(s): " + ", ".join(missing)
            )
        activity_index = indexes.get("automation_activity", {}).get(AUTOMATION_ACTIVITY_INDEX)
        if activity_index is None:
            actions.append("add_automation_activity_index")
        elif tuple(activity_index) != ("username", "id"):
            errors.append(
                f"Index {AUTOMATION_ACTIVITY_INDEX} must cover (username, id); inspect it manually."
            )
    phase6_tables = {
        "automation_workflows": WORKFLOW_COLUMNS,
        "user_notification_preferences": PREFERENCE_COLUMNS,
        "assistant_reminders": REMINDER_COLUMNS,
        "assistant_notifications": NOTIFICATION_COLUMNS,
    }
    for table_name, required_columns in phase6_tables.items():
        if table_name not in tables:
            actions.append(f"create_{table_name}_table")
            continue
        missing = sorted(required_columns - columns.get(table_name, set()))
        if missing:
            errors.append(
                f"Table {table_name} is missing required column(s): " + ", ".join(missing)
            )
    for table_name, (index_name, expected_columns) in PHASE6_INDEXES.items():
        if table_name not in tables:
            continue
        actual = indexes.get(table_name, {}).get(index_name)
        if actual is None:
            actions.append(f"add_{table_name}_index")
        elif tuple(actual) != expected_columns:
            errors.append(
                f"Index {index_name} must cover {expected_columns!r}; inspect it manually."
            )
    notification_unique = indexes.get("assistant_notifications", {}).get(
        "uq_assistant_notifications_user_reminder"
    )
    if "assistant_notifications" in tables:
        if notification_unique is None:
            actions.append("add_assistant_notifications_unique")
        elif tuple(notification_unique) != ("username", "reminder_id"):
            errors.append(
                "Index uq_assistant_notifications_user_reminder must cover "
                "(username, reminder_id); inspect it manually."
            )
    phase7_tables = {
        "assistant_projects": PROJECT_COLUMNS,
        "assistant_tasks": TASK_COLUMNS,
    }
    for table_name, required_columns in phase7_tables.items():
        if table_name not in tables:
            actions.append(f"create_{table_name}_table")
            continue
        missing = sorted(required_columns - columns.get(table_name, set()))
        if missing:
            errors.append(
                f"Table {table_name} is missing required column(s): " + ", ".join(missing)
            )
    for table_name, (index_name, expected_columns) in PHASE7_INDEXES.items():
        if table_name not in tables:
            continue
        actual = indexes.get(table_name, {}).get(index_name)
        if actual is None:
            actions.append(f"add_{table_name}_index")
        elif tuple(actual) != expected_columns:
            errors.append(f"Index {index_name} must cover {expected_columns!r}; inspect it manually.")
    return actions, errors


def read_schema(cursor, database_name):
    """Read table, column, and index metadata using information_schema."""
    cursor.execute(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s",
        (database_name,),
    )
    tables = {row[0] for row in cursor.fetchall()}
    columns, indexes = {}, {}
    inspected_tables = [
        *REQUIRED_COLUMNS, "user_memories", "automation_activity",
        "automation_workflows", "user_notification_preferences",
        "assistant_reminders", "assistant_notifications",
        "assistant_projects", "assistant_tasks",
    ]
    for table_name in inspected_tables:
        if table_name not in tables:
            continue
        cursor.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (database_name, table_name),
        )
        columns[table_name] = {row[0] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX "
            "FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "ORDER BY INDEX_NAME, SEQ_IN_INDEX",
            (database_name, table_name),
        )
        per_index = {}
        for index_name, column_name, sequence in cursor.fetchall():
            per_index.setdefault(index_name, []).append((sequence, column_name))
        indexes[table_name] = {
            name: tuple(column for _, column in sorted(parts))
            for name, parts in per_index.items()
        }
    return tables, columns, indexes


def migrate_database(apply=False, confirm=input):
    """Report changes or apply them after explicit interactive confirmation."""
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        tables, columns, indexes = read_schema(cursor, Config.MYSQL_DB)
        actions, errors = plan_migration(tables, columns, indexes)
        for error in errors:
            print(f"ERROR: {error}")
        if errors:
            print("Migration stopped. No schema changes were made.")
            return 1
        if not actions:
            print(f"Database {Config.MYSQL_DB} already has the required AJARVIS schema.")
            return 0

        descriptions = {
            "add_nullable_username_column": "Add nullable command_history.username (legacy rows remain NULL)",
            "add_user_history_index": "Create index idx_command_history_username_id (username, id)",
            "create_user_memories_table": "Create user_memories for editable, user-scoped preferences and facts",
            "create_automation_activity_table": "Create privacy-minimal automation activity history",
            "add_automation_activity_index": "Create index idx_automation_activity_user_id (username, id)",

            "create_automation_workflows_table": "Create durable per-user workflow status history",
            "create_user_notification_preferences_table": "Create opt-in reminder/browser notification preferences",
            "create_assistant_reminders_table": "Create persistent scheduled reminders",
            "create_assistant_notifications_table": "Create durable in-app reminder notifications",
            "add_automation_workflows_index": "Create workflow history index",
            "add_assistant_reminders_index": "Create reminder due-date index",
            "add_assistant_notifications_index": "Create unread notification index",
            "add_assistant_notifications_unique": "Create unique notification-per-reminder constraint",
            "create_assistant_projects_table": "Create user-owned project records",
            "create_assistant_tasks_table": "Create user-owned prioritized task records",
            "add_assistant_projects_index": "Create project status/updated index",
            "add_assistant_tasks_index": "Create task status/due-date index",
        }
        print(f"Database: {Config.MYSQL_DB}")
        print("Planned schema changes:")
        for action in actions:
            print(f"  - {descriptions[action]}")
        if not apply:
            print("DRY RUN ONLY: no changes were made. Back up the database, then rerun with --apply.")
            return 0

        print("WARNING: This changes the MySQL schema. Existing records are not deleted.")
        print("A verified backup is strongly recommended before proceeding.")
        if confirm("Type MIGRATE to apply these schema changes: ").strip() != "MIGRATE":
            print("Migration cancelled. No changes were made.")
            return 2

        for action in actions:
            if action == "add_nullable_username_column":
                cursor.execute(
                    "ALTER TABLE command_history ADD COLUMN username VARCHAR(100) NULL AFTER id"
                )
            elif action == "add_user_history_index":
                cursor.execute(
                    "CREATE INDEX idx_command_history_username_id ON command_history (username, id)"
                )
            elif action == "create_user_memories_table":
                cursor.execute(
                    "CREATE TABLE user_memories ("
                    "id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,"
                    "username VARCHAR(100) NOT NULL,"
                    "memory_key VARCHAR(80) NOT NULL,"
                    "memory_value VARCHAR(1000) NOT NULL,"
                    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                    "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                    "PRIMARY KEY (id),"
                    "UNIQUE KEY uq_user_memories_username_key (username, memory_key),"
                    "KEY idx_user_memories_username_updated (username, updated_at)"
                    ") ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            elif action == "create_automation_activity_table":
                cursor.execute(
                    "CREATE TABLE automation_activity ("
                    "id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,"
                    "username VARCHAR(100) NOT NULL,"
                    "plan_id CHAR(32) NOT NULL,"
                    "step_number INT NULL,"
                    "event_type VARCHAR(40) NOT NULL,"
                    "tool_name VARCHAR(64) NULL,"
                    "summary VARCHAR(240) NOT NULL,"
                    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                    "PRIMARY KEY (id),"
                    "KEY idx_automation_activity_user_id (username, id)"
                    ") ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            elif action == "add_automation_activity_index":
                cursor.execute(
                    "CREATE INDEX idx_automation_activity_user_id "
                    "ON automation_activity (username, id)"
                )

            elif action == "create_automation_workflows_table":
                cursor.execute(
                    "CREATE TABLE automation_workflows ("
                    "plan_id CHAR(32) NOT NULL, username VARCHAR(100) NOT NULL, "
                    "status VARCHAR(32) NOT NULL, step_count INT NOT NULL DEFAULT 0, "
                    "tools_summary VARCHAR(320) NOT NULL DEFAULT '', "
                    "process_instance_id CHAR(32) NOT NULL, created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL, finished_at DATETIME NULL, "
                    "PRIMARY KEY (plan_id), "
                    "KEY idx_automation_workflows_user_updated (username, updated_at)"
                    ") ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            elif action == "create_user_notification_preferences_table":
                cursor.execute(
                    "CREATE TABLE user_notification_preferences ("
                    "username VARCHAR(100) NOT NULL, reminders_enabled TINYINT(1) NOT NULL DEFAULT 0, "
                    "browser_notifications_enabled TINYINT(1) NOT NULL DEFAULT 0, "
                    "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, "
                    "PRIMARY KEY (username)"
                    ") ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            elif action == "create_assistant_reminders_table":
                cursor.execute(
                    "CREATE TABLE assistant_reminders ("
                    "id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, username VARCHAR(100) NOT NULL, "
                    "title VARCHAR(180) NOT NULL, due_at DATETIME NOT NULL, "
                    "status VARCHAR(20) NOT NULL DEFAULT 'pending', "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, "
                    "completed_at DATETIME NULL, PRIMARY KEY (id), "
                    "KEY idx_assistant_reminders_user_status_due (username, status, due_at)"
                    ") ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            elif action == "create_assistant_notifications_table":
                cursor.execute(
                    "CREATE TABLE assistant_notifications ("
                    "id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, username VARCHAR(100) NOT NULL, "
                    "reminder_id BIGINT UNSIGNED NOT NULL, title VARCHAR(180) NOT NULL, "
                    "body VARCHAR(240) NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "presented_at DATETIME NULL, read_at DATETIME NULL, PRIMARY KEY (id), "
                    "UNIQUE KEY uq_assistant_notifications_user_reminder (username, reminder_id), "
                    "KEY idx_assistant_notifications_user_read (username, read_at, id)"
                    ") ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            elif action == "add_automation_workflows_index":
                cursor.execute(
                    "CREATE INDEX idx_automation_workflows_user_updated "
                    "ON automation_workflows (username, updated_at)"
                )
            elif action == "add_assistant_reminders_index":
                cursor.execute(
                    "CREATE INDEX idx_assistant_reminders_user_status_due "
                    "ON assistant_reminders (username, status, due_at)"
                )
            elif action == "add_assistant_notifications_index":
                cursor.execute(
                    "CREATE INDEX idx_assistant_notifications_user_read "
                    "ON assistant_notifications (username, read_at, id)"
                )
            elif action == "add_assistant_notifications_unique":
                cursor.execute(
                    "CREATE UNIQUE INDEX uq_assistant_notifications_user_reminder "
                    "ON assistant_notifications (username, reminder_id)"
                )

            elif action == "create_assistant_projects_table":
                cursor.execute(
                    "CREATE TABLE assistant_projects ("
                    "id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, username VARCHAR(100) NOT NULL, "
                    "name VARCHAR(180) NOT NULL, objective VARCHAR(500) NOT NULL DEFAULT '', "
                    "status VARCHAR(20) NOT NULL DEFAULT 'active', "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, "
                    "PRIMARY KEY (id), "
                    "KEY idx_assistant_projects_user_status_updated (username, status, updated_at)"
                    ") ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            elif action == "create_assistant_tasks_table":
                cursor.execute(
                    "CREATE TABLE assistant_tasks ("
                    "id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, username VARCHAR(100) NOT NULL, "
                    "project_id BIGINT UNSIGNED NULL, title VARCHAR(180) NOT NULL, "
                    "details VARCHAR(500) NOT NULL DEFAULT '', priority VARCHAR(12) NOT NULL DEFAULT 'normal', "
                    "due_at DATETIME NULL, effort_minutes SMALLINT UNSIGNED NULL, "
                    "status VARCHAR(20) NOT NULL DEFAULT 'pending', "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, "
                    "completed_at DATETIME NULL, PRIMARY KEY (id), "
                    "KEY idx_assistant_tasks_user_status_due (username, status, due_at), "
                    "KEY idx_assistant_tasks_user_project (username, project_id)"
                    ") ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            elif action == "add_assistant_projects_index":
                cursor.execute(
                    "CREATE INDEX idx_assistant_projects_user_status_updated "
                    "ON assistant_projects (username, status, updated_at)"
                )
            elif action == "add_assistant_tasks_index":
                cursor.execute(
                    "CREATE INDEX idx_assistant_tasks_user_status_due "
                    "ON assistant_tasks (username, status, due_at)"
                )
        connection.commit()
        print("Migration completed. Existing history rows remain unassigned (username IS NULL).")
        return 0
    except Exception as exc:
        print(f"ERROR: Migration could not be completed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Apply planned changes after typing MIGRATE at the confirmation prompt.",
    )
    return migrate_database(apply=parser.parse_args().apply)


if __name__ == "__main__":
    sys.exit(main())
