"""APP 4 - ATTENDANCE  (runs on the Edge AI; laptop webcam = PTZ camera)

Starts an attendance session for a class, looks at the camera (or sample photos / a video),
finds every face, asks the Edge AI service (app 3) who it is, and marks a student PRESENT after
they are recognised in a few frames. Press Q to end the session: unseen students become ABSENT.

Live webcam:          python app4_attendance.py --class MBBS1
Sample photos folder: python app4_attendance.py --class MBBS1 --source sim\\classroom
One group photo:      python app4_attendance.py --class MBBS1 --source group.jpg
Video file:           python app4_attendance.py --class MBBS1 --source sim\\classroom.mp4
"""
import argparse
import sys
import time

import cv2
import numpy as np
import requests

from common import config
from common.face_engine import FaceEngine, draw_label
from common.sources import FrameSource

WIN = "APP 4 - Attendance (Edge AI)"
GREEN, YELLOW, RED = (0, 190, 0), (0, 215, 255), (0, 0, 230)


class Edge:
    def __init__(self, url):
        self.url = url
        self.s = requests.Session()

    def call(self, method, path, **kw):
        r = self.s.request(method, self.url + path, timeout=10, **kw)
        r.raise_for_status()
        return r.json()


def side_panel(height, cls, session, present, enrolled, source_name, frames_per_sec):
    panel = np.full((height, 330, 3), 245, np.uint8)
    lines = [("ATTENDANCE", 0.75, 2), (f"Class {cls}", 0.6, 1), (f"Session {session}", 0.45, 1),
             (f"Source: {source_name[:34]}", 0.45, 1), (f"{frames_per_sec:.1f} frames/s", 0.45, 1),
             (f"PRESENT {len(present)} / {enrolled}", 0.7, 2)]
    y = 32
    for text, sc, th in lines:
        cv2.putText(panel, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, sc, (30, 30, 30), th, cv2.LINE_AA)
        y += 30 if sc > 0.5 else 24
    for sid, (name, t) in list(present.items())[-((height - y - 40) // 24):]:
        cv2.putText(panel, f"{t}  {sid}  {name[:16]}", (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 120, 0), 1, cv2.LINE_AA)
        y += 24
    cv2.putText(panel, "Q = end session", (12, height - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 80, 80), 1, cv2.LINE_AA)
    return panel


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--class", dest="class_name", help="class taking attendance, e.g. MBBS1")
    ap.add_argument("--hall", default="Laptop hall")
    ap.add_argument("--source", default="camera",
                    help="'camera' (default), a webcam number, a photo, a folder of photos, or a video file")
    ap.add_argument("--hold", type=int, default=15, help="frames to look at each sample photo (default 15)")
    ap.add_argument("--confirm", type=int, default=config.CONFIRM_FRAMES,
                    help="frames a student must be recognised in before marking PRESENT")
    ap.add_argument("--duration", type=float, default=0, help="end the session after N seconds (0 = press Q)")
    ap.add_argument("--no-window", action="store_true", help="run without a picture window")
    args = ap.parse_args()

    cls = (args.class_name or input("Class for this attendance session (e.g. MBBS1): ").strip() or "MBBS1").upper()
    edge = Edge(config.EDGE_URL)
    try:
        health = edge.call("GET", "/api/health")
    except requests.RequestException:
        sys.exit(f"Edge AI service not reachable at {config.EDGE_URL}. Start app 3 first.")
    if health["face_templates"] == 0:
        print("Warning: the Edge AI database is empty. Enrol students with apps 1 and 2 first.")
    sess = edge.call("POST", "/api/sessions", json={"class_name": cls, "hall": args.hall})
    sid_session = sess["session_id"]
    print(f"\n=== APP 4: ATTENDANCE ===\nSession {sid_session}  class {cls}  enrolled {sess['enrolled']}\n"
          f"Press Q in the picture window to end the session.\n")

    engine = FaceEngine(need_recogniser=True)
    source = FrameSource(args.source, hold=args.hold)
    hits, present = {}, {}                 # student_id -> frames recognised; student_id -> (name, time)
    t0, n_frames, fps = time.time(), 0, 0.0
    try:
        while True:
            frame, label = source.read()
            if frame is None:
                print("End of sample photos / video.")
                break
            n_frames += 1
            faces = [f for f in engine.detect(frame) if min(f[2], f[3]) >= config.MIN_FACE_PX_ATTEND]
            results = []
            if faces:
                vecs = [engine.embed(frame, f).tolist() for f in faces]
                results = edge.call("POST", "/api/identify", json={"embeddings": vecs})
            seen_now = set()
            for f, r in zip(faces, results):
                x, y, w, h = [int(v) for v in f[:4]]
                sid = r["student_id"]
                if sid is None:
                    colour, text = RED, f"Unknown {r['score']:.2f}"
                else:
                    if sid not in seen_now:
                        hits[sid] = hits.get(sid, 0) + 1
                        seen_now.add(sid)
                    if sid in present:
                        colour, text = GREEN, f"{sid} {r['name']}  PRESENT"
                    elif r["class_name"] != cls:
                        colour, text = YELLOW, f"{sid} {r['name']} (class {r['class_name']})"
                    elif hits[sid] >= args.confirm:
                        edge.call("POST", f"/api/sessions/{sid_session}/mark",
                                  json={"student_id": sid, "confidence": r["score"]})
                        present[sid] = (r["name"], time.strftime("%H:%M:%S"))
                        print(f"  PRESENT  {sid}  {r['name']}  (score {r['score']:.2f})")
                        colour, text = GREEN, f"{sid} {r['name']}  PRESENT"
                    else:
                        colour, text = YELLOW, f"{sid} {r['name']} {hits[sid]}/{args.confirm}"
                cv2.rectangle(frame, (x, y), (x + w, y + h), colour, 2)
                draw_label(frame, text, (x, max(y - 4, 22)), colour, 0.55, 1)
            if n_frames % 10 == 0:
                fps = n_frames / (time.time() - t0)
            if not args.no_window:
                panel = side_panel(frame.shape[0], cls, sid_session, present, sess["enrolled"], label, fps)
                cv2.imshow(WIN, np.hstack([frame, panel]))
                if (cv2.waitKey(1) & 0xFF) in (ord("q"), ord("Q"), 27):
                    break
            if args.duration and time.time() - t0 > args.duration:
                break
    finally:
        source.release()
        if not args.no_window:
            cv2.destroyAllWindows()

    rep = edge.call("POST", f"/api/sessions/{sid_session}/end")
    print(f"\nSession {sid_session} ended. Class {cls}.")
    for rec in rep["records"]:
        print(f"  {rec['status']:<8} {rec['student_id']:<10} {rec['name'] or ''}")
    p = sum(r["status"] == "PRESENT" for r in rep["records"])
    print(f"\nPRESENT {p}   ABSENT {len(rep['records']) - p}\n"
          f"College pull API: {config.EDGE_URL}/api/attendance?session_id={sid_session}")


if __name__ == "__main__":
    main()
