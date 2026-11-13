from types import SimpleNamespace

import pytest

from intelligence.agent import build_default_registry, generate_agent_response
from intelligence.tool_registry import ToolRegistry


class FakeTypes:
    class FunctionDeclaration:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class Tool:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class AutomaticFunctionCallingConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class Part:
        @staticmethod
        def from_function_response(**kwargs):
            return SimpleNamespace(**kwargs)

    class Content:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    class Models:
        def __init__(self, owner):
            self.owner = owner

        def generate_content(self, **kwargs):
            self.owner.calls.append(kwargs)
            return self.owner.responses.pop(0)

    @property
    def models(self):
        return self.Models(self)


def response(text="", function_calls=None, content=None):
    candidates = [SimpleNamespace(content=content)] if content is not None else []
    return SimpleNamespace(
        text=text,
        function_calls=function_calls or [],
        candidates=candidates,
    )


def function_call(name, args=None):
    return SimpleNamespace(name=name, args=args or {})


def test_default_registry_exposes_only_read_only_tools():
    registry = build_default_registry()
    tools = registry.list_tools()

    assert {tool["name"] for tool in tools} == {
        "get_current_datetime", "get_system_status", "get_battery_status",
        "read_recent_notes", "search_personal_notes", "read_user_memories",
        "search_user_memories", "get_personal_focus"
    }
    assert all(tool["risk_level"] == "read_only" for tool in tools)


def test_agent_manually_executes_valid_read_only_tool_and_returns_final_text():
    registry = ToolRegistry()
    executed = []
    registry.register(
        "get_value",
        "Read a test value.",
        lambda *, username: executed.append(username) or {"value": 42},
    )
    model_content = SimpleNamespace(role="model", parts=["function call"])
    client = FakeClient([
        response(
            function_calls=[function_call("get_value")],
            content=model_content,
        ),
        response(text="The value is 42."),
    ])

    result = generate_agent_response(
        client=client,
        contents=[{"role": "user", "parts": [{"text": "Get the value"}]}],
        system_instruction="Test assistant",
        username="ajay",
        registry=registry,
        types_module=FakeTypes,
    )

    assert result == "The value is 42."
    assert executed == ["ajay"]
    assert len(client.calls) == 2
    first_config = client.calls[0]["config"]
    assert first_config.automatic_function_calling.disable is True
    assert first_config.tools[0].function_declarations[0].name == "get_value"
    tool_content = client.calls[1]["contents"][-1]
    assert tool_content.role == "tool"
    assert tool_content.parts[0].response == {"result": {"value": 42}}


@pytest.mark.parametrize(
    "requested_name, risk_level",
    [("not_registered", "read_only"), ("delete_file", "destructive")],
)
def test_unknown_and_side_effecting_tools_are_not_executed(requested_name, risk_level):
    registry = ToolRegistry()
    executed = []
    if requested_name == "delete_file":
        registry.register(
            requested_name, "Delete file.", lambda **_: executed.append(True),
            risk_level=risk_level,
        )
    else:
        registry.register("read_safe_value", "Read a test value.", lambda **_: "safe")
    content = SimpleNamespace(role="model", parts=["function call"])
    client = FakeClient([
        response(function_calls=[function_call(requested_name)], content=content),
        response(text="I could not safely run that action."),
    ])

    result = generate_agent_response(
        client=client,
        contents=[],
        system_instruction="Test assistant",
        username="ajay",
        registry=registry,
        types_module=FakeTypes,
    )

    assert result == "I could not safely run that action."
    assert executed == []
    tool_content = client.calls[1]["contents"][-1]
    message = tool_content.parts[0].response["result"]["error"]
    assert "not allowed" in message or "approval" in message


def test_invalid_arguments_are_rejected_before_handler_execution():
    registry = ToolRegistry()
    executed = []
    registry.register(
        "lookup",
        "Find something.",
        lambda *, username, query: executed.append(query),
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 1}},
            "required": ["query"],
            "additionalProperties": False,
        },
    )
    content = SimpleNamespace(role="model", parts=["function call"])
    client = FakeClient([
        response(function_calls=[function_call("lookup", {"query": 3})], content=content),
        response(text="I could not safely run that lookup."),
    ])

    generate_agent_response(
        client=client,
        contents=[],
        system_instruction="Test assistant",
        username="ajay",
        registry=registry,
        types_module=FakeTypes,
    )

    assert executed == []
    error = client.calls[1]["contents"][-1].parts[0].response["result"]["error"]
    assert "not allowed" in error


def test_agent_requires_a_nonempty_username():
    client = FakeClient([response(text="unused")])
    with pytest.raises(ValueError, match="username"):
        generate_agent_response(
            client=client,
            contents=[],
            system_instruction="Test",
            username=" ",
            registry=ToolRegistry(),
            types_module=FakeTypes,
        )



def test_empty_registry_falls_back_to_plain_gemini_response():
    client = FakeClient([response(text="Hello there.")])

    result = generate_agent_response(
        client=client,
        contents=[{"role": "user", "parts": [{"text": "Hello"}]}],
        system_instruction="Test assistant",
        username="ajay",
        registry=ToolRegistry(),
        types_module=FakeTypes,
    )

    assert result == "Hello there."
    assert not getattr(client.calls[0]["config"], "tools", [])


def test_default_registry_includes_read_only_personal_memory_tools(monkeypatch):
    from intelligence import agent

    monkeypatch.setattr(agent, "list_memories", lambda username, limit=10: [{"key": "answer_style", "value": "concise"}])
    monkeypatch.setattr(agent, "search_memories", lambda username, query, limit=5: [{"key": "answer_style", "value": "concise"}])
    registry = agent.build_default_registry()

    assert registry.invoke("read_user_memories", username="ajay")["memories"][0]["value"] == "concise"
    assert registry.invoke("search_user_memories", username="ajay", arguments={"query": "style"})["matches"][0]["key"] == "answer_style"
    assert all(item["risk_level"] == "read_only" for item in registry.list_tools())


def test_default_registry_exposes_explainable_personal_focus(monkeypatch):
    from intelligence import agent

    monkeypatch.setattr(
        agent,
        "build_personal_focus",
        lambda username: {
            "active_projects": [{"id": 1, "name": "AJARVIS"}],
            "next_tasks": [{"id": 4, "title": "Run Phase 7 tests", "priority_score": 95}],
            "metrics": {"active_projects": 1, "open_tasks": 1, "overdue_tasks": 0, "in_progress_tasks": 0},
            "prioritisation": "Transparent score.",
        },
    )
    registry = agent.build_default_registry()
    result = registry.invoke("get_personal_focus", username="alice")
    assert result["next_tasks"][0]["priority_score"] == 95
    assert all(tool["risk_level"] == "read_only" for tool in registry.list_tools())

def test_agent_uses_default_model_for_tool_enabled_requests_when_model_omitted():
    registry = ToolRegistry()
    registry.register("read_value", "Read a value.", lambda *, username: {"value": 7})
    client = FakeClient([response(text="The value is seven.")])

    result = generate_agent_response(
        client=client,
        contents=[{"role": "user", "parts": [{"text": "Read the value"}]}],
        system_instruction="Test assistant",
        username="ajay",
        registry=registry,
        types_module=FakeTypes,
    )

    assert result == "The value is seven."
    assert client.calls[0]["model"] == "gemini-2.5-flash"
