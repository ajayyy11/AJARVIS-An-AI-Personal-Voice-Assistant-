"""Privacy-minimal per-user automation activity log.

Activity records store tool identifiers and status summaries only; they never
store arguments, URLs, note contents, model prompts, or tool outputs.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from database.db import get_connection

logger = logging.getLogger(__name__)


def record_activity(
    *,
    username: str,
    plan_id: str,
    step_number: int | None,
    event_type: str,
    tool_name: str | None,
    summary: str,
) -> bool:
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO automation_activity "
            "(username, plan_id, step_number, event_type, tool_name, summary) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (username, plan_id, step_number, event_type, tool_name, summary[:240]),
        )
        connection.commit()
        return True
    except Exception:
        logger.warning("Could not persist automation activity", exc_info=True)
        return False
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def list_recent_activity(username: str, limit: int = 30) -> list[dict[str, Any]]:
    if not isinstance(username, str) or not username.strip():
        return []
    try:
        bounded = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        bounded = 30
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, plan_id, step_number, event_type, tool_name, summary, created_at "
            "FROM automation_activity WHERE username = %s "
            "ORDER BY id DESC LIMIT %s",
            (username.strip(), bounded),
        )
        output = []
        for row in cursor.fetchall():
            stamp = row[6].isoformat() if isinstance(row[6], (datetime, date)) else str(row[6])
            output.append({
                "id": row[0], "plan_id": row[1], "step_number": row[2],
                "event_type": row[3], "tool_name": row[4],
                "summary": row[5], "created_at": stamp,
            })
        return output
    except Exception:
        logger.warning("Could not read automation activity", exc_info=True)
        return []
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass
