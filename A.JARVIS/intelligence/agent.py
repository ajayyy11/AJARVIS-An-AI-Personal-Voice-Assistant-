"""Manual Gemini tool-calling adapter with an explicit read-only allow-list.

The model proposes calls; this module validates every call against the registry.
Only read-only handlers are ever auto-executed. Side-effecting tools are rejected
until a trusted UI confirmation workflow is implemented.
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any, Mapping


from intelligence.tool_registry import (
    ToolArgumentError,
    ToolNotFoundError,
    ToolRegistry,
    ToolRegistryError,
)

logger = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 3
MAX_TOOL_CALLS = 5
MAX_TOOL_RESULT_CHARS = 4000


def _current_datetime(*, username: str) -> str:
    return datetime.datetime.now().astimezone().strftime("%A, %B %d, %Y at %I:%M:%S %p %Z")


def _system_status(*, username: str) -> dict[str, Any]:
    """Return a small, read-only snapshot of the current computer."""
    import psutil

    memory = psutil.virtual_memory()
    home = os.path.expanduser("~")
    try:
        disk_percent = psutil.disk_usage(home).percent
    except (OSError, PermissionError):
        disk_percent = None
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": memory.percent,
        "disk_percent": disk_percent,
    }


def _battery_status(*, username: str) -> dict[str, Any]:
    """Report battery values without changing machine state."""
    import psutil

    battery = psutil.sensors_battery()
    if battery is None:
        return {"available": False, "message": "Battery information is not available."}
    return {
        "available": True,
        "percent": int(battery.percent),
        "charging": bool(battery.power_plugged),
    }


def build_default_registry() -> ToolRegistry:
    """Build the small, safe starter toolkit. All tools are read-only."""
    registry = ToolRegistry()
    registry.register(
        "get_current_datetime",
        "Get the current local date, time, and timezone.",
        _current_datetime,
    )
    registry.register(
        "get_system_status",
        "Read CPU, memory, and home-disk usage percentages.",
        _system_status,
    )
    registry.register(
        "get_battery_status",
        "Read battery percentage and charging state, if available.",
        _battery_status,
    )
    return registry


def _plain_result(value: Any) -> Any:
    """Bound tool output size before returning it to the model."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        result = value
    elif isinstance(value, Mapping):
        result = dict(value)
    elif isinstance(value, (list, tuple)):
        result = list(value)
    else:
        result = str(value)
    rendered = str(result)
    if len(rendered) > MAX_TOOL_RESULT_CHARS:
        return rendered[:MAX_TOOL_RESULT_CHARS] + "… [truncated]"
    return result


def _part_value(part: Any, name: str, fallback: Any = None) -> Any:
    if isinstance(part, Mapping):
        return part.get(name, fallback)
    return getattr(part, name, fallback)


def generate_agent_response(
    *,
    client: Any,
    contents: list[Any],
    system_instruction: str,
    username: str,
    model: str = "gemini-2.5-flash",
    registry: ToolRegistry | None = None,
    types_module: Any = None,
) -> str:
    """Run bounded manual function calling; never invoke side-effecting tools.

    The SDK types module is injectable to allow isolated unit tests without a
    network connection or Google SDK installation. Normal usage imports lazily.
    """
    if not isinstance(username, str) or not username.strip():
        raise ValueError("An authenticated username is required.")
    if registry is None:
        registry = build_default_registry()

    config_types = types_module
    if config_types is None:
        from google.genai import types as config_types

    declarations = []
    for item in registry.function_declarations():
        declarations.append(
            config_types.FunctionDeclaration(
                name=item["name"],
                description=item["description"],
                parameters_json_schema=item["parameters"],
            )
        )
    if not declarations:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config_types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=512,
            ),
        )
        return (getattr(response, "text", None) or "").strip()

    provider_tool = config_types.Tool(function_declarations=declarations)
    config = config_types.GenerateContentConfig(
        system_instruction=system_instruction,
        max_output_tokens=512,
        tools=[provider_tool],
        automatic_function_calling=config_types.AutomaticFunctionCallingConfig(
            disable=True
        ),
    )

    conversation = list(contents)
    calls_executed = 0
    latest_text = ""
    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = client.models.generate_content(
            model=model,
            contents=conversation,
            config=config,
        )
        latest_text = (getattr(response, "text", None) or "").strip()
        function_calls = getattr(response, "function_calls", None) or []
        if not function_calls:
            return latest_text

        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            logger.warning("Gemini returned function calls without candidate content.")
            return latest_text or "I couldn't safely process that tool request."
        model_content = _part_value(candidates[0], "content")
        if model_content is None:
            return latest_text or "I couldn't safely process that tool request."
        conversation.append(model_content)

        function_parts = []
        for function_call in function_calls:
            calls_executed += 1
            name = _part_value(function_call, "name", "")
            arguments = _part_value(function_call, "args", {})
            result: Any

            if calls_executed > MAX_TOOL_CALLS:
                result = {"error": "Tool-call limit reached. Please ask a simpler question."}
            else:
                try:
                    spec = registry.get(name)
                    if spec.risk_level != "read_only" or spec.confirmation_required:
                        result = {
                            "error": "This action requires explicit user approval and was not run."
                        }
                    else:
                        if not isinstance(arguments, Mapping):
                            raise ToolArgumentError("Tool arguments must be an object.")
                        result = registry.invoke(
                            name,
                            username=username,
                            arguments=arguments,
                        )
                        result = _plain_result(result)
                except (ToolNotFoundError, ToolArgumentError, ToolRegistryError):
                    logger.info("Rejected invalid or unavailable agent tool: %r", name)
                    result = {"error": "The requested tool or its arguments are not allowed."}
                except Exception:
                    logger.warning("Agent tool failed: %r", name, exc_info=True)
                    result = {"error": "The requested tool failed. No further action was taken."}

            function_parts.append(
                config_types.Part.from_function_response(
                    name=name if isinstance(name, str) else "",
                    response={"result": result},
                )
            )

        conversation.append(
            config_types.Content(role="tool", parts=function_parts)
        )

    logger.warning("Gemini agent reached its maximum tool round count.")
    return latest_text or "I reached the tool-call limit. Please break the request into smaller steps."
