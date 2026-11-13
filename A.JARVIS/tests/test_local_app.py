import os
from pathlib import Path
from datetime import datetime,timezone
import pytest
os.environ["SECRET_KEY"]="test-only-secret-key-for-automated-tests-123456"
import app as local_app


@pytest.fixture
def client():
    local_app.app.config.update(TESTING=True,SECRET_KEY=os.environ["SECRET_KEY"])
    with local_app.app.test_client() as test_client: yield test_client


def login(client,username="alice"):
    with client.session_transaction() as session:
        session["user"]=username
        session["login_time"]=datetime.now(timezone.utc).isoformat()
        session["csrf_token"]="test-csrf-token"


def test_local_command_requires_authentication(client):
    assert client.post("/command",json={"command":"what time is it?"}).status_code==401


@pytest.mark.parametrize("path",["/command","/voice_command"])
def test_typed_and_spoken_routes_share_backend_and_authoritative_state(client,monkeypatch,path):
    login(client); calls=[]
    monkeypatch.setattr(local_app,"process_command",lambda command,username:calls.append((command,username)) or "Command received.")
    monkeypatch.setattr(local_app,"is_user_active",lambda _username:True)
    response=client.post(path,json={"command":"open Chrome"},headers={"X-CSRF-Token":"test-csrf-token"})
    assert response.status_code==200
    assert response.get_json()=={"response":"Command received.","active":True,"intent":"command"}
    assert calls==[("open Chrome","alice")]


def test_local_command_rejects_invalid_payloads(client):
    login(client)
    headers={"X-CSRF-Token":"test-csrf-token"}
    assert client.post("/command",json=["open Chrome"],headers=headers).status_code==400
    assert client.post("/command",json={"command":" "},headers=headers).status_code==400
    assert client.post("/command",json={"command":"x"*2001},headers=headers).status_code==400


def test_face_access_grants_only_detected_user(client,monkeypatch):
    monkeypatch.setattr(local_app,"_ensure_face_cache_loaded",lambda:None)
    monkeypatch.setattr(local_app.camera,"get_detected_user",lambda:"alice")
    monkeypatch.setattr(local_app.camera,"is_camera_ready",lambda:True)
    reset=[]; monkeypatch.setattr(local_app.camera,"reset_detected_user",lambda:reset.append(True))
    response=client.get("/check_access")
    assert response.status_code==200 and response.get_json()["access"] is True
    assert response.get_json()["user"]=="alice" and reset==[True]


def test_authenticated_session_is_not_reassigned_by_background_face_match(client,monkeypatch):
    login(client,username="bob")
    monkeypatch.setattr(local_app.camera,"get_detected_user",lambda:"alice")
    reset=[]; monkeypatch.setattr(local_app.camera,"reset_detected_user",lambda:reset.append(True))
    response=client.get("/check_access")
    assert response.status_code==200
    assert response.get_json()=={"access":True,"user":"bob"}
    assert reset==[]


def test_face_authentication_fails_closed_if_cache_cannot_load(client,monkeypatch):
    monkeypatch.setattr(local_app,"_ensure_face_cache_loaded",lambda:(_ for _ in ()).throw(RuntimeError("database down")))
    response=client.get("/check_access")
    assert response.status_code==503 and response.get_json()["access"] is False


def test_system_stats_requires_auth_and_disables_cache(client,monkeypatch):
    monkeypatch.setattr(local_app,"get_stats",lambda:{"cpu":1.0})
    assert client.get("/system_stats").status_code==401
    login(client); response=client.get("/system_stats")
    assert response.status_code==200 and response.get_json()=={"cpu":1.0}
    assert response.headers["Cache-Control"]=="no-store"


def test_dashboard_uses_server_activation_state(client,monkeypatch):
    login(client); monkeypatch.setattr(local_app,"is_user_active",lambda _username:True)
    response=client.get("/dashboard")
    dashboard_js = Path(local_app.__file__).parent / "static" / "cloud-dashboard.js"
    source = dashboard_js.read_text(encoding="utf-8")
    assert response.status_code==200 and b'data-active="true"' in response.data
    assert 'document.body.dataset.active === "true"' in source


def test_command_route_rejects_missing_csrf_token(client,monkeypatch):
    login(client)
    monkeypatch.setattr(local_app,"process_command",lambda *_args:"must not execute")
    response=client.post("/command",json={"command":"what time is it?"})
    assert response.status_code==403


def test_memory_api_requires_authentication(client):
    assert client.get("/api/memories").status_code==401
    assert client.post("/api/memories",json={"key":"answer_style","value":"concise"}).status_code==401


def test_memory_api_lists_only_authenticated_users_memories(client,monkeypatch):
    login(client)
    calls=[]
    monkeypatch.setattr(local_app,"list_memories",lambda username:calls.append(username) or [{"key":"answer_style","value":"concise"}])
    response=client.get("/api/memories")
    assert response.status_code==200
    assert response.get_json()["memories"][0]["key"]=="answer_style"
    assert calls==["alice"]
    assert response.headers["Cache-Control"]=="no-store"


def test_memory_api_requires_csrf_before_save_or_delete(client,monkeypatch):
    login(client)
    monkeypatch.setattr(local_app,"save_memory",lambda *_args:pytest.fail("Save must be blocked without CSRF"))
    monkeypatch.setattr(local_app,"delete_memory",lambda *_args:pytest.fail("Delete must be blocked without CSRF"))
    assert client.post("/api/memories",json={"key":"answer_style","value":"concise"}).status_code==403
    assert client.delete("/api/memories/answer_style").status_code==403


def test_memory_api_saves_and_deletes_only_current_users_memory(client,monkeypatch):
    login(client)
    saves=[]; deletes=[]
    monkeypatch.setattr(local_app,"save_memory",lambda username,key,value:saves.append((username,key,value)) or {"key":key,"value":value})
    monkeypatch.setattr(local_app,"delete_memory",lambda username,key:deletes.append((username,key)) or True)
    headers={"X-CSRF-Token":"test-csrf-token"}
    saved=client.post("/api/memories",json={"key":"answer_style","value":"concise"},headers=headers)
    removed=client.delete("/api/memories/answer_style",headers=headers)
    assert saved.status_code==200 and saved.get_json()["memory"]["key"]=="answer_style"
    assert removed.status_code==200 and removed.get_json()["ok"] is True
    assert saves==[("alice","answer_style","concise")]
    assert deletes==[("alice","answer_style")]


def test_memory_api_validates_input_and_reports_missing_memory(client,monkeypatch):
    login(client)
    headers={"X-CSRF-Token":"test-csrf-token"}
    monkeypatch.setattr(local_app,"save_memory",lambda *_args:(_ for _ in ()).throw(ValueError("invalid memory")))
    monkeypatch.setattr(local_app,"delete_memory",lambda *_args:False)
    assert client.post("/api/memories",json={"key":"bad","value":"x"},headers=headers).status_code==400
    assert client.delete("/api/memories/no_such_memory",headers=headers).status_code==404


def test_dashboard_includes_csrf_token_for_api_calls(client,monkeypatch):
    login(client)
    monkeypatch.setattr(local_app,"is_user_active",lambda _username:False)
    response=client.get("/dashboard")
    assert response.status_code==200
    with client.session_transaction() as session:
        assert len(session["csrf_token"])>=32
    assert b'<meta name="csrf-token"' in response.data


def test_automation_plan_endpoint_requires_authentication_and_csrf(client,monkeypatch):
    assert client.post("/api/automation/plan",json={"task":"Check status"}).status_code==401
    login(client)
    monkeypatch.setattr(local_app,"is_user_active",lambda _username:True)
    monkeypatch.setattr(local_app,"generate_task_plan",lambda *_args:pytest.fail("Must reject without CSRF"))
    assert client.post("/api/automation/plan",json={"task":"Check status"}).status_code==403


def test_automation_plan_endpoint_requires_active_assistant(client,monkeypatch):
    login(client)
    monkeypatch.setattr(local_app,"is_user_active",lambda _username:False)
    response=client.post("/api/automation/plan",json={"task":"Check status"},headers={"X-CSRF-Token":"test-csrf-token"})
    assert response.status_code==409


def test_automation_plan_endpoint_validates_task_and_advances_plan(client,monkeypatch):
    login(client)
    monkeypatch.setattr(local_app,"is_user_active",lambda _username:True)
    calls=[]
    monkeypatch.setattr(local_app,"_get_genai_client",lambda:"fake-client")
    monkeypatch.setattr(local_app,"generate_task_plan",lambda client,task,username:calls.append((client,task,username)) or {"plan_id":"plan-1"})
    monkeypatch.setattr(local_app,"advance_plan",lambda plan_id,username:{"plan_id":plan_id,"status":"awaiting_approval","steps":[],"approval":{"approval_id":"a1"}})
    headers={"X-CSRF-Token":"test-csrf-token"}
    bad=client.post("/api/automation/plan",json={"task":" "},headers=headers)
    good=client.post("/api/automation/plan",json={"task":"Open a site"},headers=headers)
    assert bad.status_code==400
    assert good.status_code==201
    assert good.get_json()["plan"]["status"]=="awaiting_approval"
    assert calls==[("fake-client","Open a site","alice")]


def test_automation_approval_endpoint_is_csrf_and_owner_protected(client,monkeypatch):
    login(client)
    monkeypatch.setattr(local_app,"is_user_active",lambda _username:True)
    monkeypatch.setattr(local_app,"respond_to_approval",lambda approval_id,username,decision:{"status":decision,"approval_id":approval_id,"username":username})
    assert client.post("/api/automation/approval/a1",json={"decision":"approve"}).status_code==403
    response=client.post("/api/automation/approval/a1",json={"decision":"approve"},headers={"X-CSRF-Token":"test-csrf-token"})
    assert response.status_code==200
    assert response.get_json()["plan"]["username"]=="alice"


def test_automation_cancel_activity_endpoints_are_authenticated_and_scoped(client,monkeypatch):
    login(client)
    monkeypatch.setattr(local_app,"cancel_plan",lambda plan_id,username:{"plan_id":plan_id,"status":"cancelled","owner":username})
    monkeypatch.setattr(local_app,"list_recent_activity",lambda username,limit:{"rows":[],"owner":username})
    headers={"X-CSRF-Token":"test-csrf-token"}
    cancelled=client.post("/api/automation/plan/p1/cancel",json={},headers=headers)
    activity=client.get("/api/automation/activity")
    assert cancelled.status_code==200 and cancelled.get_json()["plan"]["owner"]=="alice"
    assert activity.status_code==200 and activity.get_json()["activity"]["owner"]=="alice"


def test_reminder_api_requires_authentication_and_csrf(client,monkeypatch):
    assert client.get("/api/reminders").status_code==401
    assert client.post("/api/reminders",json={"title":"Check","due_at":"2030-01-01T10:00:00Z"}).status_code==401
    login(client)
    monkeypatch.setattr(local_app,"create_reminder",lambda *_args:pytest.fail("CSRF must be checked first"))
    assert client.post("/api/reminders",json={"title":"Check","due_at":"2030-01-01T10:00:00Z"}).status_code==403


def test_reminder_api_creates_user_scoped_reminder(client,monkeypatch):
    login(client)
    calls=[]
    monkeypatch.setattr(local_app,"create_reminder",lambda username,title,due_at:calls.append((username,title,due_at)) or {"id":4,"title":title,"due_at":due_at,"status":"pending"})
    response=client.post(
        "/api/reminders",
        headers={"X-CSRF-Token":"test-csrf-token"},
        json={"title":"Review the checklist","due_at":"2030-01-01T10:00:00Z"},
    )
    assert response.status_code==201
    assert response.get_json()["reminder"]["id"]==4
    assert calls==[("alice","Review the checklist","2030-01-01T10:00:00Z")]


def test_reminder_status_route_requires_csrf_and_uses_session_username(client,monkeypatch):
    login(client)
    calls=[]
    monkeypatch.setattr(local_app,"update_reminder_status",lambda username,reminder_id,status:calls.append((username,reminder_id,status)) or True)
    assert client.post("/api/reminders/4/status",json={"status":"completed"}).status_code==403
    response=client.post("/api/reminders/4/status",headers={"X-CSRF-Token":"test-csrf-token"},json={"status":"completed"})
    assert response.status_code==200
    assert calls==[("alice",4,"completed")]


def test_notification_preferences_are_authenticated_csrf_protected_and_opt_in(client,monkeypatch):
    assert client.get("/api/notification-preferences").status_code==401
    login(client)
    monkeypatch.setattr(local_app,"set_notification_preferences",lambda *_args,**_kwargs:pytest.fail("CSRF must be checked first"))
    assert client.put("/api/notification-preferences",json={"reminders_enabled":True}).status_code==403


def test_notification_preferences_api_saves_explicit_opt_in(client,monkeypatch):
    login(client)
    calls=[]
    monkeypatch.setattr(
        local_app,"set_notification_preferences",
        lambda username,**kwargs:calls.append((username,kwargs)) or kwargs
    )
    response=client.put(
        "/api/notification-preferences",
        headers={"X-CSRF-Token":"test-csrf-token"},
        json={"reminders_enabled":True,"browser_notifications_enabled":False},
    )
    assert response.status_code==200
    assert calls==[("alice",{"reminders_enabled":True,"browser_notifications_enabled":False})]


def test_notifications_api_returns_user_owned_unread_and_due_items(client,monkeypatch):
    login(client)
    calls=[]
    monkeypatch.setattr(local_app,"get_notification_preferences",lambda username:{"reminders_enabled":True,"browser_notifications_enabled":False})
    monkeypatch.setattr(local_app,"collect_due_notifications",lambda username,limit:calls.append((username,limit)) or [{"id":5,"title":"AJARVIS reminder","body":"Review checklist"}])
    monkeypatch.setattr(local_app,"list_unread_notifications",lambda username,limit:[{"id":5,"title":"AJARVIS reminder","body":"Review checklist"}])
    response=client.get("/api/notifications")
    assert response.status_code==200
    assert response.get_json()["newly_due"][0]["id"]==5
    assert calls==[("alice",20)]


def test_notification_mark_read_route_is_csrf_protected_and_scoped(client,monkeypatch):
    login(client)
    calls=[]
    monkeypatch.setattr(local_app,"mark_notification_read",lambda username,notification_id:calls.append((username,notification_id)) or True)
    assert client.post("/api/notifications/5/read").status_code==403
    response=client.post("/api/notifications/5/read",headers={"X-CSRF-Token":"test-csrf-token"})
    assert response.status_code==200
    assert calls==[("alice",5)]


def test_workflow_history_api_requires_auth_and_scopes_results(client,monkeypatch):
    assert client.get("/api/automation/workflows").status_code==401
    login(client)
    calls=[]
    monkeypatch.setattr(local_app,"list_recent_workflows",lambda username,limit:calls.append((username,limit)) or [{"status":"interrupted"}])
    response=client.get("/api/automation/workflows")
    assert response.status_code==200
    assert response.get_json()["workflows"][0]["status"]=="interrupted"
    assert calls==[("alice",30)]


def test_personal_intelligence_focus_api_requires_authentication_and_scopes_user(client,monkeypatch):
    assert client.get("/api/personal-intelligence/focus").status_code == 401
    login(client)
    calls=[]
    monkeypatch.setattr(
        local_app, "build_personal_focus",
        lambda username: calls.append(username) or {"metrics": {"open_tasks": 2}},
    )
    response=client.get("/api/personal-intelligence/focus")
    assert response.status_code == 200
    assert response.get_json()["focus"]["metrics"]["open_tasks"] == 2
    assert calls == ["alice"]
    assert response.headers["Cache-Control"] == "no-store"


def test_project_creation_requires_csrf_and_uses_signed_in_owner(client,monkeypatch):
    assert client.post("/api/projects",json={"name":"AJARVIS"}).status_code == 401
    login(client)
    monkeypatch.setattr(local_app,"create_project",lambda *_args:pytest.fail("Must check CSRF before creation"))
    assert client.post("/api/projects",json={"name":"AJARVIS"}).status_code == 403


def test_project_and_task_creation_are_user_scoped_and_csrf_protected(client,monkeypatch):
    login(client)
    calls=[]
    monkeypatch.setattr(local_app,"create_project",lambda username,name,objective:calls.append(("project",username,name,objective)) or {"id":2,"name":name})
    monkeypatch.setattr(local_app,"create_task",lambda username,title,**kwargs:calls.append(("task",username,title,kwargs)) or {"id":8,"title":title})
    headers={"X-CSRF-Token":"test-csrf-token"}
    project=client.post("/api/projects",headers=headers,json={"name":"AJARVIS","objective":"Assistant roadmap"})
    task=client.post("/api/tasks",headers=headers,json={"title":"Run tests","project_id":2,"priority":"urgent"})
    assert project.status_code == 201 and task.status_code == 201
    assert calls[0] == ("project","alice","AJARVIS","Assistant roadmap")
    assert calls[1][1:3] == ("alice","Run tests")
    assert calls[1][3]["project_id"] == 2
    assert calls[1][3]["priority"] == "urgent"


def test_project_and_task_status_routes_require_csrf_and_scope_owner(client,monkeypatch):
    login(client)
    calls=[]
    monkeypatch.setattr(local_app,"update_project_status",lambda username,project_id,status:calls.append(("project",username,project_id,status)) or True)
    monkeypatch.setattr(local_app,"update_task_status",lambda username,task_id,status:calls.append(("task",username,task_id,status)) or True)
    assert client.post("/api/projects/2/status",json={"status":"paused"}).status_code == 403
    assert client.post("/api/tasks/8/status",json={"status":"completed"}).status_code == 403
    headers={"X-CSRF-Token":"test-csrf-token"}
    assert client.post("/api/projects/2/status",headers=headers,json={"status":"paused"}).status_code == 200
    assert client.post("/api/tasks/8/status",headers=headers,json={"status":"completed"}).status_code == 200
    assert calls == [("project","alice",2,"paused"),("task","alice",8,"completed")]

def test_dashboard_voice_capture_handles_only_new_final_results_and_preserves_wake_flow():
    dashboard = Path(local_app.__file__).parent / "static" / "cloud-dashboard.js"
    source = dashboard.read_text(encoding="utf-8")
    assert "result.isFinal" in source
    assert "resultIndex <= lastHandledResultIndex" in source
    assert "lastAcceptedTranscriptAt" in source
    assert "startsWithWakePhrase" in source
    assert "STATE 2 — GREETED" in source
    assert "processCommand(transcript)" in source


def test_dashboard_voice_capture_uses_one_guarded_start_and_recovery_timer():
    dashboard = Path(local_app.__file__).parent / "templates" / "dashboard.html"
    source = dashboard.read_text(encoding="utf-8")
    assert "function startRecognitionSafely()" in source
    assert "function scheduleRecognitionRestart(" in source
    assert "recognitionStartWatchdog" in source
    assert "recognitionActive" in source
    assert source.count("recognition.start()") == 1




def test_local_dashboard_microphone_visualizer_reuses_one_stream_and_cleans_up():
    from pathlib import Path

    dashboard = (Path(__file__).resolve().parents[1] / "static" / "cloud-dashboard.js").read_text(encoding="utf-8")
    assert "let microphoneStream = null;" in dashboard
    assert "let audioStartPromise = null;" in dashboard
    assert "if (audioContext && audioContext.state !== \"closed\")" in dashboard
    assert "if (audioStartPromise) return audioStartPromise;" in dashboard
    assert "window.addEventListener(\"pagehide\", stopMicReactiveSystem)" in dashboard
    assert "microphoneStream.getTracks().forEach((track) => track.stop())" in dashboard
    assert "window.cancelAnimationFrame(audioFrameId)" in dashboard
    assert "if (!shouldListen || recognitionBlocked) stopMicReactiveSystem();" in dashboard



def test_logout_rejects_cross_site_get_and_requires_csrf_post(client,monkeypatch):
    login(client)
    monkeypatch.setattr(local_app,"cancel_user_plans",lambda _username:None)

    get_response=client.get("/logout")
    assert get_response.status_code==405
    with client.session_transaction() as session:
        assert session.get("user")=="alice"

    denied=client.post("/logout")
    assert denied.status_code==403
    with client.session_transaction() as session:
        assert session.get("user")=="alice"

    allowed=client.post("/logout",headers={"X-CSRF-Token":"test-csrf-token"})
    assert allowed.status_code==302
    with client.session_transaction() as session:
        assert "user" not in session



def test_desktop_audio_capture_error_pauses_auto_restart_and_keeps_manual_retry():
    dashboard = (Path(__file__).resolve().parents[1] / "templates" / "dashboard.html").read_text(encoding="utf-8")
    audio_error = dashboard.split('} else if (errorCode === "audio-capture") {', 1)[1].split('} else if (errorCode === "language-not-supported") {', 1)[0]
    assert 'recognitionBlocked = true;' in audio_error
    assert 'shouldListen = false;' in audio_error
    assert 'TAP THE CORE TO RETRY' in audio_error
    assert 'scheduleRecognitionRestart(450);' in dashboard
    retry_handler = dashboard.split("document.getElementById('ai-core').addEventListener('click', () => {", 1)[1].split("});", 1)[0]
    assert "shouldListen = true;" in retry_handler
    assert "recognitionBlocked = false;" in retry_handler
    assert "startRecognitionSafely();" in retry_handler



def test_untrusted_host_is_rejected_before_route_runs(client, monkeypatch):
    monkeypatch.setattr(local_app.camera, "get_latest_frame", lambda: pytest.fail("Host check must run first"))
    response = client.post("/register", base_url="http://evil.example", json={"username": "attacker"})
    assert response.status_code == 421


def test_first_local_registration_requires_csrf_and_is_allowed_when_no_users(client, monkeypatch):
    monkeypatch.setattr(local_app, "_registration_is_allowed", lambda: (True, None))
    monkeypatch.setattr(local_app.camera, "resume_recognition", lambda: None)
    denied = client.post("/register", json={"username": "alice"})
    assert denied.status_code == 403
    with client.session_transaction() as state:
        state["csrf_token"] = "x" * 40
    monkeypatch.setattr(local_app.camera, "get_latest_frame", lambda: None)
    allowed = client.post("/register", headers={"X-CSRF-Token": "x" * 40}, json={"username": "alice"})
    assert allowed.status_code == 400
    assert "Camera not ready" in allowed.get_json()["message"]


def test_local_registration_is_closed_after_first_account(client, monkeypatch):
    monkeypatch.setattr(local_app.camera, "resume_recognition", lambda: None)
    monkeypatch.setattr(local_app, "_registration_is_allowed", lambda: (False, (local_app.jsonify({"status":"error"}), 403)))
    with client.session_transaction() as state:
        state["csrf_token"] = "x" * 40
    response = client.post("/register", headers={"X-CSRF-Token": "x" * 40}, json={"username": "bob"})
    assert response.status_code == 403



def test_registration_page_is_closed_after_first_user(client, monkeypatch):
    monkeypatch.setattr(local_app, "_registration_is_allowed", lambda: (False, (local_app.jsonify({"error": "closed"}), 403)))
    response = client.get("/register")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_video_feed_is_not_available_after_first_user_until_authenticated(client, monkeypatch):
    monkeypatch.setattr(local_app, "_registration_is_allowed", lambda: (False, (local_app.jsonify({"error": "closed"}), 403)))
    monkeypatch.setattr(local_app, "generate_frames", lambda: pytest.fail("Camera feed must not start"))
    response = client.get("/video_feed")
    assert response.status_code == 403


def test_dashboard_sends_csp_and_security_headers(client, monkeypatch):
    login(client)
    monkeypatch.setattr(local_app.camera, "pause_recognition", lambda: None)
    monkeypatch.setattr(local_app, "is_user_active", lambda _username: True)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"



def test_login_page_can_request_same_origin_camera_preview_but_cross_site_cannot(client, monkeypatch):
    monkeypatch.setattr(local_app, "_registration_is_allowed", lambda: (False, (local_app.jsonify({"error":"closed"}), 403)))
    monkeypatch.setattr(local_app, "generate_frames", lambda: iter([b"frame"]))
    denied = client.get("/video_feed", headers={"Sec-Fetch-Site": "cross-site"})
    assert denied.status_code == 403
    allowed = client.get("/video_feed", headers={"Sec-Fetch-Site": "same-origin"})
    assert allowed.status_code == 200
    assert allowed.headers["Cache-Control"] == "no-store"



def test_reminder_and_notification_database_outages_return_503(client, monkeypatch):
    from intelligence.reminders import ReminderUnavailable

    login(client)
    monkeypatch.setattr(
        local_app,
        "list_reminders",
        lambda _username: (_ for _ in ()).throw(ReminderUnavailable("Reminders are temporarily unavailable.")),
    )
    response = client.get("/api/reminders")
    assert response.status_code == 503
    assert "temporarily unavailable" in response.get_json()["error"]

    monkeypatch.setattr(
        local_app,
        "mark_notification_read",
        lambda *_args: (_ for _ in ()).throw(ReminderUnavailable("Notification updates are temporarily unavailable.")),
    )
    response = client.post(
        "/api/notifications/7/read",
        headers={"X-CSRF-Token": "test-csrf-token"},
    )
    assert response.status_code == 503


def test_missing_notification_is_404_not_a_database_error(client, monkeypatch):
    login(client)
    monkeypatch.setattr(local_app, "mark_notification_read", lambda *_args: False)
    response = client.post(
        "/api/notifications/999/read",
        headers={"X-CSRF-Token": "test-csrf-token"},
    )
    assert response.status_code == 404
