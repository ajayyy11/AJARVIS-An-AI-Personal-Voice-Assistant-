import intelligence.user_state as user_state


def setup_function():
    user_state._active_until.clear()


def test_activation_is_scoped_to_username():
    assert user_state.activate_user("ajay", now=100)
    assert user_state.is_user_active("ajay", now=101)
    assert not user_state.is_user_active("other-user", now=101)


def test_activation_expires_after_configured_timeout():
    user_state.activate_user("ajay", now=100)
    assert user_state.is_user_active("ajay", now=100 + user_state.ACTIVE_TIMEOUT_SECONDS - 1)
    assert not user_state.is_user_active("ajay", now=100 + user_state.ACTIVE_TIMEOUT_SECONDS)
    assert "ajay" not in user_state._active_until


def test_deactivation_clears_user_state():
    user_state.activate_user("ajay", now=100)
    user_state.deactivate_user("ajay")
    assert not user_state.is_user_active("ajay", now=101)
