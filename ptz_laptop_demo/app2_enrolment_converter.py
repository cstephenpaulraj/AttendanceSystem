"""APP 2 - ENROLMENT CONVERTER  (this laptop plays the office PC)

1. Receives a student's enrolment photos from the Face capture app (app 1), which runs on the dedicated
   college phone under college staff supervision. Uploads are accepted only from a registered college
   phone, with a valid staff ID + PIN and the staff member's confirmation that the ID card was checked.
2. Verifies them: exactly one face per photo, big enough, sharp, well lit, and all photos the same person.
3. Converts each good photo into a standard database image (face aligned to 112 x 112) plus its face code.
4. Pushes the database images to the Edge AI service (app 3), which stores them.
5. When the Edge AI confirms, wipes the photos from this PC. If the Edge AI is not reachable,
   keeps the job and retries every 30 seconds.

Run:   python app2_enrolment_converter.py        (then open http://127.0.0.1:8001)
"""
import argparse
import base64
import datetime as dt
import html
import json
import shutil
import threading
import time
import uuid

import cv2
import numpy as np
import requests
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from common import config
from common.face_engine import FaceEngine

INBOX = config.DATA_DIR / "office_pc" / "inbox"          # photos waiting (wiped after edge confirms)
JOB_LOG = config.DATA_DIR / "office_pc" / "jobs.json"     # job history, NO photos
engine = None
jobs = []
lock = threading.Lock()
app = FastAPI(title="PTZ demo - Enrolment Converter (office PC)")


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_log():
    JOB_LOG.parent.mkdir(parents=True, exist_ok=True)
    keep = [{k: v for k, v in j.items() if not k.startswith("_")} for j in jobs]
    JOB_LOG.write_text(json.dumps(keep, indent=1))


def photos_on_disk():
    return sum(1 for p in INBOX.rglob("*") if p.is_file()) if INBOX.exists() else 0


# =====================================================================  conversion
def convert(job_dir):
    """Check every photo and turn the good ones into database images + face codes."""
    good, rejected = [], []
    for path in sorted(job_dir.glob("*.jpg")):
        img = cv2.imread(str(path))
        if img is None:
            rejected.append({"photo": path.name, "reason": "not a picture"})
            continue
        faces = engine.detect(img)
        if len(faces) == 0:
            rejected.append({"photo": path.name, "reason": "no face found"})
            continue
        if len(faces) > 1:
            rejected.append({"photo": path.name, "reason": f"{len(faces)} faces - only the student may be in the photo"})
            continue
        q = engine.quality(img, faces[0])
        problem = engine.quality_problem(q)
        if problem:
            rejected.append({"photo": path.name, "reason": problem})
            continue
        aligned = engine.align(img, faces[0])                 # standard 112 x 112 database image
        good.append({"photo": path.name, "aligned": aligned, "embedding": engine.embed_aligned(aligned),
                     "quality": round(q["sharpness"], 1)})
    # all photos must be the same person
    if len(good) >= 2:
        mean = np.mean([g["embedding"] for g in good], axis=0)
        mean /= np.linalg.norm(mean)
        same = [g for g in good if float(g["embedding"] @ mean) >= config.SAME_PERSON_MIN]
        for g in good:
            if g not in same:
                rejected.append({"photo": g["photo"], "reason": "does not look like the same person as the other photos"})
        good = same
    return good, rejected


def push_to_edge(job, good):
    payload = {
        "student_id": job["student_id"], "name": job["name"], "class_name": job["class_name"],
        "supervised_by": job["supervised_by"], "device_id": job["device_id"],
        "templates": [{"embedding": g["embedding"].tolist(), "quality": g["quality"],
                       "image_jpg_b64": base64.b64encode(cv2.imencode(".jpg", g["aligned"],
                                                                      [cv2.IMWRITE_JPEG_QUALITY, 95])[1]).decode()}
                      for g in good]}
    r = requests.post(f"{config.EDGE_URL}/api/enrol", json=payload,
                      headers={"X-Edge-Key": config.EDGE_PUSH_KEY}, timeout=15)
    if r.status_code == 200:
        return True, r.json()
    try:
        detail = r.json().get("detail")
    except ValueError:
        detail = r.text
    if r.status_code in (400, 401, 409, 422):
        raise ValueError(f"Edge AI refused: {detail}")
    return False, detail


def process(job):
    job_dir = INBOX / job["job_id"]
    good, rejected = convert(job_dir)
    job["accepted"] = len(good)
    job["rejected"] = rejected
    if len(good) < config.MIN_GOOD_PHOTOS:
        job["status"] = f"REJECTED - only {len(good)} good photo(s), need {config.MIN_GOOD_PHOTOS}. Capture again."
        shutil.rmtree(job_dir, ignore_errors=True)
        return job
    job["_good"] = good
    try_push(job)
    return job


def try_push(job):
    job_dir = INBOX / job["job_id"]
    try:
        ok, info = push_to_edge(job, job["_good"])
    except requests.RequestException:
        ok, info = False, "Edge AI not reachable"
    except ValueError as exc:                                 # refused for good - do not retry
        job["status"] = f"REJECTED - {exc}"
        job.pop("_good", None)
        shutil.rmtree(job_dir, ignore_errors=True)
        return
    if ok:
        shutil.rmtree(job_dir, ignore_errors=True)            # edge confirmed -> wipe photos here
        job.pop("_good", None)
        job["status"] = "STORED ON EDGE AI - local photos wiped"
        job["pushed_at"] = now()
    else:
        job["status"] = f"WAITING FOR EDGE AI ({info}) - will retry every 30 s"


def retry_loop():
    while True:
        time.sleep(30)
        with lock:
            for job in jobs:
                if job["status"].startswith("WAITING") and "_good" in job:
                    try_push(job)
            save_log()


# =====================================================================  API
@app.post("/api/upload")
def upload(student_id: str = Form(...), name: str = Form(...), class_name: str = Form(...),
           staff_id: str = Form(...), staff_pin: str = Form(...), device_id: str = Form(...),
           id_card_checked: bool = Form(False), photos: list[UploadFile] = File(...)):
    student_id, name, class_name = student_id.strip(), name.strip(), class_name.strip().upper()
    staff_id, device_id = staff_id.strip().upper(), device_id.strip().upper()
    if device_id not in config.ENROLMENT_DEVICES:
        raise HTTPException(403, f"{device_id} is not a registered college enrolment phone")
    if config.STAFF_ACCOUNTS.get(staff_id) != staff_pin:
        raise HTTPException(403, "Wrong staff ID or PIN: enrolment must be supervised by college staff")
    if not id_card_checked:
        raise HTTPException(400, "The supervising staff member must confirm the student's ID card was checked")
    if not (student_id and len(student_id) <= 32 and all(c.isalnum() or c in "-_" for c in student_id)):
        raise HTTPException(400, "Student ID may use letters, digits, - and _ only (max 32)")
    if not name or not class_name:
        raise HTTPException(400, "Name and class are required")
    if not 1 <= len(photos) <= 20:
        raise HTTPException(400, "Send 1 to 20 photos")
    job = {"job_id": dt.datetime.now().strftime("%Y%m%d%H%M%S-") + uuid.uuid4().hex[:6],
           "student_id": student_id, "name": name, "class_name": class_name, "received_at": now(),
           "photos": len(photos), "supervised_by": staff_id, "device_id": device_id, "status": "RECEIVED"}
    job_dir = INBOX / job["job_id"]
    job_dir.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(photos, 1):
        (job_dir / f"photo_{i:02d}.jpg").write_bytes(p.file.read())
    with lock:
        jobs.insert(0, job)
        process(job)
        save_log()
    print(f"[office] {student_id} {name} (staff {staff_id}, {device_id}): {job['accepted']}/{job['photos']} good -> {job['status']}")
    return {k: v for k, v in job.items() if not k.startswith("_")}


@app.get("/api/jobs")
def list_jobs():
    return [{k: v for k, v in j.items() if not k.startswith("_")} for j in jobs]


@app.get("/api/health")
def health():
    return {"status": "ok", "photos_on_disk": photos_on_disk()}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(j['received_at'])}</td><td>{e(j['student_id'])}</td><td>{e(j['name'])}</td>"
        f"<td>{e(j['class_name'])}</td><td>{e(j.get('supervised_by', '-'))}</td><td>{e(j.get('device_id', '-'))}</td>"
        f"<td>{j.get('accepted', 0)} / {j['photos']}</td>"
        f"<td>{'<br>'.join(e(r['photo'] + ': ' + r['reason']) for r in j.get('rejected', [])) or '-'}</td>"
        f"<td class={'ok' if j['status'].startswith('STORED') else 'bad'}>{e(j['status'])}</td></tr>"
        for j in jobs) or "<tr><td colspan=9>No enrolments received yet</td></tr>"
    return f"""<!doctype html><html><head><meta charset=utf-8><meta http-equiv=refresh content=3>
<title>Enrolment Converter</title><style>
body{{font-family:Arial,sans-serif;font-size:15px;margin:24px;background:#f7f6f2;color:#1b2430}}
h1{{font-size:22px}} table{{border-collapse:collapse;background:#fff}}
td,th{{border:1px solid #d6d2c6;padding:6px 10px;text-align:left;vertical-align:top}} th{{background:#ece8dc}}
.ok{{color:#11713a;font-weight:bold}} .bad{{color:#a23a10;font-weight:bold}} .note{{color:#555}}</style></head><body>
<h1>APP 2 &middot; Enrolment Converter (office PC)</h1>
<p class=note>Edge AI: {e(config.EDGE_URL)} &middot; photos currently stored on this PC: <b>{photos_on_disk()}</b>
&middot; page refreshes every 3 s</p>
<table><tr><th>Received</th><th>ID</th><th>Name</th><th>Class</th><th>Supervised by</th><th>Device</th><th>Good photos</th><th>Rejected photos</th>
<th>Status</th></tr>{rows}</table></body></html>"""


def main():
    global engine, jobs
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=config.OFFICE_PORT)
    ap.add_argument("--host", default=config.OFFICE_HOST)
    args = ap.parse_args()
    engine = FaceEngine(need_recogniser=True, score_threshold=0.6)
    INBOX.mkdir(parents=True, exist_ok=True)
    if JOB_LOG.exists():
        jobs = json.loads(JOB_LOG.read_text())
        # photos of unfinished jobs from a previous run: convert and push again
        for job in jobs:
            if job["status"].startswith(("WAITING", "RECEIVED")) and (INBOX / job["job_id"]).exists():
                process(job)
        save_log()
    threading.Thread(target=retry_loop, daemon=True).start()
    print(f"\n=== APP 2: ENROLMENT CONVERTER (office PC) ===\nDashboard: http://{args.host}:{args.port}\n"
          f"Pushes to : {config.EDGE_URL}\nPress Ctrl+C to stop.\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
