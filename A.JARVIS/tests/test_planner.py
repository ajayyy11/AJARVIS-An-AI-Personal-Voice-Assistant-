import json
from types import SimpleNamespace
import pytest

from intelligence import planner
from intelligence.automation import build_automation_registry
from intelligence.planner import PlannerError


class FakeConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeTypes:
    GenerateContentConfig=FakeConfig


class FakeClient:
    def __init__(self, text):
        self.text=text
        self.calls=[]
    class Models:
        def __init__(self, owner): self.owner=owner
        def generate_content(self, **kwargs):
            self.owner.calls.append(kwargs)
            return SimpleNamespace(text=self.owner.text)
    @property
    def models(self): return self.Models(self)


@pytest.fixture(autouse=True)
def clear_plans():
    with planner.create_plan.__globals__["_plans_lock"] if "_plans_lock" in planner.create_plan.__globals__ else __import__("contextlib").nullcontext():
        pass
    from intelligence import automation
    with automation._lock:
        automation._plans.clear()
    yield
    with automation._lock:
        automation._plans.clear()


def test_planner_builds_validated_plan_from_json_and_does_not_enable_model_tool_calls():
    client=FakeClient(json.dumps({
        "goal":"Check system status.",
        "steps":[{"tool":"get_system_status","arguments":{},"summary":"Read host status","reason":"Report the current device state."}],
    }))
    result=planner.generate_task_plan(client,"Check my system status.","alice",types_module=FakeTypes)
    assert result["goal"]=="Check system status."
    assert result["status"]=="ready"
    assert result["steps"][0]["tool"]=="get_system_status"
    assert client.calls[0]["config"].response_mime_type=="application/json"
    assert client.calls[0]["config"].temperature==0.1


@pytest.mark.parametrize("text",["","not json","[]",'{"goal":"x","steps":[{"tool":"run_shell","arguments":{"command":"calc"},"summary":"run","reason":"bad"}]}'])
def test_planner_rejects_empty_malformed_or_unapproved_plan(text):
    with pytest.raises(PlannerError):
        planner.generate_task_plan(FakeClient(text),"Do something","alice",types_module=FakeTypes)


def test_planner_rejects_unbounded_or_invalid_requests():
    with pytest.raises(PlannerError,match="1000"):
        planner.generate_task_plan(FakeClient("{}"),"x"*1001,"alice",types_module=FakeTypes)
    with pytest.raises(PlannerError,match="No safe executable"):
        planner.generate_task_plan(FakeClient('{"goal":"x","steps":[]}'),"Do unsupported work","alice",types_module=FakeTypes)


def test_planner_limits_steps_and_rejects_unregistered_arguments():
    payload={"goal":"Too many","steps":[
        {"tool":"get_system_status","arguments":{},"summary":"Read status","reason":"Need a reading."}
        for _ in range(6)
    ]}
    with pytest.raises(PlannerError,match="between 1 and"):
        planner.generate_task_plan(FakeClient(json.dumps(payload)),"Check status six times","alice",types_module=FakeTypes)
    bad={"goal":"Use unlisted argument","steps":[
        {"tool":"get_system_status","arguments":{"shell":"calc"},"summary":"Read status","reason":"Invalid arguments."}
    ]}
    with pytest.raises(PlannerError,match="invalid arguments"):
        planner.generate_task_plan(FakeClient(json.dumps(bad)),"Check status","alice",types_module=FakeTypes)


def test_planner_prompt_contains_tool_allowlist_and_marks_request_untrusted():
    client=FakeClient('{"goal":"Status","steps":[{"tool":"get_system_status","arguments":{},"summary":"Read status","reason":"A status check."}]}')
    planner.generate_task_plan(client,"Check status","alice",types_module=FakeTypes)
    prompt=client.calls[0]["contents"]
    assert "open_website" in prompt
    assert "USER TASK (untrusted)" in prompt
    assert "shell commands" in prompt
