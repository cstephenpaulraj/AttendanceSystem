"""Picture sources: the live laptop webcam OR sample photos / videos (simulation)."""
import time
from pathlib import Path

import cv2

from .face_engine import open_camera

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".wmv"}


def list_images(folder):
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXT)


class FrameSource:
    """Gives frames one by one from:
       * "camera" or a number  -> live webcam (the PTZ camera stand-in)
       * a picture file        -> that picture, repeated `hold` times
       * a folder of pictures  -> each picture in turn, each repeated `hold` times
       * a video file          -> its frames
    """

    def __init__(self, source="camera", hold=15, fps=10):
        self.hold, self.delay = max(1, hold), 1.0 / fps
        self.cap, self.images, self.live = None, [], False
        src = str(source)
        if src.lower() == "camera" or src.isdigit():
            self.cap = open_camera(0 if src.lower() == "camera" else int(src))
            self.live, self.name = True, "live webcam"
        else:
            p = Path(src)
            if p.is_dir():
                self.images = list_images(p)
                if not self.images:
                    raise SystemExit(f"No pictures found in folder {p}")
                self.name = f"{len(self.images)} sample photos in {p}"
            elif p.suffix.lower() in IMAGE_EXT:
                self.images, self.name = [p], f"sample photo {p.name}"
            elif p.suffix.lower() in VIDEO_EXT:
                self.cap, self.name = cv2.VideoCapture(str(p)), f"sample video {p.name}"
                if not self.cap.isOpened():
                    raise SystemExit(f"Cannot open video {p}")
            else:
                raise SystemExit(f"Source not found or not supported: {src}")
        self._i = 0
        self._cache = None

    def read(self):
        """Return (frame, label) or (None, None) at the end of the photos / video."""
        if self.cap is not None:
            ok, frame = self.cap.read()
            if not self.live:
                time.sleep(self.delay)
            return (frame, self.name) if ok else (None, None)
        idx = self._i // self.hold
        if idx >= len(self.images):
            return None, None
        if self._i % self.hold == 0:
            self._cache = cv2.imread(str(self.images[idx]))
            if self._cache is None:
                raise SystemExit(f"Cannot read picture {self.images[idx]}")
        self._i += 1
        time.sleep(self.delay)
        return self._cache.copy(), self.images[idx].name

    def release(self):
        if self.cap is not None:
            self.cap.release()
