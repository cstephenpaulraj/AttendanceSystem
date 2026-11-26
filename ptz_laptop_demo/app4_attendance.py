"""APP 4 - ATTENDANCE  (runs on the Edge AI; laptop webcam = PTZ camera)

Runs the attendance of one lecture SESSION that the college central system sent to the Edge AI
(subject, lecturer, hall, time and the list of students expected). By default it takes the session
of this hall that is on now (or the next one today).

* Looks at the primary camera (or sample photos / a video), finds every face, asks the Edge AI
  service (app 3) who it is, and marks a student after they are recognised in a few frames:
  PRESENT if the student is on the session's list, NOT_IN_LIST if the student is enrolled but the
  central system did not list them for this session.
* If the primary camera fails, it switches to the standby camera. If both cameras fail, it switches
  the session to RF READER FALLBACK: students tap their college RF cards (the demo reads card
  numbers typed on the keyboard, as a USB RF reader does, or from a file).
* Press Q (or end of photos / video) to end the session: listed students not seen become ABSENT.

Session from the central system: python app4_attendance.py                 (current session of the hall)
                                 python app4_attendance.py --session ANAT-0900
Sample photos / video:           python app4_attendance.py --source sim\\classroom
Standby camera:                  python app4_attendance.py --source fail --standby sim\\classroom.mp4
Both cameras failed (RF):        python app4_attendance.py --source fail --standby fail
Session not sent by the central system (flagged LOCAL): python app4_attendance.py --local-class MBBS1
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests

from common import config
from common.face_engine import FaceEngine, draw_label
from common.sources import CameraFailure, FrameSource

WIN = "APP 4 - Attendance (Edge AI)"
GREEN, YELLOW, RED, BLUE = (0, 190, 0), (0, 215, 255), (0, 0, 230), (220, 120, 0)


class Edge:
    def __init__(self, url):
        self.url = url
        self.s = requests.Session()

    def call(self, method, path, ok=(200,), **kw):
        r = self.s.request(method, self.url + path, timeout=10, **kw)
        if r.status_code not in ok:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = r.text
            raise RuntimeError(f"{r.status_code}: {detail}")
        return r.json()


def side_panel(height, sess, present, extra, expected, source_name, frames_per_sec, camera_name):
    panel = np.full((height, 360, 3), 245, np.uint8)
    lines = [("ATTENDANCE", 0.75, 2), (f"{sess['subject_code']}  {sess['hall']}", 0.55, 1),
             (f"Session {sess['session_id'][:30]}", 0.45, 1), (f"Lecturer {sess['lecturer_id']}", 0.45, 1),
             (f"{camera_name}: {source_name[:26]}", 0.45, 1), (f"{frames_per_sec:.1f} frames/s", 0.45, 1),
             (f"PRESENT {len(present)} / {expected}", 0.7, 2), (f"Not in list {len(extra)}", 0.5, 1)]
    y = 32
    for text, sc, th in lines:
        cv2.putText(panel, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, sc, (30, 30, 30), th, cv2.LINE_AA)
        y += 30 if sc > 0.5 else 24
    items = [(sid, n, t, (0, 120, 0)) for sid, (n, t) in present.items()] + \
            [(sid, n, t, (160, 90, 0)) for sid, (n, t) in extra.items()]
    for sid, name, t, col in items[-((height - y - 40) // 24):]:
        cv2.putText(panel, f"{t}  {sid}  {name[:16]}", (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, col, 1, cv2.LINE_AA)
        y += 24
    cv2.putText(panel, "Q = end session", (12, height - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 80, 80), 1, cv2.LINE_AA)
    return panel


def pick_session(edge, args):
    if args.local_class:
        return edge.call("POST", "/api/sessions/local", json={"class_name": args.local_class, "hall": args.hall})
    if args.session:
        rows = [s for s in edge.call("GET", "/api/v1/sessions") if s["session_id"] == args.session]
        if not rows:
            sys.exit(f"Session {args.session} not found on the Edge AI. Send it with APP 5 first.")
        return rows[0]
    if args.subject:
        today = time.strftime("%Y-%m-%d")
        rows = [s for s in edge.call("GET", "/api/v1/sessions", params={"date": today, "hall": args.hall})
                if s["subject_code"] == args.subject and s["state"] != "ENDED"]
        if not rows:
            sys.exit(f"No open {args.subject} session today in {args.hall}. Send the timetable with APP 5 first.")
        return rows[-1]
    try:
        return edge.call("GET", "/api/sessions/current", params={"hall": args.hall})
    except RuntimeError as exc:
        sys.exit(f"{exc}\nSend today's sessions with APP 5 (5_Central_System.bat), or use --local-class MBBS1.")


def run_camera(edge, engine, source, sess, args, state, camera_name):
    """Face attendance from one camera until Q / end of pictures. Raises CameraFailure if it breaks."""
    sid_session = sess["session_id"]
    t0, n_frames, fps = time.time(), 0, 0.0
    while True:
        frame, label = source.read()
        if frame is None:
            print("End of sample photos / video.")
            return
        n_frames += 1
        faces = [f for f in engine.detect(frame) if min(f[2], f[3]) >= config.MIN_FACE_PX_ATTEND]
        results = []
        if faces:
            vecs = [engine.embed(frame, f).tolist() for f in faces]
            results = edge.call("POST", "/api/identify", json={"embeddings": vecs})
        seen_now, unknown_now = set(), 0
        for f, r in zip(faces, results):
            x, y, w, h = [int(v) for v in f[:4]]
            sid = r["student_id"]
            if sid is None:
                unknown_now += 1
                colour, text = RED, f"Unknown {r['score']:.2f}"
            else:
                if sid not in seen_now:
                    state["hits"][sid] = state["hits"].get(sid, 0) + 1
                    seen_now.add(sid)
                if sid in state["present"]:
                    colour, text = GREEN, f"{sid} {r['name']}  PRESENT"
                elif sid in state["extra"]:
                    colour, text = BLUE, f"{sid} {r['name']}  NOT IN LIST"
                elif state["hits"][sid] >= args.confirm:
                    res = edge.call("POST", f"/api/sessions/{sid_session}/mark",
                                    json={"student_id": sid, "confidence": r["score"]})
                    when = time.strftime("%H:%M:%S")
                    if res["status"] == "PRESENT":
                        state["present"][sid] = (r["name"], when)
                        colour, text = GREEN, f"{sid} {r['name']}  PRESENT"
                    else:
                        state["extra"][sid] = (r["name"], when)
                        colour, text = BLUE, f"{sid} {r['name']}  NOT IN LIST"
                    print(f"  {res['status']:<12} {sid}  {r['name']}  (score {r['score']:.2f})")
                else:
                    colour, text = YELLOW, f"{sid} {r['name']} {state['hits'][sid]}/{args.confirm}"
            cv2.rectangle(frame, (x, y), (x + w, y + h), colour, 2)
            draw_label(frame, text, (x, max(y - 4, 22)), colour, 0.55, 1)
        state["unknown_max"] = max(state["unknown_max"], unknown_now)
        if n_frames % 10 == 0:
            fps = n_frames / (time.time() - t0)
        if not args.no_window:
            panel = side_panel(frame.shape[0], sess, state["present"], state["extra"], state["expected"], label,
                               fps, camera_name)
            cv2.imshow(WIN, np.hstack([frame, panel]))
            if (cv2.waitKey(1) & 0xFF) in (ord("q"), ord("Q"), 27):
                return
        if args.duration and time.time() - t0 > args.duration:
            return


def run_rf_fallback(edge, sess, args, state):
    """Both PTZ cameras failed: attendance from the hall's existing RF card readers."""
    sid_session = sess["session_id"]
    print("\n*** BOTH CAMERAS FAILED: attendance now from the RF card readers ***")
    if args.rf_taps:
        cards = [c.strip() for c in Path(args.rf_taps).read_text().splitlines() if c.strip()]
        print(f"Reading {len(cards)} card taps from {args.rf_taps}")
    else:
        print("Tap a card on the reader (or type the card number and press Enter). Empty line = end session.")
        cards = iter(lambda: input("card> ").strip(), "")
    for card in cards:
        try:
            res = edge.call("POST", f"/api/sessions/{sid_session}/rf_tap", json={"card": card})
        except RuntimeError as exc:
            print(f"  card {card}: {exc}")
            continue
        target = state["present"] if res["status"] == "PRESENT" else state["extra"]
        target[res["student_id"]] = (res["name"], time.strftime("%H:%M:%S"))
        print(f"  {res['status']:<12} {res['student_id']}  {res['name']}  (RF card {card})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", help="session ID sent by the central system (default: current session)")
    ap.add_argument("--subject", help="today's open session of this subject code in the hall, e.g. ANAT101")
    ap.add_argument("--local-class", help="start a LOCAL session for this class (not sent by the central system)")
    ap.add_argument("--hall", default=config.HALL)
    ap.add_argument("--source", default="camera",
                    help="primary camera: 'camera' (default), a webcam number, a photo, a folder, a video, or 'fail'")
    ap.add_argument("--standby", default="fail",
                    help="standby camera, same choices (default 'fail' = no standby on a laptop)")
    ap.add_argument("--rf-taps", help="file with one RF card number per line (instead of typing)")
    ap.add_argument("--hold", type=int, default=15, help="frames to look at each sample photo (default 15)")
    ap.add_argument("--confirm", type=int, default=config.CONFIRM_FRAMES,
                    help="frames a student must be recognised in before marking")
    ap.add_argument("--duration", type=float, default=0, help="end the session after N seconds (0 = press Q)")
    ap.add_argument("--no-window", action="store_true", help="run without a picture window")
    args = ap.parse_args()

    edge = Edge(config.EDGE_URL)
    try:
        health = edge.call("GET", "/api/health")
    except requests.RequestException:
        sys.exit(f"Edge AI service not reachable at {config.EDGE_URL}. Start app 3 first.")
    if health["face_templates"] == 0:
        print("Warning: the Edge AI database is empty. Enrol students with apps 1 and 2 first.")
    sess = pick_session(edge, args)
    sess = edge.call("POST", f"/api/sessions/{sess['session_id']}/start")
    sid_session = sess["session_id"]
    print(f"\n=== APP 4: ATTENDANCE ===\nSession {sid_session}  {sess['subject_code']} {sess.get('subject_name') or ''}\n"
          f"Lecturer {sess['lecturer_id']}  hall {sess['hall']}  {sess['date']} {sess['start_time']}-{sess['end_time']}"
          f"  ({'sent by the central system' if sess['origin'] == 'CENTRAL' else 'LOCAL: not sent by the central system'})\n"
          f"Students expected: {sess['expected']}\nPress Q in the picture window to end the session.\n")

    state = {"hits": {}, "present": {}, "extra": {}, "unknown_max": 0, "expected": sess["expected"]}
    engine = None
    cameras = [("Primary PTZ", args.source, "CAMERA"), ("Standby PTZ", args.standby, "STANDBY_CAMERA")]
    done = False
    try:
        for camera_name, src, mode in cameras:
            try:
                source = FrameSource(src, hold=args.hold)
            except CameraFailure as exc:
                print(f"{camera_name} camera failed: {exc}")
                continue
            if engine is None:
                engine = FaceEngine(need_recogniser=True)
            edge.call("POST", f"/api/sessions/{sid_session}/mode",
                      json={"mode": mode, "reason": "" if mode == "CAMERA" else "primary camera failed"})
            print(f"Using the {camera_name} camera ({source.name}).")
            try:
                run_camera(edge, engine, source, sess, args, state, camera_name)
                done = True
                break
            except CameraFailure as exc:
                print(f"{camera_name} camera failed during the session: {exc}")
            finally:
                source.release()
        if not done:
            edge.call("POST", f"/api/sessions/{sid_session}/mode",
                      json={"mode": "RF_FALLBACK", "reason": "primary and standby PTZ cameras failed"})
            run_rf_fallback(edge, sess, args, state)
    finally:
        if not args.no_window:
            cv2.destroyAllWindows()

    rep = edge.call("POST", f"/api/sessions/{sid_session}/end", json={"unknown_faces": state["unknown_max"]})
    print(f"\nSession {sid_session} ended ({rep['session']['mode']}).")
    for rec in rep["records"]:
        print(f"  {rec['status']:<12} {rec['method']:<6} {rec['student_id']:<10} {rec['name'] or ''}")
    c = rep["counts"]
    print(f"\nPRESENT {c['PRESENT']}   ABSENT {c['ABSENT']}   NOT_IN_LIST {c['NOT_IN_LIST']}   "
          f"unknown faces (most at once) {state['unknown_max']}\n"
          f"Lecturer override (official duty) open until {rep['override_open_until']}: {config.EDGE_URL}/lecturer\n"
          f"Central system pull: {config.EDGE_URL}/api/v1/sessions/{sid_session}/attendance")


if __name__ == "__main__":
    main()
