import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask, session

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-for-automated-tests-123456")

from security.session_manager import grant_access, is_authenticated, revoke_access


@pytest.fixture
def app():
    app = Flask(__name__)
    app.secret_key = os.environ["SECRET_KEY"]
    app.config["TESTING"] = True
    return app


def test_grant_access_creates_authenticated_session(app):
    with app.test_request_context("/"):
        session["unrelated"] = "remove-me"
        grant_access("tester")
        assert is_authenticated()
        assert session["user"] == "tester"
        assert "unrelated" not in session


def test_revoke_access_clears_session(app):
    with app.test_request_context("/"):
        grant_access("tester")
        revoke_access()
        assert not is_authenticated()
        assert not session


def test_expired_session_is_rejected(app):
    with app.test_request_context("/"):
        session["user"] = "tester"
        session["login_time"] = (
            datetime.now(timezone.utc) - timedelta(minutes=ConfigTimeout())
        ).isoformat()
        assert not is_authenticated()
        assert "user" not in session


def test_malformed_session_timestamp_is_rejected(app):
    with app.test_request_context("/"):
        session["user"] = "tester"
        session["login_time"] = "not-a-timestamp"
        assert not is_authenticated()
        assert "user" not in session


def test_missing_login_timestamp_is_rejected(app):
    with app.test_request_context("/"):
        session["user"] = "tester"
        assert not is_authenticated()
        assert not session


def test_future_login_timestamp_is_rejected(app):
    with app.test_request_context("/"):
        session["user"] = "tester"
        session["login_time"] = (
            datetime.now(timezone.utc) + timedelta(minutes=5)
        ).isoformat()
        assert not is_authenticated()
        assert not session


def ConfigTimeout():
    from config import Config
    return Config.SESSION_TIMEOUT_MINUTES + 1
