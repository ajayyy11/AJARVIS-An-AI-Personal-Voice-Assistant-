"""Bounded multi-step task execution with user-bound, one-time approvals.

Only registered tools may run. Read-only steps execute automatically; every
computer-changing step pauses until the signed-in user approves that exact step.
Pending plans/approvals live in memory and expire, so a restart fails closed.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import subprocess
import threading
import time
import uuid
import webbrowser
from urllib.parse import urlsplit
from typing import Any, Mapping

from intelligence.agent import build_default_registry
from intelligence.tool_registry import ToolArgumentError, ToolRegistry, ToolRegistryError

logger = logging.getLogger(__name__)

MAX_PLAN_STEPS = 5
MAX_PLAN_TEXT = 1000
PLAN_TTL_SECONDS = 300
APPROVAL_TTL_SECONDS = 60

_plans: dict[str, dict[str, Any]] = {}
_lock = threading.RLock()


class AutomationError(ValueError):
    """Raised for invalid automation plans, ownership, or state transitions."""


def _valid_owner(username: str) -> str:
    if not isinstance(username, str) or not username.strip() or len(username.strip()) > 100:
        raise AutomationError("An authenticated username is required.")
    return username.strip()


def _validate_website_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2000:
        raise ToolArgumentError("Website URL is invalid.")
    normalized = url.strip()
    parts = urlsplit(normalized)
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise ToolArgumentError("Only HTTPS website URLs are allowed.")
    if parts.username or parts.password:
        raise ToolArgumentError("URLs containing embedded credentials are not allowed.")
    hostname = parts.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ToolArgumentError("Local network destinations are not allowed.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ToolArgumentError("Private or local IP destinations are not allowed.")
    return normalized


def _open_website(*, username: str, url: str) -> dict[str, Any]:
    """Open one explicit HTTPS website; never evaluate a command or file path."""
    normalized = _validate_website_url(url)
    opened = webbrowser.open(normalized, new=2)
    return {"opened": bool(opened), "message": "Browser request submitted." if opened else "Browser did not confirm opening."}


def _launch_application(*, username: str, application: str) -> dict[str, str]:
    """Launch a single fixed application identifier without a shell."""
    if os.name != "nt":
        raise RuntimeError("Application launching is available only on Windows.")
    allowed = {
        "calculator": ["calc.exe"],
        "notepad": ["notepad.exe"],
        "file_explorer": ["explorer.exe"],
        "chrome": ["chrome.exe"],
        "vscode": ["code.exe"],
    }
    command = allowed.get(application)
    if command is None:
        raise ToolArgumentError("That application is not on the approved launch list.")
    subprocess.Popen(command, shell=False, close_fds=True)
    return {"started": application}


def _lock_workstation(*, username: str) -> dict[str, str]:
    """Lock the current Windows workstation."""
    if os.name != "nt":
        raise RuntimeError("Workstation locking is available only on Windows.")
    import ctypes

    if not ctypes.windll.user32.LockWorkStation():
        raise OSError("Windows did not confirm the workstation lock request.")
    return {"locked": True}


def build_automation_registry() -> ToolRegistry:
    """Create read-only tools plus a small, explicitly gated action allow-list."""
    registry = build_default_registry()
    registry.register(
        "open_website",
        "Open one HTTPS website in the default browser.",
        _open_website,
        risk_level="reversible",
        requires_confirmation=True,
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "minLength": 9, "maxLength": 2000}},
            "required": ["url"],
            "additionalProperties": False,
        },
    )
    registry.register(
        "launch_application",
        "Launch one application from the fixed Windows allow-list.",
        _launch_application,
        risk_level="reversible",
        requires_confirmation=True,
        parameters={
            "type": "object",
            "properties": {
                "application": {
                    "type": "string",
                    "enum": ["calculator", "notepad", "file_explorer", "chrome", "vscode"],
                }
            },
            "required": ["application"],
            "additionalProperties": False,
        },
    )
    registry.register(
        "lock_workstation",
        "Lock the current Windows workstation.",
        _lock_workstation,
        risk_level="destructive",
        requires_confirmation=True,
    )
    return registry


def _safe_preview(value: Any) -> Any:
    """Return JSON-compatible, bounded arguments/results for the owning user."""
    if isinstance(value, Mapping):
        return {str(key): _safe_preview(item) for key, item in list(value.items())[:20]}
    if isinstance(value, (list, tuple)):
        return [_safe_preview(item) for item in value[:20]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value[:2000] if isinstance(value, str) else value
    return str(value)[:300]


def _snapshot(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan_id": plan["plan_id"],
        "goal": plan["goal"],
        "status": plan["status"],
        "steps": [
            {
                "step_id": step["step_id"],
                "tool": step["tool"],
                "summary": step["summary"],
                "reason": step["reason"],
                "risk_level": step["risk_level"],
                "requires_confirmation": step["requires_confirmation"],
                "status": step["status"],
                "arguments": _safe_preview(step["arguments"]),
                "result": _safe_preview(step.get("result")),
                "error": step.get("error"),
            }
            for step in plan["steps"]
        ],
        "cancel_requested": bool(plan.get("cancel_requested", False)),
        "approval": (
            {
                "approval_id": plan["approval_id"],
                "step_id": plan["steps"][plan["current_step"]]["step_id"],
                "expires_in_seconds": max(0, int(plan["approval_expires_at"] - time.monotonic())),
            }
            if plan.get("approval_id") else None
        ),
        "created_at": plan["created_at"],
    }


def _activity(username: str, plan: dict[str, Any], event: str, step: dict[str, Any] | None = None, summary: str = "") -> None:
    try:
        from intelligence.activity_log import record_activity

        # Keep audit data metadata-only. Planner-generated summaries, user goals,
        # URLs, arguments and tool results are never persisted to this table.
        safe_summary = f"{step['tool']} {event}" if step else f"Automation {event}"
        record_activity(
            username=username,
            plan_id=plan["plan_id"],
            step_number=(plan["steps"].index(step) + 1) if step in plan["steps"] else None,
            event_type=event,
            tool_name=step["tool"] if step else None,
            summary=safe_summary[:240],
        )
    except Exception:
        logger.warning("Could not write automation activity event", exc_info=True)


def create_plan(
    username: str,
    goal: str,
    proposed_steps: list[Mapping[str, Any]],
    *,
    registry: ToolRegistry | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Validate a planner proposal and store a bounded user-owned plan."""
    owner = _valid_owner(username)
    if not isinstance(goal, str) or not goal.strip() or len(goal.strip()) > 180:
        raise AutomationError("The plan goal must contain 1–180 characters.")
    if not isinstance(proposed_steps, list) or not 1 <= len(proposed_steps) <= MAX_PLAN_STEPS:
        raise AutomationError(f"A task plan must contain between 1 and {MAX_PLAN_STEPS} steps.")
    tools = registry or build_automation_registry()
    steps: list[dict[str, Any]] = []
    for index, proposed in enumerate(proposed_steps):
        if not isinstance(proposed, Mapping):
            raise AutomationError(f"Step {index + 1} must be an object.")
        allowed_keys = {"tool", "arguments", "summary", "reason"}
        if set(proposed) - allowed_keys:
            raise AutomationError(f"Step {index + 1} contains unsupported fields.")
        name = proposed.get("tool")
        if not isinstance(name, str):
            raise AutomationError(f"Step {index + 1} must name a registered tool.")
        try:
            spec = tools.get(name)
        except ToolRegistryError as exc:
            raise AutomationError(f"Step {index + 1} requests an unavailable tool.") from exc
        arguments = proposed.get("arguments", {})
        if not isinstance(arguments, Mapping):
            raise AutomationError(f"Step {index + 1} arguments must be an object.")
        try:
            ToolRegistry._validate_arguments(spec.parameters, dict(arguments))
        except ToolArgumentError as exc:
            raise AutomationError(f"Step {index + 1} has invalid arguments: {exc}") from exc
        summary = proposed.get("summary", spec.description)
        reason = proposed.get("reason", "This step contributes to the requested task.")
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 180:
            raise AutomationError(f"Step {index + 1} summary must contain 1–180 characters.")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 240:
            raise AutomationError(f"Step {index + 1} reason must contain 1–240 characters.")
        if spec.name == "open_website":
            _validate_website_url(str(arguments.get("url", "")))
        needs_confirmation = spec.risk_level != "read_only" or spec.confirmation_required
        steps.append({
            "step_id": uuid.uuid4().hex,
            "tool": spec.name,
            "arguments": dict(arguments),
            "summary": summary.strip(),
            "reason": reason.strip(),
            "risk_level": spec.risk_level,
            "requires_confirmation": needs_confirmation,
            "status": "pending",
            "result": None,
            "error": None,
        })

    current_time = time.monotonic() if now is None else float(now)
    plan = {
        "plan_id": uuid.uuid4().hex,
        "username": owner,
        "goal": goal.strip(),
        "steps": steps,
        "status": "ready",
        "current_step": 0,
        "approval_id": None,
        "approval_expires_at": None,
        "expires_at": current_time + PLAN_TTL_SECONDS,
        "cancel_requested": False,
        "created_at": time.time(),
    }
    with _lock:
        _plans[plan["plan_id"]] = plan
    _activity(owner, plan, "plan_created")
    return _snapshot(plan)


def _get_plan(plan_id: str, username: str, now: float | None = None) -> dict[str, Any]:
    owner = _valid_owner(username)
    if not isinstance(plan_id, str):
        raise AutomationError("Plan was not found.")
    with _lock:
        plan = _plans.get(plan_id)
        if not plan or plan["username"] != owner:
            raise AutomationError("Plan was not found.")
        current_time = time.monotonic() if now is None else float(now)
        if current_time >= plan["expires_at"] and plan["status"] not in {"completed", "cancelled", "failed", "expired"}:
            plan["status"] = "expired"
            plan["approval_id"] = None
            _activity(owner, plan, "plan_expired")
        return plan


def advance_plan(plan_id: str, username: str, *, registry: ToolRegistry | None = None, now: float | None = None) -> dict[str, Any]:
    """Run read-only steps and pause at the first changing step for approval."""
    tools = registry or build_automation_registry()
    current_time = time.monotonic() if now is None else float(now)
    plan = _get_plan(plan_id, username, current_time)
    with _lock:
        if plan["status"] in {"awaiting_approval", "completed", "cancelled", "failed", "expired"}:
            return _snapshot(plan)
        if plan["status"] in {"running", "executing"}:
            raise AutomationError("This plan is already being executed.")
        plan["status"] = "running"

    while True:
        with _lock:
            if plan.get("cancel_requested"):
                plan["status"] = "cancelled"
                for pending_step in plan["steps"][plan["current_step"]:]:
                    if pending_step["status"] == "pending":
                        pending_step["status"] = "cancelled"
                _activity(username, plan, "plan_cancelled")
                return _snapshot(plan)
            if plan["current_step"] >= len(plan["steps"]):
                plan["status"] = "completed"
                _activity(username, plan, "plan_completed")
                return _snapshot(plan)
            step = plan["steps"][plan["current_step"]]
            if step["requires_confirmation"]:
                plan["approval_id"] = uuid.uuid4().hex
                plan["approval_expires_at"] = min(
                    plan["expires_at"], current_time + APPROVAL_TTL_SECONDS
                )
                plan["status"] = "awaiting_approval"
                step["status"] = "awaiting_approval"
                _activity(username, plan, "approval_required", step)
                return _snapshot(plan)
            step["status"] = "running"
            plan["status"] = "running"
        _activity(username, plan, "step_started", step)
        try:
            result = tools.invoke(step["tool"], username=username, arguments=step["arguments"])
            with _lock:
                step["status"] = "completed"
                step["result"] = _safe_preview(result)
                plan["current_step"] += 1
                if plan.get("cancel_requested"):
                    plan["status"] = "cancelled"
                    for pending_step in plan["steps"][plan["current_step"]:]:
                        if pending_step["status"] == "pending":
                            pending_step["status"] = "cancelled"
            _activity(username, plan, "step_completed", step)
            if plan["status"] == "cancelled":
                _activity(username, plan, "plan_cancelled")
                return _snapshot(plan)
        except Exception as exc:
            with _lock:
                step["status"] = "failed"
                step["error"] = "Execution failed. Review the activity log."
                plan["status"] = "failed"
            _activity(username, plan, "step_failed", step, type(exc).__name__)
            logger.warning("Automation step failed: %s", step["tool"], exc_info=True)
            return _snapshot(plan)


def respond_to_approval(
    approval_id: str,
    username: str,
    decision: str,
    *,
    registry: ToolRegistry | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Approve/reject exactly one pending step; approval tokens are one-time."""
    if decision not in {"approve", "reject"}:
        raise AutomationError("Approval decision must be 'approve' or 'reject'.")
    owner = _valid_owner(username)
    current_time = time.monotonic() if now is None else float(now)
    with _lock:
        match = next(
            (
                plan for plan in _plans.values()
                if plan["username"] == owner and plan.get("approval_id") == approval_id
            ),
            None,
        )
        if match is None:
            raise AutomationError("Approval was not found, has expired, or was already used.")
        plan = match
        if current_time >= plan["expires_at"] or current_time >= plan["approval_expires_at"]:
            plan["status"] = "expired"
            plan["approval_id"] = None
            _activity(owner, plan, "approval_expired", plan["steps"][plan["current_step"]])
            raise AutomationError("Approval has expired. Create a new plan.")
        step = plan["steps"][plan["current_step"]]
        if plan["status"] != "awaiting_approval" or step["status"] != "awaiting_approval":
            raise AutomationError("This step is not waiting for approval.")
        plan["approval_id"] = None  # consume before invoking; prevents replay/races
        plan["approval_expires_at"] = None
        if decision == "reject":
            step["status"] = "rejected"
            plan["status"] = "cancelled"
            _activity(owner, plan, "approval_rejected", step)
            return _snapshot(plan)
        plan["status"] = "executing"
        step["status"] = "running"

    _activity(owner, plan, "approval_granted", step)
    _activity(owner, plan, "step_started", step)
    tools = registry or build_automation_registry()
    try:
        result = tools.invoke(
            step["tool"],
            username=owner,
            arguments=step["arguments"],
            confirmed=True,
        )
        with _lock:
            step["status"] = "completed"
            step["result"] = _safe_preview(result)
            plan["current_step"] += 1
            plan["status"] = "cancelled" if plan.get("cancel_requested") else "ready"
            if plan["status"] == "cancelled":
                for pending_step in plan["steps"][plan["current_step"]:]:
                    if pending_step["status"] == "pending":
                        pending_step["status"] = "cancelled"
        _activity(owner, plan, "step_completed", step)
    except Exception as exc:
        with _lock:
            step["status"] = "failed"
            step["error"] = "Execution failed. Review the activity log."
            plan["status"] = "failed"
        _activity(owner, plan, "step_failed", step, type(exc).__name__)
        logger.warning("Approved automation step failed: %s", step["tool"], exc_info=True)
        return _snapshot(plan)
    if plan["status"] == "cancelled":
        _activity(owner, plan, "plan_cancelled")
        return _snapshot(plan)
    return advance_plan(plan["plan_id"], owner, registry=tools, now=current_time)


def cancel_plan(plan_id: str, username: str) -> dict[str, Any]:
    plan = _get_plan(plan_id, username)
    with _lock:
        if plan["status"] in {"completed", "cancelled", "failed", "expired"}:
            return _snapshot(plan)
        plan["approval_id"] = None
        plan["approval_expires_at"] = None
        if plan["status"] in {"running", "executing"}:
            # Do not claim that an already-started operation was undone. The
            # current step may finish, but the executor will not start another.
            plan["cancel_requested"] = True
            _activity(username, plan, "cancel_requested")
            return _snapshot(plan)
        plan["status"] = "cancelled"
        for step in plan["steps"][plan["current_step"]:]:
            if step["status"] in {"pending", "awaiting_approval"}:
                step["status"] = "cancelled"
    _activity(username, plan, "plan_cancelled")
    return _snapshot(plan)


def cancel_user_plans(username: str) -> int:
    """Invalidate outstanding approvals when a user logs out or deactivates AJARVIS."""
    owner = _valid_owner(username)
    with _lock:
        plan_ids = [
            plan["plan_id"] for plan in _plans.values()
            if plan["username"] == owner
            and plan["status"] not in {"completed", "cancelled", "failed", "expired"}
        ]
    cancelled = 0
    for plan_id in plan_ids:
        cancel_plan(plan_id, owner)
        cancelled += 1
    return cancelled
