"""Manual Gemini tool-calling adapter with an explicit read-only allow-list.

The model proposes calls; this module validates every call against the registry.
Only read-only handlers are ever auto-executed. Side-effecting tools are rejected
until a trusted UI confirmation workflow is implemented.
"""

from __future__ import annotations

import datetime
import logging
import os
import time
from typing import Any, Mapping


from intelligence.notes import read_recent_notes, search_personal_notes
from intelligence.genai_client import build_gemini_http_options
from intelligence.user_memory import list_memories, search_memories
from intelligence.personal_intelligence import build_personal_focus
from intelligence.tool_registry import (
    ToolArgumentError,
    ToolNotFoundError,
    ToolRegistry,
    ToolRegistryError,
)

logger = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 2
MAX_TOOL_CALLS = 5
MAX_TOOL_RESULT_CHARS = 4000
DEFAULT_AGENT_REQUEST_DEADLINE_SECONDS = 25.0
MAX_AGENT_REQUEST_DEADLINE_SECONDS = 60.0
AGENT_TIMEOUT_MESSAGE = "That request took too long to complete. Please try a smaller request."


def _resolve_agent_deadline_seconds(value: float | None) -> float:
    """Return a finite, bounded wall-clock budget for the full agent request."""
    if value is None:
        raw = os.getenv("GEMINI_REQUEST_DEADLINE_SECONDS", "").strip()
        try:
            value = float(raw) if raw else DEFAULT_AGENT_REQUEST_DEADLINE_SECONDS
        except (TypeError, ValueError):
            value = DEFAULT_AGENT_REQUEST_DEADLINE_SECONDS
    if isinstance(value, bool):
        raise ValueError("Agent request deadline must be a positive number.")
    try:
        budget = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Agent request deadline must be a positive number.") from exc
    if not 0 < budget <= MAX_AGENT_REQUEST_DEADLINE_SECONDS:
        raise ValueError(
            f"Agent request deadline must be greater than zero and no more than "
            f"{MAX_AGENT_REQUEST_DEADLINE_SECONDS:g} seconds."
        )
    return budget


def _deadline_http_options(types_module: Any, deadline: float) -> Any:
    """Create one-attempt HTTP options using the time left in the outer request."""
    remaining_ms = int((deadline - time.monotonic()) * 1000)
    if remaining_ms < 100:
        raise TimeoutError("The agent request deadline has elapsed.")
    return build_gemini_http_options(
        types_module=types_module,
        timeout_ms_override=remaining_ms,
        retry_attempts_override=1,
    )


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


def _read_recent_notes_tool(*, username: str, limit: int = 5) -> dict[str, Any]:
    try:
        notes = read_recent_notes(username, limit=limit)
    except OSError:
        return {"available": False, "message": "Personal notes are not available right now."}
    return {"count": len(notes), "notes": notes}


def _search_personal_notes_tool(
    *, username: str, query: str, limit: int = 5
) -> dict[str, Any]:
    try:
        matches = search_personal_notes(username, query, limit=limit)
    except OSError:
        return {"available": False, "message": "Personal notes are not available right now."}
    return {"count": len(matches), "matches": matches}


def build_default_registry() -> ToolRegistry:
    """Build the safe starter toolkit. Every registered built-in is read-only."""
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
    registry.register(
        "read_recent_notes",
        "Read the most recent saved notes belonging to the signed-in user.",
        _read_recent_notes_tool,
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 5}},
            "required": [],
            "additionalProperties": False,
        },
    )
    registry.register(
        "search_personal_notes",
        "Search the signed-in user's saved notes for a phrase.",
        _search_personal_notes_tool,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 120},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    )
    registry.register(
        "read_user_memories",
        "Read the signed-in user's explicitly saved preferences and facts.",
        lambda *, username, limit=10: {"memories": list_memories(username, limit=limit)},
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 30}},
            "required": [],
            "additionalProperties": False,
        },
    )
    registry.register(
        "search_user_memories",
        "Find explicitly saved user preferences and facts containing a phrase.",
        lambda *, username, query, limit=5: {"matches": search_memories(username, query, limit=limit)},
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 120},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    )
    registry.register(
        "get_personal_focus",
        "Read the signed-in user's active projects and explainably prioritised open tasks.",
        lambda *, username: build_personal_focus(username),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
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
    model: str | None = None,
    registry: ToolRegistry | None = None,
    types_module: Any = None,
    request_timeout_seconds: float | None = None,
) -> str:
    """Run bounded manual function calling; never invoke side-effecting tools.

    The SDK types module is injectable to allow isolated unit tests without a
    network connection or Google SDK installation. Normal usage imports lazily.
    """
    if not isinstance(username, str) or not username.strip():
        raise ValueError("An authenticated username is required.")
    request_budget = _resolve_agent_deadline_seconds(request_timeout_seconds)
    deadline = time.monotonic() + request_budget
    if registry is None:
        registry = build_default_registry()

    selected_model = (model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")).strip()
    if not selected_model:
        selected_model = "gemini-2.5-flash"

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
        try:
            request_config = config_types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=512,
                http_options=_deadline_http_options(config_types, deadline),
            )
            response = client.models.generate_content(
                model=selected_model,
                contents=contents,
                config=request_config,
            )
        except Exception:
            if time.monotonic() >= deadline:
                logger.warning("Gemini request exceeded the agent wall-clock deadline.")
                return AGENT_TIMEOUT_MESSAGE
            raise
        return (getattr(response, "text", None) or "").strip()

    provider_tool = config_types.Tool(function_declarations=declarations)
    base_config = {
        "system_instruction": system_instruction,
        "max_output_tokens": 512,
        "tools": [provider_tool],
        "automatic_function_calling": config_types.AutomaticFunctionCallingConfig(
            disable=True
        ),
    }

    conversation = list(contents)
    calls_executed = 0
    latest_text = ""
    for _ in range(MAX_TOOL_ROUNDS + 1):
        try:
            request_config = config_types.GenerateContentConfig(
                **base_config,
                http_options=_deadline_http_options(config_types, deadline),
            )
            response = client.models.generate_content(
                model=selected_model,
                contents=conversation,
                config=request_config,
            )
        except Exception:
            if time.monotonic() >= deadline:
                logger.warning("Gemini tool-calling request exceeded the agent wall-clock deadline.")
                return latest_text or AGENT_TIMEOUT_MESSAGE
            raise
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
