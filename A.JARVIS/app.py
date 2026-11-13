from flask import Flask, render_template, Response, redirect, url_for, jsonify, request, session
import hmac
import ipaddress
from functools import wraps
from urllib.parse import urlsplit
import secrets
import threading
from config import Config
from security.camera import generate_frames
from security.session_manager import is_authenticated, revoke_access, grant_access
from security.face_auth import load_known_faces
from intelligence.command_router import process_command, _get_genai_client
from intelligence.automation import (
    AutomationError,
    advance_plan,
    cancel_plan,
    cancel_user_plans,
    respond_to_approval,
)
from intelligence.planner import PlannerError, generate_task_plan
from intelligence.activity_log import (
    list_recent_activity,
    list_recent_workflows,
    recover_interrupted_workflows,
)
from intelligence.personal_intelligence import (
    PersonalIntelligenceError,
    build_personal_focus,
    create_project,
    list_projects,
    update_project_status,
    create_task,
    list_tasks,
    update_task_status,
)
from intelligence.reminders import (
    ReminderError,
    ReminderUnavailable,
    create_reminder,
    list_reminders,
    set_notification_preferences,
    get_notification_preferences,
    collect_due_notifications,
    list_unread_notifications,
    mark_notification_read,
    update_reminder_status,
)
from intelligence.context import classify_intent
from intelligence.user_state import is_user_active
from intelligence.user_memory import list_memories, save_memory, delete_memory
from intelligence.memory import get_all_recent
from system.stats import get_stats
from database.db import get_connection
import security.camera as camera

import face_recognition
import cv2
import os

app = Flask(__name__)
app.config.from_object(Config)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower()
        in {"1", "true", "yes", "on"},
)

@app.after_request
def add_local_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.endpoint == "dashboard":
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
            "form-action 'self'; script-src 'self'; style-src 'self'; "
            "style-src-attr 'unsafe-inline'; img-src 'self' data: blob:; "
            "font-src 'self' data:; connect-src 'self'; media-src 'self' blob:"
        )
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


LOCAL_ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.getenv("AJARVIS_ALLOWED_HOSTS", "localhost,127.0.0.1,::1").split(",")
    if host.strip()
}
_local_registration_lock = threading.Lock()


@app.before_request
def reject_untrusted_host():
    """Reject arbitrary Host headers before routes touch the camera or database."""
    try:
        hostname = urlsplit("//" + request.host).hostname
    except ValueError:
        hostname = None
    if not hostname or hostname.lower() not in LOCAL_ALLOWED_HOSTS:
        return jsonify({"error": "Untrusted Host header."}), 421
    return None


def _serialize_registration(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        # This is a local, single-process bootstrap lock. It prevents parallel
        # first-user registrations from both observing an empty users table.
        with _local_registration_lock:
            return handler(*args, **kwargs)
    return wrapper


def _registration_is_allowed():
    if is_authenticated():
        return True, None
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        row = cursor.fetchone()
        user_count = int(row[0]) if row else 0
        if user_count == 0:
            return True, None
        return False, (jsonify({
            "status": "error",
            "message": "Registration is closed. Sign in with an existing account first.",
        }), 403)
    except Exception:
        app.logger.warning("Could not verify first-user registration state", exc_info=True)
        return False, (jsonify({
            "status": "error",
            "message": "Registration is temporarily unavailable.",
        }), 503)
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


_face_cache_loaded = False
_face_cache_lock = threading.Lock()
def _ensure_face_cache_loaded():
    global _face_cache_loaded
    with _face_cache_lock:
        if not _face_cache_loaded:
            load_known_faces()
            _face_cache_loaded = True
def _refresh_face_cache():
    global _face_cache_loaded
    with _face_cache_lock:
        load_known_faces()
        _face_cache_loaded = True


def _csrf_is_valid():
    expected = session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token", "") or request.form.get("csrf_token", "")
    return (
        isinstance(expected, str)
        and bool(expected)
        and isinstance(supplied, str)
        and bool(supplied)
        and hmac.compare_digest(expected, supplied)
    )


# ==========================================
# HOME
# ==========================================
@app.route("/")
def home():
    if is_authenticated():
        camera.pause_recognition()
        return redirect(url_for("dashboard"))
    camera.resume_recognition()
    return render_template("home.html")


# ==========================================
# LOGIN PAGE
# ==========================================
@app.route("/login")
def login():
    if is_authenticated():
        camera.pause_recognition()
        return redirect(url_for("dashboard"))
    camera.resume_recognition()
    return render_template("login.html")


# ==========================================
# REGISTER (GET + POST)
# ==========================================
@app.route("/register", methods=["GET", "POST"])
@_serialize_registration
def register():
    allowed, denial = _registration_is_allowed()
    if not allowed:
        if request.method == "GET" and denial[1] == 403:
            return redirect(url_for("login"))
        return denial

    camera.resume_recognition()
    if request.method == "GET":
        csrf_token = session.get("csrf_token")
        if not isinstance(csrf_token, str) or len(csrf_token) < 32:
            csrf_token = secrets.token_urlsafe(32)
            session["csrf_token"] = csrf_token
        return render_template("register.html", csrf_token=csrf_token)

    expected_csrf = session.get("csrf_token")
    supplied_csrf = request.headers.get("X-CSRF-Token", "")
    if (
        not isinstance(expected_csrf, str)
        or len(expected_csrf) < 32
        or not supplied_csrf
        or not hmac.compare_digest(expected_csrf, supplied_csrf)
    ):
        return jsonify({"status": "error", "message": "Security token expired. Reload the registration page and try again."}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "A JSON object is required."}), 400

    username = data.get("username")
    if not isinstance(username, str) or not username.strip():
        return jsonify({"status": "error", "message": "Missing username"}), 400
    username = username.strip()
    if len(username) > 100:
        return jsonify({"status": "error", "message": "Username must be 100 characters or fewer"}), 400

    latest = camera.get_latest_frame()
    if latest is None:
        return jsonify({"status": "error", "message": "Camera not ready, please wait a moment."}), 400

    try:
        rgb_frame = cv2.cvtColor(latest, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        if len(face_locations) != 1:
            return jsonify({
                "status": "error",
                "message": "Ensure exactly one face is visible and well lit.",
            }), 400

        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        if len(face_encodings) != 1:
            return jsonify({
                "status": "error",
                "message": "Could not create a face encoding. Adjust lighting and try again.",
            }), 400
        face_encoding = face_encodings[0]
        encoding_bytes = face_encoding.tobytes()
    except Exception:
        app.logger.exception("Face processing failed during registration")
        return jsonify({
            "status": "error",
            "message": "Face processing failed. Check camera input and try again.",
        }), 503

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            return jsonify({"status": "error", "message": "Username already exists"}), 400

        cursor.execute(
            "INSERT INTO users (username, face_encoding) VALUES (%s, %s)",
            (username, encoding_bytes),
        )
        conn.commit()
    except Exception:
        app.logger.exception("Face registration failed")
        if conn is not None:
            conn.rollback()
        return jsonify({"status": "error", "message": "Registration failed. Check server logs."}), 500
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

    try:
        _refresh_face_cache()
    except Exception:
        # The new record is committed already; don't report it as an insertion
        # failure. Explain that recognition needs a successful cache refresh.
        app.logger.exception("Face registration saved but cache refresh failed")
        return jsonify({
            "status": "success",
            "message": "Registration saved. Restart AJARVIS before attempting face login.",
        }), 201

    return jsonify({"status": "success", "message": "Face registered successfully."})


# ==========================================
# VIDEO FEED (Face Login)
# ==========================================
@app.route("/video_feed")
def video_feed():
    # Only the bootstrap owner (before the first account) or an authenticated
    # user may read the camera. The loopback check remains a second boundary.
    if not is_authenticated():
        allowed, denial = _registration_is_allowed()
        if not allowed:
            return denial
    try:
        remote_ip = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return jsonify({"error": "Local camera access is restricted."}), 403
    if not remote_ip.is_loopback:
        return jsonify({"error": "Local camera access is restricted."}), 403
    response = Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")
    response.headers["Cache-Control"] = "no-store"
    return response


# ==========================================
# CHECK ACCESS (Auto Login)
# ==========================================
@app.route("/check_access")
def check_access():
    if is_authenticated():
        camera.pause_recognition()
        response = jsonify({"access": True, "user": session.get("user")})
        response.headers["Cache-Control"] = "no-store"
        return response
    try:
        _ensure_face_cache_loaded()
        detected = camera.get_detected_user()
        camera_ready = camera.is_camera_ready()
    except Exception:
        app.logger.exception("Face authentication unavailable")
        response = jsonify({"access": False, "camera_ready": False,
                            "error": "Face authentication is temporarily unavailable."})
        response.status_code = 503
        response.headers["Cache-Control"] = "no-store"
        return response
    if detected:
        grant_access(detected)
        camera.pause_recognition()
        camera.reset_detected_user()
        response = jsonify({"access": True, "user": detected, "camera_ready": camera_ready})
    else:
        response = jsonify({"access": False, "camera_ready": camera_ready})
    response.headers["Cache-Control"] = "no-store"
    return response


# ==========================================
# DASHBOARD
# ==========================================
@app.route("/dashboard")
def dashboard():
    if not is_authenticated():
        return redirect(url_for("home"))
    camera.pause_recognition()
    csrf_token = session.get("csrf_token")
    if not isinstance(csrf_token, str) or len(csrf_token) < 32:
        csrf_token = secrets.token_urlsafe(32)
        session["csrf_token"] = csrf_token
    return render_template(
        "dashboard.html",
        user=session["user"],
        is_active=is_user_active(session["user"]),
        csrf_token=csrf_token,
    )


# ==========================================
# SYSTEM STATS
# ==========================================
@app.route("/system_stats")
def system_stats():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    try:
        response = jsonify(get_stats())
    except Exception:
        app.logger.exception("System telemetry collection failed")
        response = jsonify({"error": "System telemetry is temporarily unavailable."})
        response.status_code = 503
    response.headers["Cache-Control"] = "no-store"
    return response


# ==========================================
# COMMAND HISTORY
# ==========================================
@app.route("/command_history")
def command_history():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"history": get_all_recent(20, username=session["user"])})


# ==========================================
# USAGE ANALYTICS
# ==========================================
@app.route("/analytics")
def analytics():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT command, COUNT(*) as count
            FROM command_history
            WHERE username = %s
            GROUP BY command
            ORDER BY count DESC
            LIMIT 5
            """,
            (session["user"],),
        )
        rows = cursor.fetchall()
        return jsonify({"labels": [row[0] for row in rows], "data": [row[1] for row in rows]})
    except Exception:
        app.logger.exception("Analytics query failed")
        return jsonify({"error": "Analytics temporarily unavailable"}), 503
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


# ==========================================
# PERSONAL MEMORY API
# ==========================================
@app.route("/api/memories", methods=["GET", "POST"])
def personal_memories_api():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401

    username = session["user"]
    if request.method == "GET":
        try:
            response = jsonify({"memories": list_memories(username)})
            response.headers["Cache-Control"] = "no-store"
            return response
        except Exception:
            app.logger.exception("Could not list personal memories")
            return jsonify({"error": "Personal memory is unavailable."}), 503

    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    try:
        saved = save_memory(username, data.get("key"), data.get("value"))
        return jsonify({"memory": saved}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("Could not save personal memory")
        return jsonify({"error": "Personal memory could not be saved. Check the database migration."}), 503


@app.route("/api/memories/<memory_key>", methods=["DELETE"])
def delete_personal_memory_api(memory_key):
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    try:
        deleted = delete_memory(session["user"], memory_key)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("Could not delete personal memory")
        return jsonify({"error": "Personal memory could not be deleted."}), 503
    if not deleted:
        return jsonify({"error": "Memory not found."}), 404
    return jsonify({"ok": True})


# ==========================================
# PHASE 5 — TASK PLANNING & CONTROLLED AUTOMATION
# ==========================================
@app.route("/api/automation/plan", methods=["POST"])
def create_automation_plan_api():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403

    username = session["user"]
    if not is_user_active(username):
        return jsonify({"error": "Activate AJARVIS before starting an automation plan."}), 409

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    task = data.get("task")
    if not isinstance(task, str) or not task.strip() or len(task.strip()) > 1000:
        return jsonify({"error": "Task must contain 1–1000 characters."}), 400

    try:
        planned = generate_task_plan(_get_genai_client(), task, username)
        plan = advance_plan(planned["plan_id"], username)
        response = jsonify({"plan": plan})
        response.status_code = 201
        response.headers["Cache-Control"] = "no-store"
        return response
    except PlannerError as exc:
        return jsonify({"error": str(exc)}), 422
    except AutomationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("Automation planning failed")
        return jsonify({"error": "The automation plan could not be created."}), 503


@app.route("/api/automation/approval/<approval_id>", methods=["POST"])
def respond_automation_approval_api(approval_id):
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    username = session["user"]
    if not is_user_active(username):
        return jsonify({"error": "Activate AJARVIS before approving automation."}), 409
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get("decision") not in {"approve", "reject"}:
        return jsonify({"error": "Decision must be 'approve' or 'reject'."}), 400
    try:
        plan = respond_to_approval(approval_id, username, data["decision"])
        response = jsonify({"plan": plan})
        response.headers["Cache-Control"] = "no-store"
        return response
    except AutomationError as exc:
        return jsonify({"error": str(exc)}), 409


@app.route("/api/automation/plan/<plan_id>/cancel", methods=["POST"])
def cancel_automation_plan_api(plan_id):
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    try:
        plan = cancel_plan(plan_id, session["user"])
        response = jsonify({"plan": plan})
        response.headers["Cache-Control"] = "no-store"
        return response
    except AutomationError as exc:
        return jsonify({"error": str(exc)}), 404


@app.route("/api/automation/activity", methods=["GET"])
def automation_activity_api():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    response = jsonify({"activity": list_recent_activity(session["user"], limit=30)})
    response.headers["Cache-Control"] = "no-store"
    return response


# ==========================================
# PHASE 6 — PROACTIVE REMINDERS & WORKFLOW MEMORY
# ==========================================
@app.route("/api/automation/workflows", methods=["GET"])
def automation_workflows_api():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    response = jsonify({"workflows": list_recent_workflows(session["user"], limit=30)})
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/reminders", methods=["GET", "POST"])
def reminders_api():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    username = session["user"]
    if request.method == "GET":
        try:
            response = jsonify({"reminders": list_reminders(username)})
            response.headers["Cache-Control"] = "no-store"
            return response
        except ReminderUnavailable as exc:
            return jsonify({"error": str(exc)}), 503
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    try:
        reminder = create_reminder(username, data.get("title"), data.get("due_at"))
        response = jsonify({"reminder": reminder})
        response.status_code = 201
        response.headers["Cache-Control"] = "no-store"
        return response
    except ReminderUnavailable as exc:
        return jsonify({"error": str(exc)}), 503
    except ReminderError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/reminders/<int:reminder_id>/status", methods=["POST"])
def reminder_status_api(reminder_id):
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    try:
        changed = update_reminder_status(session["user"], reminder_id, data.get("status"))
    except ReminderUnavailable as exc:
        return jsonify({"error": str(exc)}), 503
    except ReminderError as exc:
        return jsonify({"error": str(exc)}), 400
    if not changed:
        return jsonify({"error": "Reminder was not found or is no longer active."}), 404
    response = jsonify({"ok": True})
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/notification-preferences", methods=["GET", "PUT"])
def notification_preferences_api():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    username = session["user"]
    if request.method == "GET":
        try:
            response = jsonify({"preferences": get_notification_preferences(username)})
            response.headers["Cache-Control"] = "no-store"
            return response
        except ReminderUnavailable as exc:
            return jsonify({"error": str(exc)}), 503
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    try:
        preferences = set_notification_preferences(
            username,
            reminders_enabled=data.get("reminders_enabled"),
            browser_notifications_enabled=data.get("browser_notifications_enabled", False),
        )
        response = jsonify({"preferences": preferences})
        response.headers["Cache-Control"] = "no-store"
        return response
    except ReminderUnavailable as exc:
        return jsonify({"error": str(exc)}), 503
    except ReminderError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/notifications", methods=["GET"])
def notifications_api():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    username = session["user"]
    try:
        preferences = get_notification_preferences(username)
        newly_due = collect_due_notifications(username, limit=20)
        response = jsonify({
            "notifications": list_unread_notifications(username, limit=30),
            "newly_due": newly_due,
            "preferences": preferences,
        })
        response.headers["Cache-Control"] = "no-store"
        return response
    except ReminderUnavailable as exc:
        return jsonify({"error": str(exc)}), 503


@app.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
def mark_notification_read_api(notification_id):
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    try:
        changed = mark_notification_read(session["user"], notification_id)
    except ReminderUnavailable as exc:
        return jsonify({"error": str(exc)}), 503
    except ReminderError as exc:
        return jsonify({"error": str(exc)}), 400
    if not changed:
        return jsonify({"error": "Notification was not found or is already read."}), 404
    response = jsonify({"ok": True})
    response.headers["Cache-Control"] = "no-store"
    return response


# ==========================================
# PHASE 7 — PERSONAL PROJECT & TASK INTELLIGENCE
# ==========================================
@app.route("/api/personal-intelligence/focus", methods=["GET"])
def personal_intelligence_focus_api():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    try:
        response = jsonify({"focus": build_personal_focus(session["user"])})
        response.headers["Cache-Control"] = "no-store"
        return response
    except PersonalIntelligenceError as exc:
        return jsonify({"error": str(exc)}), 503


@app.route("/api/projects", methods=["GET", "POST"])
def personal_projects_api():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    username = session["user"]
    if request.method == "GET":
        try:
            response = jsonify({"projects": list_projects(username)})
            response.headers["Cache-Control"] = "no-store"
            return response
        except PersonalIntelligenceError as exc:
            return jsonify({"error": str(exc)}), 503
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    try:
        project = create_project(username, data.get("name"), data.get("objective", ""))
        response = jsonify({"project": project})
        response.status_code = 201
        response.headers["Cache-Control"] = "no-store"
        return response
    except PersonalIntelligenceError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/projects/<int:project_id>/status", methods=["POST"])
def personal_project_status_api(project_id):
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    try:
        changed = update_project_status(session["user"], project_id, data.get("status"))
    except PersonalIntelligenceError as exc:
        return jsonify({"error": str(exc)}), 400
    if not changed:
        return jsonify({"error": "Project not found."}), 404
    return jsonify({"ok": True})


@app.route("/api/tasks", methods=["GET", "POST"])
def personal_tasks_api():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    username = session["user"]
    if request.method == "GET":
        try:
            response = jsonify({"tasks": list_tasks(
                username,
                include_completed=request.args.get("include_completed", "").lower() in {"1", "true", "yes"},
            )})
            response.headers["Cache-Control"] = "no-store"
            return response
        except PersonalIntelligenceError as exc:
            return jsonify({"error": str(exc)}), 503
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    try:
        task = create_task(
            username,
            data.get("title"),
            project_id=data.get("project_id"),
            details=data.get("details", ""),
            priority=data.get("priority", "normal"),
            due_at=data.get("due_at"),
            effort_minutes=data.get("effort_minutes"),
        )
        response = jsonify({"task": task})
        response.status_code = 201
        response.headers["Cache-Control"] = "no-store"
        return response
    except PersonalIntelligenceError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/tasks/<int:task_id>/status", methods=["POST"])
def personal_task_status_api(task_id):
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400
    try:
        changed = update_task_status(session["user"], task_id, data.get("status"))
    except PersonalIntelligenceError as exc:
        return jsonify({"error": str(exc)}), 400
    if not changed:
        return jsonify({"error": "Task not found or no longer active."}), 404
    return jsonify({"ok": True})


# ==========================================
# VOICE COMMAND
# ==========================================
@app.route("/voice_command", methods=["POST"])
@app.route("/command", methods=["POST"])
def voice_command():
    if not is_authenticated():
        return jsonify({"response": "Unauthorized access."}), 401
    if not _csrf_is_valid():
        return jsonify({"response": "CSRF validation failed."}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"response": "A JSON object is required."}), 400
    command = data.get("command")
    if not isinstance(command, str) or not command.strip():
        return jsonify({"response": "A non-empty command is required."}), 400
    command = command.strip()
    if len(command) > 2000:
        return jsonify({"response": "Command is too long."}), 400
    username = session["user"]
    reply = process_command(command, username)
    response = jsonify({"response": reply, "active": is_user_active(username),
                        "intent": classify_intent(command)})
    response.headers["Cache-Control"] = "no-store"
    return response


# ==========================================
# LOGOUT
# ==========================================
@app.route("/logout", methods=["POST"])
def logout():
    if not is_authenticated():
        return redirect(url_for("home"))
    if not _csrf_is_valid():
        return jsonify({"error": "CSRF validation failed."}), 403
    try:
        cancel_user_plans(session["user"])
    except AutomationError:
        app.logger.warning("Could not cancel pending automation plans during logout")
    revoke_access()
    camera.resume_recognition()
    return redirect(url_for("home"))


# ==========================================
# START APP
# ==========================================
if __name__ == "__main__":
    try:
        recover_interrupted_workflows()
    except Exception:
        app.logger.warning("Workflow recovery check failed", exc_info=True)
    _ensure_face_cache_loaded()
    app.run(host="127.0.0.1", port=5000, debug=False)
