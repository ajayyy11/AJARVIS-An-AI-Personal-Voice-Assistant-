"""Privacy-minimal per-user automation activity log.

Activity records store tool identifiers and status summaries only; they never
store arguments, URLs, note contents, model prompts, or tool outputs.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
import uuid
from typing import Any

from database.db import get_connection

PROCESS_INSTANCE_ID = uuid.uuid4().hex

logger = logging.getLogger(__name__)


def record_activity(
    *,
    username: str,
    plan_id: str,
    step_number: int | None,
    event_type: str,
    tool_name: str | None,
    summary: str,
    workflow_status: str | None = None,
    step_count: int | None = None,
    tools_summary: str = "",
    process_instance_id: str | None = None,
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
        if workflow_status is not None:
            cursor.execute(
                "INSERT INTO automation_workflows "
                "(plan_id, username, status, step_count, tools_summary, process_instance_id, "
                "created_at, updated_at, finished_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, UTC_TIMESTAMP(), UTC_TIMESTAMP(), "
                "IF(%s IN ('completed', 'cancelled', 'failed', 'expired', 'interrupted'), UTC_TIMESTAMP(), NULL)) "
                "ON DUPLICATE KEY UPDATE status = VALUES(status), "
                "step_count = VALUES(step_count), tools_summary = VALUES(tools_summary), "
                "process_instance_id = VALUES(process_instance_id), updated_at = UTC_TIMESTAMP(), "
                "finished_at = IF(VALUES(status) IN ('completed', 'cancelled', 'failed', 'expired', 'interrupted'), "
                "UTC_TIMESTAMP(), NULL)",
                (
                    plan_id, username, workflow_status, int(step_count or 0),
                    (tools_summary or "")[:320], process_instance_id or PROCESS_INSTANCE_ID,
                    workflow_status,
                ),
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


def list_recent_workflows(username: str, limit: int = 30) -> list[dict[str, Any]]:
    """Return durable workflow metadata without storing prompts or tool arguments."""
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
            "SELECT plan_id, status, step_count, tools_summary, created_at, updated_at, finished_at "
            "FROM automation_workflows WHERE username = %s "
            "ORDER BY updated_at DESC LIMIT %s",
            (username.strip(), bounded),
        )
        output = []
        for row in cursor.fetchall():
            output.append({
                "plan_id": row[0],
                "status": row[1],
                "step_count": int(row[2] or 0),
                "tools": row[3] or "",
                "created_at": _timestamp(row[4]),
                "updated_at": _timestamp(row[5]),
                "finished_at": _timestamp(row[6]),
            })
        return output
    except Exception:
        logger.warning("Could not read automation workflow history", exc_info=True)
        return []
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, (datetime, date)) else str(value)


def recover_interrupted_workflows(process_instance_id: str | None = None) -> int:
    """Mark unfinished workflows from older app processes as interrupted.

    The execution arguments and approval tokens are intentionally not persisted,
    so interrupted plans are review-only and must be planned again.
    """
    current_id = process_instance_id or PROCESS_INSTANCE_ID
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE automation_workflows SET status = 'interrupted', "
            "updated_at = UTC_TIMESTAMP(), finished_at = UTC_TIMESTAMP() "
            "WHERE process_instance_id <> %s "
            "AND status IN ('ready', 'running', 'awaiting_approval', 'executing')",
            (current_id,),
        )
        changed = int(getattr(cursor, "rowcount", 0) or 0)
        connection.commit()
        return changed
    except Exception:
        logger.warning("Could not recover interrupted automation workflows", exc_info=True)
        return 0
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass
