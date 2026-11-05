from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cloud_dashboard_has_simple_feature_navigation_and_status_panel():
    html = (ROOT / "templates" / "cloud_dashboard.html").read_text(encoding="utf-8")
    for marker in (
        'class="sidebar"',
        'id="newChatButton"',
        "url_for('history_page')",
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


def test_interface_script_uses_safe_text_rendering_and_route_navigation():
    script = (ROOT / "static" / "interface.js").read_text(encoding="utf-8")
    assert "message.textContent" in script
    assert 'aria-expanded' in script
    assert 'fetch("/api/history"' not in script


def test_chat_history_is_loaded_by_its_own_feature_page():
    script = (ROOT / "static" / "cloud.js").read_text(encoding="utf-8")
    assert 'if (body.dataset.page !== "history") return;' in script
    assert 'const list = $("historyList")' in script
    assert 'const result = await api("/api/history")' in script


def test_new_chat_uses_server_provided_conversation_boundary():
    html = (ROOT / "templates" / "cloud_dashboard.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "cloud.js").read_text(encoding="utf-8")
    assert 'data-context-after-id="{{ context_after_id }}"' in html
    assert "body.dataset.contextAfterId" in script
    assert "payload.context_after_id = contextAfterId" in script


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



def test_cloud_dashboard_has_a_fresh_context_boundary_and_does_not_autoload_saved_history():
    html = (ROOT / "templates" / "cloud_dashboard.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "cloud.js").read_text(encoding="utf-8")
    assert 'data-context-after-id="{{ context_after_id }}"' in html
    assert 'id="historyList"' in html
    assert not any(line.strip() == "refreshHistory().catch(() => {});" for line in script.splitlines())
    assert 'if (activePage === "history") refreshHistory()' in script
    assert 'if (activePage === "tasks") loadTasks()' in script
    assert 'if (activePage === "notes") loadNotes()' in script


def test_each_feature_has_a_dedicated_route_and_active_navigation_link():
    html = (ROOT / "templates" / "cloud_dashboard.html").read_text(encoding="utf-8")
    for route in (
        "dashboard", "history_page", "tasks_page", "notes_page",
        "memory_page", "activity_page", "visual_page", "documents_page",
        "account_page", "settings_page",
    ):
        assert "url_for('" + route + "')" in html
    assert 'data-page="{{ active_page }}"' in html


def test_separate_feature_pages_hide_non_active_panels_and_animate_login_aurora():
    style = (ROOT / "static" / "cloud.css").read_text(encoding="utf-8")
    for page, panel in (
        ("dashboard", "assistant-panel"), ("history", "history-panel"),
        ("tasks", "tasks-panel"), ("notes", "notes-panel"),
        ("memory", "preferences-panel"), ("activity", "activity-panel"),
        ("visual", "visual-panel"), ("documents", "documents-panel"),
        ("settings", "settings-panel"), ("account", "account-panel"),
    ):
        assert f'body[data-page="{page}"]' in style
        assert panel in style
    assert "auroraWaveDrift" in style
    assert "prefers-reduced-motion" in style
