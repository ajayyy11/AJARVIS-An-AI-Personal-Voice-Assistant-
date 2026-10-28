"""Safely plan/apply the user-scoped command-history schema migration.

Default mode is read-only and reports the changes that would be made.
Use --apply only after backing up the database. Apply mode prompts for MIGRATE.
"""

import argparse
import sys

from config import Config
from database.db import get_connection


REQUIRED_COLUMNS = {
    "users": {"username", "face_encoding"},
    "command_history": {"id", "command", "response"},
}
HISTORY_INDEX_NAME = "idx_command_history_username_id"
HISTORY_INDEX_COLUMNS = ("username", "id")


def plan_migration(tables, columns, indexes):
    """Return (actions, errors) without making any database changes."""
    actions = []
    errors = []

    for table_name in REQUIRED_COLUMNS:
        if table_name not in tables:
            errors.append(f"Missing required table: {table_name}")

    if errors:
        return actions, errors

    for table_name, required in REQUIRED_COLUMNS.items():
        missing = sorted(required - columns.get(table_name, set()))
        if missing:
            errors.append(
                f"Table {table_name} is missing required column(s): {', '.join(missing)}"
            )

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

    return actions, errors


def read_schema(cursor, database_name):
    """Read table, column, and index metadata using information_schema."""
    cursor.execute(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s",
        (database_name,),
    )
    tables = {row[0] for row in cursor.fetchall()}

    columns = {}
    indexes = {}
    for table_name in REQUIRED_COLUMNS:
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
    """Report planned changes, or apply after an explicit interactive confirmation."""
    connection = None
    cursor = None
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
            print(f"Database {Config.MYSQL_DB} already has the required user-history schema.")
            return 0

        descriptions = {
            "add_nullable_username_column": (
                "Add nullable command_history.username (existing rows stay NULL)"
            ),
            "add_user_history_index": (
                "Create index idx_command_history_username_id (username, id)"
            ),
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
                    "ALTER TABLE command_history "
                    "ADD COLUMN username VARCHAR(100) NULL AFTER id"
                )
            elif action == "add_user_history_index":
                cursor.execute(
                    "CREATE INDEX idx_command_history_username_id "
                    "ON command_history (username, id)"
                )

        print("Migration completed. Existing history rows remain unassigned (username IS NULL).")
        return 0
    except Exception as exc:
        print(f"ERROR: Migration could not be completed: {type(exc).__name__}: {exc}")
        return 1
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the planned changes after typing MIGRATE at the confirmation prompt.",
    )
    args = parser.parse_args()
    return migrate_database(apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
