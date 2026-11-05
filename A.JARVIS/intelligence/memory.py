"""User-scoped command history with a bounded local fallback cache."""

import logging
from threading import RLock

from database.db import get_connection

logger = logging.getLogger(__name__)

MAX_MEMORY = 50
_cache = []
_cache_lock = RLock()


def clear_user_memory(username):
    """Remove cached history for a user after account deletion or privacy cleanup."""
    if not isinstance(username, str) or not username.strip():
        return
    normalized = username.strip()
    with _cache_lock:
        _cache[:] = [entry for entry in _cache if entry.get("username") != normalized]


def _normalise_limit(value, default):
    """Return a safe query/cache limit bounded by the local cache size."""
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = default
    return max(0, min(limit, MAX_MEMORY))


def _close_resources(cursor, conn):
    """Close database resources even after a query or commit fails."""
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            logger.debug("Unable to close history cursor", exc_info=True)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            logger.debug("Unable to close history connection", exc_info=True)


def _cache_snapshot(n, username, newest_first=False):
    """Copy only this user's entries, with no shared-history fallback."""
    with _cache_lock:
        entries = [
            {"command": entry["command"], "response": entry["response"]}
            for entry in _cache
            if entry["username"] == username
        ][-n:] if n else []

    return list(reversed(entries)) if newest_first else entries


def add_memory(command, response, username):
    """Persist a command/response pair under the authenticated username."""
    if not isinstance(username, str) or not username.strip():
        raise ValueError("A username is required to store command history.")
    username = username.strip()

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO command_history (username, command, response) "
            "VALUES (%s, %s, %s)",
            (username, command, response),
        )
        conn.commit()
    except Exception:
        # Do not log command contents, which may contain personal information.
        # Existing databases must apply the user-scoping migration to persist rows.
        logger.warning("History database write failed; using user-scoped local cache", exc_info=True)
    finally:
        _close_resources(cursor, conn)

    with _cache_lock:
        _cache.append({
            "username": username,
            "command": command,
            "response": response,
        })
        if len(_cache) > MAX_MEMORY:
            del _cache[:-MAX_MEMORY]


def get_recent(n=5, username=None):
    """Return this user's recent history oldest-first for AI context."""
    if not isinstance(username, str) or not username.strip():
        return []
    username = username.strip()
    limit = _normalise_limit(n, 5)
    if limit == 0:
        return []

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT command, response FROM command_history "
            "WHERE username = %s ORDER BY id DESC LIMIT %s",
            (username, limit),
        )
        rows = cursor.fetchall()
        return [{"command": row[0], "response": row[1]} for row in reversed(rows)]
    except Exception:
        logger.warning("History database read failed; using user-scoped local cache", exc_info=True)
        return _cache_snapshot(limit, username)
    finally:
        _close_resources(cursor, conn)


def get_all_recent(n=20, username=None):
    """Return this user's recent dashboard history newest-first."""
    if not isinstance(username, str) or not username.strip():
        return []
    username = username.strip()
    limit = _normalise_limit(n, 20)
    if limit == 0:
        return []

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT command, response FROM command_history "
            "WHERE username = %s ORDER BY id DESC LIMIT %s",
            (username, limit),
        )
        rows = cursor.fetchall()
        return [{"command": row[0], "response": row[1]} for row in rows]
    except Exception:
        logger.warning("Dashboard history read failed; using user-scoped local cache", exc_info=True)
        return _cache_snapshot(limit, username, newest_first=True)
    finally:
        _close_resources(cursor, conn)


def _normalise_after_id(value):
    """Validate a persisted history cursor before using it in a scoped query."""
    if isinstance(value, bool):
        raise ValueError("History cursor must be a non-negative integer.")
    try:
        after_id = int(value)
    except (TypeError, ValueError):
        raise ValueError("History cursor must be a non-negative integer.") from None
    if after_id < 0:
        raise ValueError("History cursor must be a non-negative integer.")
    return after_id


def get_recent_after(n=5, username=None, after_id=0):
    """Return this user's conversation entries after a history cursor, oldest-first.

    Unlike the general history readers, this deliberately does not fall back to
    the process cache: cached entries have no durable database IDs and cannot be
    safely separated by conversation boundary.
    """
    if not isinstance(username, str) or not username.strip():
        return []
    username = username.strip()
    limit = _normalise_limit(n, 5)
    if limit == 0:
        return []
    cursor_id = _normalise_after_id(after_id)

    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT command, response FROM command_history "
            "WHERE username = %s AND id > %s ORDER BY id DESC LIMIT %s",
            (username, cursor_id, limit),
        )
        rows = cursor.fetchall()
        return [{"command": row[0], "response": row[1]} for row in reversed(rows)]
    except Exception:
        logger.warning("Conversation history read failed; refusing to reuse older context.", exc_info=True)
        raise RuntimeError("Conversation history is temporarily unavailable.") from None
    finally:
        _close_resources(cursor, conn)


def get_all_recent_after(n=30, username=None, after_id=0):
    """Return this user's recent entries after a conversation cursor, newest-first."""
    if not isinstance(username, str) or not username.strip():
        return []
    username = username.strip()
    limit = _normalise_limit(n, 30)
    if limit == 0:
        return []
    cursor_id = _normalise_after_id(after_id)

    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT command, response FROM command_history "
            "WHERE username = %s AND id > %s ORDER BY id DESC LIMIT %s",
            (username, cursor_id, limit),
        )
        rows = cursor.fetchall()
        return [{"command": row[0], "response": row[1]} for row in rows]
    except Exception:
        logger.warning("Conversation history display failed.", exc_info=True)
        raise RuntimeError("Conversation history is temporarily unavailable.") from None
    finally:
        _close_resources(cursor, conn)


def get_latest_id(username=None):
    """Return the latest durable command-history ID for this signed-in user."""
    if not isinstance(username, str) or not username.strip():
        return 0
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(MAX(id), 0) FROM command_history WHERE username = %s",
            (username.strip(),),
        )
        row = cursor.fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:
        logger.warning("Could not determine the conversation history boundary.", exc_info=True)
        raise RuntimeError("Conversation history is temporarily unavailable.") from None
    finally:
        _close_resources(cursor, conn)
