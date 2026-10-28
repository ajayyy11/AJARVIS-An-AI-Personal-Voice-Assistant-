import pytest

from intelligence.tool_registry import (
    ToolArgumentError,
    ToolConfirmationRequired,
    ToolNotFoundError,
    ToolRegistry,
    ToolRegistryError,
)


def schema():
    return {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 80},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
        "additionalProperties": False,
    }


def test_tool_invocation_passes_user_and_validated_arguments():
    registry = ToolRegistry()
    calls = []
    registry.register(
        "search_notes",
        "Search the current user's notes.",
        lambda *, username, **kwargs: calls.append((username, kwargs)) or "ok",
        parameters=schema(),
    )
    assert registry.invoke(
        "search_notes", username=" ajay ", arguments={"query": "meeting", "limit": 3}
    ) == "ok"
    assert calls == [("ajay", {"query": "meeting", "limit": 3})]


def test_unregistered_or_disabled_tool_is_not_invokable():
    registry = ToolRegistry()
    registry.register("hidden_tool", "Disabled.", lambda **_: None, enabled=False)
    with pytest.raises(ToolNotFoundError):
        registry.invoke("not_registered", username="ajay")
    with pytest.raises(ToolNotFoundError):
        registry.invoke("hidden_tool", username="ajay")


def test_duplicate_names_and_invalid_names_are_rejected():
    registry = ToolRegistry()
    registry.register("read_notes", "Read notes.", lambda **_: None)
    with pytest.raises(ToolRegistryError, match="already registered"):
        registry.register("read_notes", "Again.", lambda **_: None)
    for name in ("", "OpenApp", "run-shell", "1tool", "a"):
        with pytest.raises(ToolRegistryError):
            registry.register(name, "Invalid.", lambda **_: None)


def test_required_and_unrecognized_arguments_are_rejected():
    registry = ToolRegistry()
    registry.register("search_notes", "Search.", lambda **_: None, parameters=schema())
    with pytest.raises(ToolArgumentError, match="Missing required"):
        registry.invoke("search_notes", username="ajay")
    with pytest.raises(ToolArgumentError, match="Unknown argument"):
        registry.invoke(
            "search_notes", username="ajay",
            arguments={"query": "meeting", "local_path": "secret"},
        )


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": 123},
        {"query": ""},
        {"query": "q" * 81},
        {"query": "meeting", "limit": True},
        {"query": "meeting", "limit": 0},
        {"query": "meeting", "limit": 11},
    ],
)
def test_argument_types_lengths_and_bounds_are_enforced(arguments):
    registry = ToolRegistry()
    registry.register("search_notes", "Search.", lambda **_: None, parameters=schema())
    with pytest.raises(ToolArgumentError):
        registry.invoke("search_notes", username="ajay", arguments=arguments)


def test_destructive_tool_requires_confirmation_before_handler_runs():
    registry = ToolRegistry()
    calls = []
    registry.register(
        "shutdown_system", "Shut down the computer.",
        lambda *, username: calls.append(username),
        risk_level="destructive",
    )
    with pytest.raises(ToolConfirmationRequired):
        registry.invoke("shutdown_system", username="ajay")
    assert calls == []
    assert registry.invoke("shutdown_system", username="ajay", confirmed=True) is None
    assert calls == ["ajay"]


def test_explicit_confirmation_can_gate_other_side_effects():
    registry = ToolRegistry()
    registry.register(
        "send_message", "Send a message.", lambda *, username: "sent",
        risk_level="reversible", requires_confirmation=True,
    )
    with pytest.raises(ToolConfirmationRequired):
        registry.invoke("send_message", username="ajay")
    assert registry.invoke("send_message", username="ajay", confirmed=True) == "sent"


def test_username_must_be_nonempty():
    registry = ToolRegistry()
    registry.register("get_profile", "Read profile.", lambda **_: "ok")
    with pytest.raises(ToolArgumentError):
        registry.invoke("get_profile", username=" ")
    assert registry.invoke("get_profile", username=" ajay ") == "ok"


def test_declarations_do_not_expose_handlers_and_are_defensive_copies():
    registry = ToolRegistry()
    registry.register("search_notes", "Search.", lambda **_: None, parameters=schema())
    declarations = registry.function_declarations()
    assert len(declarations) == 1
    assert "handler" not in declarations[0]
    declarations[0]["parameters"]["properties"]["query"]["maxLength"] = 1
    assert registry.get("search_notes").parameters["properties"]["query"]["maxLength"] == 80


def test_list_is_sorted_and_disabled_tools_are_hidden_by_default():
    registry = ToolRegistry()
    registry.register("z_tool", "Z.", lambda **_: None)
    registry.register("a_tool", "A.", lambda **_: None, enabled=False)
    assert [item["name"] for item in registry.list_tools()] == ["z_tool"]
    assert [item["name"] for item in registry.list_tools(include_disabled=True)] == [
        "a_tool", "z_tool"
    ]
