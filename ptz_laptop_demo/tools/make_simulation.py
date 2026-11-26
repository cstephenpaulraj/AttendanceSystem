"""PHOTO SIMULATION - make test pictures for apps 1 and 4 without a classroom.

Input: a folder with one sub-folder per person, named <ID>_<Name>, holding 1 to 10 clear photos
of that person (use your own photos or photos of people who agreed to it). Folders whose name starts
with UNKNOWN are strangers: they appear in the classroom pictures but are never enrolled.

    sim\\people\\S001_Asha\\*.jpg
    sim\\people\\S002_Ravi\\*.jpg
    sim\\people\\UNKNOWN_visitor\\*.jpg

Run:
    python tools\\make_simulation.py --people sim\\people --out sim

It synthesises:
  sim\\enrol\\<ID>_<Name>\\shot_01..05.jpg  enrolment shots (small turns, light changes, zoom)  -> app 1
  sim\\classroom\\scene_01..NN.jpg         classroom pictures with 5-6 people seated          -> app 4
  sim\\classroom.mp4                       a video that pans across a wide classroom, stopping
                                          at "taught points" like the PTZ camera does         -> app 4
  sim\\expected.txt                        who is in each scene (to check the result)
  sim\\college_students.csv                the college student list with RF card numbers     -> app 5
  sim\\timetable.csv                       3 lecture sessions of today with their students     -> app 5
  sim\\rf_taps.txt                         RF card taps for the "both cameras failed" test     -> app 4
If a person has 2 or more photos, the LAST photo is kept out of enrolment and used only for the
classroom pictures, so recognition is tested on a photo the system has never seen.
"""
import argparse
import random
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.face_engine import FaceEngine, largest_face  # noqa: E402
from common.sources import list_images  # noqa: E402


# --------------------------------------------------------------------------- picture helpers
def rotate(img, angle, scale=1.0):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    return cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)


def light(img, gain, bias=0):
    return np.clip(img.astype(np.float32) * gain + bias, 0, 255).astype(np.uint8)


def crop_around_face(img, face, left=0.6, right=0.6, top=0.7, bottom=1.1):
    x, y, w, h = face[:4]
    x0, y0 = int(max(0, x - left * w)), int(max(0, y - top * h))
    x1, y1 = int(min(img.shape[1], x + w + right * w)), int(min(img.shape[0], y + h + bottom * h))
    return img[y0:y1, x0:x1].copy(), (x - x0, y - y0, w, h)


def enrolment_shots(engine, photos, n=5):
    """n portrait shots (face well inside the frame) synthesised from the enrolment photos."""
    variants = [(0, 1.0, 1.0), (-7, 1.0, 1.08), (7, 1.0, 0.92), (-3, 1.04, 1.15), (4, 0.97, 0.85),
                (-9, 1.0, 1.0), (9, 1.02, 1.1)]
    shots = []
    for i in range(n):
        img = photos[i % len(photos)]
        face = largest_face(engine.detect(img))
        crop, _ = crop_around_face(img, face, 1.2, 1.2, 1.0, 1.6)
        if crop.shape[1] > 640:                       # shrink big photos, never enlarge small ones
            crop = cv2.resize(crop, (640, int(crop.shape[0] * 640 / crop.shape[1])), interpolation=cv2.INTER_AREA)
        ang, sc, gain = variants[i % len(variants)]
        shots.append(light(rotate(crop, ang, sc), gain))
    return shots


def classroom_background(w, h, seed):
    rnd = random.Random(seed)
    bg = np.zeros((h, w, 3), np.uint8)
    wall = np.array([rnd.randint(175, 205), rnd.randint(190, 215), rnd.randint(200, 225)], np.float32)
    for yy in range(h):                                   # wall with a soft light gradient
        bg[yy, :] = np.clip(wall * (0.85 + 0.25 * yy / h), 0, 255)
    cv2.rectangle(bg, (0, int(h * 0.72)), (w, h), (60, 85, 120), -1)          # floor
    for i in range(0, w, 260):                                                  # windows
        cv2.rectangle(bg, (i + 40, int(h * 0.06)), (i + 170, int(h * 0.30)), (235, 225, 205), -1)
        cv2.rectangle(bg, (i + 40, int(h * 0.06)), (i + 170, int(h * 0.30)), (120, 120, 120), 3)
    noise = np.random.default_rng(seed).normal(0, 4, bg.shape)
    return np.clip(bg + noise, 0, 255).astype(np.uint8)


def paste_person(canvas, head, face_box, cx, face_top, face_w):
    """Paste a head-and-shoulders crop so that its face is face_w pixels wide at (cx, face_top)."""
    fx, fy, fw, fh = face_box
    s = face_w / fw
    head = cv2.resize(head, (max(1, int(head.shape[1] * s)), max(1, int(head.shape[0] * s))))
    fx, fy, fw, fh = fx * s, fy * s, fw * s, fh * s
    x0, y0 = int(cx - (fx + fw / 2)), int(face_top - fy)
    H, W = canvas.shape[:2]
    hh, hw = head.shape[:2]
    mask = np.zeros((hh, hw), np.float32)
    cv2.ellipse(mask, (hw // 2, hh // 2), (int(hw * 0.44), int(hh * 0.46)), 0, 0, 360, 1.0, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), max(2, hw / 30))[..., None]
    ax0, ay0, ax1, ay1 = max(0, x0), max(0, y0), min(W, x0 + hw), min(H, y0 + hh)
    if ax1 <= ax0 or ay1 <= ay0:
        return
    sub = (slice(ay0 - y0, ay1 - y0), slice(ax0 - x0, ax1 - x0))
    region = canvas[ay0:ay1, ax0:ax1].astype(np.float32)
    canvas[ay0:ay1, ax0:ax1] = (region * (1 - mask[sub]) + head[sub].astype(np.float32) * mask[sub]).astype(np.uint8)


def draw_desk_row(canvas, y, colour=(40, 70, 110)):
    cv2.rectangle(canvas, (0, y), (canvas.shape[1], y + 26), colour, -1)
    cv2.rectangle(canvas, (0, y), (canvas.shape[1], y + 4), (80, 115, 160), -1)


def compose_scene(people, seed, w=1280, h=720, n_people=6, rows=2):
    """Classroom picture with up to n_people seated in `rows` rows (back row smaller faces)."""
    rnd = random.Random(seed)
    canvas = classroom_background(w, h, seed)
    chosen = rnd.sample(people, min(n_people, len(people)))
    per_row = int(np.ceil(len(chosen) / rows))
    row_cfg = [(0.22, 62), (0.40, 80), (0.58, 100)][-rows:] if rows <= 3 else [(0.4, 80)] * rows
    placed = []
    for r in range(rows):
        top_frac, face_w = row_cfg[r]
        group = chosen[r * per_row:(r + 1) * per_row]
        for i, p in enumerate(group):
            cx = (i + 1) * w / (len(group) + 1) + rnd.uniform(-35, 35)
            head = light(rotate(p["head"], rnd.uniform(-5, 5)), rnd.uniform(0.85, 1.12), rnd.uniform(-10, 10))
            paste_person(canvas, head, p["head_face"], cx, top_frac * h, face_w * rnd.uniform(0.9, 1.1))
            placed.append(p["label"])
        draw_desk_row(canvas, int(top_frac * h + face_w * 2.3))
    if rnd.random() < 0.5:                                   # a little camera blur sometimes
        canvas = cv2.GaussianBlur(canvas, (3, 3), 0)
    return canvas, placed


def make_video(people, out_path, fps=10):
    """Wide classroom (all people) and a 1280x720 window that moves to each 'taught point'."""
    n = len(people)
    wide, _ = compose_scene(people, seed=999, w=max(1280, 300 * ((n + 1) // 2) + 400), h=720,
                            n_people=n, rows=2)
    W = wide.shape[1]
    stops = np.linspace(0, W - 1280, max(2, int(np.ceil(W / 900)) + 1)).astype(int)
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (1280, 720))
    pos = stops[0]
    for s in stops:
        for x in np.linspace(pos, s, fps).astype(int):        # 1 s move
            vw.write(wide[:, x:x + 1280])
        for _ in range(int(fps * 1.5)):                       # 1.5 s still at the taught point
            vw.write(wide[:, s:s + 1280])
        pos = s
    vw.release()
    return len(stops)


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--people", required=True, help="folder with one sub-folder <ID>_<Name> per person")
    ap.add_argument("--out", default="sim", help="output folder (default: sim)")
    ap.add_argument("--scenes", type=int, default=6, help="number of classroom pictures")
    ap.add_argument("--per-scene", type=int, default=6, help="people per classroom picture")
    ap.add_argument("--shots", type=int, default=5, help="enrolment shots per person")
    ap.add_argument("--class-name", default="MBBS1", help="class of the simulated students")
    ap.add_argument("--hall", default="Hall 1", help="hall of the simulated sessions")
    args = ap.parse_args()

    engine = FaceEngine(need_recogniser=False, score_threshold=0.6)
    out = Path(args.out)
    people = []
    for folder in sorted(p for p in Path(args.people).iterdir() if p.is_dir()):
        photos, names = [], []
        for path in list_images(folder):
            img = cv2.imread(str(path))
            if img is not None and len(engine.detect(img)) >= 1:
                photos.append(img)
                names.append(path.name)
            else:
                print(f"   skipped {path}: no face found")
        if not photos:
            print(f"!! {folder.name}: no usable photo, skipped")
            continue
        stranger = folder.name.upper().startswith("UNKNOWN")
        held_out = photos[-1]
        enrol_photos = photos[:-1] if len(photos) >= 2 else photos
        head, head_face = crop_around_face(held_out, largest_face(engine.detect(held_out)))
        people.append({"label": folder.name, "stranger": stranger, "head": head, "head_face": head_face})
        if not stranger:
            dest = out / "enrol" / folder.name
            dest.mkdir(parents=True, exist_ok=True)
            for old in dest.glob("*.jpg"):
                old.unlink()
            for i, shot in enumerate(enrolment_shots(engine, enrol_photos, args.shots), 1):
                cv2.imwrite(str(dest / f"shot_{i:02d}.jpg"), shot, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"{'stranger' if stranger else 'student '}  {folder.name}: {len(photos)} photo(s)"
              f"{' (last one kept for classroom only)' if len(photos) >= 2 else ' (only one photo: same photo used for classroom)'}")
    if len(people) < 2:
        sys.exit("Need at least 2 people.")

    scenes = out / "classroom"
    scenes.mkdir(parents=True, exist_ok=True)
    for old in scenes.glob("scene_*.jpg"):
        old.unlink()
    lines = []
    for k in range(1, args.scenes + 1):
        img, placed = compose_scene(people, seed=k, n_people=args.per_scene, rows=2)
        cv2.imwrite(str(scenes / f"scene_{k:02d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        lines.append(f"scene_{k:02d}.jpg: " + ", ".join(placed))
    stops = make_video(people, out / "classroom.mp4")
    (out / "expected.txt").write_text(
        "Who is in each classroom picture (UNKNOWN_* must NOT be marked present):\n" + "\n".join(lines) +
        "\nclassroom.mp4: everyone (" + ", ".join(p["label"] for p in people) + ")\n")
    # ---- college central system data: student list with RF cards, a timetable, RF card taps
    studs = [p["label"] for p in people if not p["stranger"]]
    with open(out / "college_students.csv", "w", newline="", encoding="utf-8") as f:
        f.write("student_id,name,class_name,rf_card\n")
        for i, lab in enumerate(studs, 1):
            sid, _, nm = lab.partition("_")
            f.write(f"{sid},{nm.replace('_', ' ') or sid},{args.class_name},RF{10000 + i}\n")
    ids = [lab.partition("_")[0] for lab in studs]
    sessions = [  # session 2 leaves out the last student -> that student is reported NOT_IN_LIST
        ("SIM-{date}-ANAT101", "ANAT101", "Anatomy", "L01", "Dr Lecturer One", "09:00", "10:00", ids),
        ("SIM-{date}-PHYS102", "PHYS102", "Physiology", "L02", "Dr Lecturer Two", "11:00", "12:00", ids[:-1]),
        ("SIM-{date}-BIOC103", "BIOC103", "Biochemistry", "L03", "Dr Lecturer Three", "14:00", "15:00", ids)]
    with open(out / "timetable.csv", "w", newline="", encoding="utf-8") as f:
        f.write("session_id,subject_code,subject_name,lecturer_id,lecturer_name,hall,start_time,end_time,students\n")
        for s in sessions:
            f.write(",".join(s[:5]) + f",{args.hall}," + ",".join(s[5:7]) + "," + " ".join(s[7]) + "\n")
    taps = [f"RF{10000 + i}" for i in range(1, len(studs) + 1)][:max(1, len(studs) - 1)] + ["RF99999"]
    (out / "rf_taps.txt").write_text("\n".join(taps) + "\n")
    print(f"\nMade {sum(not p['stranger'] for p in people)} enrolment folders in {out / 'enrol'}, "
          f"{args.scenes} classroom pictures in {scenes}, {out / 'classroom.mp4'} ({stops} taught points),\n"
          f"and the central system files {out / 'college_students.csv'}, {out / 'timetable.csv'} (3 sessions) "
          f"and {out / 'rf_taps.txt'}.")


if __name__ == "__main__":
    main()
