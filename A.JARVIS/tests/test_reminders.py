from datetime import datetime, timedelta, timezone

import pytest

from intelligence import reminders


class FakeCursor:
    def __init__(self, fetchall_values=None, fetchone_value=None, rowcount=1, lastrowid=7):
        self.fetchall_values = list(fetchall_values or [])
        self.fetchone_value = fetchone_value
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self.executed = []
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.fetchall_values.pop(0) if self.fetchall_values else []

    def fetchone(self):
        return self.fetchone_value

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def future_iso(hours=2):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def test_reminder_requires_timezone_aware_future_datetime():
    assert reminders._parse_due_at(future_iso()).tzinfo is None
    with pytest.raises(reminders.ReminderError, match="timezone offset"):
        reminders._parse_due_at("2030-01-01T10:00:00")
    with pytest.raises(reminders.ReminderError, match="future"):
        reminders._parse_due_at("2000-01-01T10:00:00Z")


@pytest.mark.parametrize("title", ["", "  ", "x" * 181])
def test_reminder_title_is_required_and_bounded(title):
    with pytest.raises(reminders.ReminderError):
        reminders.create_reminder("alice", title, future_iso())


def test_create_reminder_stores_utc_time_and_only_current_user(monkeypatch):
    cursor = FakeCursor(lastrowid=42)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(reminders, "get_connection", lambda: connection)
    due = future_iso().replace("+00:00", "Z")
    saved = reminders.create_reminder("alice", "Review checklist", due)
    sql, params = cursor.executed[0]
    assert "assistant_reminders" in sql
    assert params[0] == "alice"
    assert saved["id"] == 42 and saved["status"] == "pending"
    assert saved["due_at"].endswith("+00:00")
    assert connection.committed and cursor.closed and connection.closed


def test_list_reminders_filters_by_username_and_active_status(monkeypatch):
    due = datetime.now(timezone.utc) + timedelta(hours=1)
    cursor = FakeCursor(fetchall_values=[[(2, "Call office", due, "pending", due, None)]])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(reminders, "get_connection", lambda: connection)
    results = reminders.list_reminders("alice")
    sql, params = cursor.executed[0]
    assert "WHERE username = %s" in sql
    assert "pending', 'notified" in sql
    assert params == ("alice", 50)
    assert results[0]["id"] == 2 and results[0]["due_at"].endswith("+00:00")


def test_notification_preferences_default_to_disabled(monkeypatch):
    cursor = FakeCursor(fetchone_value=None)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(reminders, "get_connection", lambda: connection)
    assert reminders.get_notification_preferences("alice") == {
        "reminders_enabled": False,
        "browser_notifications_enabled": False,
    }


def test_notification_preferences_require_explicit_reminder_opt_in():
    with pytest.raises(reminders.ReminderError, match="Enable reminder alerts"):
        reminders.set_notification_preferences(
            "alice", reminders_enabled=False, browser_notifications_enabled=True
        )


def test_set_notification_preferences_persists_both_opt_ins(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(reminders, "get_connection", lambda: connection)
    saved = reminders.set_notification_preferences(
        "alice", reminders_enabled=True, browser_notifications_enabled=True
    )
    assert saved == {"reminders_enabled": True, "browser_notifications_enabled": True}
    assert "ON DUPLICATE KEY UPDATE" in cursor.executed[0][0]
    assert cursor.executed[0][1] == ("alice", 1, 1)
    assert connection.committed


def test_due_collection_is_disabled_until_user_opts_in(monkeypatch):
    cursor = FakeCursor(fetchone_value=(0, 0))
    connection = FakeConnection(cursor)
    monkeypatch.setattr(reminders, "get_connection", lambda: connection)
    assert reminders.collect_due_notifications("alice") == []
    assert cursor.executed[0][1] == ("alice",)


def test_due_reminders_create_one_unread_notification_and_are_marked_notified(monkeypatch):
    cursor = FakeCursor(fetchall_values=[
        [(3, "Send monthly report")],
        [(9, "AJARVIS reminder", "Send monthly report", datetime.now(timezone.utc))],
    ])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(reminders, "get_notification_preferences", lambda _username: {
        "reminders_enabled": True, "browser_notifications_enabled": False,
    })
    monkeypatch.setattr(reminders, "get_connection", lambda: connection)
    output = reminders.collect_due_notifications("alice")
    assert output[0]["id"] == 9
    assert "FOR UPDATE" in cursor.executed[0][0]
    assert "INSERT IGNORE INTO assistant_notifications" in cursor.executed[1][0]
    assert "status = 'notified'" in cursor.executed[2][0]
    assert connection.committed


def test_mark_notification_read_and_reminder_status_are_user_scoped(monkeypatch):
    cursor = FakeCursor(rowcount=1)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(reminders, "get_connection", lambda: connection)
    assert reminders.mark_notification_read("alice", 10)
    assert cursor.executed[0][1] == (10, "alice")
    cursor.executed.clear()
    assert reminders.update_reminder_status("alice", 11, "completed")
    assert cursor.executed[0][1] == ("completed", "completed", 11, "alice")
    with pytest.raises(reminders.ReminderError):
        reminders.update_reminder_status("alice", 11, "deleted")


def test_notification_and_reminder_ids_are_validated():
    with pytest.raises(reminders.ReminderError):
        reminders.mark_notification_read("alice", True)
    with pytest.raises(reminders.ReminderError):
        reminders.update_reminder_status("alice", 0, "completed")


def test_reminder_cannot_be_scheduled_more_than_one_year_ahead():
    too_far = (datetime.now(timezone.utc) + timedelta(days=366)).isoformat()
    with pytest.raises(reminders.ReminderError, match="one year"):
        reminders._parse_due_at(too_far)
