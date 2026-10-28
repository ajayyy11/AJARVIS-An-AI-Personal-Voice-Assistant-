"""Face-encoding loading and matching for local AJARVIS authentication."""

import logging
import os

import cv2
import face_recognition
import numpy as np

from database.db import get_connection

logger = logging.getLogger(__name__)

# A lower threshold is stricter. Tune against consented samples on the target
# camera/lighting setup; this is not a substitute for liveness detection.
try:
    FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "0.55"))
except ValueError as exc:
    raise RuntimeError("FACE_MATCH_THRESHOLD must be a number between 0 and 1.") from exc
if not 0.0 <= FACE_MATCH_THRESHOLD <= 1.0:
    raise RuntimeError("FACE_MATCH_THRESHOLD must be a number between 0 and 1.")

ENCODING_LENGTH = 128

# Cache entries are (username, 128-dimensional face encoding).
known_users = []


def load_known_faces():
    """Load valid face encodings while reliably closing database resources.

    Keep the previous cache if the database query fails; only publish the new
    cache after a successful read.
    """
    global known_users
    conn = None
    cursor = None
    loaded_users = []

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username, face_encoding FROM users")
        users = cursor.fetchall()

        for username, raw_encoding in users:
            if not raw_encoding:
                logger.warning("Skipping face record with empty encoding for %r", username)
                continue

            try:
                encoding = np.frombuffer(raw_encoding, dtype=np.float64)
            except (TypeError, ValueError):
                logger.warning("Skipping unreadable face encoding for %r", username)
                continue

            if (
                encoding.shape != (ENCODING_LENGTH,)
                or not np.isfinite(encoding).all()
            ):
                logger.warning("Skipping malformed face encoding for %r", username)
                continue

            loaded_users.append((username, encoding))

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

    known_users = loaded_users
    logger.info("Loaded %d valid face encoding(s)", len(known_users))
    return len(known_users)


def check_face(frame):
    """Return (username-or-None, face-location) for each detected face."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb)
    if not face_locations:
        return []

    face_encodings = face_recognition.face_encodings(rgb, face_locations)
    recognized_results = []

    for face_encoding, face_location in zip(face_encodings, face_locations):
        matched_username = None
        best_distance = float("inf")

        for username, db_encoding in known_users:
            distance = float(
                face_recognition.face_distance([db_encoding], face_encoding)[0]
            )
            if distance < best_distance:
                best_distance = distance
                matched_username = username

        if best_distance >= FACE_MATCH_THRESHOLD:
            matched_username = None

        recognized_results.append((matched_username, face_location))

    return recognized_results
