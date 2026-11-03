"""Local face-encoding lookup. Face recognition is not liveness detection."""
import logging, os
import cv2, face_recognition, numpy as np
from database.db import get_connection
logger=logging.getLogger(__name__)
try: FACE_MATCH_THRESHOLD=float(os.getenv("FACE_MATCH_THRESHOLD","0.55"))
except (TypeError,ValueError) as exc: raise RuntimeError("FACE_MATCH_THRESHOLD must be between 0 and 1.") from exc
if not np.isfinite(FACE_MATCH_THRESHOLD) or not 0.0<=FACE_MATCH_THRESHOLD<=1.0: raise RuntimeError("FACE_MATCH_THRESHOLD must be between 0 and 1.")
ENCODING_LENGTH=128
known_users=[]
def _valid_encoding(value):
    try: encoding=np.asarray(value,dtype=np.float64)
    except (TypeError,ValueError): return None
    if encoding.shape!=(ENCODING_LENGTH,) or not np.isfinite(encoding).all(): return None
    return encoding
def load_known_faces():
    """Atomically refresh valid encodings; retain old cache on DB failure."""
    global known_users
    conn=cursor=None
    loaded=[]
    try:
        conn=get_connection(); cursor=conn.cursor()
        cursor.execute("SELECT username, face_encoding FROM users")
        for username,raw in cursor.fetchall():
            if not raw:
                logger.warning("Skipping empty face encoding"); continue
            try: encoding=np.frombuffer(raw,dtype=np.float64)
            except (TypeError,ValueError):
                logger.warning("Skipping unreadable face encoding"); continue
            encoding=_valid_encoding(encoding)
            if encoding is None:
                logger.warning("Skipping malformed face encoding"); continue
            loaded.append((username,encoding))
    finally:
        try:
            if cursor is not None: cursor.close()
        finally:
            if conn is not None: conn.close()
    known_users=loaded
    logger.info("Loaded %d valid face encodings",len(known_users))
    return len(known_users)
def check_face(frame):
    """Return (username-or-None, face-location) for all detected faces."""
    if frame is None: return []
    rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
    locations=face_recognition.face_locations(rgb)
    if not locations: return []
    candidates=face_recognition.face_encodings(rgb,locations)
    valid=[(name,enc) for name,raw in known_users if (enc:=_valid_encoding(raw)) is not None]
    results=[]
    for index,location in enumerate(locations):
        matched=None
        if index<len(candidates) and valid:
            candidate=_valid_encoding(candidates[index])
            if candidate is not None:
                distances=np.asarray(face_recognition.face_distance([enc for _name,enc in valid],candidate),dtype=np.float64).reshape(-1)
                if distances.size==len(valid) and np.isfinite(distances).all():
                    best=int(np.argmin(distances))
                    if float(distances[best])<FACE_MATCH_THRESHOLD: matched=valid[best][0]
        results.append((matched,location))
    return results
