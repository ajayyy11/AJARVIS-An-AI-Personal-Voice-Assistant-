import intelligence.power_actions as power_actions


def setup_function():
    power_actions._pending_actions.clear()


def test_shutdown_requires_explicit_confirmation():
    event = power_actions.handle_power_command("shutdown system", "ajay", now=10)
    assert event == {"status": "confirmation_required", "action": "shutdown"}
    assert power_actions.handle_power_command("confirm shutdown", "ajay", now=11) == {
        "status": "confirmed",
        "action": "shutdown",
    }


def test_wrong_confirmation_does_not_execute_pending_action():
    power_actions.handle_power_command("shutdown system", "ajay", now=10)
    assert power_actions.handle_power_command("confirm restart", "ajay", now=11) == {
        "status": "no_pending",
        "action": "restart",
    }
    assert power_actions.handle_power_command("confirm shutdown", "ajay", now=12) == {
        "status": "confirmed",
        "action": "shutdown",
    }


def test_action_expires_after_confirmation_window():
    power_actions.handle_power_command("restart system", "ajay", now=10)
    assert power_actions.handle_power_command("confirm restart", "ajay", now=40) == {
        "status": "expired",
        "action": "restart",
    }


def test_cancel_clears_pending_action():
    power_actions.handle_power_command("shutdown system", "ajay", now=10)
    assert power_actions.handle_power_command("cancel shutdown", "ajay", now=11) == {
        "status": "cancelled",
        "action": "shutdown",
    }
    assert power_actions.handle_power_command("confirm shutdown", "ajay", now=12) == {
        "status": "no_pending",
        "action": "shutdown",
    }


def test_confirmation_is_scoped_to_username():
    power_actions.handle_power_command("shutdown system", "ajay", now=10)
    assert power_actions.handle_power_command("confirm shutdown", "other-user", now=11) == {
        "status": "no_pending",
        "action": "shutdown",
    }
    assert power_actions.handle_power_command("confirm shutdown", "ajay", now=12) == {
        "status": "confirmed",
        "action": "shutdown",
    }
