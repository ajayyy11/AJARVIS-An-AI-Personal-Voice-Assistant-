import intelligence.memory as memory


class FakeCursor:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.executed = None
        self.closed = False

    def execute(self, query, params=None):
        if self.error:
            raise self.error
        self.executed = (query, params)

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor
        self.closed = False
        self.committed = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def setup_function():
    with memory._cache_lock:
        memory._cache.clear()


def test_add_memory_commits_and_closes_resources(monkeypatch):
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    monkeypatch.setattr(memory, "get_connection", lambda: conn)

    memory.add_memory("hello", "hello there")

    assert conn.committed
    assert cursor.closed and conn.closed
    assert cursor.executed[1] == ("hello", "hello there")
    assert memory._cache == [{"command": "hello", "response": "hello there"}]


def test_failed_write_still_updates_fallback_cache_and_closes(monkeypatch):
    cursor = FakeCursor(error=RuntimeError("database unavailable"))
    conn = FakeConnection(cursor)
    monkeypatch.setattr(memory, "get_connection", lambda: conn)

    memory.add_memory("hello", "fallback")

    assert cursor.closed and conn.closed
    assert memory.get_recent(1) == [{"command": "hello", "response": "fallback"}]


def test_database_recent_rows_are_returned_oldest_first(monkeypatch):
    cursor = FakeCursor(rows=[("newer", "response 2"), ("older", "response 1")])
    conn = FakeConnection(cursor)
    monkeypatch.setattr(memory, "get_connection", lambda: conn)

    assert memory.get_recent(2) == [
        {"command": "older", "response": "response 1"},
        {"command": "newer", "response": "response 2"},
    ]
    assert cursor.closed and conn.closed


def test_read_failure_uses_fallback_and_closes_resources(monkeypatch):
    cursor = FakeCursor(error=RuntimeError("database unavailable"))
    conn = FakeConnection(cursor)
    monkeypatch.setattr(memory, "get_connection", lambda: conn)
    memory._cache.extend([
        {"command": "first", "response": "one"},
        {"command": "second", "response": "two"},
    ])

    assert memory.get_all_recent(2) == [
        {"command": "second", "response": "two"},
        {"command": "first", "response": "one"},
    ]
    assert cursor.closed and conn.closed


def test_zero_limit_does_not_open_database(monkeypatch):
    def should_not_connect():
        raise AssertionError("Database should not be contacted for a zero limit")

    monkeypatch.setattr(memory, "get_connection", should_not_connect)
    assert memory.get_recent(0) == []
    assert memory.get_all_recent(0) == []
