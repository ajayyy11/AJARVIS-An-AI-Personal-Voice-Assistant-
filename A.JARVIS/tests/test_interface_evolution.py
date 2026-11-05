from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cloud_dashboard_has_simple_feature_navigation_and_status_panel():
    html = (ROOT / "templates" / "cloud_dashboard.html").read_text(encoding="utf-8")
    for marker in (
        'class="sidebar"',
        'id="newChatButton"',
        'id="chatHistoryButton"',
        'id="systemStatusButton"',
        'id="systemStatusPanel"',
        'id="commandConsole"',
        'id="tasksPanel"',
        'id="notesPanel"',
        'href="#preferencesPanel"',
        'href="#activityPanel"',
        'id="visualPanel"',
        'id="documentsPanel"',
        'id="voiceSettings"',
        'id="accountPanel"',
        'class="hologram-stage"',
        "filename='interface.js'",
    ):
        assert marker in html, f"Missing interface element: {marker}"


def test_cloud_auth_keeps_login_and_registration_flow():
    html = (ROOT / "templates" / "cloud_auth.html").read_text(encoding="utf-8")
    assert 'id="authForm"' in html
    assert 'id="username"' in html
    assert 'id="password"' in html
    assert 'url_for(\'register_page\')' in html
    assert 'url_for(\'login_page\')' in html


def test_interface_script_uses_safe_history_text_rendering():
    script = (ROOT / "static" / "interface.js").read_text(encoding="utf-8")
    assert 'fetch("/api/history"' in script
    assert "message.textContent" in script
    assert 'aria-expanded' in script


def test_new_chat_establishes_and_persists_a_conversation_boundary():
    script = (ROOT / "static" / "interface.js").read_text(encoding="utf-8")
    assert 'result.latest_id' in script
    assert 'ajarvis.cloud.context_after_id:' in script
    assert 'body.dataset.contextAfterId' in script


def test_cloud_chat_sends_and_restores_conversation_boundary():
    script = (ROOT / "static" / "cloud.js").read_text(encoding="utf-8")
    assert 'payload.context_after_id = contextAfterId' in script
    assert 'historyEndpoint()' in script
    assert '"/api/history?after_id="' in script
