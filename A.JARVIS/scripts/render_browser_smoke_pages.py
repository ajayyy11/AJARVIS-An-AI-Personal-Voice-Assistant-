"""Render authenticated AJARVIS pages for the jsdom browser smoke suite."""
from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("SECRET_KEY", "ci-only-browser-smoke-secret-key-0123456789")
APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import cloud_app  # noqa: E402

cloud_app.ensure_cloud_schema = lambda: None
cloud_app.get_latest_id = lambda username: 42
cloud_app.app.config.update(
    TESTING=True,
    SECRET_KEY="ci-only-browser-smoke-secret-key-0123456789",
)

ROUTES = {
    "dashboard": "/dashboard",
    "history": "/history",
    "tasks": "/tasks",
    "notes": "/notes",
    "memory": "/memory",
    "activity": "/activity",
    "visual": "/visual",
    "documents": "/documents",
    "account": "/account",
    "settings": "/settings",
}


def main() -> None:
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    with cloud_app.app.test_client() as client:
        with client.session_transaction() as session:
            from datetime import datetime, timezone
            session["user"] = "qa_user"
            session["login_time"] = datetime.now(timezone.utc).isoformat()
            session["csrf_token"] = "qa-csrf-token"
        for page, route in ROUTES.items():
            response = client.get(route)
            if response.status_code != 200:
                raise SystemExit(f"{route} returned HTTP {response.status_code}")
            html = response.get_data(as_text=True)
            marker = f'data-page="{page}"'
            if marker not in html:
                raise SystemExit(f"{route} is missing {marker}")
            (output / f"{page}.html").write_text(html, encoding="utf-8")
    # Authentication pages must be rendered without the authenticated workspace session.
    with cloud_app.app.test_client() as auth_client:
        for page in ("login", "register"):
            response = auth_client.get("/" + page)
            if response.status_code != 200:
                raise SystemExit(f"/{page} returned HTTP {response.status_code}")
            (output / f"{page}.html").write_text(response.get_data(as_text=True), encoding="utf-8")


if __name__ == "__main__":
    main()
