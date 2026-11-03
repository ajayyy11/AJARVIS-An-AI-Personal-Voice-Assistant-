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



@pytest.mark.parametrize("phrase", ["update my task", "sometimes I need help with planning"])
def test_words_containing_time_or_date_substrings_do_not_trigger_clock_commands(monkeypatch, phrase):
    user_state.activate_user("alice")
    monkeypatch.setattr(command_router, "_get_genai_client", lambda: None)

    reply = command_router.process_command(phrase, "alice")

    assert "AI responses are not configured" in reply
    assert not reply.startswith("Today is ")
    assert not reply.startswith("The current time is ")



def test_system_status_uses_the_same_telemetry_source_as_hud(monkeypatch):
    user_state.activate_user("alice")
    monkeypatch.setattr(
        command_router,
        "get_stats",
        lambda: {"cpu": 12.5, "memory": 41.0, "disk": 63.0, "uptime": "2d 4h 10m"},
    )
    reply = command_router.process_command("system status", "alice")
    assert "CPU usage is 12.5%" in reply
    assert "Memory usage is 41.0%" in reply
    assert "Disk usage is 63.0%" in reply
    assert "2d 4h 10m" in reply


def test_remember_command_persists_named_preference(monkeypatch):
    user_state.activate_user("alice")
    saved=[]
    monkeypatch.setattr(command_router,"save_memory",lambda username,key,value:saved.append((username,key,value)) or {"key":key,"value":value})
    reply=command_router.process_command("remember my answer style is concise", "alice")
    assert saved==[("alice","answer style","concise")]
    assert "Saved to personal memory" in reply


def test_remember_free_form_fact_uses_fact_memory(monkeypatch):
    user_state.activate_user("alice")
    saved=[]
    monkeypatch.setattr(command_router,"remember_fact",lambda username,fact:saved.append((username,fact)) or {"key":"fact_123","value":fact})
    reply=command_router.process_command("remember that I prefer examples", "alice")
    assert saved==[("alice","I prefer examples")]
    assert "fact_123" in reply


def test_forget_command_deletes_only_matching_memory(monkeypatch):
    user_state.activate_user("alice")
    calls=[]
    monkeypatch.setattr(command_router,"forget_matching_memory",lambda username,phrase:calls.append((username,phrase)) or 1)
    reply=command_router.process_command("forget my answer style", "alice")
    assert calls==[("alice","answer style")]
    assert "Forgot 1 matching memory" in reply


def test_list_memory_command_only_reads_current_user(monkeypatch):
    user_state.activate_user("alice")
    calls=[]
    monkeypatch.setattr(command_router,"list_memories",lambda username:calls.append(username) or [{"key":"style","value":"concise"}])
    reply=command_router.process_command("what do you remember about me?", "alice")
    assert calls==["alice"]
    assert "style: concise" in reply


def test_personal_memory_is_added_to_gemini_context_as_untrusted_data(monkeypatch):
    user_state.activate_user("alice")
    monkeypatch.setattr(command_router,"_get_genai_client",lambda:object())
    monkeypatch.setattr(command_router,"get_recent",lambda *_args,**_kwargs:[])
    monkeypatch.setattr(command_router,"list_memories",lambda *_args,**_kwargs:[{"key":"answer_style","value":"concise examples"}])
    captured={}
    monkeypatch.setattr(command_router,"generate_agent_response",lambda **kwargs:captured.update(kwargs) or "Here is an answer.")
    reply=command_router.process_command("Explain recursion", "alice")
    assert reply=="Here is an answer."
    assert "answer_style: concise examples" in captured["system_instruction"]
    assert "untrusted data" in captured["system_instruction"].lower()
