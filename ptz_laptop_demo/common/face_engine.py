"""Face engine shared by all apps: OpenCV YuNet (detect) + SFace (recognise), CPU only."""
import sys

import cv2
import numpy as np

from . import config


class FaceEngine:
    """Detects faces, checks photo quality, aligns faces to 112x112 and makes 128-number face codes."""

    def __init__(self, need_recogniser=True, score_threshold=None):
        for model in ([config.DETECTOR_MODEL] + ([config.RECOGNISER_MODEL] if need_recogniser else [])):
            if not model.exists() or model.stat().st_size < 100_000:
                sys.exit(f"\nModel file missing: {model}\nRun setup_windows.bat (or: python tools\\download_models.py) first.\n")
        self.detector = cv2.FaceDetectorYN.create(
            str(config.DETECTOR_MODEL), "", (320, 320),
            score_threshold if score_threshold is not None else config.DETECTOR_SCORE, 0.3, 5000)
        self.recogniser = cv2.FaceRecognizerSF.create(str(config.RECOGNISER_MODEL), "") if need_recogniser else None

    # ---------------------------------------------------------------- detect
    def detect(self, image):
        """Return an array of faces, one row each: x, y, w, h, 5 landmarks (10 numbers), score."""
        h, w = image.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(image)
        if faces is None:
            return np.empty((0, 15), dtype=np.float32)
        return faces

    # ---------------------------------------------------------------- quality
    @staticmethod
    def quality(image, face):
        """Simple quality figures for one face: size, sharpness, brightness, detector score."""
        x, y, w, h = [int(v) for v in face[:4]]
        x0, y0 = max(x, 0), max(y, 0)
        crop = image[y0:y0 + max(h, 1), x0:x0 + max(w, 1)]
        if crop.size == 0:
            return {"size": 0, "sharpness": 0.0, "brightness": 0.0, "score": float(face[14])}
        # judge sharpness on the face resized to 112 x 112, so big and small faces are treated alike
        grey = cv2.cvtColor(cv2.resize(crop, (112, 112), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        return {
            "size": int(min(w, h)),
            "sharpness": float(cv2.Laplacian(grey, cv2.CV_64F).var()),
            "brightness": float(grey.mean()),
            "score": float(face[14]),
        }

    @staticmethod
    def quality_problem(q):
        """Return a short reason if the enrolment photo is not good enough, else None."""
        if q["size"] < config.MIN_FACE_PX_ENROL:
            return "face too small - come closer"
        if q["brightness"] < config.MIN_BRIGHTNESS:
            return "too dark"
        if q["brightness"] > config.MAX_BRIGHTNESS:
            return "too bright"
        if q["sharpness"] < config.MIN_SHARPNESS:
            return "blurred - hold still"
        if q["score"] < config.MIN_DETECTION_SCORE:
            return "face not clear - look at the camera"
        return None

    # ---------------------------------------------------------------- recognise
    def align(self, image, face):
        """Standard database image: the face rotated/scaled to a fixed 112x112 crop."""
        return self.recogniser.alignCrop(image, face)

    def embed_aligned(self, aligned):
        """Face code (embedding) of an aligned 112x112 face, scaled to length 1."""
        feat = self.recogniser.feature(aligned).flatten().astype(np.float32)
        return feat / (np.linalg.norm(feat) + 1e-9)

    def embed(self, image, face):
        return self.embed_aligned(self.align(image, face))


def largest_face(faces):
    if len(faces) == 0:
        return None
    return faces[int(np.argmax(faces[:, 2] * faces[:, 3]))]


def open_camera(index=None, width=None, height=None):
    """Open the laptop webcam (it plays the PTZ camera). Uses DirectShow on Windows for a fast start."""
    index = config.CAMERA_INDEX if index is None else index
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(index)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        sys.exit(f"Could not open camera {index}. Close other apps using the webcam (Teams, Zoom, "
                 f"the other demo app) or try --camera 1.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width or config.CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height or config.CAMERA_HEIGHT)
    return cap


def draw_label(img, text, org, colour, scale=0.6, thickness=2):
    """Text with a filled background so it can be read on any picture."""
    (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    x, y = int(org[0]), int(org[1])
    cv2.rectangle(img, (x, y - th - base - 4), (x + tw + 6, y + 2), colour, -1)
    cv2.putText(img, text, (x + 3, y - base), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0) if sum(colour) > 380 else (255, 255, 255), thickness, cv2.LINE_AA)
