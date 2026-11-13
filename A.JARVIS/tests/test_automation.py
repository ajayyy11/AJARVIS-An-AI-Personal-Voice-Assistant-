import pytest

from intelligence import automation
from intelligence.tool_registry import ToolRegistry


@pytest.fixture(autouse=True)
def clear_pending_plans(monkeypatch):
    monkeypatch.setattr(automation, "_activity", lambda *_args, **_kwargs: None)
    with automation._lock:
        automation._plans.clear()
    yield
    with automation._lock:
        automation._plans.clear()


def registry_with_read_and_write_tools(events):
    registry=ToolRegistry()
    registry.register(
        "read_status","Read a test status.",
        lambda *,username: events.append(("read",username)) or {"status":"healthy"},
    )
    registry.register(
        "set_setting","Change a test setting.",
        lambda *,username,value: events.append(("write",username,value)) or {"changed":value},
        risk_level="reversible",
        requires_confirmation=True,
        parameters={
            "type":"object",
            "properties":{"value":{"type":"string","minLength":1,"maxLength":20}},
            "required":["value"],
            "additionalProperties":False,
        },
    )
    return registry


def step(tool,arguments=None):
    return {"tool":tool,"arguments":arguments or {},"summary":"Test "+tool,"reason":"Test plan step."}


def test_read_only_steps_run_automatically_and_changing_step_pauses_for_approval(monkeypatch):
    events=[]
    registry=registry_with_read_and_write_tools(events)
    created=automation.create_plan(
        "alice","Read and update a setting.",
        [step("read_status"),step("set_setting",{"value":"on"})],
        registry=registry,
    )
    state=automation.advance_plan(created["plan_id"],"alice",registry=registry)
    assert events==[("read","alice")]
    assert state["status"]=="awaiting_approval"
    assert state["steps"][0]["status"]=="completed"
    assert state["steps"][1]["status"]=="awaiting_approval"
    assert state["approval"]["approval_id"]


def test_approval_executes_exact_pending_step_once_and_completes_plan():
    events=[]
    registry=registry_with_read_and_write_tools(events)
    created=automation.create_plan("alice","Update one setting.",[step("set_setting",{"value":"on"})],registry=registry)
    waiting=automation.advance_plan(created["plan_id"],"alice",registry=registry)
    approval=waiting["approval"]["approval_id"]
    done=automation.respond_to_approval(approval,"alice","approve",registry=registry)
    assert events==[("write","alice","on")]
    assert done["status"]=="completed"
    assert done["steps"][0]["status"]=="completed"
    with pytest.raises(automation.AutomationError,match="not found|already used"):
        automation.respond_to_approval(approval,"alice","approve",registry=registry)
    assert events==[("write","alice","on")]


def test_approval_token_cannot_be_used_by_another_user():
    events=[]
    registry=registry_with_read_and_write_tools(events)
    created=automation.create_plan("alice","Update setting.",[step("set_setting",{"value":"on"})],registry=registry)
    waiting=automation.advance_plan(created["plan_id"],"alice",registry=registry)
    with pytest.raises(automation.AutomationError,match="not found"):
        automation.respond_to_approval(waiting["approval"]["approval_id"],"bob","approve",registry=registry)
    assert events==[]


def test_rejecting_approval_stops_remaining_steps():
    events=[]
    registry=registry_with_read_and_write_tools(events)
    created=automation.create_plan(
        "alice","Update and read.",
        [step("set_setting",{"value":"on"}),step("read_status")],
        registry=registry,
    )
    waiting=automation.advance_plan(created["plan_id"],"alice",registry=registry)
    rejected=automation.respond_to_approval(waiting["approval"]["approval_id"],"alice","reject",registry=registry)
    assert rejected["status"]=="cancelled"
    assert rejected["steps"][0]["status"]=="rejected"
    assert events==[]


def test_approval_expires_and_cannot_execute_after_expiry():
    events=[]
    registry=registry_with_read_and_write_tools(events)
    created=automation.create_plan("alice","Update.",[step("set_setting",{"value":"on"})],registry=registry,now=100)
    waiting=automation.advance_plan(created["plan_id"],"alice",registry=registry,now=100)
    with pytest.raises(automation.AutomationError,match="expired"):
        automation.respond_to_approval(waiting["approval"]["approval_id"],"alice","approve",registry=registry,now=161)
    assert events==[]


def test_plan_is_user_scoped_and_cancelled_on_logout():
    events=[]
    registry=registry_with_read_and_write_tools(events)
    created=automation.create_plan("alice","Update.",[step("set_setting",{"value":"on"})],registry=registry)
    waiting=automation.advance_plan(created["plan_id"],"alice",registry=registry)
    with pytest.raises(automation.AutomationError,match="not found"):
        automation.cancel_plan(created["plan_id"],"bob")
    assert automation.cancel_user_plans("alice")==1
    cancelled=automation.cancel_plan(created["plan_id"],"alice")
    assert cancelled["status"]=="cancelled"
    with pytest.raises(automation.AutomationError):
        automation.respond_to_approval(waiting["approval"]["approval_id"],"alice","approve",registry=registry)


def test_invalid_plans_cannot_call_unknown_tools_or_unregistered_arguments():
    events=[]
    registry=registry_with_read_and_write_tools(events)
    with pytest.raises(automation.AutomationError,match="unavailable tool"):
        automation.create_plan("alice","Bad plan.",[step("run_shell",{"command":"calc"})],registry=registry)
    with pytest.raises(automation.AutomationError,match="invalid arguments"):
        automation.create_plan("alice","Bad plan.",[step("set_setting",{"value":3})],registry=registry)
    with pytest.raises(automation.AutomationError,match="unsupported fields"):
        automation.create_plan("alice","Bad plan.",[{"tool":"read_status","arguments":{},"shell":"calc"}],registry=registry)
    with pytest.raises(automation.AutomationError,match="between 1 and"):
        automation.create_plan("alice","Too many.",[step("read_status")]*6,registry=registry)
    assert events==[]


def test_url_tool_rejects_non_https_and_private_destinations():
    for url in ("http://example.com","https://localhost/admin","https://127.0.0.1/","https://user:pass@example.com"):
        with pytest.raises(Exception):
            automation._validate_website_url(url)


def test_url_tool_accepts_public_https_destinations(monkeypatch):
    monkeypatch.setattr(
        automation.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("93.184.216.34", 443)),
        ],
    )
    assert automation._validate_website_url("https://example.com/path")=="https://example.com/path"


def test_url_tool_rejects_dns_answers_containing_private_addresses(monkeypatch):
    monkeypatch.setattr(
        automation.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("93.184.216.34", 443)),
            (2, 1, 6, "", ("10.0.0.8", 443)),
        ],
    )
    with pytest.raises(automation.ToolArgumentError, match="Private or local"):
        automation._validate_website_url("https://attacker-controlled.example")


def test_url_tool_fails_closed_when_dns_resolution_fails(monkeypatch):
    def fail_dns(*_args, **_kwargs):
        raise OSError("DNS unavailable")

    monkeypatch.setattr(automation.socket, "getaddrinfo", fail_dns)
    with pytest.raises(automation.ToolArgumentError, match="could not be safely resolved"):
        automation._validate_website_url("https://unresolvable.example")


def test_screenshot_writes_unique_file_in_user_pictures(monkeypatch, tmp_path):
    from pathlib import Path
    import sys
    import types

    saved = []

    def write_png(file_object, format=None):
        assert hasattr(file_object, "write")
        saved.append(format)
        file_object.write(b"PNG-test-data")

    fake_image = types.SimpleNamespace(save=write_png)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setitem(sys.modules, "pyautogui", types.SimpleNamespace(screenshot=lambda: fake_image))

    first = automation._capture_screenshot(username="alice")
    second = automation._capture_screenshot(username="alice")

    assert first["saved_to"] != second["saved_to"]
    assert Path(first["saved_to"]).parent == tmp_path / "Pictures" / "AJARVIS" / "Screenshots"
    assert Path(first["saved_to"]).read_bytes() == b"PNG-test-data"
    assert Path(second["saved_to"]).read_bytes() == b"PNG-test-data"
    assert saved == ["PNG", "PNG"]


def test_action_registry_marks_mutating_tools_as_confirmation_required():
    registry=automation.build_automation_registry()
    actions={item["name"]:item for item in registry.list_tools()}
    assert actions["open_website"]["requires_confirmation"] is False
    assert actions["open_website"]["risk_level"]=="reversible"
    assert actions["read_user_memories"]["risk_level"]=="read_only"
    if automation.os.name == "nt":
        assert actions["launch_application"]["requires_confirmation"] is False
        assert actions["lock_workstation"]["requires_confirmation"] is True
        assert actions["lock_workstation"]["risk_level"]=="destructive"
    else:
        assert "launch_application" not in actions
        assert "lock_workstation" not in actions


def test_execution_failure_stops_plan_and_does_not_run_later_steps():
    events=[]
    registry=ToolRegistry()
    registry.register("fail_step","Fail.",lambda **_:(_ for _ in ()).throw(RuntimeError("failure")))
    registry.register("later_step","Later.",lambda **_:events.append("later"))
    created=automation.create_plan("alice","Run steps.",[step("fail_step"),step("later_step")],registry=registry)
    state=automation.advance_plan(created["plan_id"],"alice",registry=registry)
    assert state["status"]=="failed"
    assert state["steps"][0]["status"]=="failed"
    assert events==[]


def test_cancellation_during_read_only_step_prevents_later_actions():
    import threading

    entered=threading.Event()
    release=threading.Event()
    events=[]
    registry=ToolRegistry()
    def read_slow(*,username):
        entered.set()
        assert release.wait(2)
        return {"ready":True}
    registry.register("read_slow","Wait for a test signal.",read_slow)
    registry.register(
        "set_setting","Change setting.",lambda *,username,value:events.append(value),
        risk_level="reversible",requires_confirmation=True,
        parameters={
            "type":"object",
            "properties":{"value":{"type":"string","minLength":1}},
            "required":["value"],"additionalProperties":False,
        },
    )
    created=automation.create_plan(
        "alice","Read then change.",
        [step("read_slow"),step("set_setting",{"value":"on"})],
        registry=registry,
    )
    result={}
    worker=threading.Thread(target=lambda:result.update(
        automation.advance_plan(created["plan_id"],"alice",registry=registry)
    ))
    worker.start()
    assert entered.wait(2)
    cancelling=automation.cancel_plan(created["plan_id"],"alice")
    assert cancelling["cancel_requested"] is True
    release.set()
    worker.join(2)
    assert not worker.is_alive()
    assert result["status"]=="cancelled"
    assert result["steps"][0]["status"]=="completed"
    assert result["steps"][1]["status"]=="cancelled"
    assert events==[]


def test_plan_expiring_during_slow_read_only_work_does_not_start_next_step(monkeypatch):
    events=[]
    registry=ToolRegistry()
    registry.register(
        "read_slow","Read status.",
        lambda *,username: events.append("read") or {"status":"ok"},
    )
    registry.register(
        "set_setting","Change a setting.",
        lambda *,username,value: events.append("write"),
        risk_level="reversible",
        requires_confirmation=True,
        parameters={
            "type":"object",
            "properties":{"value":{"type":"string","minLength":1}},
            "required":["value"],
            "additionalProperties":False,
        },
    )
    created=automation.create_plan(
        "alice","Read then write.",
        [step("read_slow"),step("set_setting",{"value":"on"})],
        registry=registry,
        now=100,
    )
    clock=iter([101.0,102.0,401.0])
    monkeypatch.setattr(automation.time,"monotonic",lambda:next(clock))
    expired=automation.advance_plan(created["plan_id"],"alice",registry=registry)
    assert expired["status"]=="expired"
    assert expired["steps"][0]["status"]=="completed"
    assert expired["steps"][1]["status"]=="expired"
    assert expired["approval"] is None
    assert events==["read"]



@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1.nip.io",
        "https://10.0.0.1.sslip.io",
        "https://127.0.0.1.localtest.me",
        "https://printer.local",
        "https://192.168.1.2",
    ],
)
def test_url_tool_rejects_wildcard_dns_and_local_destinations(url):
    with pytest.raises(automation.ToolArgumentError):
        automation._validate_website_url(url)


def test_plan_registry_is_bounded_and_prunes_old_terminal_plans(monkeypatch):
    with automation._lock:
        for index in range(automation.MAX_STORED_PLANS):
            automation._plans[str(index)] = {
                "plan_id": str(index),
                "username": "alice",
                "status": "completed",
                "created_at": 0,
                "expires_at": 0,
                "approval_id": None,
                "approval_expires_at": None,
                "current_step": 0,
                "steps": [],
            }
    events=[]
    registry=registry_with_read_and_write_tools(events)
    created=automation.create_plan("alice","New bounded plan.",[step("read_status")],registry=registry,now=10)
    with automation._lock:
        assert len(automation._plans) <= automation.MAX_STORED_PLANS
        assert created["plan_id"] in automation._plans
