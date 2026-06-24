# security/face_auth.py

import face_recognition
import numpy as np
import cv2
from database.db import get_connection

# Global cache
known_users = []

def load_known_faces():
    global known_users
    known_users = []

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT username, face_encoding FROM users")
    users = cursor.fetchall()

    cursor.close()
    conn.close()

    for user in users:
        username = user[0]
        encoding = np.frombuffer(user[1], dtype=np.float64)
        known_users.append((username, encoding))

def check_face(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb)

    if not face_locations:
        return []

    face_encodings = face_recognition.face_encodings(rgb, face_locations)
    recognized_results = []

    for face_encoding, face_location in zip(face_encodings, face_locations):
        matched_username = None
        for username, db_encoding in known_users:
            distance = face_recognition.face_distance(
                [db_encoding],
                face_encoding
            )[0]
            
            if distance < 0.65:
                matched_username = username
                break
        
        recognized_results.append((matched_username, face_location))

    return recognized_results