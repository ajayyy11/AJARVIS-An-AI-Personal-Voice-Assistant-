"""Regression tests for spoken wake phrases in the local Windows assistant."""

import sys
import types

import pytest

# The cloud CI environment intentionally excludes desktop-control packages.
# Stub only pyautogui's imported module surface so command routing can be tested
# without a desktop session; production installs the real package.
try:
    import pyautogui  # noqa: F401
except ModuleNotFoundError:
    pyautogui_stub = types.ModuleType("pyautogui")
    pyautogui_stub.press = lambda *_args, **_kwargs: None
    pyautogui_stub.screenshot = lambda *_args, **_kwargs: None
    sys.modules["pyautogui"] = pyautogui_stub

from intelligence import command_router
from intelligence import user_state


@pytest.fixture(autouse=True)
def isolate_activation(monkeypatch):
    user_state.deactivate_user("alice")
    monkeypatch.setattr(command_router, "add_memory", lambda *_args, **_kwargs: None)
    yield
    user_state.deactivate_user("alice")


@pytest.mark.parametrize("phrase", ["Hey Jarvis", "Jarvis", "Hey, Jarvis", "Okay Jarvis"])
def test_standalone_wake_phrase_greets_without_executing_a_command(phrase):
    reply = command_router.process_command(phrase, "alice")

    assert reply == "Hello alice. Awaiting system activation."
    assert not user_state.is_user_active("alice")


def test_wake_prefix_does_not_swallow_activation_command():
    reply = command_router.process_command("Hey Jarvis, system activate", "alice")

    assert reply == "Activating system. All functions online."
    assert user_state.is_user_active("alice")


def test_wake_prefix_does_not_swallow_time_command():
    user_state.activate_user("alice")

    reply = command_router.process_command("Hey Jarvis, what time is it?", "alice")

    assert reply.startswith("The current time is ")
    assert "Awaiting system activation" not in reply


def test_wake_prefix_does_not_swallow_note_command(tmp_path, monkeypatch):
    user_state.activate_user("alice")
    note_file = tmp_path / "alice-notes.txt"
    monkeypatch.setattr(command_router, "notes_path", lambda _username: note_file)

    reply = command_router.process_command(
        "Hey Jarvis, take a note: review the cloud voice flow",
        "alice",
    )

    assert reply == "Note saved to your personal notes."
    assert "review the cloud voice flow" in note_file.read_text(encoding="utf-8")


def test_wake_phrase_in_middle_of_sentence_is_not_a_wake_only_command():
    user_state.activate_user("alice")

    reply = command_router.process_command("Please tell me the time, hey Jarvis", "alice")

    assert reply.startswith("The current time is ")
