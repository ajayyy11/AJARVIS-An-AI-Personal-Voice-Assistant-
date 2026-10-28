from flask import Flask, render_template, Response, redirect, url_for, jsonify, request, session
from config import Config
from security.camera import generate_frames
from security.session_manager import is_authenticated, revoke_access, grant_access
from security.face_auth import load_known_faces
from intelligence.command_router import process_command
from intelligence.memory import get_all_recent
from system.stats import get_stats
from database.db import get_connection
import security.camera as camera

import face_recognition
import numpy as np
import base64
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


# ==========================================
# HOME
# ==========================================
@app.route("/")
def home():
    if is_authenticated():
        return redirect(url_for("dashboard"))
    return render_template("home.html")


# ==========================================
# LOGIN PAGE
# ==========================================
@app.route("/login")
def login():
    if is_authenticated():
        return redirect(url_for("dashboard"))
    return render_template("login.html")


# ==========================================
# REGISTER (GET + POST)
# ==========================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

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
        load_known_faces()
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
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


# ==========================================
# CHECK ACCESS (Auto Login)
# ==========================================
@app.route("/check_access")
def check_access():
    detected = camera.get_detected_user()
    if detected:
        grant_access(detected)
        camera.reset_detected_user()
        return jsonify({"access": True})
    return jsonify({"access": is_authenticated()})


# ==========================================
# DASHBOARD
# ==========================================
@app.route("/dashboard")
def dashboard():
    if not is_authenticated():
        return redirect(url_for("home"))
    return render_template("dashboard.html", user=session["user"])


# ==========================================
# SYSTEM STATS
# ==========================================
@app.route("/system_stats")
def system_stats():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_stats())


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
# VOICE COMMAND
# ==========================================
@app.route("/voice_command", methods=["POST"])
def voice_command():
    if not is_authenticated():
        return jsonify({"response": "Unauthorized access."}), 401

    data = request.get_json(silent=True) or {}
    command = data.get("command")
    if not isinstance(command, str) or not command.strip():
        return jsonify({"response": "A non-empty command is required."}), 400
    if len(command) > 2000:
        return jsonify({"response": "Command is too long."}), 400

    username = session.get("user", "User")
    return jsonify({"response": process_command(command.strip(), username)})


# ==========================================
# LOGOUT
# ==========================================
@app.route("/logout")
def logout():
    revoke_access()
    return redirect(url_for("home"))


# ==========================================
# START APP
# ==========================================
if __name__ == "__main__":
    load_known_faces()
    app.run(host="127.0.0.1", port=5000, debug=False)
