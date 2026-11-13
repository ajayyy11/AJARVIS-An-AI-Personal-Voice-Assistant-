import sys
import types

import pytest

from database import db


class FakePostgresPool:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.opened = False
        self.closed = False
        self.connection = object()
        self.instances.append(self)

    def open(self, *, wait, timeout):
        self.opened = (wait, timeout)

    def getconn(self, *, timeout):
        self.request_timeout = timeout
        return self.connection

    def close(self):
        self.closed = True


def test_postgres_connections_use_bounded_reusable_pool(monkeypatch):
    FakePostgresPool.instances.clear()
    monkeypatch.setattr(db, "_postgres_pool", None)
    monkeypatch.setattr(db.Config, "DATABASE_URL", "postgres://test:secret@db.invalid/app")
    monkeypatch.setattr(db.Config, "DATABASE_POOL_MAX_SIZE", 3)
    monkeypatch.setattr(db.Config, "DATABASE_POOL_TIMEOUT_SECONDS", 7)

    fake_module = types.ModuleType("psycopg_pool")
    fake_module.ConnectionPool = FakePostgresPool
    monkeypatch.setitem(sys.modules, "psycopg_pool", fake_module)

    first = db.get_connection()
    second = db.get_connection()

    pool = FakePostgresPool.instances[-1]
    assert first is second is pool.connection
    assert pool.kwargs["conninfo"] == "postgresql://test:secret@db.invalid/app"
    assert pool.kwargs["min_size"] == 1
    assert pool.kwargs["max_size"] == 3
    assert pool.kwargs["max_waiting"] == 12
    assert pool.kwargs["close_returns"] is True
    assert pool.opened == (True, 7)
    assert pool.request_timeout == 7

    db.close_pools()
    assert pool.closed is True


def test_postgres_pool_initialization_failure_closes_partial_pool(monkeypatch):
    FakePostgresPool.instances.clear()
    monkeypatch.setattr(db, "_postgres_pool", None)
    monkeypatch.setattr(db.Config, "DATABASE_URL", "postgresql://db.invalid/app")

    class FailingPool(FakePostgresPool):
        def open(self, *, wait, timeout):
            raise TimeoutError("connection attempt failed")

    fake_module = types.ModuleType("psycopg_pool")
    fake_module.ConnectionPool = FailingPool
    monkeypatch.setitem(sys.modules, "psycopg_pool", fake_module)

    with pytest.raises(RuntimeError, match="unavailable or exhausted"):
        db.get_connection()

    assert FailingPool.instances[-1].closed is True
    assert db._postgres_pool is None
