"""Confirmation state for shutdown/restart actions.

Power actions are intentionally two-step to reduce accidental execution from
speech-recognition mistakes. This module never executes operating-system
commands itself.
"""

import time

CONFIRMATION_TIMEOUT_SECONDS = 30
_pending_actions = {}


def handle_power_command(command, username, now=None):
    """Handle a power-control phrase, returning an event or None."""
    command = str(command).strip().lower()
    current_time = time.monotonic() if now is None else float(now)

    pending = _pending_actions.get(username)
    expired_action = None
    if pending and current_time >= pending["expires_at"]:
        expired_action = pending["action"]
        _pending_actions.pop(username, None)
        pending = None

    requested_action = {
        "shutdown system": "shutdown",
        "shut down system": "shutdown",
        "restart system": "restart",
    }.get(command)
    if requested_action:
        _pending_actions[username] = {
            "action": requested_action,
            "expires_at": current_time + CONFIRMATION_TIMEOUT_SECONDS,
        }
        return {"status": "confirmation_required", "action": requested_action}

    if command in {"confirm shutdown", "confirm restart"}:
        action = command.removeprefix("confirm ")
        pending = _pending_actions.get(username)
        if pending and pending["action"] == action:
            _pending_actions.pop(username, None)
            return {"status": "confirmed", "action": action}
        if expired_action == action:
            return {"status": "expired", "action": action}
        return {"status": "no_pending", "action": action}

    if command in {"cancel", "cancel shutdown", "cancel restart", "cancel power action"}:
        pending = _pending_actions.pop(username, None)
        if pending:
            return {"status": "cancelled", "action": pending["action"]}
        if expired_action:
            return {"status": "expired", "action": expired_action}
        return {"status": "no_pending", "action": None}

    return None
