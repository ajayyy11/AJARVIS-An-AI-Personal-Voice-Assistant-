"""Database-backed command history with a bounded local fallback cache."""

import logging
from threading import RLock

from database.db import get_connection

logger = logging.getLogger(__name__)

MAX_MEMORY = 50
_cache = []
_cache_lock = RLock()


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
            logger.debug("Unable to close memory cursor", exc_info=True)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            logger.debug("Unable to close memory connection", exc_info=True)


def _cache_snapshot(n, newest_first=False):
    with _cache_lock:
        entries = list(_cache[-n:]) if n else []
    return list(reversed(entries)) if newest_first else entries


def add_memory(command, response):
    """Persist a command/response pair and retain it in the fallback cache."""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO command_history (command, response) VALUES (%s, %s)",
            (command, response),
        )
        conn.commit()
    except Exception:
        # Do not log command contents, which may contain personal information.
        logger.warning("Memory database write failed; using local cache", exc_info=True)
    finally:
        _close_resources(cursor, conn)

    with _cache_lock:
        _cache.append({"command": command, "response": response})
        if len(_cache) > MAX_MEMORY:
            del _cache[:-MAX_MEMORY]


def get_recent(n=5):
    """Return recent history oldest-first for chronological AI context."""
    limit = _normalise_limit(n, 5)
    if limit == 0:
        return []

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT command, response FROM command_history ORDER BY id DESC LIMIT %s",
            (limit,),
        )
        rows = cursor.fetchall()
        return [{"command": row[0], "response": row[1]} for row in reversed(rows)]
    except Exception:
        logger.warning("Memory database read failed; using local cache", exc_info=True)
        return _cache_snapshot(limit)
    finally:
        _close_resources(cursor, conn)


def get_all_recent(n=20):
    """Return recent dashboard history newest-first."""
    limit = _normalise_limit(n, 20)
    if limit == 0:
        return []

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT command, response FROM command_history ORDER BY id DESC LIMIT %s",
            (limit,),
        )
        rows = cursor.fetchall()
        return [{"command": row[0], "response": row[1]} for row in rows]
    except Exception:
        logger.warning("Dashboard history read failed; using local cache", exc_info=True)
        return _cache_snapshot(limit, newest_first=True)
    finally:
        _close_resources(cursor, conn)
