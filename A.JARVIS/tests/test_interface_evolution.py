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
        'id="visualPanel"',
        'id="documentsPanel"',
        'id="voiceSettings"',
        'id="accountPanel"',
        'class="hologram-stage"',
        'static/interface.js',
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
