"""User-scoped projects, tasks and transparent personal prioritisation.

Scores are deterministic and explainable. The service does not infer sensitive
attributes, modify task priority automatically, or treat project text as commands.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import logging
import re
from typing import Any

from database.db import get_connection

logger = logging.getLogger(__name__)

MAX_PROJECTS = 30
MAX_TASKS = 200
MAX_TITLE = 180
_SECRET_RE = re.compile(
    r"\b(?:password|passcode|api[\s_-]*key|access[\s_-]*token|secret|private[\s_-]*key)\b",
    re.IGNORECASE,
)
_PRIORITIES = {"low": 20, "normal": 35, "high": 55, "urgent": 70}
_PROJECT_STATUSES = {"active", "paused", "completed", "archived"}
_TASK_STATUSES = {"pending", "in_progress", "completed", "cancelled"}


class PersonalIntelligenceError(ValueError):
    """Raised when project/task input or ownership is invalid."""


def _owner(username: str) -> str:
    if not isinstance(username, str) or not username.strip() or len(username.strip()) > 100:
        raise PersonalIntelligenceError("A valid signed-in username is required.")
    return username.strip()


def _safe_text(value: Any, label: str, maximum: int, *, optional: bool = False) -> str:
    if optional and value is None:
        return ""
    if not isinstance(value, str):
        raise PersonalIntelligenceError(f"{label} must be text.")
    text = value.strip()
    if (not text and not optional) or len(text) > maximum:
        raise PersonalIntelligenceError(f"{label} must contain 1–{maximum} characters.")
    if text and _SECRET_RE.search(text):
        raise PersonalIntelligenceError("Do not store credentials or secrets in project or task details.")
    return text


def _parse_due_at(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise PersonalIntelligenceError("Due date must be an ISO 8601 date/time with a timezone.")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise PersonalIntelligenceError("Due date must be a valid ISO 8601 date/time.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PersonalIntelligenceError("Due date must include a timezone offset.")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _connection():
    return get_connection()


def create_project(username: str, name: str, objective: str = "") -> dict[str, Any]:
    owner = _owner(username)
    project_name = _safe_text(name, "Project name", MAX_TITLE)
    project_objective = _safe_text(objective, "Project objective", 500, optional=True)
    connection = cursor = None
    try:
        connection = _connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO assistant_projects (username, name, objective, status) "
            "VALUES (%s, %s, %s, 'active')",
            (owner, project_name, project_objective),
        )
        project_id = int(cursor.lastrowid)
        connection.commit()
        return {
            "id": project_id, "name": project_name, "objective": project_objective,
            "status": "active",
        }
    except PersonalIntelligenceError:
        raise
    except Exception as exc:
        if connection is not None:
            try: connection.rollback()
            except Exception: pass
        logger.warning("Could not create personal project", exc_info=True)
        raise PersonalIntelligenceError("Project could not be saved. Check the database migration.") from exc
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def list_projects(username: str, limit: int = MAX_PROJECTS) -> list[dict[str, Any]]:
    owner = _owner(username)
    try:
        bounded = max(1, min(int(limit), MAX_PROJECTS))
    except (TypeError, ValueError):
        bounded = MAX_PROJECTS
    connection = cursor = None
    try:
        connection = _connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, name, objective, status, created_at, updated_at "
            "FROM assistant_projects WHERE username = %s "
            "ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END, updated_at DESC "
            "LIMIT %s",
            (owner, bounded),
        )
        return [
            {
                "id": row[0], "name": row[1], "objective": row[2] or "",
                "status": row[3], "created_at": _format_datetime(row[4]),
                "updated_at": _format_datetime(row[5]),
            }
            for row in cursor.fetchall()
        ]
    except Exception as exc:
        logger.warning("Could not list personal projects", exc_info=True)
        raise PersonalIntelligenceError("Projects are temporarily unavailable.") from exc
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def update_project_status(username: str, project_id: int, status: str) -> bool:
    owner = _owner(username)
    if isinstance(project_id, bool) or not isinstance(project_id, int) or project_id < 1:
        raise PersonalIntelligenceError("Project ID is invalid.")
    if status not in _PROJECT_STATUSES:
        raise PersonalIntelligenceError("Unsupported project status.")
    connection = cursor = None
    try:
        connection = _connection()
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE assistant_projects SET status = %s, updated_at = UTC_TIMESTAMP() "
            "WHERE id = %s AND username = %s",
            (status, project_id, owner),
        )
        changed = bool(cursor.rowcount)
        connection.commit()
        return changed
    except Exception as exc:
        logger.warning("Could not update project status", exc_info=True)
        raise PersonalIntelligenceError("Project could not be updated.") from exc
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def create_task(
    username: str,
    title: str,
    *,
    project_id: int | None = None,
    details: str = "",
    priority: str = "normal",
    due_at: str | None = None,
    effort_minutes: int | None = None,
) -> dict[str, Any]:
    owner = _owner(username)
    task_title = _safe_text(title, "Task title", MAX_TITLE)
    task_details = _safe_text(details, "Task details", 500, optional=True)
    if priority not in _PRIORITIES:
        raise PersonalIntelligenceError("Priority must be low, normal, high, or urgent.")
    due = _parse_due_at(due_at)
    if project_id is not None and (
        isinstance(project_id, bool) or not isinstance(project_id, int) or project_id < 1
    ):
        raise PersonalIntelligenceError("Project ID is invalid.")
    if effort_minutes is not None and (
        isinstance(effort_minutes, bool) or not isinstance(effort_minutes, int)
        or not 5 <= effort_minutes <= 480
    ):
        raise PersonalIntelligenceError("Estimated effort must be between 5 and 480 minutes.")
    connection = cursor = None
    try:
        connection = _connection()
        cursor = connection.cursor()
        if project_id is not None:
            cursor.execute(
                "SELECT id FROM assistant_projects WHERE id = %s AND username = %s AND status = 'active'",
                (project_id, owner),
            )
            if not cursor.fetchone():
                raise PersonalIntelligenceError("The selected active project was not found.")
        cursor.execute(
            "INSERT INTO assistant_tasks "
            "(username, project_id, title, details, priority, due_at, effort_minutes, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')",
            (owner, project_id, task_title, task_details, priority, due, effort_minutes),
        )
        task_id = int(cursor.lastrowid)
        connection.commit()
        task = {
            "id": task_id, "project_id": project_id, "title": task_title,
            "details": task_details, "priority": priority,
            "due_at": _format_datetime(due), "effort_minutes": effort_minutes,
            "status": "pending",
        }
        return score_task(task)
    except PersonalIntelligenceError:
        if connection is not None:
            try: connection.rollback()
            except Exception: pass
        raise
    except Exception as exc:
        if connection is not None:
            try: connection.rollback()
            except Exception: pass
        logger.warning("Could not create personal task", exc_info=True)
        raise PersonalIntelligenceError("Task could not be saved. Check the database migration.") from exc
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def _due_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
    if isinstance(value, str):
        raw = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def score_task(task: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Add an explainable 0–100 score without mutating stored task priority."""
    result = dict(task)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    score = _PRIORITIES.get(str(result.get("priority", "normal")).lower(), _PRIORITIES["normal"])
    reasons = [f"User-selected priority: {result.get('priority', 'normal')}."]
    due = _due_datetime(result.get("due_at"))
    if due is not None:
        hours_left = (due - current).total_seconds() / 3600
        if hours_left < 0:
            score += 25
            reasons.append("Overdue: move this task up for review.")
        elif hours_left <= 24:
            score += 25
            reasons.append("Due within 24 hours.")
        elif hours_left <= 72:
            score += 18
            reasons.append("Due within three days.")
        elif hours_left <= 168:
            score += 12
            reasons.append("Due within seven days.")
        elif hours_left <= 720:
            score += 6
            reasons.append("Due within 30 days.")
    effort = result.get("effort_minutes")
    if isinstance(effort, int) and not isinstance(effort, bool) and 0 < effort <= 30:
        score += 5
        reasons.append("Quick win: estimated at 30 minutes or less.")
    if result.get("status") == "in_progress":
        score += 3
        reasons.append("Already in progress.")
    result["priority_score"] = min(100, score)
    result["priority_reason"] = " ".join(reasons)
    result["due_at"] = _format_datetime(result.get("due_at"))
    return result


def list_tasks(username: str, *, limit: int = MAX_TASKS, include_completed: bool = False) -> list[dict[str, Any]]:
    owner = _owner(username)
    try:
        bounded = max(1, min(int(limit), MAX_TASKS))
    except (TypeError, ValueError):
        bounded = MAX_TASKS
    statuses = ("pending", "in_progress", "completed", "cancelled") if include_completed else ("pending", "in_progress")
    placeholders = ", ".join(["%s"] * len(statuses))
    connection = cursor = None
    try:
        connection = _connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT t.id, t.project_id, p.name, t.title, t.details, t.priority, "
            "t.due_at, t.effort_minutes, t.status, t.created_at, t.updated_at "
            "FROM assistant_tasks t LEFT JOIN assistant_projects p "
            "ON p.id = t.project_id AND p.username = t.username "
            f"WHERE t.username = %s AND t.status IN ({placeholders}) "
            "ORDER BY t.created_at DESC LIMIT %s",
            (owner, *statuses, bounded),
        )
        rows = [
            {
                "id": row[0], "project_id": row[1], "project_name": row[2],
                "title": row[3], "details": row[4] or "", "priority": row[5],
                "due_at": _format_datetime(row[6]), "effort_minutes": row[7],
                "status": row[8], "created_at": _format_datetime(row[9]),
                "updated_at": _format_datetime(row[10]),
            }
            for row in cursor.fetchall()
        ]
        return sorted(
            (score_task(row) for row in rows),
            key=lambda item: (
                -item["priority_score"],
                item["due_at"] is None,
                item["due_at"] or "",
                item["id"],
            ),
        )
    except Exception as exc:
        logger.warning("Could not list personal tasks", exc_info=True)
        raise PersonalIntelligenceError("Tasks are temporarily unavailable.") from exc
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def update_task_status(username: str, task_id: int, status: str) -> bool:
    owner = _owner(username)
    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1:
        raise PersonalIntelligenceError("Task ID is invalid.")
    if status not in _TASK_STATUSES:
        raise PersonalIntelligenceError("Unsupported task status.")
    connection = cursor = None
    try:
        connection = _connection()
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE assistant_tasks SET status = %s, "
            "completed_at = IF(%s = 'completed', UTC_TIMESTAMP(), NULL), "
            "updated_at = UTC_TIMESTAMP() WHERE id = %s AND username = %s "
            "AND status IN ('pending', 'in_progress')",
            (status, status, task_id, owner),
        )
        changed = bool(cursor.rowcount)
        connection.commit()
        return changed
    except Exception as exc:
        logger.warning("Could not update task status", exc_info=True)
        raise PersonalIntelligenceError("Task could not be updated.") from exc
    finally:
        if cursor is not None:
            try: cursor.close()
            except Exception: pass
        if connection is not None:
            try: connection.close()
            except Exception: pass


def build_personal_focus(username: str, *, now: datetime | None = None) -> dict[str, Any]:
    owner = _owner(username)
    projects = list_projects(owner, limit=MAX_PROJECTS)
    tasks = list_tasks(owner, limit=MAX_TASKS)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    overdue = [
        task for task in tasks
        if (due := _due_datetime(task.get("due_at"))) is not None
        and due < current.astimezone(timezone.utc)
    ]
    return {
        "active_projects": [project for project in projects if project["status"] == "active"],
        "next_tasks": tasks[:5],
        "metrics": {
            "active_projects": sum(project["status"] == "active" for project in projects),
            "open_tasks": len(tasks),
            "overdue_tasks": len(overdue),
            "in_progress_tasks": sum(task["status"] == "in_progress" for task in tasks),
        },
        "prioritisation": (
            "Score uses user-selected priority, due-date urgency, a small quick-win bonus, "
            "and a small in-progress bonus. It is a suggestion, not an automatic task change."
        ),
    }
