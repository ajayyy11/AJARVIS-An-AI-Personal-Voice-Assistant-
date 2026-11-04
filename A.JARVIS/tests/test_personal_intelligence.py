from datetime import datetime, timedelta, timezone

import pytest

from intelligence import personal_intelligence as pi


class FakeCursor:
    def __init__(self, rows=None, rowcount=1, lastrowid=12, one=None):
        self.rows = list(rows or [])
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self.one = one
        self.executed = []
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self.one is not None:
            value, self.one = self.one, None
            return value
        if self.rows:
            return self.rows.pop(0)
        return None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

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


def test_priority_scoring_is_deterministic_explainable_and_bounded():
    now = datetime(2026, 11, 4, 10, tzinfo=timezone.utc)
    due = (now + timedelta(hours=12)).isoformat()
    result = pi.score_task(
        {"priority": "urgent", "due_at": due, "effort_minutes": 20, "status": "in_progress"},
        now=now,
    )
    assert result["priority_score"] == 100
    assert "User-selected priority" in result["priority_reason"]
    assert "Due within 24 hours" in result["priority_reason"]
    assert "Quick win" in result["priority_reason"]
    assert "Already in progress" in result["priority_reason"]


def test_priority_scoring_adds_overdue_urgency_and_does_not_change_priority():
    now = datetime(2026, 11, 4, 10, tzinfo=timezone.utc)
    task = {"priority": "low", "due_at": (now - timedelta(days=2)).isoformat(), "status": "pending"}
    result = pi.score_task(task, now=now)
    assert result["priority"] == "low"
    assert result["priority_score"] == 45
    assert "Overdue" in result["priority_reason"]


@pytest.mark.parametrize("priority", ["", "critical", None])
def test_unknown_priority_falls_back_to_normal_without_invented_urgency(priority):
    result = pi.score_task({"priority": priority, "status": "pending"})
    assert result["priority_score"] == 35
    assert "User-selected priority" in result["priority_reason"]


def test_due_date_requires_timezone_and_is_stored_as_utc():
    with pytest.raises(pi.PersonalIntelligenceError, match="timezone offset"):
        pi._parse_due_at("2026-12-01T10:00:00")
    parsed = pi._parse_due_at("2026-12-01T15:30:00+05:30")
    assert parsed == datetime(2026, 12, 1, 10, 0)


@pytest.mark.parametrize("value", ["", "  ", "password for account", "x" * 181])
def test_project_name_validation_rejects_empty_secrets_or_oversize(value):
    with pytest.raises(pi.PersonalIntelligenceError):
        pi.create_project("alice", value)


def test_create_project_is_user_scoped_and_commits(monkeypatch):
    cursor = FakeCursor(lastrowid=5)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(pi, "_connection", lambda: connection)
    created = pi.create_project("alice", "AJARVIS", "Personal assistant roadmap")
    sql, params = cursor.executed[0]
    assert "assistant_projects" in sql
    assert params == ("alice", "AJARVIS", "Personal assistant roadmap")
    assert created["id"] == 5 and created["status"] == "active"
    assert connection.committed and cursor.closed and connection.closed


def test_create_task_requires_an_owned_active_project(monkeypatch):
    cursor = FakeCursor(one=None)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(pi, "_connection", lambda: connection)
    with pytest.raises(pi.PersonalIntelligenceError, match="active project"):
        pi.create_task("alice", "Finish tests", project_id=9)
    assert len(cursor.executed) == 1
    assert cursor.executed[0][1] == (9, "alice")
    assert connection.rolled_back


def test_create_task_stores_user_selected_priority_and_utc_deadline(monkeypatch):
    cursor = FakeCursor(one=(9,), lastrowid=21)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(pi, "_connection", lambda: connection)
    due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    saved = pi.create_task(
        "alice", "Run CI", project_id=9, details="Check suite",
        priority="high", due_at=due, effort_minutes=25,
    )
    insert_sql, params = cursor.executed[1]
    assert "assistant_tasks" in insert_sql
    assert params[:6] == ("alice", 9, "Run CI", "Check suite", "high", pi._parse_due_at(due))
    assert saved["id"] == 21 and saved["priority"] == "high"
    assert saved["effort_minutes"] == 25 and connection.committed


def test_list_tasks_is_user_scoped_and_returns_sorted_scored_rows(monkeypatch):
    now = datetime.now(timezone.utc)
    due = now + timedelta(hours=3)
    cursor = FakeCursor(rows=[
        (1, None, None, "Later task", "", "normal", now + timedelta(days=8), 90, "pending", now, now),
        (2, None, None, "Urgent task", "", "urgent", due, 20, "pending", now, now),
    ])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(pi, "_connection", lambda: connection)
    tasks = pi.list_tasks("alice")
    sql, params = cursor.executed[0]
    assert "WHERE t.username = %s" in sql
    assert params == ("alice", "pending", "in_progress", 200)
    assert tasks[0]["title"] == "Urgent task"
    assert tasks[0]["priority_score"] > tasks[1]["priority_score"]


def test_project_and_task_status_updates_are_user_scoped(monkeypatch):
    cursor = FakeCursor(rowcount=1)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(pi, "_connection", lambda: connection)
    assert pi.update_project_status("alice", 4, "paused")
    assert cursor.executed[0][1] == ("paused", 4, "alice")
    cursor.executed.clear()
    assert pi.update_task_status("alice", 6, "completed")
    assert cursor.executed[0][1] == ("completed", "completed", 6, "alice")
    with pytest.raises(pi.PersonalIntelligenceError):
        pi.update_task_status("alice", 6, "delete")


def test_focus_brief_summarises_projects_open_work_and_overdue(monkeypatch):
    now = datetime(2026, 11, 4, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(pi, "list_projects", lambda _user, limit: [
        {"id": 1, "name": "AJARVIS", "status": "active"},
        {"id": 2, "name": "Old project", "status": "completed"},
    ])
    monkeypatch.setattr(pi, "list_tasks", lambda _user, limit: [
        {"id": 4, "title": "Overdue", "status": "pending", "due_at": (now - timedelta(hours=2)).isoformat(), "priority_score": 90},
        {"id": 5, "title": "Next", "status": "in_progress", "due_at": None, "priority_score": 50},
    ])
    focus = pi.build_personal_focus("alice", now=now)
    assert [p["name"] for p in focus["active_projects"]] == ["AJARVIS"]
    assert focus["next_tasks"][0]["title"] == "Overdue"
    assert focus["metrics"] == {
        "active_projects": 1, "open_tasks": 2, "overdue_tasks": 1, "in_progress_tasks": 1
    }
    assert "suggestion" in focus["prioritisation"]
