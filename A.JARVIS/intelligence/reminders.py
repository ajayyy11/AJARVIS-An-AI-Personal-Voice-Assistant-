"""Persistent user-owned reminders and opt-in notification delivery.

Due reminders are converted into notifications when the authenticated dashboard
polls. This avoids background workers and keeps delivery honest: reminders stay
stored while AJARVIS is closed, and are surfaced when the dashboard is opened.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from database.db import get_connection

logger = logging.getLogger(__name__)
MAX_REMINDER_DAYS = 365


class ReminderError(ValueError):
    """Raised when reminder input or ownership state is invalid."""


class ReminderUnavailable(ReminderError):
    """Raised when the reminder database cannot complete the requested operation."""


def _owner(username: str) -> str:
    if not isinstance(username, str) or not username.strip() or len(username.strip()) > 100:
        raise ReminderError("An authenticated username is required.")
    return username.strip()


def _parse_due_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ReminderError("Choose a date and time for the reminder.")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ReminderError("Reminder time must be a valid ISO 8601 date and time.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReminderError("Reminder time must include a timezone offset.")
    utc_value = parsed.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if utc_value <= now:
        raise ReminderError("Reminder time must be in the future.")
    if utc_value - now > timedelta(days=MAX_REMINDER_DAYS):
        raise ReminderError("Reminders can be scheduled up to one year ahead.")
    return utc_value.replace(tzinfo=None)


def _format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def create_reminder(username: str, title: str, due_at: str) -> dict[str, Any]:
    owner = _owner(username)
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 180:
        raise ReminderError("Reminder title must contain 1–180 characters.")
    due = _parse_due_at(due_at)
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO assistant_reminders (username, title, due_at, status) "
            "VALUES (%s, %s, %s, 'pending')",
            (owner, title.strip(), due),
        )
        reminder_id = int(cursor.lastrowid)
        connection.commit()
        return {
            "id": reminder_id, "title": title.strip(), "due_at": due.replace(tzinfo=timezone.utc).isoformat(),
            "status": "pending",
        }
    except ReminderError:
        raise
    except Exception:
        logger.warning("Could not create reminder", exc_info=True)
        raise ReminderUnavailable("Reminder storage is temporarily unavailable. Please retry.") from None
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def list_reminders(username: str, limit: int = 50) -> list[dict[str, Any]]:
    owner = _owner(username)
    try:
        bounded = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        bounded = 50
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, title, due_at, status, created_at, completed_at "
            "FROM assistant_reminders WHERE username = %s "
            "AND status IN ('pending', 'notified') ORDER BY due_at ASC LIMIT %s",
            (owner, bounded),
        )
        return [
            {
                "id": row[0], "title": row[1], "due_at": _format_datetime(row[2]),
                "status": row[3], "created_at": _format_datetime(row[4]),
                "completed_at": _format_datetime(row[5]),
            }
            for row in cursor.fetchall()
        ]
    except Exception:
        logger.warning("Could not list reminders", exc_info=True)
        raise ReminderUnavailable("Reminders are temporarily unavailable. Please retry.") from None
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def set_notification_preferences(
    username: str,
    *,
    reminders_enabled: bool,
    browser_notifications_enabled: bool = False,
) -> dict[str, bool]:
    owner = _owner(username)
    if not isinstance(reminders_enabled, bool) or not isinstance(browser_notifications_enabled, bool):
        raise ReminderError("Notification preferences must be boolean values.")
    if browser_notifications_enabled and not reminders_enabled:
        raise ReminderError("Enable reminder alerts before enabling browser notifications.")
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO user_notification_preferences "
            "(username, reminders_enabled, browser_notifications_enabled) "
            "VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE "
            "reminders_enabled = VALUES(reminders_enabled), "
            "browser_notifications_enabled = VALUES(browser_notifications_enabled), "
            "updated_at = UTC_TIMESTAMP()",
            (owner, int(reminders_enabled), int(browser_notifications_enabled)),
        )
        connection.commit()
        return {
            "reminders_enabled": reminders_enabled,
            "browser_notifications_enabled": browser_notifications_enabled,
        }
    except Exception:
        logger.warning("Could not save notification preferences", exc_info=True)
        raise ReminderUnavailable("Notification preferences are temporarily unavailable. Please retry.") from None
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def get_notification_preferences(username: str) -> dict[str, bool]:
    owner = _owner(username)
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT reminders_enabled, browser_notifications_enabled "
            "FROM user_notification_preferences WHERE username = %s",
            (owner,),
        )
        row = cursor.fetchone()
        return {
            "reminders_enabled": bool(row[0]) if row else False,
            "browser_notifications_enabled": bool(row[1]) if row else False,
        }
    except Exception:
        logger.warning("Could not load notification preferences", exc_info=True)
        raise ReminderUnavailable("Notification preferences are temporarily unavailable. Please retry.") from None
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def collect_due_notifications(username: str, limit: int = 20) -> list[dict[str, Any]]:
    """Create and return each due reminder notification exactly once per user."""
    owner = _owner(username)
    preferences = get_notification_preferences(owner)
    if not preferences["reminders_enabled"]:
        return []
    bounded = max(1, min(int(limit), 50))
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, title FROM assistant_reminders "
            "WHERE username = %s AND status = 'pending' AND due_at <= UTC_TIMESTAMP() "
            "ORDER BY due_at ASC LIMIT %s FOR UPDATE",
            (owner, bounded),
        )
        due = cursor.fetchall()
        for reminder_id, title in due:
            cursor.execute(
                "INSERT IGNORE INTO assistant_notifications "
                "(username, reminder_id, title, body, created_at) "
                "VALUES (%s, %s, %s, %s, UTC_TIMESTAMP())",
                (owner, reminder_id, "AJARVIS reminder", title),
            )
            cursor.execute(
                "UPDATE assistant_reminders SET status = 'notified', updated_at = UTC_TIMESTAMP() "
                "WHERE id = %s AND username = %s AND status = 'pending'",
                (reminder_id, owner),
            )
        cursor.execute(
            "SELECT id, title, body, created_at FROM assistant_notifications "
            "WHERE username = %s AND presented_at IS NULL AND read_at IS NULL "
            "ORDER BY id ASC LIMIT %s",
            (owner, bounded),
        )
        rows = cursor.fetchall()
        notifications = [
            {
                "id": row[0], "title": row[1], "body": row[2],
                "created_at": _format_datetime(row[3]),
            }
            for row in rows
        ]
        for notification in notifications:
            cursor.execute(
                "UPDATE assistant_notifications SET presented_at = UTC_TIMESTAMP() "
                "WHERE id = %s AND username = %s AND presented_at IS NULL",
                (notification["id"], owner),
            )
        connection.commit()
        return notifications
    except Exception:
        logger.warning("Could not collect due reminder notifications", exc_info=True)
        if connection is not None:
            try: connection.rollback()
            except Exception: pass
        raise ReminderUnavailable("Reminder alerts are temporarily unavailable. Please retry.") from None
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def list_unread_notifications(username: str, limit: int = 30) -> list[dict[str, Any]]:
    owner = _owner(username)
    bounded = max(1, min(int(limit), 100))
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, title, body, created_at FROM assistant_notifications "
            "WHERE username = %s AND read_at IS NULL ORDER BY id DESC LIMIT %s",
            (owner, bounded),
        )
        return [
            {"id": row[0], "title": row[1], "body": row[2], "created_at": _format_datetime(row[3])}
            for row in cursor.fetchall()
        ]
    except Exception:
        logger.warning("Could not list notifications", exc_info=True)
        raise ReminderUnavailable("Notifications are temporarily unavailable. Please retry.") from None
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def mark_notification_read(username: str, notification_id: int) -> bool:
    owner = _owner(username)
    if isinstance(notification_id, bool) or not isinstance(notification_id, int) or notification_id < 1:
        raise ReminderError("Notification ID is invalid.")
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE assistant_notifications SET read_at = UTC_TIMESTAMP() "
            "WHERE id = %s AND username = %s AND read_at IS NULL",
            (notification_id, owner),
        )
        changed = bool(cursor.rowcount)
        connection.commit()
        return changed
    except Exception:
        logger.warning("Could not mark notification as read", exc_info=True)
        raise ReminderUnavailable("Notification updates are temporarily unavailable. Please retry.") from None
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def update_reminder_status(username: str, reminder_id: int, status: str) -> bool:
    owner = _owner(username)
    if isinstance(reminder_id, bool) or not isinstance(reminder_id, int) or reminder_id < 1:
        raise ReminderError("Reminder ID is invalid.")
    if status not in {"completed", "cancelled"}:
        raise ReminderError("Unsupported reminder status.")
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE assistant_reminders SET status = %s, "
            "completed_at = IF(%s = 'completed', UTC_TIMESTAMP(), completed_at), "
            "updated_at = UTC_TIMESTAMP() WHERE id = %s AND username = %s "
            "AND status IN ('pending', 'notified')",
            (status, status, reminder_id, owner),
        )
        changed = bool(cursor.rowcount)
        connection.commit()
        return changed
    except Exception:
        logger.warning("Could not update reminder", exc_info=True)
        raise ReminderUnavailable("Reminder updates are temporarily unavailable. Please retry.") from None
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass
