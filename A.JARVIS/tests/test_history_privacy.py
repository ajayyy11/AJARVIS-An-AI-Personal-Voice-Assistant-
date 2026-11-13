from intelligence import memory as history


class FakeCursor:
    def __init__(self, fetchall=None):
        self.rows = list(fetchall or [])
        self.executed = []
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self.value = cursor
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.value

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_add_memory_redacts_note_and_personal_memory_commands(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(history, "get_connection", lambda: connection)
    original_cache = list(history._cache)
    try:
        history.add_memory(
            "remember that my door code is 1234",
            "Saved to personal memory.",
            "alice",
        )
        sql, params = cursor.executed[0]
        assert "INSERT INTO command_history" in sql
        assert params[1] == history.PRIVATE_HISTORY_COMMAND
        assert params[2] == history.PRIVATE_HISTORY_RESPONSE
        assert "1234" not in repr(params)
        with history._cache_lock:
            saved = [item for item in history._cache if item["username"] == "alice"][-1]
        assert saved["command"] == history.PRIVATE_HISTORY_COMMAND
        assert saved["response"] == history.PRIVATE_HISTORY_RESPONSE
    finally:
        with history._cache_lock:
            history._cache[:] = original_cache


def test_cursor_history_reads_redact_sensitive_legacy_rows(monkeypatch):
    rows = [
        ("remember that my door code is 1234", "Saved to personal memory."),
        ("What time is it?", "It is noon."),
    ]

    def connection_factory():
        return FakeConnection(FakeCursor(fetchall=rows))

    monkeypatch.setattr(history, "get_connection", connection_factory)

    after = history.get_recent_after(5, "alice", 0)
    assert after[0]["command"] == history.PRIVATE_HISTORY_COMMAND
    assert after[0]["response"] == history.PRIVATE_HISTORY_RESPONSE
    assert after[1]["command"] == "What time is it?"

    all_after = history.get_all_recent_after(5, "alice", 0)
    assert all_after[0]["command"] == history.PRIVATE_HISTORY_COMMAND
    assert all_after[1]["command"] == "What time is it?"


def test_history_page_redacts_legacy_sensitive_rows(monkeypatch):
    rows = [(8, "take a note: passport number 1234", "Note saved to your account.")]
    monkeypatch.setattr(
        history,
        "get_connection",
        lambda: FakeConnection(FakeCursor(fetchall=rows)),
    )
    result = history.get_history_page(5, "alice")
    assert result == [{
        "id": 8,
        "command": history.PRIVATE_HISTORY_COMMAND,
        "response": history.PRIVATE_HISTORY_RESPONSE,
    }]
