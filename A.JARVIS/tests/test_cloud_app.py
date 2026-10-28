import os
from datetime import datetime, timezone

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

os.environ.setdefault("SECRET_KEY", "test-only-cloud-secret-key-12345678901234567890")

import cloud_app


class FakeCursor:
    def __init__(self, fetchone_value=None, fetchall_value=None):
        self.next_row = fetchone_value
        self.rows = fetchall_value or []
        self.last_sql = ""
        self.last_params = None
        self.rowcount = 1
        self.closed = False
        self.executed = []

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        self.executed.append((sql, params))
        if "INSERT INTO cloud_users" in sql:
            self.next_row = (123,)
        elif "SELECT password_hash FROM cloud_users" in sql:
            pass
        elif "SELECT note_text, created_at FROM cloud_notes" in sql:
            self.rows = []

    def fetchone(self):
        row = self.next_row
        self.next_row = None
        return row

    def fetchall(self):
        return self.rows

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


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(cloud_app, "ensure_cloud_schema", lambda: None)
    cloud_app.app.config.update(TESTING=True, SECRET_KEY="test-only-cloud-secret-key-12345678901234567890")
    with cloud_app.app.test_client() as test_client:
        yield test_client


def login_session(client, username="alice", csrf="test-token"):
    with client.session_transaction() as sess:
        sess["user"] = username
        sess["login_time"] = datetime.now(timezone.utc).isoformat()
        sess["csrf_token"] = csrf


def test_health_endpoint_does_not_require_database(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_private_api_rejects_unauthenticated_requests(client):
    response = client.get("/api/tasks")
    assert response.status_code == 401


def test_post_request_requires_csrf_token(client, monkeypatch):
    login_session(client)
    saved = []
    monkeypatch.setattr(cloud_app, "_save_note", lambda username, text: saved.append((username, text)))

    denied = client.post("/api/notes", json={"text": "test note"})
    assert denied.status_code == 403
    assert saved == []

    allowed = client.post(
        "/api/notes",
        json={"text": "my personal note"},
        headers={"X-CSRF-Token": "test-token"},
    )
    assert allowed.status_code == 201
    assert saved == [("alice", "my personal note")]


def test_registration_hashes_password_and_creates_fresh_session(client, monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)

    response = client.post(
        "/api/auth/register",
        json={"username": "Alice_01", "password": "a-strong-password-123"},
    )
    assert response.status_code == 201
    assert response.get_json()["ok"] is True

    sql, params = cursor.executed[0]
    assert "INSERT INTO cloud_users" in sql
    assert params[0] == "alice_01"
    assert params[1] != "a-strong-password-123"
    assert check_password_hash(params[1], "a-strong-password-123")
    assert connection.committed is True
    with client.session_transaction() as sess:
        assert sess["user"] == "alice_01"
        assert sess["csrf_token"] == response.get_json()["csrf_token"]
        assert "password" not in sess


def test_registration_rejects_short_password_before_database(client, monkeypatch):
    monkeypatch.setattr(cloud_app, "_database", lambda: pytest.fail("Database should not be touched"))
    response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "short"},
    )
    assert response.status_code == 400
    assert "12" in response.get_json()["error"]


def test_login_uses_password_hash_and_does_not_reveal_username_exists(client, monkeypatch):
    password_hash = generate_password_hash("my-strong-password-123")
    cursor = FakeCursor(fetchone_value=(password_hash,))
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)

    response = client.post(
        "/api/auth/login",
        json={"username": "ALICE", "password": "wrong password"},
    )
    assert response.status_code == 401
    assert response.get_json()["error"] == "Invalid username or password."


def test_cloud_note_command_saves_only_via_note_helper(monkeypatch):
    calls = []
    monkeypatch.setattr(cloud_app, "_save_note", lambda username, text: calls.append((username, text)))

    result = cloud_app.process_cloud_command("alice", "take a note Buy filters tomorrow")

    assert result == "Note saved to your cloud account."
    assert calls == [("alice", "Buy filters tomorrow")]


def test_cloud_note_reads_are_scoped_to_current_user(monkeypatch):
    monkeypatch.setattr(
        cloud_app,
        "_recent_notes",
        lambda username, limit=5: {"notes": ["[2026-10-28 09:00] " + username + "'s note"]},
    )

    result = cloud_app.process_cloud_command("alice", "read my notes")
    assert "alice's note" in result
    assert "bob's note" not in result


def test_current_time_is_answered_without_api_key(monkeypatch):
    monkeypatch.setattr(cloud_app, "_genai", lambda: None)
    result = cloud_app.process_cloud_command("alice", "what time is it")
    assert "UTC" in result


def test_cloud_agent_registry_exposes_no_desktop_control():
    registry = cloud_app._cloud_tool_registry()
    names = {tool["name"] for tool in registry.list_tools()}
    assert names == {
        "get_current_datetime",
        "read_recent_notes",
        "search_personal_notes",
        "search_saved_documents",
    }
    assert not any("shutdown" in name or "shell" in name or "open_app" in name for name in names)
