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


def test_add_memory_commits_scoped_entry_and_closes_resources(monkeypatch):
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    monkeypatch.setattr(memory, "get_connection", lambda: conn)

    memory.add_memory("hello", "hello there", "ajay")

    assert conn.committed
    assert cursor.closed and conn.closed
    assert cursor.executed[1] == ("ajay", "hello", "hello there")
    assert memory._cache == [
        {"username": "ajay", "command": "hello", "response": "hello there"}
    ]


def test_failed_write_still_updates_scoped_fallback_cache(monkeypatch):
    cursor = FakeCursor(error=RuntimeError("database unavailable"))
    conn = FakeConnection(cursor)
    monkeypatch.setattr(memory, "get_connection", lambda: conn)

    memory.add_memory("hello", "fallback", "ajay")

    assert cursor.closed and conn.closed
    assert memory.get_recent(1, username="ajay") == [
        {"command": "hello", "response": "fallback"}
    ]
    assert memory.get_recent(1, username="other-user") == []


def test_database_recent_rows_are_returned_oldest_first_and_scoped(monkeypatch):
    cursor = FakeCursor(rows=[("newer", "response 2"), ("older", "response 1")])
    conn = FakeConnection(cursor)
    monkeypatch.setattr(memory, "get_connection", lambda: conn)

    assert memory.get_recent(2, username="ajay") == [
        {"command": "older", "response": "response 1"},
        {"command": "newer", "response": "response 2"},
    ]
    assert cursor.executed[1] == ("ajay", 2)
    assert "WHERE username = %s" in cursor.executed[0]
    assert cursor.closed and conn.closed


def test_read_failure_uses_only_matching_users_fallback(monkeypatch):
    cursor = FakeCursor(error=RuntimeError("database unavailable"))
    conn = FakeConnection(cursor)
    monkeypatch.setattr(memory, "get_connection", lambda: conn)
    memory._cache.extend([
        {"username": "ajay", "command": "first", "response": "one"},
        {"username": "other", "command": "private", "response": "not for ajay"},
        {"username": "ajay", "command": "second", "response": "two"},
    ])

    assert memory.get_all_recent(2, username="ajay") == [
        {"command": "second", "response": "two"},
        {"command": "first", "response": "one"},
    ]
    assert cursor.closed and conn.closed


def test_zero_limit_or_missing_username_does_not_open_database(monkeypatch):
    def should_not_connect():
        raise AssertionError("Database should not be contacted for an invalid query")

    monkeypatch.setattr(memory, "get_connection", should_not_connect)
    assert memory.get_recent(0, username="ajay") == []
    assert memory.get_all_recent(0, username="ajay") == []
    assert memory.get_recent(5) == []
    assert memory.get_all_recent(5) == []
