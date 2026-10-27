from datetime import datetime, timezone

from flask import session
from config import Config


def grant_access(username):
    # Start with a fresh session payload whenever authentication succeeds.
    session.clear()
    session["user"] = username
    session["login_time"] = datetime.now(timezone.utc).isoformat()


def revoke_access():
    session.clear()


def is_authenticated():
    if not session.get("user"):
        return False

    login_time_str = session.get("login_time")
    if not login_time_str:
        revoke_access()
        return False

    try:
        login_time = datetime.fromisoformat(login_time_str)
        if login_time.tzinfo is None:
            # Compatibility with older sessions created before UTC timestamps were used.
            login_time = login_time.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        revoke_access()
        return False

    elapsed_seconds = (datetime.now(timezone.utc) - login_time).total_seconds()
    if elapsed_seconds < 0 or elapsed_seconds > Config.SESSION_TIMEOUT_MINUTES * 60:
        revoke_access()
        return False

    return True
