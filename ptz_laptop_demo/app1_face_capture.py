"""APP 1 - FACE CAPTURE  (plays the enrolment app on the DEDICATED COLLEGE PHONE; laptop webcam = its camera)

Enrolment is done only on a registered college phone and only under the supervision of a college
staff member, who logs in with staff ID + PIN and confirms for every student that the student's ID
card matches the person in front of the camera. Students never use their own phones.
The photos are sent to the Enrolment Converter on the office PC (app 2).

Live webcam (default):
    python app1_face_capture.py
Sample photos of ONE student (folder of pictures):
    python app1_face_capture.py --photos sim\\enrol\\S001_Asha --id S001 --name "Asha" --class MBBS1 --staff STAFF01 --pin 1111 --id-card-checked
Sample photos of MANY students (one sub-folder per student, named <ID>_<Name>):
    python app1_face_capture.py --batch sim\\enrol --class MBBS1 --staff STAFF01 --pin 1111 --id-card-checked
Send photos that were saved because the office PC was not reachable:
    python app1_face_capture.py --resend --staff STAFF01 --pin 1111
"""
import argparse
import getpass
import re
import shutil
import sys
import time
from pathlib import Path

import cv2
import requests

from common import config
from common.face_engine import FaceEngine, draw_label, open_camera
from common.sources import list_images

OUTBOX = config.DATA_DIR / "capture_outbox"
WIN = "APP 1 - Face capture (PTZ camera = laptop webcam)"


STAFF = {"id": None, "pin": None, "device": config.ENROLMENT_DEVICE_ID}


def staff_login(args):
    """The supervising college staff member logs in once per enrolment sitting."""
    sid = (args.staff or input("Supervising staff ID (e.g. STAFF01): ").strip()).upper()
    pin = args.pin or getpass.getpass("Staff PIN: ")
    if config.STAFF_ACCOUNTS.get(sid) != pin:
        sys.exit("Wrong staff ID or PIN. Enrolment must be supervised by college staff.")
    STAFF.update(id=sid, pin=pin, device=(args.device or config.ENROLMENT_DEVICE_ID).upper())
    print(f"Staff {sid} logged in on enrolment phone {STAFF['device']}.")


def id_card_confirmed(args, student_id, name):
    if args.id_card_checked:
        return True
    ans = input(f"   Staff: does {student_id} {name}'s college ID card match the student in front of you? (Y/N): ")
    return ans.strip().lower().startswith("y")


def send_to_office(student_id, name, class_name, jpgs):
    """Send the photos (JPEG bytes) to the office PC. Returns the converter's answer or None."""
    files = [("photos", (f"photo_{i:02d}.jpg", b, "image/jpeg")) for i, b in enumerate(jpgs, 1)]
    try:
        r = requests.post(f"{config.OFFICE_URL}/api/upload", files=files, timeout=60,
                          data={"student_id": student_id, "name": name, "class_name": class_name,
                                "staff_id": STAFF["id"], "staff_pin": STAFF["pin"], "device_id": STAFF["device"],
                                "id_card_checked": "true"})
    except requests.RequestException:
        return None
    if r.status_code != 200:
        print(f"   Office PC refused the upload: {r.text}")
        return {"status": "REFUSED", "accepted": 0, "rejected": []}
    return r.json()


def report(res, student_id, name, class_name, jpgs):
    if res is None:                                   # office not reachable: keep for --resend
        folder = OUTBOX / f"{student_id}__{name}__{class_name}"
        folder.mkdir(parents=True, exist_ok=True)
        for i, b in enumerate(jpgs, 1):
            (folder / f"photo_{i:02d}.jpg").write_bytes(b)
        print(f"   Office PC ({config.OFFICE_URL}) not reachable. Photos kept in {folder}.\n"
              f"   Start app 2, then run:  python app1_face_capture.py --resend")
        return False
    print(f"   Office PC: {res.get('accepted', 0)} of {len(jpgs)} photos good -> {res['status']}")
    for r in res.get("rejected", []):
        print(f"      rejected {r['photo']}: {r['reason']}")
    return res["status"].startswith(("STORED", "WAITING"))


# =====================================================================  live webcam
def capture_live(engine, student_id, name, class_name, n_photos, camera, show_window=True):
    cap = open_camera(camera)
    shots, auto, last_shot = [], False, 0.0
    print("   SPACE = take photo   A = auto-capture on/off   ESC = cancel")
    try:
        while len(shots) < n_photos:
            ok, frame = cap.read()
            if not ok:
                print("   Camera stopped giving pictures.")
                return None
            faces = engine.detect(frame)
            view = frame.copy()
            if len(faces) == 0:
                problem = "no face - look at the camera"
            elif len(faces) > 1:
                problem = "only one person in front of the camera"
            else:
                problem = engine.quality_problem(engine.quality(frame, faces[0]))
            for f in faces:
                x, y, w, h = [int(v) for v in f[:4]]
                cv2.rectangle(view, (x, y), (x + w, y + h), (0, 200, 0) if not problem else (0, 0, 230), 2)
            draw_label(view, f"{student_id}  {name}  ({class_name})", (10, 35), (255, 255, 255), 0.8)
            draw_label(view, f"Photo {len(shots)}/{n_photos}   " + ("READY - press SPACE" if not problem else problem),
                       (10, 75), (0, 200, 0) if not problem else (0, 0, 230), 0.7)
            draw_label(view, f"Auto-capture {'ON' if auto else 'OFF'} (A)   Turn your head slightly between photos   ESC = cancel",
                       (10, view.shape[0] - 15), (40, 40, 40), 0.55, 1)
            cv2.imshow(WIN, view)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                return None
            if key in (ord("a"), ord("A")):
                auto = not auto
            take = key == 32 or (auto and time.time() - last_shot > 1.0)
            if take and not problem:
                shots.append(cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes())
                last_shot = time.time()
                flash = view.copy()
                cv2.rectangle(flash, (0, 0), (flash.shape[1], flash.shape[0]), (255, 255, 255), 25)
                cv2.imshow(WIN, flash)
                cv2.waitKey(150)
        return shots
    finally:
        cap.release()


def ask(prompt, default=""):
    v = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return v or default


def live_mode(args, engine):
    class_name = args.class_name or ""
    print("\n=== APP 1: FACE CAPTURE on the college enrolment phone (live webcam) ===  Leave Student ID empty to quit.\n")
    while True:
        student_id = args.id or ask("Student ID (e.g. S001)")
        if not student_id:
            break
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,32}", student_id):
            print("   Use letters, digits, - and _ only.")
            continue
        name = args.name or ask("Student name")
        class_name = args.class_name or ask("Class", class_name or "MBBS1")
        if not id_card_confirmed(args, student_id, name):
            print("   ID card not confirmed: enrolment of this student stopped.\n")
            continue
        shots = capture_live(engine, student_id, name, class_name, args.count, args.camera)
        cv2.destroyAllWindows()
        if not shots:
            print("   Cancelled.\n")
        else:
            print(f"   Sending {len(shots)} photos to the office PC ...")
            report(send_to_office(student_id, name, class_name, shots), student_id, name, class_name, shots)
            print()
        if args.id:          # single student given on the command line
            break


# =====================================================================  sample photos
def read_photos(folder, engine, show_window):
    """Read sample photos; show each with its face box (simulates the capture screen)."""
    jpgs = []
    for p in list_images(folder):
        img = cv2.imread(str(p))
        if img is None:
            print(f"   skipped {p.name}: not a picture")
            continue
        faces = engine.detect(img)
        if len(faces) != 1:
            print(f"   note {p.name}: {len(faces)} faces found (office PC will check)")
        if show_window:
            view = img.copy()
            for f in faces:
                x, y, w, h = [int(v) for v in f[:4]]
                cv2.rectangle(view, (x, y), (x + w, y + h), (0, 200, 0), 2)
            draw_label(view, f"Sample photo {p.name}", (10, 30), (255, 255, 255), 0.7)
            cv2.imshow(WIN, view)
            cv2.waitKey(400)
        jpgs.append(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes())
    return jpgs


def split_folder_name(folder):
    """'S001_Asha_Kumar' -> ('S001', 'Asha Kumar')."""
    sid, _, rest = Path(folder).name.partition("_")
    return sid, rest.replace("_", " ").strip() or sid


def photo_mode(args, engine, folders):
    ok_count = 0
    for folder in folders:
        sid, nm = split_folder_name(folder)
        sid = args.id if (args.id and len(folders) == 1) else sid
        nm = args.name if (args.name and len(folders) == 1) else nm
        cls = args.class_name or "MBBS1"
        print(f"\n-> {sid}  {nm}  ({cls})  from {folder}")
        if not id_card_confirmed(args, sid, nm):
            print("   ID card not confirmed: skipped")
            continue
        jpgs = read_photos(folder, engine, not args.no_window)
        if not jpgs:
            print("   no photos")
            continue
        ok_count += bool(report(send_to_office(sid, nm, cls, jpgs), sid, nm, cls, jpgs))
    if not args.no_window:
        cv2.destroyAllWindows()
    print(f"\nDone: {ok_count} of {len(folders)} students accepted by the office PC.")


def resend():
    folders = sorted(p for p in OUTBOX.iterdir() if p.is_dir()) if OUTBOX.exists() else []
    if not folders:
        print("Nothing waiting to be sent.")
    for folder in folders:
        sid, name, cls = folder.name.split("__")
        jpgs = [p.read_bytes() for p in list_images(folder)]
        print(f"-> {sid} {name}")
        res = send_to_office(sid, name, cls, jpgs)
        if res is None:
            print("   Office PC still not reachable.")
            return
        report(res, sid, name, cls, jpgs)
        shutil.rmtree(folder)            # sent: delete the local copy


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", type=int, default=config.CAMERA_INDEX, help="webcam number (default 0)")
    ap.add_argument("--photos", help="folder with sample photos of ONE student")
    ap.add_argument("--batch", help="folder with one sub-folder <ID>_<Name> per student")
    ap.add_argument("--id", help="student ID")
    ap.add_argument("--name", help="student name")
    ap.add_argument("--class", dest="class_name", help="class, e.g. MBBS1")
    ap.add_argument("--count", type=int, default=config.PHOTOS_PER_STUDENT, help="photos per student (live mode)")
    ap.add_argument("--resend", action="store_true", help="send photos kept while the office PC was offline")
    ap.add_argument("--staff", help="supervising college staff ID (asked if not given)")
    ap.add_argument("--pin", help="staff PIN (asked if not given)")
    ap.add_argument("--device", help=f"enrolment phone ID (default {config.ENROLMENT_DEVICE_ID})")
    ap.add_argument("--id-card-checked", action="store_true",
                    help="staff confirms the ID cards of all students in this batch were checked")
    ap.add_argument("--no-window", action="store_true", help="do not show picture windows (sample photo modes)")
    args = ap.parse_args()

    staff_login(args)
    if args.resend:
        return resend()
    engine = FaceEngine(need_recogniser=False, score_threshold=0.6)
    if args.photos:
        return photo_mode(args, engine, [Path(args.photos)])
    if args.batch:
        folders = sorted(p for p in Path(args.batch).iterdir() if p.is_dir())
        if not folders:
            sys.exit(f"No student folders in {args.batch}")
        return photo_mode(args, engine, folders)
    live_mode(args, engine)


if __name__ == "__main__":
    main()
