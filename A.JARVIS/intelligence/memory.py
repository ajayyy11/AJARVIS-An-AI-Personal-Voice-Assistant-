"""User-scoped command history with a bounded local fallback cache."""

import logging
import re
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
            _safe_history_record(entry["command"], entry["response"])
            for entry in _cache
            if entry["username"] == username
        ][-n:] if n else []

    return list(reversed(entries)) if newest_first else entries


_PRIVATE_HISTORY_PREFIX = re.compile(
    r"^\s*(?:(?:hey|hi|hello|okay|ok)\s+)?"
    r"(?:a\.?\s*j\.?\s*a\.?\s*r\.?\s*v\.?\s*i\.?\s*s\.?|"
    r"j\.?\s*a\.?\s*r\.?\s*v\.?\s*i\.?\s*s\.?|ajarvis|jarvis)"
    r"[\s,.:;!?-]*",
    re.IGNORECASE,
)
_PRIVATE_HISTORY_COMMAND = re.compile(
    r"^(?:"
    r"remember(?:\s+that)?|note\s+that|"
    r"don't\s+forget(?:\s+that)?|do\s+not\s+forget(?:\s+that)?|"
    r"save\s+to\s+memory|"
    r"(?:take|make|save|write|create)(?:\s+down)?\s+(?:a\s+)?note(?:\s+that)?|"
    r"forget|remove\s+from\s+memory"
    r")\b"
    r"|^(?:what\s+do\s+you\s+remember|what\s+did\s+i\s+ask\s+you\s+to\s+remember|show\s+my\s+memories|list\s+my\s+memories|"
    r"read\s+my\s+preferences|what\s+are\s+(?:my\s+)?(?:saved\s+)?notes?|"
    r"(?:read|show|list|display|search|find|tell)\s+(?:me\s+)?(?:my\s+)?notes?|"
    r"(?:add|create|make)\s+(?:a\s+)?task|"
    r"(?:remind\s+me\s+to|don't\s+let\s+me\s+forget\s+to|do\s+not\s+let\s+me\s+forget\s+to)|"
    r"(?:show|list|read|tell)\s+(?:me\s+)?(?:my\s+)?tasks|"
    r"what\s+(?:are\s+)?(?:my\s+)?tasks|"
    r"what(?:'s|\s+is)\s+on\s+my\s+(?:task\s+list|agenda))\b",
    re.IGNORECASE,
)
PRIVATE_HISTORY_COMMAND = "[private command redacted]"
PRIVATE_HISTORY_RESPONSE = "[private response redacted]"


def is_sensitive_history_command(command):
    """Identify commands whose text or response can contain private notes/facts."""
    if not isinstance(command, str):
        return False
    normalized = _PRIVATE_HISTORY_PREFIX.sub("", command.strip(), count=1).strip()
    return bool(_PRIVATE_HISTORY_COMMAND.search(normalized))


def _safe_history_record(command, response):
    """Hide sensitive legacy rows at read time until the cleanup migration is run."""
    if is_sensitive_history_command(command):
        return {"command": PRIVATE_HISTORY_COMMAND, "response": PRIVATE_HISTORY_RESPONSE}
    return {"command": command, "response": response}


def add_memory(command, response, username, *, private: bool = False):
    """Persist user-scoped history, with explicit private-intent redaction.

    The private flag is supplied by command handlers that know the semantic
    intent. The classifier remains a defence-in-depth layer for legacy callers,
    cloud commands and historical records.
    """
    if not isinstance(username, str) or not username.strip():
        raise ValueError("A username is required to store command history.")
    if not isinstance(private, bool):
        raise ValueError("The private history flag must be a boolean.")
    username = username.strip()
    if private or is_sensitive_history_command(command):
        command = PRIVATE_HISTORY_COMMAND
        response = PRIVATE_HISTORY_RESPONSE

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
        return [_safe_history_record(row[0], row[1]) for row in reversed(rows)]
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
        return [_safe_history_record(row[0], row[1]) for row in rows]
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
        return [_safe_history_record(row[0], row[1]) for row in reversed(rows)]
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
        return [_safe_history_record(row[0], row[1]) for row in rows]
    except Exception:
        logger.warning("Conversation history display failed.", exc_info=True)
        raise RuntimeError("Conversation history is temporarily unavailable.") from None
    finally:
        _close_resources(cursor, conn)


def get_history_page(n=30, username=None, before_id=None):
    """Return one newest-first history page with durable IDs for older-page cursors.

    A database-backed page is required here: process-local fallback entries have
    no durable IDs and cannot safely support a cross-request pagination cursor.
    """
    if not isinstance(username, str) or not username.strip():
        return []
    username = username.strip()
    limit = _normalise_limit(n, 30)
    if limit == 0:
        return []
    cursor_id = None if before_id is None else _normalise_after_id(before_id)

    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if cursor_id is None:
            cursor.execute(
                "SELECT id, command, response FROM command_history "
                "WHERE username = %s ORDER BY id DESC LIMIT %s",
                (username, limit),
            )
        else:
            cursor.execute(
                "SELECT id, command, response FROM command_history "
                "WHERE username = %s AND id < %s ORDER BY id DESC LIMIT %s",
                (username, cursor_id, limit),
            )
        rows = cursor.fetchall()
        return [
            {"id": int(row[0]), **_safe_history_record(row[1], row[2])}
            for row in rows
        ]
    except Exception:
        logger.warning("Paginated history read failed; refusing to return an incomplete page.", exc_info=True)
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
