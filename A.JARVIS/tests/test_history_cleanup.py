from scripts.redact_private_command_history import redact_history
from intelligence.memory import PRIVATE_HISTORY_COMMAND, PRIVATE_HISTORY_RESPONSE


class FakeCursor:
    def __init__(self):
        self.batches = [
            [(1, "What time is it?"), (2, "remember that my code is 1234")],
            [(3, "take a note: passport 1234")],
            [],
        ]
        self.executed = []
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.batches.pop(0)

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self.value = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def test_legacy_history_cleanup_dry_run_never_writes():
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    scanned, matched = redact_history(
        apply=False,
        connection_factory=lambda: connection,
    )
    assert (scanned, matched) == (3, 2)
    assert not any(sql.startswith("UPDATE command_history") for sql, _ in cursor.executed)
    assert connection.commits == 0
    assert cursor.closed and connection.closed


def test_legacy_history_cleanup_apply_redacts_only_matching_rows():
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    scanned, matched = redact_history(
        apply=True,
        connection_factory=lambda: connection,
    )
    updates = [(sql, params) for sql, params in cursor.executed if sql.startswith("UPDATE command_history")]
    assert (scanned, matched) == (3, 2)
    assert len(updates) == 2
    assert updates[0][1] == (PRIVATE_HISTORY_COMMAND, PRIVATE_HISTORY_RESPONSE, 2)
    assert updates[1][1] == (PRIVATE_HISTORY_COMMAND, PRIVATE_HISTORY_RESPONSE, 3)
    assert connection.commits == 2
    assert cursor.closed and connection.closed
