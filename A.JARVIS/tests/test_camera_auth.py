import threading
import numpy as np
import pytest
from security import camera as camera_module
from security import face_auth


def test_face_match_accepts_encoding_below_threshold(monkeypatch):
    encoding=np.zeros(128,dtype=np.float64)
    monkeypatch.setattr(face_auth,"known_users",[("alice",encoding)])
    monkeypatch.setattr(face_auth.cv2,"cvtColor",lambda frame,_code:frame)
    monkeypatch.setattr(face_auth.face_recognition,"face_locations",lambda _frame:[(1,10,10,1)])
    monkeypatch.setattr(face_auth.face_recognition,"face_encodings",lambda _frame,_loc:[encoding])
    monkeypatch.setattr(face_auth.face_recognition,"face_distance",lambda _known,_candidate:np.asarray([.42]))
    assert face_auth.check_face(object())==[("alice",(1,10,10,1))]


def test_face_match_rejects_value_at_or_above_threshold(monkeypatch):
    encoding=np.zeros(128,dtype=np.float64)
    monkeypatch.setattr(face_auth,"known_users",[("alice",encoding)])
    monkeypatch.setattr(face_auth.cv2,"cvtColor",lambda frame,_code:frame)
    monkeypatch.setattr(face_auth.face_recognition,"face_locations",lambda _frame:[(0,8,8,0)])
    monkeypatch.setattr(face_auth.face_recognition,"face_encodings",lambda _frame,_loc:[encoding])
    monkeypatch.setattr(face_auth.face_recognition,"face_distance",lambda _known,_candidate:np.asarray([face_auth.FACE_MATCH_THRESHOLD]))
    assert face_auth.check_face(object())[0][0] is None


def test_face_cache_skips_malformed_encodings_and_closes_resources(monkeypatch):
    valid=np.zeros(128,dtype=np.float64).tobytes()
    malformed=np.zeros(127,dtype=np.float64).tobytes()
    class Cursor:
        closed=False
        def execute(self,_sql): pass
        def fetchall(self): return [("alice",valid),("bad-shape",malformed),("empty",None)]
        def close(self): self.closed=True
    class Connection:
        closed=False
        def __init__(self): self.cursor_value=Cursor()
        def cursor(self): return self.cursor_value
        def close(self): self.closed=True
    connection=Connection()
    monkeypatch.setattr(face_auth,"get_connection",lambda:connection)
    assert face_auth.load_known_faces()==1
    assert [name for name,_encoding in face_auth.known_users]==["alice"]
    assert connection.cursor_value.closed and connection.closed


def test_face_cache_is_preserved_if_database_refresh_fails(monkeypatch):
    previous=[("alice",np.zeros(128,dtype=np.float64))]
    monkeypatch.setattr(face_auth,"known_users",previous)
    monkeypatch.setattr(face_auth,"get_connection",lambda:(_ for _ in ()).throw(RuntimeError("database unavailable")))
    with pytest.raises(RuntimeError,match="database unavailable"): face_auth.load_known_faces()
    assert face_auth.known_users is previous


def _camera_without_hardware():
    instance=camera_module.Camera.__new__(camera_module.Camera)
    instance.lock=threading.RLock()
    instance.latest_frame=[[1]]; instance.latest_frame_at=100.0
    instance.detected_results=[]; instance.last_recognition_at=0.0
    instance._last_recognition_frame_at=0.0
    instance._candidate_username=None; instance._candidate_count=0; instance._stable_username=None
    instance.is_running=True; instance.camera_available=True
    return instance


def test_camera_requires_two_distinct_fresh_single_face_matches(monkeypatch):
    instance=_camera_without_hardware()
    monkeypatch.setattr(camera_module.time,"monotonic",lambda:100.3)
    face=(0,10,10,0)
    instance._record_recognition([("alice",face)],recognized_at=100.1,frame_timestamp=100.0)
    assert instance.get_detected_user() is None
    instance._record_recognition([("alice",face)],recognized_at=100.2,frame_timestamp=100.0)
    assert instance.get_detected_user() is None
    instance._record_recognition([("alice",face)],recognized_at=100.3,frame_timestamp=100.2)
    assert instance.get_detected_user()=="alice"


def test_camera_rejects_multiple_faces_even_when_one_matches(monkeypatch):
    instance=_camera_without_hardware()
    monkeypatch.setattr(camera_module.time,"monotonic",lambda:100.3)
    face=(0,10,10,0)
    instance._record_recognition([("alice",face),(None,face)],recognized_at=100.1,frame_timestamp=100.0)
    instance._record_recognition([("alice",face),(None,face)],recognized_at=100.2,frame_timestamp=100.2)
    assert instance.get_detected_user() is None


def test_camera_rejects_unknown_and_stale_recognition(monkeypatch):
    instance=_camera_without_hardware()
    face=(0,10,10,0)
    instance._record_recognition([(None,face)],recognized_at=100.1,frame_timestamp=100.0)
    instance._record_recognition([(None,face)],recognized_at=100.2,frame_timestamp=100.2)
    assert instance.get_detected_user() is None
    instance._record_recognition([("alice",face)],recognized_at=100.4,frame_timestamp=100.4)
    instance._record_recognition([("alice",face)],recognized_at=100.6,frame_timestamp=100.6)
    monkeypatch.setattr(camera_module.time,"monotonic",lambda:103.0)
    assert instance.get_detected_user() is None


def test_camera_frame_accessor_rejects_stale_frames(monkeypatch):
    instance=_camera_without_hardware()
    monkeypatch.setattr(camera_module.time,"monotonic",lambda:100.5)
    assert instance.get_latest_frame()==[[1]]
    monkeypatch.setattr(camera_module.time,"monotonic",lambda:103.0)
    assert instance.get_latest_frame() is None
