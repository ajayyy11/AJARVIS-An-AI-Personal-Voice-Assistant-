"""Atomic, shared PostgreSQL rate limiting for the AJARVIS cloud service."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _open_connection(connection_factory: Callable[[], Any] | None):
    if connection_factory is not None:
        return connection_factory()
    from database.db import get_connection
    return get_connection()


def _validate(key: str, limit: int, window_seconds: int) -> None:
    if not isinstance(key, str) or len(key) != 64:
        raise ValueError("Rate-limit keys must be 64-character SHA-256 digests.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1_000_000:
        raise ValueError("Rate-limit limit must be between 1 and 1,000,000.")
    if (
        isinstance(window_seconds, bool)
        or not isinstance(window_seconds, int)
        or not 1 <= window_seconds <= 31_536_000
    ):
        raise ValueError("Rate-limit window must be between 1 second and one year.")


def consume_rate_limit(
    key: str,
    *,
    limit: int,
    window_seconds: int,
    connection_factory: Callable[[], Any] | None = None,
) -> bool:
    """Atomically consume a request slot; return True when the limit is exceeded.

    All limit state is stored in PostgreSQL, so multiple Gunicorn threads,
    processes and Render instances enforce the same budget. The key is already
    HMAC-derived by the caller; raw usernames and IP addresses are never stored.
    """
    _validate(key, limit, window_seconds)
    connection = cursor = None
    try:
        connection = _open_connection(connection_factory)
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO ajarvis_rate_limits
                (rate_key, window_started_at, request_count, expires_at)
            VALUES (
                %s,
                CURRENT_TIMESTAMP,
                1,
                CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
            )
            ON CONFLICT (rate_key) DO UPDATE SET
                window_started_at = CASE
                    WHEN ajarvis_rate_limits.window_started_at
                         <= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                    THEN CURRENT_TIMESTAMP
                    ELSE ajarvis_rate_limits.window_started_at
                END,
                request_count = CASE
                    WHEN ajarvis_rate_limits.window_started_at
                         <= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                    THEN 1
                    ELSE ajarvis_rate_limits.request_count + 1
                END,
                expires_at = CASE
                    WHEN ajarvis_rate_limits.window_started_at
                         <= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                    THEN CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
                    ELSE ajarvis_rate_limits.expires_at
                END
            RETURNING request_count
            """,
            (
                key,
                window_seconds,
                window_seconds,
                window_seconds,
                window_seconds,
                window_seconds,
            ),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("The database did not return the updated rate-limit counter.")
        exceeded = int(row[0]) > limit
        connection.commit()
        return exceeded
    except Exception:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        raise
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


def clear_rate_limit(
    key: str,
    *,
    connection_factory: Callable[[], Any] | None = None,
) -> None:
    """Remove one exact rate-limit key, typically after successful login."""
    if not isinstance(key, str) or len(key) != 64:
        raise ValueError("Rate-limit keys must be 64-character SHA-256 digests.")
    connection = cursor = None
    try:
        connection = _open_connection(connection_factory)
        cursor = connection.cursor()
        cursor.execute("DELETE FROM ajarvis_rate_limits WHERE rate_key = %s", (key,))
        connection.commit()
    except Exception:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        raise
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


def cleanup_expired_rate_limits(
    *,
    connection_factory: Callable[[], Any] | None = None,
) -> int:
    """Delete expired counters periodically so the shared table stays bounded."""
    connection = cursor = None
    try:
        connection = _open_connection(connection_factory)
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM ajarvis_rate_limits WHERE expires_at <= CURRENT_TIMESTAMP"
        )
        deleted = max(0, int(cursor.rowcount))
        connection.commit()
        return deleted
    except Exception:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        raise
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
