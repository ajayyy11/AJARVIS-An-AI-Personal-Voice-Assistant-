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
    with command_router._PENDING_COMMAND_APPROVALS_LOCK:
        command_router._PENDING_COMMAND_APPROVALS.clear()
    monkeypatch.setattr(command_router, "add_memory", lambda *_args, **_kwargs: None)
    yield
    with command_router._PENDING_COMMAND_APPROVALS_LOCK:
        command_router._PENDING_COMMAND_APPROVALS.clear()
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



def test_weather_request_failure_does_not_log_api_key(caplog, monkeypatch):
    secret = "qa-weather-secret-key"
    user_state.activate_user("alice")
    monkeypatch.setattr(command_router, "WEATHER_API_KEY", secret)

    def fail_with_secret(*_args, **_kwargs):
        raise command_router.requests.ConnectionError(
            "connection failed for https://api.openweathermap.org/?appid=" + secret
        )

    monkeypatch.setattr(command_router.requests, "get", fail_with_secret)
    with caplog.at_level("WARNING", logger=command_router.logger.name):
        reply = command_router.process_command("weather in Chennai", "alice")

    assert reply == "Could not fetch weather data. Check your internet connection."
    assert "ConnectionError" in caplog.text
    assert secret not in caplog.text



@pytest.mark.parametrize("phrase", ["commute to work", "please commute tomorrow"])
def test_mute_router_does_not_match_commute(monkeypatch, phrase):
    user_state.activate_user("alice")
    presses = []
    monkeypatch.setattr(command_router.pyautogui, "press", lambda key: presses.append(key))
    monkeypatch.setattr(command_router, "_get_genai_client", lambda: None)
    reply = command_router.process_command(phrase, "alice")
    assert presses == []
    assert "AI responses are not configured" in reply


@pytest.mark.parametrize("phrase", ["check battery", "what is my battery", "battery status"])
def test_battery_status_matches_explicit_intent(monkeypatch, phrase):
    user_state.activate_user("alice")
    class Battery:
        percent = 74
        power_plugged = False
    monkeypatch.setattr(command_router.psutil, "sensors_battery", lambda: Battery())
    reply = command_router.process_command(phrase, "alice")
    assert "Battery is at 74%" in reply


def test_today_question_does_not_get_swallowed_by_date_handler(monkeypatch):
    user_state.activate_user("alice")
    monkeypatch.setattr(command_router, "_get_genai_client", lambda: None)
    reply = command_router.process_command("what's on today?", "alice")
    assert "AI responses are not configured" in reply
    assert not reply.startswith("Today is ")


def test_find_file_without_name_returns_specific_prompt():
    user_state.activate_user("alice")
    assert command_router.process_command("find file", "alice") == "Please specify a file name to find."


def test_search_for_file_without_name_returns_specific_prompt():
    user_state.activate_user("alice")
    assert command_router.process_command("search for file", "alice") == "Please specify a file name to find."



def test_direct_desktop_action_waits_for_exact_tool_registry_approval(monkeypatch):
    from intelligence import automation as automation_module
    from intelligence.tool_registry import ToolRegistry

    user_state.activate_user("alice")
    events = []
    registry = ToolRegistry()
    registry.register(
        "test_launch",
        "Launch a test application.",
        lambda *, username: events.append(username) or {"started": True},
        risk_level="reversible",
        requires_confirmation=True,
    )
    monkeypatch.setattr(command_router, "build_automation_registry", lambda: registry)
    monkeypatch.setattr(
        automation_module,
        "_activity",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setitem(
        command_router._DIRECT_ACTIONS,
        "open chrome",
        ("test_launch", {}, "open chrome"),
    )

    waiting = command_router.process_command("open chrome", "alice")
    assert "waiting for your approval" in waiting.lower()
    assert events == []

    wrong = command_router.process_command("confirm lock system", "alice")
    assert "does not match" in wrong.lower()
    assert events == []

    completed = command_router.process_command("confirm open chrome", "alice")
    assert "approved and completed" in completed.lower()
    assert events == ["alice"]


def test_direct_desktop_action_can_be_cancelled_without_execution(monkeypatch):
    from intelligence import automation as automation_module
    from intelligence.tool_registry import ToolRegistry

    user_state.activate_user("alice")
    events = []
    registry = ToolRegistry()
    registry.register(
        "test_screenshot",
        "Capture a test screenshot.",
        lambda *, username: events.append(username) or {"saved": True},
        risk_level="reversible",
        requires_confirmation=True,
    )
    monkeypatch.setattr(command_router, "build_automation_registry", lambda: registry)
    monkeypatch.setattr(automation_module, "_activity", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(
        command_router._DIRECT_ACTIONS,
        "take screenshot",
        ("test_screenshot", {}, "take screenshot"),
    )

    waiting = command_router.process_command("take screenshot", "alice")
    assert "waiting for your approval" in waiting.lower()
    cancelled = command_router.process_command("cancel action", "alice")
    assert "cancelled" in cancelled.lower()
    assert events == []


def test_power_action_confirmation_still_reaches_power_handler(monkeypatch):
    user_state.activate_user("alice")
    monkeypatch.setattr(
        command_router,
        "handle_power_command",
        lambda command, username: {"status": "confirmed", "action": "shutdown"},
    )
    monkeypatch.setattr(command_router.os, "name", "posix")
    reply = command_router.process_command("confirm shutdown", "alice")
    assert "supported only on Windows" in reply



def test_system_deactivation_clears_pending_direct_action(monkeypatch):
    from intelligence import automation as automation_module
    from intelligence.tool_registry import ToolRegistry

    user_state.activate_user("alice")
    registry = ToolRegistry()
    registry.register(
        "test_action",
        "A test action.",
        lambda *, username: {"ok": True},
        risk_level="reversible",
        requires_confirmation=True,
    )
    monkeypatch.setattr(command_router, "build_automation_registry", lambda: registry)
    monkeypatch.setattr(automation_module, "_activity", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(
        command_router._DIRECT_ACTIONS,
        "open chrome",
        ("test_action", {}, "open chrome"),
    )
    queued = command_router.process_command("open chrome", "alice")
    assert "waiting for your approval" in queued.lower()
    assert "alice" in command_router._PENDING_COMMAND_APPROVALS

    reply = command_router.process_command("system deactivate", "alice")
    assert "System deactivating" in reply
    assert "alice" not in command_router._PENDING_COMMAND_APPROVALS
