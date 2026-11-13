"""Database connection factory with bounded PostgreSQL and MySQL pools."""

from __future__ import annotations

import atexit
import os
import threading
from typing import Any

from config import Config

_pool_lock = threading.RLock()
_postgres_pool: Any = None
_mysql_pool: Any = None


def _postgres_connection_pool():
    """Return the process-local PostgreSQL pool, creating it only when needed."""
    global _postgres_pool

    database_url = Config.DATABASE_URL
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    with _pool_lock:
        if _postgres_pool is not None:
            return _postgres_pool

        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL is set but psycopg[pool] is not installed. "
                "Install the locked web requirements."
            ) from exc

        conninfo = database_url
        if conninfo.startswith("postgres://"):
            conninfo = "postgresql://" + conninfo[len("postgres://"):]

        pool = ConnectionPool(
            conninfo=conninfo,
            kwargs={"connect_timeout": Config.MYSQL_CONNECT_TIMEOUT_SECONDS},
            min_size=1,
            max_size=Config.DATABASE_POOL_MAX_SIZE,
            max_waiting=Config.DATABASE_POOL_MAX_SIZE * 4,
            timeout=Config.DATABASE_POOL_TIMEOUT_SECONDS,
            max_lifetime=1800,
            max_idle=120,
            open=False,
            close_returns=True,
        )
        try:
            pool.open(wait=True, timeout=Config.DATABASE_POOL_TIMEOUT_SECONDS)
        except Exception:
            pool.close()
            raise
        _postgres_pool = pool
        return _postgres_pool


def _mysql_connection_pool():
    """Return the process-local MySQL pool, creating it only when needed."""
    global _mysql_pool

    with _pool_lock:
        if _mysql_pool is not None:
            return _mysql_pool

        try:
            from mysql.connector.pooling import MySQLConnectionPool
        except ImportError as exc:
            raise RuntimeError(
                "MySQL is configured but mysql-connector-python is not installed."
            ) from exc

        pool = MySQLConnectionPool(
            pool_name=f"ajarvis_{os.getpid()}",
            pool_size=Config.DATABASE_POOL_MAX_SIZE,
            pool_reset_session=True,
            host=Config.MYSQL_HOST,
            port=Config.MYSQL_PORT,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB,
            connection_timeout=Config.MYSQL_CONNECT_TIMEOUT_SECONDS,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
            use_unicode=True,
            autocommit=False,
        )
        _mysql_pool = pool
        return _mysql_pool


def get_connection():
    """Borrow a connection; calling close() returns it to its pool."""
    if Config.DATABASE_URL:
        pool = _postgres_connection_pool()
        try:
            return pool.getconn(timeout=Config.DATABASE_POOL_TIMEOUT_SECONDS)
        except Exception as exc:
            raise RuntimeError(
                "PostgreSQL connection pool is unavailable or exhausted."
            ) from exc

    pool = _mysql_connection_pool()
    try:
        return pool.get_connection()
    except Exception as exc:
        raise RuntimeError(
            "MySQL connection pool is unavailable or exhausted."
        ) from exc


def close_pools() -> None:
    """Close PostgreSQL pools and release the MySQL pool manager reference.

    mysql-connector-python exposes no public close-all-pool API. Borrowed
    MySQL connections are returned normally by callers; process shutdown
    reclaims any remaining sockets.
    """
    global _postgres_pool, _mysql_pool

    with _pool_lock:
        postgres_pool, mysql_pool = _postgres_pool, _mysql_pool
        _postgres_pool = None
        _mysql_pool = None

    if postgres_pool is not None:
        postgres_pool.close()
    if mysql_pool is not None:
        # mysql.connector pools don't expose a public close-all operation.
        # Existing borrowed connections will close normally when returned.
        return


atexit.register(close_pools)
