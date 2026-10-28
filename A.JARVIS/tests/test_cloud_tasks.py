from datetime import datetime, timedelta, timezone

import pytest

import intelligence.cloud_tasks as tasks


class FakeCursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.executed = []
        self.rowcount = 1
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        row, self.row = self.row, None
        return row

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self.cur = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def task_row(task_id=5, done=False):
    now = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
    return (task_id, "Review deck", "Check slides", now, done, now, False)


def test_task_creation_persists_normalized_fields_and_returns_metadata(monkeypatch):
    cursor = FakeCursor(row=task_row())
    connection = FakeConnection(cursor)
    monkeypatch.setattr(tasks, "get_connection", lambda: connection)
    due = datetime(2026, 10, 28, 17, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    result = tasks.create_user_task("alice", " Review deck ", " Check slides ", due)

    assert result["id"] == 5
    assert result["title"] == "Review deck"
    assert result["done"] is False
    sql, params = cursor.executed[0]
    assert "RETURNING" in sql
    assert params[0:3] == ("alice", "Review deck", "Check slides")
    assert params[3].tzinfo == timezone.utc
    assert params[3].hour == 11
    assert connection.committed


@pytest.mark.parametrize("title", ["", " " , "x" * 161, None])
def test_invalid_task_title_is_rejected_before_database(monkeypatch, title):
    monkeypatch.setattr(tasks, "get_connection", lambda: pytest.fail("Database must not be used"))
    with pytest.raises(ValueError, match="title"):
        tasks.create_user_task("alice", title)


def test_task_details_limit_is_enforced_before_database(monkeypatch):
    monkeypatch.setattr(tasks, "get_connection", lambda: pytest.fail("Database must not be used"))
    with pytest.raises(ValueError, match="details"):
        tasks.create_user_task("alice", "Valid title", "d" * 2001)


def test_reminder_must_include_a_timezone(monkeypatch):
    monkeypatch.setattr(tasks, "get_connection", lambda: pytest.fail("Database must not be used"))
    with pytest.raises(ValueError, match="timezone"):
        tasks.create_user_task("alice", "Valid title", due_at=datetime(2026, 10, 28, 12, 0))


def test_task_updates_and_deletes_are_scoped_to_username(monkeypatch):
    cursor = FakeCursor(row=task_row(done=True))
    connection = FakeConnection(cursor)
    monkeypatch.setattr(tasks, "get_connection", lambda: connection)

    updated = tasks.update_user_task("alice", 5, done=True)
    assert updated["done"] is True
    assert cursor.executed[0][1] == (True, 5, "alice")

    cursor.rowcount = 1
    assert tasks.delete_user_task("alice", 9) is True
    assert cursor.executed[1][1] == (9, "alice")


def test_non_boolean_done_flag_is_rejected_before_database(monkeypatch):
    monkeypatch.setattr(tasks, "get_connection", lambda: pytest.fail("Database must not be used"))
    with pytest.raises(ValueError, match="boolean"):
        tasks.update_user_task("alice", 5, done=1)


def test_due_reminder_claim_query_is_user_scoped_and_transactional(monkeypatch):
    cursor = FakeCursor(rows=[task_row()])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(tasks, "get_connection", lambda: connection)

    reminders = tasks.claim_due_reminders("alice", limit=7)

    assert [item["id"] for item in reminders] == [5]
    select_sql, select_params = cursor.executed[0]
    assert "username = %s" in select_sql
    assert "SKIP LOCKED" in select_sql
    assert select_params[0] == "alice"
    assert select_params[2] == 7
    assert "UPDATE ajarvis_tasks" in cursor.executed[1][0]
    assert cursor.executed[1][1][1:] == (5, "alice")
    assert connection.committed
