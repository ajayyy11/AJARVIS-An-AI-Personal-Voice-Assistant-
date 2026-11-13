"""Persistent, user-controlled facts and preferences for local AJARVIS.

Only explicitly saved memory is stored here. Values are bounded, private to the
signed-in username, and never treated as executable instructions.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import re
from typing import Any

from database.db import get_connection

MAX_MEMORIES = 30
MAX_KEY_LENGTH = 80
MAX_VALUE_LENGTH = 1000
_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")
_SECRET_RE = re.compile(
    r"\b(?:password|passcode|api[\s_-]*key|access[\s_-]*token|secret|private[\s_-]*key)\b",
    re.IGNORECASE,
)


def _username(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
        raise ValueError("A valid signed-in username is required.")
    return value.strip()


def normalize_memory_key(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Memory key must be text.")
    key = re.sub(r"\s+", "_", value.strip().lower())
    if not _KEY_RE.fullmatch(key):
        raise ValueError("Memory keys must be 2–80 characters and use letters, numbers, dots, underscores or hyphens.")
    return key


def validate_memory_value(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Memory value must be text.")
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_VALUE_LENGTH:
        raise ValueError(f"Memory values must contain 1–{MAX_VALUE_LENGTH} characters.")
    if _SECRET_RE.search(normalized):
        raise ValueError("Do not store passwords, API keys, tokens or other credentials in personal memory.")
    return normalized


def _close(cursor, connection):
    if cursor is not None:
        try: cursor.close()
        except Exception: pass
    if connection is not None:
        try: connection.close()
        except Exception: pass


def _json_value(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def list_memories(username: str, limit: int = MAX_MEMORIES) -> list[dict[str, str]]:
    owner = _username(username)
    if isinstance(limit, bool):
        limit = MAX_MEMORIES
    try:
        count = max(1, min(int(limit), MAX_MEMORIES))
    except (TypeError, ValueError):
        count = MAX_MEMORIES
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT memory_key, memory_value, updated_at FROM user_memories "
            "WHERE username = %s ORDER BY updated_at DESC, id DESC LIMIT %s",
            (owner, count),
        )
        return [
            {"key": row[0], "value": row[1], "updated_at": _json_value(row[2])}
            for row in cursor.fetchall()
        ]
    finally:
        _close(cursor, connection)


def save_memory(username: str, key: str, value: str) -> dict[str, str]:
    """Save or update a memory under a per-user MySQL advisory lock.

    The named lock serializes saves across worker threads/processes, so the
    per-user 30-record cap cannot be bypassed by concurrent SELECT-then-INSERTs.
    """
    owner = _username(username)
    memory_key = normalize_memory_key(key)
    memory_value = validate_memory_value(value)
    connection = cursor = None
    lock_name = "ajarvis_mem_" + hashlib.sha256(owner.casefold().encode("utf-8")).hexdigest()[:48]
    lock_acquired = False
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT GET_LOCK(%s, 5)", (lock_name,))
        lock_row = cursor.fetchone()
        lock_acquired = bool(lock_row and lock_row[0] == 1)
        if not lock_acquired:
            raise ValueError("Personal memory is busy. Please retry your save.")

        cursor.execute(
            "SELECT id FROM user_memories WHERE username = %s AND memory_key = %s",
            (owner, memory_key),
        )
        exists = cursor.fetchone()
        if exists:
            cursor.execute(
                "UPDATE user_memories SET memory_value = %s, updated_at = CURRENT_TIMESTAMP "
                "WHERE username = %s AND memory_key = %s",
                (memory_value, owner, memory_key),
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM user_memories WHERE username = %s", (owner,))
            count_row = cursor.fetchone()
            current_count = int(count_row[0]) if count_row else 0
            if current_count >= MAX_MEMORIES:
                raise ValueError(
                    f"Personal memory is limited to {MAX_MEMORIES} saved items. Delete an existing item before adding another."
                )
            cursor.execute(
                "INSERT INTO user_memories (username, memory_key, memory_value) VALUES (%s, %s, %s)",
                (owner, memory_key, memory_value),
            )
        connection.commit()
        return {"key": memory_key, "value": memory_value}
    except Exception:
        if connection is not None:
            try: connection.rollback()
            except Exception: pass
        raise
    finally:
        if lock_acquired and cursor is not None:
            try:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
                cursor.fetchone()
            except Exception:
                pass
        _close(cursor, connection)


def delete_memory(username: str, key: str) -> bool:
    owner = _username(username)
    memory_key = normalize_memory_key(key)
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM user_memories WHERE username = %s AND memory_key = %s",
            (owner, memory_key),
        )
        deleted = cursor.rowcount > 0
        connection.commit()
        return deleted
    except Exception:
        if connection is not None:
            try: connection.rollback()
            except Exception: pass
        raise
    finally:
        _close(cursor, connection)


def remember_fact(username: str, fact: str) -> dict[str, str]:
    """Save free-form explicitly requested memory under a deterministic key."""
    value = validate_memory_value(fact)
    digest = hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()[:16]
    return save_memory(username, "fact_" + digest, value)


def forget_matching_memory(username: str, phrase: str) -> int:
    """Delete only this user's entries containing an explicitly named phrase."""
    owner = _username(username)
    if not isinstance(phrase, str) or not phrase.strip():
        raise ValueError("Tell me which memory to forget.")
    target = phrase.strip().casefold()
    entries = list_memories(owner)
    matches = [entry["key"] for entry in entries if target in entry["key"].casefold()
               or target in entry["value"].casefold()]
    deleted = 0
    for key in matches:
        deleted += int(delete_memory(owner, key))
    return deleted


def search_memories(username: str, query: str, limit: int = 5) -> list[dict[str, str]]:
    owner = _username(username)
    if not isinstance(query, str) or not query.strip():
        raise ValueError("A non-empty memory search is required.")
    term = query.strip().casefold()
    return [
        entry for entry in list_memories(owner)
        if term in entry["key"].casefold() or term in entry["value"].casefold()
    ][:max(1, min(int(limit), 10))]
