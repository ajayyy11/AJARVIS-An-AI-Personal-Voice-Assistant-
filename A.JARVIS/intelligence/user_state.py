"""Per-user assistant activation state with an expiry."""

import os
import time

try:
    ACTIVE_TIMEOUT_SECONDS = max(1, int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))) * 60
except ValueError:
    ACTIVE_TIMEOUT_SECONDS = 30 * 60

_active_until = {}


def activate_user(username, now=None):
    """Activate one user until the configured timeout expires."""
    if not isinstance(username, str) or not username.strip():
        return False
    current_time = time.monotonic() if now is None else float(now)
    _active_until[username.strip()] = current_time + ACTIVE_TIMEOUT_SECONDS
    return True


def deactivate_user(username):
    """Deactivate a user and remove their activation timestamp."""
    if isinstance(username, str) and username.strip():
        _active_until.pop(username.strip(), None)


def is_user_active(username, now=None):
    """Return whether a user's activation remains valid; expire stale entries."""
    if not isinstance(username, str) or not username.strip():
        return False
    user_key = username.strip()
    expires_at = _active_until.get(user_key)
    if expires_at is None:
        return False

    current_time = time.monotonic() if now is None else float(now)
    if current_time >= expires_at:
        _active_until.pop(user_key, None)
        return False
    return True
