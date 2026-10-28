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
        "get_current_datetime", "get_system_status", "get_battery_status"
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
