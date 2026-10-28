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
        print("AJARVIS database preflight FAILED.")
        return 1

    print(f"AJARVIS database schema is usable: {Config.MYSQL_DB}")
    if warnings:
        print("Review the warnings above before treating the database as fully migrated.")
    return 0


if __name__ == "__main__":
    sys.exit(verify_schema())
