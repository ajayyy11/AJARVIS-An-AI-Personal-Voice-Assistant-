"""Threaded local camera with fresh-frame and stable-match authentication gates."""
import logging, threading, time
import cv2
from security.face_auth import check_face
logger=logging.getLogger(__name__)
FRAME_MAX_AGE_SECONDS=2.0
RECOGNITION_MAX_AGE_SECONDS=1.5
REQUIRED_STABLE_MATCHES=2
STREAM_INTERVAL_SECONDS=1/15
class Camera:
    def __init__(self,source=0):
        self.video=cv2.VideoCapture(source)
        try: self.camera_available=bool(self.video and self.video.isOpened())
        except Exception: self.camera_available=False
        self.latest_frame=None; self.latest_frame_at=0.0; self.detected_results=[]
        self.last_recognition_at=0.0; self._last_recognition_frame_at=0.0
        self._candidate_username=None; self._candidate_count=0; self._stable_username=None
        self.is_running=True; self.recognition_enabled=True; self.lock=threading.RLock()
        self.capture_thread=threading.Thread(target=self._capture_frames,daemon=True,name="ajarvis-camera")
        self.recognition_thread=threading.Thread(target=self._recognize_faces,daemon=True,name="ajarvis-face")
        self.capture_thread.start(); self.recognition_thread.start()
    def _capture_frames(self):
        while self.is_running:
            try: success,frame=self.video.read() if self.camera_available else (False,None)
            except Exception:
                logger.exception("Camera capture failed"); success,frame=False,None
            if success and frame is not None:
                with self.lock: self.latest_frame=frame; self.latest_frame_at=time.monotonic()
            else: time.sleep(.1)
    def _record_recognition(self,results,*,recognized_at=None,frame_timestamp=None):
        recognized_at=time.monotonic() if recognized_at is None else recognized_at
        with self.lock:
            # A recognition call may finish after pause_recognition() is invoked.
            # Discard its result so it cannot re-enable a stale post-login match.
            if not self.recognition_enabled:
                return
            if frame_timestamp is not None:
                if frame_timestamp<=self._last_recognition_frame_at: return
                self._last_recognition_frame_at=frame_timestamp
            self.detected_results=list(results or []); self.last_recognition_at=recognized_at
            name=self.detected_results[0][0] if len(self.detected_results)==1 else None
            if name:
                if name==self._candidate_username: self._candidate_count+=1
                else: self._candidate_username,self._candidate_count=name,1
                self._stable_username=name if self._candidate_count>=REQUIRED_STABLE_MATCHES else None
            else:
                self._candidate_username=None; self._candidate_count=0; self._stable_username=None
    def _recognize_faces(self):
        while self.is_running:
            frame=None; timestamp=0.0
            with self.lock:
                enabled=self.recognition_enabled
                if enabled and self.latest_frame is not None and self.latest_frame_at>self._last_recognition_frame_at:
                    frame=self.latest_frame.copy(); timestamp=self.latest_frame_at
            if not enabled or frame is None: time.sleep(.1); continue
            try: results=check_face(frame)
            except Exception:
                logger.exception("Face recognition failed"); results=[]
            self._record_recognition(results,recognized_at=time.monotonic(),frame_timestamp=timestamp)
            time.sleep(.05)
    def get_detected_user(self):
        now=time.monotonic()
        with self.lock:
            fresh=now-self.last_recognition_at<=RECOGNITION_MAX_AGE_SECONDS and now-self.latest_frame_at<=FRAME_MAX_AGE_SECONDS
            if fresh and self._stable_username and self._candidate_count>=REQUIRED_STABLE_MATCHES: return self._stable_username
        return None
    def reset_detected_user(self):
        with self.lock:
            self.detected_results=[]; self._candidate_username=None; self._candidate_count=0
            self._stable_username=None; self.last_recognition_at=0.0
    def pause_recognition(self):
        with self.lock:
            self.recognition_enabled=False
            self.detected_results=[]; self._candidate_username=None; self._candidate_count=0
            self._stable_username=None; self.last_recognition_at=0.0
    def resume_recognition(self):
        with self.lock:
            self._last_recognition_frame_at=0.0
            self.recognition_enabled=True
    def get_latest_frame(self):
        with self.lock:
            if self.latest_frame is None or time.monotonic()-self.latest_frame_at>FRAME_MAX_AGE_SECONDS: return None
            return self.latest_frame.copy()
    def is_camera_ready(self): return bool(self.camera_available)
    def get_display_frame(self):
        with self.lock:
            if self.latest_frame is None: return None
            frame=self.latest_frame.copy(); results=list(self.detected_results)
        for username,(top,right,bottom,left) in results:
            color=(0,255,0) if username else (0,0,255)
            cv2.rectangle(frame,(left,top),(right,bottom),color,2)
            label=username if username else "Unknown"
            cv2.rectangle(frame,(left,bottom-35),(right,bottom),color,cv2.FILLED)
            cv2.putText(frame,label,(left+6,bottom-6),cv2.FONT_HERSHEY_DUPLEX,.8,(255,255,255),1)
        if not results: cv2.putText(frame,"Scanning...",(30,40),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,255,255),2)
        return frame
    def generate_frames(self):
        while self.is_running:
            frame_started=time.monotonic()
            frame=self.get_display_frame()
            if frame is None:
                time.sleep(.1)
                continue
            try:
                ok,buffer=cv2.imencode(".jpg",frame)
                if not ok:
                    time.sleep(.05)
                    continue
                payload=buffer.tobytes()
            except Exception:
                logger.exception("Camera frame encoding failed")
                time.sleep(.1)
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"+payload+b"\r\n"
            remaining=STREAM_INTERVAL_SECONDS-(time.monotonic()-frame_started)
            if remaining>0:
                time.sleep(remaining)
    def close(self):
        self.is_running=False
        try: self.video.release()
        except Exception: logger.debug("Camera release failed",exc_info=True)
        for thread in (self.capture_thread,self.recognition_thread):
            if thread.is_alive(): thread.join(timeout=1.0)
_cam_instance=None
_camera_lock=threading.Lock()
def get_camera():
    global _cam_instance
    if _cam_instance is None or not _cam_instance.is_running:
        with _camera_lock:
            if _cam_instance is None or not _cam_instance.is_running: _cam_instance=Camera()
    return _cam_instance
def generate_frames(): return get_camera().generate_frames()
def get_detected_user(): return get_camera().get_detected_user()
def reset_detected_user(): get_camera().reset_detected_user()
def get_latest_frame(): return get_camera().get_latest_frame()
def is_camera_ready(): return get_camera().is_camera_ready()
def pause_recognition(): get_camera().pause_recognition()
def resume_recognition(): get_camera().resume_recognition()

def stop_camera():
    """Release the physical camera and clear the shared instance.

    This is used after successful authentication so the camera hardware is not
    held open throughout the authenticated dashboard session.
    """
    global _cam_instance
    with _camera_lock:
        instance = _cam_instance
        _cam_instance = None
        if instance is None:
            return False
        instance.close()
        return True

