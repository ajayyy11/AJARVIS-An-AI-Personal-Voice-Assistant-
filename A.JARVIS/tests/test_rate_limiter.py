import pytest

from database.rate_limiter import clear_rate_limit, consume_rate_limit


class FakeCursor:
    def __init__(self, row=(1,)):
        self.row = row
        self.sql = None
        self.params = None
        self.rowcount = 1
        self.closed = False

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self.row

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self.value = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.value

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_consume_rate_limit_uses_atomic_upsert_and_commits():
    cursor = FakeCursor(row=(6,))
    connection = FakeConnection(cursor)
    result = consume_rate_limit(
        "a" * 64,
        limit=5,
        window_seconds=60,
        connection_factory=lambda: connection,
    )
    assert result is True
    assert "ON CONFLICT (rate_key) DO UPDATE" in cursor.sql
    assert "RETURNING request_count" in cursor.sql
    assert cursor.params == ("a" * 64, 60, 60, 60, 60, 60)
    assert connection.committed is True
    assert cursor.closed is True
    assert connection.closed is True


def test_consume_rate_limit_allows_a_request_below_limit():
    cursor = FakeCursor(row=(5,))
    connection = FakeConnection(cursor)
    assert consume_rate_limit(
        "b" * 64,
        limit=5,
        window_seconds=60,
        connection_factory=lambda: connection,
    ) is False
    assert connection.committed is True


@pytest.mark.parametrize(
    "key,limit,window",
    [
        ("short", 5, 60),
        ("c" * 64, 0, 60),
        ("c" * 64, 5, 0),
        ("c" * 64, True, 60),
    ],
)
def test_consume_rate_limit_rejects_invalid_arguments(key, limit, window):
    with pytest.raises(ValueError):
        consume_rate_limit(
            key,
            limit=limit,
            window_seconds=window,
            connection_factory=lambda: pytest.fail("Invalid inputs must not open a connection"),
        )


def test_clear_rate_limit_deletes_only_the_hashed_identifier():
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    clear_rate_limit(
        "d" * 64,
        connection_factory=lambda: connection,
    )
    assert cursor.sql == "DELETE FROM ajarvis_rate_limits WHERE rate_key = %s"
    assert cursor.params == ("d" * 64,)
    assert connection.committed is True
