"""Shared pytest setup for the AJARVIS application directory."""

import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


# Hosted CI has no webcam or native dlib/OpenCV stack. Keep imports testable
# without claiming to test hardware; focused tests monkeypatch every device call.
import os
import types

os.environ["SECRET_KEY"] = "test-only-secret-key-for-automated-tests-123456"


def _install_stub(name, attributes):
    try:
        __import__(name)
        return
    except ModuleNotFoundError:
        module = types.ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        sys.modules[name] = module


class _UnavailableCapture:
    def isOpened(self):
        return False

    def read(self):
        return False, None

    def release(self):
        return None


_install_stub("cv2", {
    "COLOR_BGR2RGB": 4,
    "FILLED": -1,
    "FONT_HERSHEY_DUPLEX": 0,
    "FONT_HERSHEY_SIMPLEX": 0,
    "VideoCapture": lambda *_args, **_kwargs: _UnavailableCapture(),
})
_install_stub("face_recognition", {
    "face_locations": lambda _image: [],
    "face_encodings": lambda _image, _locations: [],
    "face_distance": lambda _known, _candidate: [],
})
_install_stub("pyautogui", {
    "press": lambda *_args, **_kwargs: None,
    "screenshot": lambda *_args, **_kwargs: None,
})
