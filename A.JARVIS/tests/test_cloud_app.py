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
            self.next_row = (123, 0, "00000000-0000-4000-8000-000000000001")
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
    monkeypatch.setattr(cloud_app, "_session_version_is_current", lambda _username, version, generation: version == 0 and generation == "test-generation")
    monkeypatch.setattr(cloud_app, "_rate_limit_exceeded", lambda *_args: False)
    monkeypatch.setattr(cloud_app, "_clear_rate_limit", lambda *_args: None)
    monkeypatch.setattr(
        cloud_app,
        "_database",
        lambda: FakeConnection(FakeCursor(fetchone_value=(0,))),
    )
    cloud_app.app.config.update(TESTING=True, SECRET_KEY="test-only-cloud-secret-key-12345678901234567890")
    with cloud_app.app.test_client() as test_client:
        yield test_client


def login_session(client, username="alice", csrf="test-token"):
    with client.session_transaction() as sess:
        sess["user"] = username
        sess["login_time"] = datetime.now(timezone.utc).isoformat()
        sess["session_version"] = 0
        sess["session_generation"] = "test-generation"
        sess["csrf_token"] = csrf


def test_health_endpoint_does_not_require_database(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_platform_health_probes_bypass_public_host_allowlist(client, monkeypatch, path):
    monkeypatch.setattr(cloud_app, "verify_cloud_schema", lambda: None)
    response = client.get(path, headers={"Host": "render-internal-health-probe.invalid"})
    assert response.status_code == 200


def test_application_routes_still_reject_untrusted_host(client):
    response = client.get("/login", headers={"Host": "attacker.invalid"})
    assert response.status_code == 421


def test_private_api_rejects_unauthenticated_requests(client):
    response = client.get("/api/tasks")
    assert response.status_code == 401


def test_security_headers_are_set(client):
    response = client.get("/healthz")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "microphone=(self)" in response.headers["Permissions-Policy"]
    assert "camera=(self)" in response.headers["Permissions-Policy"]
    assert "display-capture=(self)" in response.headers["Permissions-Policy"]


def test_assistant_route_limits_request_bursts_per_user(client, monkeypatch):
    login_session(client, username="voice_tester", csrf="test-token")
    monkeypatch.setattr(cloud_app, "process_cloud_command", lambda username, command: "test reply")
    monkeypatch.setattr(cloud_app, "_save_history", lambda *_args: None)
    counts = {}

    def count_limit(scope, identifier, limit, _window):
        key = (scope, identifier)
        counts[key] = counts.get(key, 0) + 1
        return counts[key] > limit

    monkeypatch.setattr(cloud_app, "_rate_limit_exceeded", count_limit)
    for _ in range(cloud_app.MAX_ASSISTANT_REQUESTS):
        response = client.post(
            "/api/assistant",
            headers={"X-CSRF-Token": "test-token"},
            json={"command": "Hello AJARVIS"},
        )
        assert response.status_code == 200

    limited = client.post(
        "/api/assistant",
        headers={"X-CSRF-Token": "test-token"},
        json={"command": "Hello again"},
    )
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == str(cloud_app.ASSISTANT_WINDOW_SECONDS)
    assert "request limit" in limited.get_json()["error"].lower()


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


def test_history_api_returns_user_history_cursor_and_filters_new_chat(client, monkeypatch):
    login_session(client)
    calls = []
    monkeypatch.setattr(
        cloud_app, "get_all_recent_after",
        lambda limit, username, after_id: calls.append((limit, username, after_id))
        or [{"command": "new chat message", "response": "new chat reply"}],
    )
    monkeypatch.setattr(cloud_app, "get_latest_id", lambda username: 73)

    response = client.get("/api/history?after_id=42")

    assert response.status_code == 200
    assert response.get_json() == {
        "history": [{"command": "new chat message", "response": "new chat reply"}],
        "latest_id": 73,
    }
    assert calls == [(30, "alice", 42)]


@pytest.mark.parametrize("cursor", ["-1", "not-a-number"])
def test_history_api_rejects_invalid_conversation_cursor(client, cursor):
    login_session(client)
    response = client.get("/api/history?after_id=" + cursor)
    assert response.status_code == 400


def test_assistant_api_passes_conversation_cursor_to_command_processor(client, monkeypatch):
    login_session(client)
    calls = []
    monkeypatch.setattr(
        cloud_app, "process_cloud_command",
        lambda username, command, context_after_id=None:
            calls.append((username, command, context_after_id)) or "clean-context reply",
    )
    monkeypatch.setattr(cloud_app, "_save_history", lambda *_args: None)
    response = client.post(
        "/api/assistant",
        headers={"X-CSRF-Token": "test-token"},
        json={"command": "Explain this", "context_after_id": 42},
    )

    assert response.status_code == 200
    assert response.get_json()["response"] == "clean-context reply"
    assert calls == [("alice", "Explain this", 42)]


def test_assistant_api_rejects_invalid_conversation_cursor(client, monkeypatch):
    login_session(client)
    monkeypatch.setattr(cloud_app, "process_cloud_command", lambda *_args, **_kwargs: "unexpected")
    response = client.post(
        "/api/assistant",
        headers={"X-CSRF-Token": "test-token"},
        json={"command": "Explain this", "context_after_id": -1},
    )
    assert response.status_code == 400


def test_process_cloud_command_uses_only_the_selected_conversation_history(monkeypatch):
    captured = {}
    monkeypatch.setattr(cloud_app, "_genai", lambda: object())
    monkeypatch.setattr(
        cloud_app, "get_recent_after",
        lambda limit, username, after_id: [
            {"command": "new conversation question", "response": "new conversation answer"}
        ],
    )

    def fake_generate_agent_response(**kwargs):
        captured["contents"] = kwargs["contents"]
        return "answer"

    monkeypatch.setattr(cloud_app, "generate_agent_response", fake_generate_agent_response)

    result = cloud_app.process_cloud_command(
        "alice", "Explain the next step", context_after_id=42
    )

    assert result == "answer"
    assert captured["contents"] == [
        {"role": "user", "parts": [{"text": "new conversation question"}]},
        {"role": "model", "parts": [{"text": "new conversation answer"}]},
        {"role": "user", "parts": [{"text": "Explain the next step"}]},
    ]



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
    cursor = FakeCursor(fetchone_value=(password_hash, 0, "00000000-0000-4000-8000-000000000001"))
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


@pytest.mark.parametrize(
    "spoken_command",
    [
        "Hey Jarvis, take a note: call the college tomorrow",
        "Hey, Jarvis, take a note: call the college tomorrow",
        "Jarvis, take a note: call the college tomorrow",
    ],
)
def test_wake_word_is_stripped_for_spoken_note_command(monkeypatch, spoken_command):
    calls = []
    monkeypatch.setattr(cloud_app, "_save_note", lambda username, text: calls.append((username, text)))

    result = cloud_app.process_cloud_command("alice", spoken_command)

    assert result == "Note saved to your cloud account."
    assert calls == [("alice", "call the college tomorrow")]


def test_wake_word_only_gives_ready_prompt(monkeypatch):
    monkeypatch.setattr(cloud_app, "_genai", lambda: pytest.fail("No model call expected for a wake phrase"))
    assert "What can I help" in cloud_app.process_cloud_command("alice", "Hey Jarvis")


def test_voice_task_command_creates_user_scoped_task(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cloud_app,
        "create_user_task",
        lambda username, title: calls.append((username, title)) or {"title": title},
    )

    result = cloud_app.process_cloud_command("alice", "Jarvis, add task to renew my passport")

    assert result == "Task added: renew my passport."
    assert calls == [("alice", "renew my passport")]


def test_voice_task_listing_is_owner_scoped(monkeypatch):
    monkeypatch.setattr(
        cloud_app,
        "list_user_tasks",
        lambda username: [
            {"title": "Renew passport", "done": False, "due_at": None},
            {"title": "Buy groceries", "done": True, "due_at": None},
        ] if username == "alice" else [],
    )

    result = cloud_app.process_cloud_command("alice", "Hey Jarvis, list my tasks")

    assert "Renew passport" in result
    assert "Buy groceries" not in result


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
        "read_user_preferences",
    }
    assert not any("shutdown" in name or "shell" in name or "open_app" in name for name in names)



def test_account_deletion_requires_exact_confirmation_and_password(client, monkeypatch):
    login_session(client, username="alice", csrf="test-token")
    monkeypatch.setattr(cloud_app, "_database", lambda: pytest.fail("No DB access before explicit confirmation"))

    response = client.post(
        "/api/account/delete",
        headers={"X-CSRF-Token": "test-token"},
        json={"confirmation": "DELETE"},
    )
    assert response.status_code == 400
    assert "password" in response.get_json()["error"].lower()


def test_account_deletion_removes_user_scoped_data_and_session(client, monkeypatch):
    login_session(client, username="alice", csrf="test-token")
    password_hash = generate_password_hash("strong-password-123")
    cursor = FakeCursor(fetchone_value=(password_hash,))
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)

    from intelligence.memory import _cache, _cache_lock
    with _cache_lock:
        _cache.append({"username": "alice", "command": "private", "response": "private response"})
        _cache.append({"username": "bob", "command": "other", "response": "other response"})

    response = client.post(
        "/api/account/delete",
        headers={"X-CSRF-Token": "test-token"},
        json={"confirmation": "DELETE", "password": "strong-password-123"},
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert connection.committed is True
    deleted_tables = [
        sql.split("DELETE FROM ", 1)[1].split(" ", 1)[0]
        for sql, _params in cursor.executed
        if "DELETE FROM " in sql
    ]
    assert deleted_tables == [
        "cloud_notes", "user_preferences", "ajarvis_tasks", "ajarvis_documents",
        "command_history", "ajarvis_tool_audit", "cloud_users",
    ]
    with client.session_transaction() as sess:
        assert "user" not in sess
    with _cache_lock:
        assert all(entry["username"] != "alice" for entry in _cache)
        _cache[:] = [entry for entry in _cache if entry["username"] != "bob"]


def test_note_delete_is_owner_scoped(client, monkeypatch):
    login_session(client, username="alice", csrf="test-token")
    cursor = FakeCursor()
    cursor.rowcount = 0
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)

    response = client.delete("/api/notes/18", headers={"X-CSRF-Token": "test-token"})
    assert response.status_code == 404
    assert cursor.executed[0][1] == (18, "alice")


def test_document_delete_is_owner_scoped(client, monkeypatch):
    login_session(client, username="alice", csrf="test-token")
    cursor = FakeCursor()
    cursor.rowcount = 0
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)

    response = client.delete("/api/documents/7", headers={"X-CSRF-Token": "test-token"})
    assert response.status_code == 404
    assert cursor.executed[0][1] == (7, "alice")



def test_preference_save_validates_key_and_upserts_user_scoped_data(monkeypatch):
    timestamp = datetime.now(timezone.utc)
    cursor = FakeCursor(fetchone_value=("answer_style", "Use concise examples", timestamp))
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)

    saved = cloud_app._save_user_preference("alice", "Answer_Style", "Use concise examples")

    assert saved["key"] == "answer_style"
    assert saved["value"] == "Use concise examples"
    sql, params = cursor.executed[0]
    assert "ON CONFLICT (username, preference_key)" in sql
    assert params == ("alice", "answer_style", "Use concise examples")
    assert connection.committed


@pytest.mark.parametrize("key", ["", " ", "key with spaces", "../secret", "x" * 81])
def test_preference_key_rejects_invalid_values(monkeypatch, key):
    monkeypatch.setattr(cloud_app, "_database", lambda: pytest.fail("No DB call for invalid key"))
    with pytest.raises(ValueError, match="Preference keys"):
        cloud_app._save_user_preference("alice", key, "a value")


def test_preference_value_is_bounded(monkeypatch):
    monkeypatch.setattr(cloud_app, "_database", lambda: pytest.fail("No DB call for invalid value"))
    with pytest.raises(ValueError, match="1–1,000"):
        cloud_app._save_user_preference("alice", "answer_style", "x" * 1001)


def test_remember_preference_command_saves_explicit_user_request(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cloud_app,
        "_save_user_preference",
        lambda username, key, value: calls.append((username, key, value))
        or {"key": key.lower(), "value": value},
    )
    result = cloud_app.process_cloud_command("alice", "remember preference answer_style = concise with examples")
    assert result == "Preference saved: answer_style."
    assert calls == [("alice", "answer_style", "concise with examples")]


def test_preferences_api_requires_authentication(client):
    response = client.get("/api/preferences")
    assert response.status_code == 401


def test_preferences_api_is_csrf_protected_and_owner_scoped(client, monkeypatch):
    login_session(client, username="alice", csrf="test-token")
    saves = []
    monkeypatch.setattr(
        cloud_app,
        "_save_user_preference",
        lambda username, key, value: saves.append((username, key, value))
        or {"key": key, "value": value, "updated_at": None},
    )

    denied = client.post("/api/preferences", json={"key": "answer_style", "value": "concise"})
    assert denied.status_code == 403
    assert saves == []

    allowed = client.post(
        "/api/preferences",
        headers={"X-CSRF-Token": "test-token"},
        json={"key": "answer_style", "value": "concise"},
    )
    assert allowed.status_code == 201
    assert saves == [("alice", "answer_style", "concise")]


def test_preference_delete_is_scoped_to_current_user(client, monkeypatch):
    login_session(client, username="alice", csrf="test-token")
    cursor = FakeCursor()
    cursor.rowcount = 1
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)

    response = client.delete(
        "/api/preferences/answer_style",
        headers={"X-CSRF-Token": "test-token"},
    )
    assert response.status_code == 200
    assert cursor.executed[0][1] == ("alice", "answer_style")



def test_tool_audit_records_metadata_without_arguments_or_results(monkeypatch):
    audit_entries = []
    monkeypatch.setattr(
        cloud_app,
        "_record_tool_audit",
        lambda username, tool_name, outcome, duration_ms: audit_entries.append(
            (username, tool_name, outcome, duration_ms)
        ),
    )
    handler = cloud_app._audited_tool(
        "search_personal_notes",
        lambda *, username, query: {"private_result": query},
    )

    result = handler(username="alice", query="confidential phrase")

    assert result == {"private_result": "confidential phrase"}
    assert len(audit_entries) == 1
    assert audit_entries[0][0:3] == ("alice", "search_personal_notes", "success")
    assert isinstance(audit_entries[0][3], int)
    assert "confidential phrase" not in repr(audit_entries)


def test_tool_audit_marks_failed_tool_without_storing_exception_details(monkeypatch):
    audit_entries = []
    monkeypatch.setattr(
        cloud_app,
        "_record_tool_audit",
        lambda username, tool_name, outcome, duration_ms: audit_entries.append(
            (username, tool_name, outcome, duration_ms)
        ),
    )

    def raises(*, username):
        raise RuntimeError("private failure text")

    handler = cloud_app._audited_tool("read_user_preferences", raises)
    with pytest.raises(RuntimeError, match="private failure"):
        handler(username="alice")

    assert audit_entries[0][0:3] == ("alice", "read_user_preferences", "error")
    assert "private failure text" not in repr(audit_entries)


def test_activity_api_filters_by_current_username(client, monkeypatch):
    login_session(client, username="alice")
    cursor = FakeCursor(fetchall_value=[
        ("read_user_preferences", "success", 12, datetime.now(timezone.utc)),
    ])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)

    response = client.get("/api/activity")

    assert response.status_code == 200
    assert response.get_json()["activity"][0]["tool_name"] == "read_user_preferences"
    assert cursor.executed[0][1] == ("alice", 30)



def test_document_ai_uses_the_same_account_quota_as_assistant(client, monkeypatch):
    username = "shared_quota_tester"
    login_session(client, username=username, csrf="test-token")
    calls = {"count": 0}

    def shared_quota(_username):
        calls["count"] += 1
        return calls["count"] > cloud_app.MAX_ASSISTANT_REQUESTS

    monkeypatch.setattr(cloud_app, "_assistant_rate_limited", shared_quota)
    monkeypatch.setattr(cloud_app, "process_cloud_command", lambda _username, _command: "test reply")
    monkeypatch.setattr(cloud_app, "_save_history", lambda *_args: None)
    monkeypatch.setattr(cloud_app, "_genai", lambda: object())
    monkeypatch.setattr(
        cloud_app,
        "_database",
        lambda: FakeConnection(FakeCursor(fetchone_value=("report.txt", "A saved report."))),
    )

    for _ in range(cloud_app.MAX_ASSISTANT_REQUESTS):
        response = client.post(
            "/api/assistant",
            headers={"X-CSRF-Token": "test-token"},
            json={"command": "Hello AJARVIS"},
        )
        assert response.status_code == 200

    response = client.post(
        "/api/documents/17/ask",
        headers={"X-CSRF-Token": "test-token"},
        json={"question": "Summarize the report"},
    )
    assert response.status_code == 429
    assert response.headers["Retry-After"] == str(cloud_app.ASSISTANT_WINDOW_SECONDS)



def test_document_is_saved_when_ai_quota_is_exhausted(client, monkeypatch):
    from io import BytesIO

    login_session(client, username="alice", csrf="test-token")
    timestamp = datetime.now(timezone.utc)
    cursor = FakeCursor(fetchone_value=(44, timestamp))
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)
    monkeypatch.setattr(cloud_app, "_genai", lambda: object())
    monkeypatch.setattr(
        cloud_app,
        "extract_document_text",
        lambda filename, raw: ("Readable document content", None),
    )
    monkeypatch.setattr(cloud_app, "_assistant_rate_limited", lambda _username: True)

    response = client.post(
        "/api/documents",
        headers={"X-CSRF-Token": "test-token"},
        data={"file": (BytesIO(b"test document"), "report.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    result = response.get_json()
    assert result["id"] == 44
    assert "Document saved successfully" in result["summary"]
    assert "summary was skipped" in result["summary"]
    assert connection.committed


def test_visual_analysis_requires_authentication(client):
    response = client.post("/api/visual/analyze")
    assert response.status_code == 401


def test_visual_analysis_requires_csrf(client):
    login_session(client, username="visual_user", csrf="visual-token")
    response = client.post("/api/visual/analyze", data={"prompt": "Describe."}, content_type="multipart/form-data")
    assert response.status_code == 403


def test_visual_analysis_is_transient_and_user_scoped(client, monkeypatch):
    from io import BytesIO
    login_session(client, username="visual_user", csrf="visual-token")
    monkeypatch.setattr(cloud_app, "_genai", lambda: object())
    monkeypatch.setattr(cloud_app, "_assistant_rate_limited", lambda _username: False)
    monkeypatch.setattr(cloud_app, "validate_visual_input", lambda _filename, _raw: ("image/png", None))
    monkeypatch.setattr(cloud_app, "analyze_visual_input", lambda **_kwargs: "A maintenance checklist.")
    monkeypatch.setattr(cloud_app, "_database", lambda: pytest.fail("Visual media must not be persisted."))
    response = client.post(
        "/api/visual/analyze",
        headers={"X-CSRF-Token": "visual-token"},
        data={"file": (BytesIO(b"transient-image"), "capture.png"), "prompt": "Read the title."},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["stored"] is False
    assert response.get_json()["answer"] == "A maintenance checklist."


def test_visual_analysis_uses_shared_ai_quota(client, monkeypatch):
    from io import BytesIO
    login_session(client, username="visual_quota", csrf="visual-token")
    monkeypatch.setattr(cloud_app, "validate_visual_input", lambda _filename, _raw: ("image/png", None))
    monkeypatch.setattr(cloud_app, "_genai", lambda: object())
    monkeypatch.setattr(cloud_app, "_assistant_rate_limited", lambda _username: True)
    response = client.post(
        "/api/visual/analyze", headers={"X-CSRF-Token": "visual-token"},
        data={"file": (BytesIO(b"frame"), "capture.png")}, content_type="multipart/form-data",
    )
    assert response.status_code == 429
    assert response.headers["Retry-After"] == str(cloud_app.ASSISTANT_WINDOW_SECONDS)


def test_scanned_pdf_document_upload_falls_back_to_visual_transcription(client, monkeypatch):
    from io import BytesIO
    from intelligence.documents import DocumentError

    login_session(client, username="scan_user", csrf="visual-token")
    connection = FakeConnection(FakeCursor(fetchone_value=(91, datetime.now(timezone.utc))))
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)
    monkeypatch.setattr(cloud_app, "_genai", lambda: object())
    monkeypatch.setattr(cloud_app, "_assistant_rate_limited", lambda _username: False)
    monkeypatch.setattr(
        cloud_app, "extract_document_text",
        lambda _filename, _raw: (_ for _ in ()).throw(
            DocumentError("No readable text was found. Scanned PDFs need OCR before they can be analyzed.")
        ),
    )
    transcribed = []
    monkeypatch.setattr(
        cloud_app, "extract_scanned_pdf_text",
        lambda **kwargs: transcribed.append(kwargs) or ("[Page 1] Scanned checklist", 1),
    )
    monkeypatch.setattr(
        cloud_app, "answer_document_question",
        lambda **_kwargs: "Summary of the scanned checklist.",
    )

    response = client.post(
        "/api/documents",
        headers={"X-CSRF-Token": "visual-token"},
        data={"file": (BytesIO(b"%PDF-test"), "scan.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    assert response.get_json()["summary"] == "Summary of the scanned checklist."
    assert transcribed[0]["filename"] == "scan.pdf"
    assert transcribed[0]["data"] == b"%PDF-test"
    assert connection.committed



def test_workspace_feature_routes_render_one_authenticated_page(client, monkeypatch):
    monkeypatch.setattr(cloud_app, "get_latest_id", lambda username: 91)
    login_session(client)
    routes = {
        "/dashboard": "dashboard",
        "/history": "history",
        "/tasks": "tasks",
        "/notes": "notes",
        "/memory": "memory",
        "/activity": "activity",
        "/visual": "visual",
        "/documents": "documents",
        "/account": "account",
        "/settings": "settings",
    }
    for path, page in routes.items():
        response = client.get(path)
        assert response.status_code == 200, path
        assert f'data-page="{page}"' in response.get_data(as_text=True), path



def test_history_api_returns_first_page_and_older_cursor(client, monkeypatch):
    login_session(client)
    calls = []
    rows = [{"id": index, "command": f"question {index}", "response": f"answer {index}"} for index in range(31, 0, -1)]
    monkeypatch.setattr(cloud_app, "get_history_page",
        lambda limit, username, before_id=None: calls.append((limit, username, before_id)) or rows)
    monkeypatch.setattr(cloud_app, "get_latest_id", lambda username: 91)

    response = client.get("/api/history")
    payload = response.get_json()
    assert response.status_code == 200
    assert len(payload["history"]) == 30
    assert payload["history"][0]["id"] == 31
    assert payload["history"][-1]["id"] == 2
    assert payload["has_more"] is True
    assert payload["next_before_id"] == 2
    assert calls == [(31, "alice", None)]

    older_rows = [{"id": 1, "command": "old", "response": "older answer"}]
    monkeypatch.setattr(cloud_app, "get_history_page",
        lambda limit, username, before_id=None: calls.append((limit, username, before_id)) or older_rows)
    older = client.get("/api/history?before_id=2").get_json()
    assert older["history"] == older_rows
    assert older["has_more"] is False
    assert older["next_before_id"] is None
    assert calls[-1] == (31, "alice", 2)


@pytest.mark.parametrize("cursor", ["-1", "not-a-number"])
def test_history_api_rejects_invalid_older_cursor(client, cursor):
    login_session(client)
    response = client.get("/api/history?before_id=" + cursor)
    assert response.status_code == 400


def test_history_api_rejects_ambiguous_cursor_parameters(client):
    login_session(client)
    response = client.get("/api/history?after_id=5&before_id=10")
    assert response.status_code == 400



def test_login_rate_limit_separates_source_and_account_pair_scopes(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cloud_app,
        "_rate_limit_exceeded",
        lambda scope, identifier, limit, window: calls.append(
            (scope, identifier, limit, window)
        ) or False,
    )
    with cloud_app.app.test_request_context(
        "/api/auth/login", environ_base={"REMOTE_ADDR": "198.51.100.72"}
    ):
        assert cloud_app._auth_rate_limited("target_account") is False

    assert [item[0] for item in calls] == ["login-ip", "login-account-ip"]
    assert calls[0][1] == "198.51.100.72"
    assert "target_account" in calls[1][1]
    assert calls[0][2] == cloud_app.MAX_LOGIN_ATTEMPTS_PER_IP
    assert calls[1][2] == cloud_app.MAX_LOGIN_ATTEMPTS_PER_ACCOUNT_IP



def test_unknown_username_still_verifies_dummy_password_hash(client, monkeypatch):
    cursor = FakeCursor(fetchone_value=None)
    monkeypatch.setattr(cloud_app, "_database", lambda: FakeConnection(cursor))
    calls = []
    monkeypatch.setattr(
        cloud_app,
        "check_password_hash",
        lambda encoded, password: calls.append((encoded, password)) or False,
    )
    response = client.post(
        "/api/auth/login",
        json={"username": "unknown_user", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert len(calls) == 1
    assert calls[0][0] == cloud_app._DUMMY_PASSWORD_HASH


def test_logout_increments_session_version_and_invalidates_old_cookie(client, monkeypatch):
    login_session(client, username="revocation_user", csrf="revoke-token")
    cursor = FakeCursor()
    cursor.rowcount = 1
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)
    response = client.post("/api/auth/logout", headers={"X-CSRF-Token": "revoke-token"}, json={})
    assert response.status_code == 200
    assert connection.committed is True
    assert "UPDATE cloud_users SET session_version = session_version + 1" in cursor.executed[0][0]
    with client.session_transaction() as state:
        assert "user" not in state


def test_cloud_security_headers_include_csp_and_hsts_on_https(client):
    response = client.get("/healthz", base_url="https://ajarvis-cloud.onrender.com")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "max-age=31536000" in response.headers["Strict-Transport-Security"]


def test_workspace_uses_same_origin_static_assets_without_inline_scripts(client, monkeypatch):
    login_session(client)
    monkeypatch.setattr(cloud_app, "get_latest_id", lambda **_kwargs: 0)
    response = client.get("/dashboard")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/static/cloud.css" in html
    assert "/static/cloud.js" in html
    assert "/static/interface.js" in html
    assert "chart.js" not in html.lower()
    assert "<script>" not in html.lower()
    assert "</head>" in html.lower()





def test_cloud_dashboard_pauses_background_polling_when_tab_is_hidden():
    from pathlib import Path

    source = (Path(cloud_app.__file__).parent / "static" / "cloud.js").read_text(encoding="utf-8")
    assert 'document.visibilityState !== "hidden"' in source
    assert 'document.addEventListener("visibilitychange"' in source
    assert "if (pageIsVisible()) claimReminders()" in source
    assert "if (pageIsVisible()) loadSystemStatus()" in source



def test_cloud_host_header_rejects_untrusted_host(client):
    response = client.get("/healthz", base_url="https://evil.example")
    assert response.status_code == 421


def test_cloud_proxyfix_uses_forwarded_client_address(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        cloud_app,
        "_auth_rate_limited",
        lambda _username=None: captured.setdefault("remote_addr", cloud_app.request.remote_addr) and False,
    )
    response = client.post(
        "/api/auth/login",
        base_url="https://ajarvis-cloud.onrender.com",
        environ_overrides={
            "REMOTE_ADDR": "10.0.0.10",
            "HTTP_X_FORWARDED_FOR": "198.51.100.25",
            "HTTP_X_FORWARDED_PROTO": "https",
        },
        json={"username": None, "password": None},
    )
    assert response.status_code == 401
    assert captured["remote_addr"] == "198.51.100.25"
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")



def test_session_version_check_fails_when_database_version_changes(client, monkeypatch):
    login_session(client)
    monkeypatch.setattr(cloud_app, "_session_version_is_current", lambda _username, _version, _generation: False)
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as state:
        assert "user" not in state


def test_old_session_cookie_stays_revoked_after_account_recreation(client, monkeypatch):
    login_session(client, username="recreated_user")
    monkeypatch.setattr(
        cloud_app,
        "_session_version_is_current",
        lambda _username, _version, generation: generation == "new-account-generation",
    )

    old_cookie = client.get("/dashboard")
    assert old_cookie.status_code == 302
    assert old_cookie.headers["Location"].endswith("/login")
    with client.session_transaction() as state:
        assert "user" not in state

    with client.session_transaction() as state:
        state["user"] = "recreated_user"
        state["login_time"] = datetime.now(timezone.utc).isoformat()
        state["session_version"] = 0
        state["session_generation"] = "new-account-generation"
        state["csrf_token"] = "fresh-csrf"
    monkeypatch.setattr(cloud_app, "get_latest_id", lambda **_kwargs: 0)

    new_cookie = client.get("/dashboard")
    assert new_cookie.status_code == 200


def test_readyz_checks_schema_without_running_ddl(client, monkeypatch):
    cursor = FakeCursor(fetchone_value=None)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cloud_app, "_database", lambda: connection)
    monkeypatch.setattr(
        cloud_app, "ensure_cloud_schema",
        lambda: pytest.fail("Readiness must never run schema migrations"),
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    assert cursor.executed
    assert all(
        not any(word in sql.upper() for word in ("CREATE ", "ALTER ", "DROP "))
        for sql, _params in cursor.executed
    )
