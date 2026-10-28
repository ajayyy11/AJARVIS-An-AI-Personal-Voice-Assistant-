"""PostgreSQL-backed tasks and due-reminder helpers for cloud AJARVIS."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from database.db import get_connection


def _task_dict(row: Any) -> dict[str, Any]:
    return {
        "id": int(row[0]),
        "title": row[1],
        "details": row[2] or "",
        "due_at": row[3].isoformat() if row[3] else None,
        "done": bool(row[4]),
        "created_at": row[5].isoformat() if row[5] else None,
        "reminder_notified": bool(row[6]) if len(row) > 6 else False,
    }


def list_user_tasks(username: str) -> list[dict[str, Any]]:
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, details, due_at, done, created_at, "
            "(reminder_notified_at IS NOT NULL) FROM ajarvis_tasks "
            "WHERE username = %s ORDER BY done ASC, due_at NULLS LAST, id DESC LIMIT 200",
            (username,),
        )
        return [_task_dict(row) for row in cursor.fetchall()]
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def create_user_task(username: str, title: str, details: str = "", due_at: datetime | None = None) -> dict[str, Any]:
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 160:
        raise ValueError("Task title must contain 1 to 160 characters.")
    if not isinstance(details, str) or len(details) > 2000:
        raise ValueError("Task details must be 2000 characters or fewer.")
    if due_at is not None and (due_at.tzinfo is None or due_at.utcoffset() is None):
        raise ValueError("A reminder time must include a timezone.")

    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO ajarvis_tasks (username, title, details, due_at) "
            "VALUES (%s, %s, %s, %s) "
            "RETURNING id, title, details, due_at, done, created_at, "
            "(reminder_notified_at IS NOT NULL)",
            (username, title.strip(), details.strip(), due_at.astimezone(timezone.utc) if due_at else None),
        )
        task = _task_dict(cursor.fetchone())
        conn.commit()
        return task
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def update_user_task(username: str, task_id: int, *, done: bool) -> dict[str, Any] | None:
    if not isinstance(done, bool):
        raise ValueError("done must be a boolean.")
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE ajarvis_tasks SET done = %s WHERE id = %s AND username = %s "
            "RETURNING id, title, details, due_at, done, created_at, "
            "(reminder_notified_at IS NOT NULL)",
            (done, task_id, username),
        )
        row = cursor.fetchone()
        conn.commit()
        return _task_dict(row) if row else None
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def delete_user_task(username: str, task_id: int) -> bool:
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM ajarvis_tasks WHERE id = %s AND username = %s",
            (task_id, username),
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def claim_due_reminders(username: str, limit: int = 20) -> list[dict[str, Any]]:
    """Claim due, unfinished reminders once, transactionally, for one user."""
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, details, due_at, done, created_at, "
            "(reminder_notified_at IS NOT NULL) FROM ajarvis_tasks "
            "WHERE username = %s AND done = FALSE AND due_at <= %s "
            "AND reminder_notified_at IS NULL "
            "ORDER BY due_at LIMIT %s FOR UPDATE SKIP LOCKED",
            (username, datetime.now(timezone.utc), limit),
        )
        rows = cursor.fetchall()
        tasks = [_task_dict(row) for row in rows]
        for task in tasks:
            cursor.execute(
                "UPDATE ajarvis_tasks SET reminder_notified_at = %s "
                "WHERE id = %s AND username = %s AND reminder_notified_at IS NULL",
                (datetime.now(timezone.utc), task["id"], username),
            )
        conn.commit()
        return tasks
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
