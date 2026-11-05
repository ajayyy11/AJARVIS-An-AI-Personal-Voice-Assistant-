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



def test_dashboard_uses_left_feature_navigation_without_duplicate_topbar_brand():
    html = (ROOT / "templates" / "cloud_dashboard.html").read_text(encoding="utf-8")
    assert 'id="mobileNavToggle"' in html
    assert 'id="workspaceSidebar"' in html
    assert 'id="sidebarBackdrop"' in html
    topbar = html.split('<header class="topbar">', 1)[1].split("</header>", 1)[0]
    assert 'class="brand"' not in topbar
    assert 'AJARVIS · PERSONAL AI ASSISTANT' in html


def test_login_uses_product_name_without_generic_access_or_welcome_copy():
    html = (ROOT / "templates" / "cloud_auth.html").read_text(encoding="utf-8")
    assert 'class="auth-product-title">AJARVIS</h1>' in html
    assert "SECURE CLOUD ACCESS" not in html
    assert "Welcome back" not in html
    assert 'class="brand-large"' not in html


def test_mobile_sidebar_has_drawer_and_backdrop_controls():
    script = (ROOT / "static" / "interface.js").read_text(encoding="utf-8")
    style = (ROOT / "static" / "cloud.css").read_text(encoding="utf-8")
    assert 'setSidebarOpen(sidebarToggle.getAttribute("aria-expanded") !== "true")' in script
    assert 'sidebarBackdrop.addEventListener("click"' in script
    assert ".sidebar.is-open" in style
    assert ".sidebar-backdrop:not([hidden])" in style
    assert "@media (max-width: 760px)" in style
