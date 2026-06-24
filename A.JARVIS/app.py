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
app.secret_key = app.config.get("SECRET_KEY")

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

    # -----------------------------
    # POST → Face Registration
    # -----------------------------
    data = request.get_json()
    username = data.get("username")

    if not username:
        return jsonify({"status": "error", "message": "Missing username"}), 400

    latest = camera.get_latest_frame()
    if latest is None:
        return jsonify({"status": "error", "message": "Camera not ready, please wait a moment."}), 400

    rgb_frame = cv2.cvtColor(latest, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(rgb_frame)

    if len(face_locations) != 1:
        return jsonify({"status": "error", "message": "Ensure exactly one face visible"}), 400

    face_encoding = face_recognition.face_encodings(rgb_frame, face_locations)[0]
    encoding_bytes = face_encoding.tobytes()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"status": "error", "message": "Username already exists"}), 400

    cursor.execute(
        "INSERT INTO users (username, face_encoding) VALUES (%s, %s)",
        (username, encoding_bytes)
    )

    conn.commit()
    cursor.close()
    conn.close()

    load_known_faces()

    return jsonify({"status": "success"})


# ==========================================
# VIDEO FEED (Face Login)
# ==========================================
@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


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
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify(get_stats())


# ==========================================
# COMMAND HISTORY
# ==========================================
@app.route("/command_history")
def command_history():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify({"history": get_all_recent(20)})


# ==========================================
# USAGE ANALYTICS
# ==========================================
@app.route("/analytics")
def analytics():
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT command, COUNT(*) as count 
            FROM command_history 
            GROUP BY command 
            ORDER BY count DESC 
            LIMIT 5
        ''')
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        labels = [r[0] for r in rows]
        data = [r[1] for r in rows]
        return jsonify({"labels": labels, "data": data})
    except Exception as e:
        print("Analytics error:", e)
        return jsonify({"labels": [], "data": []})


# ==========================================
# VOICE COMMAND
# ==========================================
@app.route("/voice_command", methods=["POST"])
def voice_command():

    if not is_authenticated():
        return jsonify({"response": "Unauthorized access."})

    data = request.get_json()
    command = data.get("command")

    username = session.get("user", "User")

    response = process_command(command, username)

    return jsonify({"response": response})


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
    app.run(host="0.0.0.0", port=5000, debug=True)