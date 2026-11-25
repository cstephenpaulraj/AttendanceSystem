"""Check (and if missing, download) the two free face models (about 39 MB) in ..\\models.

The models are already included in the GitHub folder; this script verifies them and downloads
them again from the OpenCV Model Zoo only if they are missing or damaged.

YuNet face detector  - MIT licence
SFace face recogniser - Apache-2.0 licence
Both allow commercial use. Run once:  python tools\\download_models.py
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent / "models"
FILES = {
    "face_detection_yunet_2023mar.onnx": "models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": "models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}
# SHA-256 of the official OpenCV Zoo files - a download is only accepted if it matches
SHA256 = {
    "face_detection_yunet_2023mar.onnx": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    "face_recognition_sface_2021dec.onnx": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
MIRRORS = [
    "https://github.com/opencv/opencv_zoo/raw/main/{path}",
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/{path}",
    "https://huggingface.co/opencv/{folder}/resolve/main/{name}",
]


def main():
    MODELS.mkdir(exist_ok=True)
    ok = True
    for name, path in FILES.items():
        target = MODELS / name
        if target.exists() and sha256(target) == SHA256[name]:
            print(f"[ok] {name} present and verified ({target.stat().st_size / 1e6:.1f} MB)")
            continue
        folder = path.split("/")[1]
        for mirror in MIRRORS:
            url = mirror.format(path=path, folder=folder, name=name)
            try:
                print(f"Downloading {name} ...\n   from {url}")
                tmp = target.with_suffix(".part")
                urllib.request.urlretrieve(url, tmp)
                if sha256(tmp) != SHA256[name]:        # an LFS pointer, error page or wrong file
                    tmp.unlink()
                    raise IOError("checksum does not match the official model")
                tmp.replace(target)
                print(f"[ok] {name} ({target.stat().st_size / 1e6:.1f} MB)")
                break
            except Exception as exc:  # try the next mirror
                print(f"   failed: {exc}")
        else:
            ok = False
            print(f"[!!] Could not download {name}. Download it in a browser from\n"
                  f"     https://github.com/opencv/opencv_zoo/tree/main/{path.rsplit('/', 1)[0]}\n"
                  f"     and save it in {MODELS}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
