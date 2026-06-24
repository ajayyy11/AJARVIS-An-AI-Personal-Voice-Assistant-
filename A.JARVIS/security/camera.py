import cv2
import threading
import time
from security.face_auth import check_face

class Camera:
    def __init__(self):
        self.video = cv2.VideoCapture(0)
        self.latest_frame = None
        self.detected_results = []  # List of (username, location)
        self.is_running = True
        self.lock = threading.Lock()
        
        # Start capture thread
        self.capture_thread = threading.Thread(target=self._capture_frames, daemon=True)
        self.capture_thread.start()
        
        # Start recognition thread
        self.recognition_thread = threading.Thread(target=self._recognize_faces, daemon=True)
        self.recognition_thread.start()

    def _capture_frames(self):
        while self.is_running:
            success, frame = self.video.read()
            if success:
                with self.lock:
                    self.latest_frame = frame
            else:
                time.sleep(0.1)

    def _recognize_faces(self):
        while self.is_running:
            frame_to_process = None
            with self.lock:
                if self.latest_frame is not None:
                    frame_to_process = self.latest_frame.copy()
            
            if frame_to_process is not None:
                # results is a list of (username, location)
                try:
                    results = check_face(frame_to_process)
                    with self.lock:
                        self.detected_results = results
                except Exception as e:
                    print(f"Recognition error: {e}")
            
            # Run recognition a few times per second to save CPU
            time.sleep(0.4)

    def get_display_frame(self):
        with self.lock:
            if self.latest_frame is None:
                return None
            frame = self.latest_frame.copy()
            results = self.detected_results
            
        # Draw bounding boxes and labels
        for username, (top, right, bottom, left) in results:
            # Color: Green for known, Red for unknown
            color = (0, 255, 0) if username else (0, 0, 255)
            
            # Draw the box around the face
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            
            # Draw the label block
            label = username if username else "Unknown"
            cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
            font = cv2.FONT_HERSHEY_DUPLEX
            cv2.putText(frame, label, (left + 6, bottom - 6), font, 0.8, (255, 255, 255), 1)
            
        if not results:
            cv2.putText(frame, "Scanning...", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        return frame

    def generate_frames(self):
        while self.is_running:
            frame = self.get_display_frame()
            if frame is None:
                time.sleep(0.1)
                continue
            
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# Global instance for backward compatibility
_cam_instance = None

def get_camera():
    global _cam_instance
    if _cam_instance is None:
        _cam_instance = Camera()
    return _cam_instance

# Global variables for app.py
@property
def detected_user():
    cam = get_camera()
    with cam.lock:
        for user, _ in cam.detected_results:
            if user: return user
    return None

@detected_user.setter
def detected_user(value):
    # This is to support camera.detected_user = None in app.py
    cam = get_camera()
    with cam.lock:
        if value is None:
            cam.detected_results = []

@property
def latest_frame():
    return get_camera().latest_frame

def generate_frames():
    return get_camera().generate_frames()

# For app.py to access these as if they were simple variables
import sys
class _ModuleProxy(object):
    def __init__(self, original_module):
        self.original_module = original_module
    def __getattr__(self, name):
        if name == 'detected_user':
            cam = get_camera()
            with cam.lock:
                for user, _ in cam.detected_results:
                    if user: return user
            return None
        if name == 'latest_frame':
            return get_camera().latest_frame
        return getattr(self.original_module, name)
    def __setattr__(self, name, value):
        if name == 'original_module':
            super().__setattr__(name, value)
            return
        if name == 'detected_user' and value is None:
            cam = get_camera()
            with cam.lock:
                cam.detected_results = []
            return
        setattr(self.original_module, name, value)

# Note: The proxy trick might be complex, let's just use regular functions or update app.py.
# Actually, I'll update app.py to use camera.get_detected_user() etc. It's cleaner.
# But I'll keep generate_frames() as it is.

def get_detected_user():
    cam = get_camera()
    with cam.lock:
        for user, _ in cam.detected_results:
            if user: return user
    return None

def reset_detected_user():
    cam = get_camera()
    with cam.lock:
        cam.detected_results = []

def get_latest_frame():
    return get_camera().latest_frame