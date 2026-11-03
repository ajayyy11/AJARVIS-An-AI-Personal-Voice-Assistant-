import os
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


def test_local_command_requires_authentication(client):
    assert client.post("/command",json={"command":"what time is it?"}).status_code==401


@pytest.mark.parametrize("path",["/command","/voice_command"])
def test_typed_and_spoken_routes_share_backend_and_authoritative_state(client,monkeypatch,path):
    login(client); calls=[]
    monkeypatch.setattr(local_app,"process_command",lambda command,username:calls.append((command,username)) or "Command received.")
    monkeypatch.setattr(local_app,"is_user_active",lambda _username:True)
    response=client.post(path,json={"command":"open Chrome"})
    assert response.status_code==200
    assert response.get_json()=={"response":"Command received.","active":True,"intent":"command"}
    assert calls==[("open Chrome","alice")]


def test_local_command_rejects_invalid_payloads(client):
    login(client)
    assert client.post("/command",json=["open Chrome"]).status_code==400
    assert client.post("/command",json={"command":" "}).status_code==400
    assert client.post("/command",json={"command":"x"*2001}).status_code==400


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
    assert response.status_code==200 and b"const initialActive = true" in response.data
