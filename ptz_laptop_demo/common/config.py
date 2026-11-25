"""Shared settings for the four PTZ laptop demo apps.

Every value can be overridden with an environment variable of the same name,
for example:  set EDGE_PORT=9002
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent      # ...\ptz_laptop_demo
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"


def _env(name, default, cast=str):
    value = os.environ.get(name)
    return cast(value) if value not in (None, "") else default


# ---- Face models (OpenCV Zoo: YuNet = MIT licence, SFace = Apache-2.0) ----
DETECTOR_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
RECOGNISER_MODEL = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

# ---- Network (everything runs on this laptop, so 127.0.0.1) ----
OFFICE_HOST = _env("OFFICE_HOST", "127.0.0.1")
OFFICE_PORT = _env("OFFICE_PORT", 8001, int)
EDGE_HOST = _env("EDGE_HOST", "127.0.0.1")
EDGE_PORT = _env("EDGE_PORT", 8002, int)
OFFICE_URL = _env("OFFICE_URL", f"http://{OFFICE_HOST}:{OFFICE_PORT}")
EDGE_URL = _env("EDGE_URL", f"http://{EDGE_HOST}:{EDGE_PORT}")
# Shared key the Enrolment Converter must present to push faces to the Edge AI.
EDGE_PUSH_KEY = _env("EDGE_PUSH_KEY", "ptz-demo-key")

# ---- Camera (the laptop webcam plays the PTZ camera) ----
CAMERA_INDEX = _env("CAMERA_INDEX", 0, int)
CAMERA_WIDTH = _env("CAMERA_WIDTH", 1280, int)
CAMERA_HEIGHT = _env("CAMERA_HEIGHT", 720, int)

# ---- Enrolment ----
PHOTOS_PER_STUDENT = _env("PHOTOS_PER_STUDENT", 5, int)
MIN_GOOD_PHOTOS = _env("MIN_GOOD_PHOTOS", 3, int)
MIN_FACE_PX_ENROL = _env("MIN_FACE_PX_ENROL", 90, int)      # face width in pixels
MIN_SHARPNESS = _env("MIN_SHARPNESS", 60.0, float)           # Laplacian variance of the 112x112 face
MIN_BRIGHTNESS = _env("MIN_BRIGHTNESS", 50.0, float)
MAX_BRIGHTNESS = _env("MAX_BRIGHTNESS", 215.0, float)
MIN_DETECTION_SCORE = _env("MIN_DETECTION_SCORE", 0.85, float)
SAME_PERSON_MIN = _env("SAME_PERSON_MIN", 0.45, float)       # photos of one student must agree
DUPLICATE_THRESHOLD = _env("DUPLICATE_THRESHOLD", 0.55, float)  # already enrolled under another ID?

# ---- Attendance ----
MATCH_THRESHOLD = _env("MATCH_THRESHOLD", 0.40, float)      # SFace cosine; OpenCV suggests 0.363
CONFIRM_FRAMES = _env("CONFIRM_FRAMES", 3, int)             # seen in N frames before marking present
MIN_FACE_PX_ATTEND = _env("MIN_FACE_PX_ATTEND", 40, int)
DETECTOR_SCORE = _env("DETECTOR_SCORE", 0.80, float)
