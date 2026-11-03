import pytest

from intelligence.context import (
    build_context_messages,
    classify_intent,
    is_follow_up,
    select_relevant_history,
)


@pytest.mark.parametrize("text,expected", [
    ("What time is it?", "question"),
    ("How do I configure the microphone?", "question"),
    ("open Chrome", "command"),
    ("search latest Python news", "search"),
    ("research Python decorators", "search"),
    ("find information about Python", "search"),
    ("explain more", "follow_up"),
    ("do that again", "follow_up"),
    ("search it", "follow_up"),
    ("hello Jarvis", "conversation"),
    ("", "unknown"),
])
def test_classify_intent(text, expected):
    assert classify_intent(text) == expected


@pytest.mark.parametrize("text", [
    "explain more", "continue", "do that again", "what about that",
    "and also", "open it", "tell me more", "how about it", "search it",
])
def test_follow_up_patterns(text):
    assert is_follow_up(text)


def test_general_how_and_why_questions_are_not_follow_ups():
    assert not is_follow_up("How do I configure the microphone?")
    assert not is_follow_up("Why does the app fail?")
    assert classify_intent("How do I configure the microphone?") == "question"
    assert classify_intent("Why does the app fail?") == "question"


def test_new_topic_selects_relevant_history():
    history = [
        {"command": "weather in Chennai", "response": "Sunny"},
        {"command": "open Chrome", "response": "Opening Chrome"},
        {"command": "explain Python decorators", "response": "They wrap functions"},
    ]
    result = select_relevant_history("Tell me about Python decorators", history)
    assert result[0]["command"] == "explain Python decorators"


def test_follow_up_prioritizes_recent_exchange():
    history = [
        {"command": "weather in Chennai", "response": "Sunny"},
        {"command": "explain Python decorators", "response": "They wrap functions"},
    ]
    result = select_relevant_history("explain more", history)
    assert result[-1]["command"] == "explain Python decorators"


def test_context_is_bounded_and_invalid_inputs_are_safe():
    history = [{"command": "x" * 9000, "response": "y" * 9000}]
    result = select_relevant_history("hello", history, limit=99)
    assert len(result) <= 5
    assert sum(len(x["command"]) + len(x["response"]) for x in result) <= 6000
    assert select_relevant_history("", history) == []
    assert select_relevant_history("hi", None) == []


def test_context_messages_end_with_current_user_request():
    messages = build_context_messages(
        "explain more",
        [{"command": "explain Python", "response": "Python is a language"}],
    )
    assert messages[-1] == {"role": "user", "parts": [{"text": "explain more"}]}
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "model"


def test_follow_up_questions_keep_previous_topic_context():
    history=[
        {"command":"Tell me about Python decorators","response":"They wrap other functions."},
        {"command":"What is a closure?","response":"A closure retains surrounding state."},
    ]
    result=select_relevant_history("What about the performance?",history)
    assert result[-1]["command"]=="What is a closure?"


@pytest.mark.parametrize("text",[
    ("What do you remember about me?","memory"),
    ("Remember that I prefer concise explanations","memory"),
    ("Forget my answer style","memory"),
    ("What about the price?","follow_up"),
    ("How much does it cost?","follow_up"),
])
def test_phase_four_intent_and_follow_up_patterns(text):
    command,expected=text
    assert classify_intent(command)==expected
