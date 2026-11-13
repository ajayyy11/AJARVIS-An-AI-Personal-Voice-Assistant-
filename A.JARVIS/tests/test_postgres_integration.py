"""Real PostgreSQL integration tests for cloud persistence and security invariants."""

from __future__ import annotations

import hashlib
import os
import uuid

import pytest
from werkzeug.security import generate_password_hash

os.environ.setdefault("SECRET_KEY", "integration-only-secret-key-not-for-production-123456")

import cloud_app
from database.rate_limiter import clear_rate_limit, consume_rate_limit
from intelligence.memory import (
    PRIVATE_HISTORY_COMMAND,
    PRIVATE_HISTORY_RESPONSE,
    add_memory,
    get_history_page,
)


@pytest.fixture(scope="session", autouse=True)
def migrated_cloud_database():
    """Create the schema once in the disposable PostgreSQL CI service."""
    cloud_app.ensure_cloud_schema()
    cloud_app.verify_cloud_schema()
    yield


def _database():
    return cloud_app._database()


def _clear_user(username: str) -> None:
    connection = cursor = None
    try:
        connection = _database()
        cursor = connection.cursor()
        for table in (
            "cloud_notes",
            "user_preferences",
            "ajarvis_tasks",
            "ajarvis_documents",
            "ajarvis_tool_audit",
            "command_history",
            "cloud_users",
        ):
            cursor.execute(f"DELETE FROM {table} WHERE username = %s", (username,))
        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def test_postgres_schema_readiness_is_read_only(migrated_cloud_database):
    response = cloud_app.app.test_client().get("/readyz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ready", "database": "ok"}


def test_postgres_rate_limits_are_shared_and_atomic(migrated_cloud_database):
    key = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    try:
        assert consume_rate_limit(key, limit=2, window_seconds=60) is False
        assert consume_rate_limit(key, limit=2, window_seconds=60) is False
        assert consume_rate_limit(key, limit=2, window_seconds=60) is True
    finally:
        clear_rate_limit(key)


def test_postgres_private_history_is_redacted_at_write_and_read(migrated_cloud_database):
    username = "privacy_" + uuid.uuid4().hex[:12]
    _clear_user(username)
    try:
        add_memory(
            "note that my passport number is TEST-PRIVATE-9182",
            "The passport number TEST-PRIVATE-9182 was saved.",
            username,
        )
        rows = get_history_page(10, username=username)

        assert len(rows) == 1
        assert rows[0]["command"] == PRIVATE_HISTORY_COMMAND
        assert rows[0]["response"] == PRIVATE_HISTORY_RESPONSE
        assert "TEST-PRIVATE-9182" not in repr(rows)
    finally:
        _clear_user(username)


def test_postgres_account_recreation_does_not_revive_old_session(migrated_cloud_database):
    username = "generation_" + uuid.uuid4().hex[:12]
    password = "integration-password-strong-123"
    _clear_user(username)

    client = cloud_app.app.test_client()
    try:
        first = client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        assert first.status_code == 201
        first_cookie = client.get_cookie("session")
        assert first_cookie is not None
        old_cookie_value = first_cookie.value
        first_csrf = first.get_json()["csrf_token"]

        saved = client.post(
            "/api/notes",
            headers={"X-CSRF-Token": first_csrf},
            json={"text": "first account private note"},
        )
        assert saved.status_code == 201

        deleted = client.post(
            "/api/account/delete",
            headers={"X-CSRF-Token": first_csrf},
            json={"confirmation": "DELETE", "password": password},
        )
        assert deleted.status_code == 200

        second = client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        assert second.status_code == 201
        new_cookie = client.get_cookie("session")
        assert new_cookie is not None
        new_cookie_value = new_cookie.value
        second_csrf = second.get_json()["csrf_token"]

        client.set_cookie("session", old_cookie_value)
        replay = client.get("/dashboard")
        assert replay.status_code == 302
        assert replay.headers["Location"].endswith("/login")

        client.set_cookie("session", new_cookie_value)
        current = client.get("/dashboard")
        assert current.status_code == 200

        notes = client.get("/api/notes")
        assert notes.status_code == 200
        assert notes.get_json()["notes"] == []
        assert second_csrf
    finally:
        _clear_user(username)
