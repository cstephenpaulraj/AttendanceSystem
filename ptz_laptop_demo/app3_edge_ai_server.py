"""APP 3 - EDGE AI SERVICE  (this laptop plays the Edge AI server in the hall)

* Face database: receives the standard database images + face codes from the Enrolment Converter
  (office PC) and stores them ONLY here (SQLite + FAISS search index).
* College central system -> Edge AI: the student list (ID, name, class, RF card) and the lecture
  sessions of the day (subject, lecturer, hall, time, list of students expected).
* Attendance per session: face recognition (app 4), RF reader fallback when both cameras fail,
  lecturer override for official duty (within 2 days). Students seen in a session who are NOT on
  the central system's list are reported as NOT_IN_LIST.
* Edge AI -> college central system: the central system pulls a session's attendance at any time
  (GET /api/v1/sessions/{session_id}/attendance). Photos and face codes never leave this service.
* Safety: encrypted face database backups (two folders), integrity check at start, tamper-evident
  audit log, two-person approval to delete a student, re-enrolment must be the same face.

Run:   python app3_edge_ai_server.py        (then open http://127.0.0.1:8002)
"""
import argparse
import base64
import csv
import datetime as dt
import hashlib
import html
import io
import json
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import faiss
import numpy as np
import uvicorn
from cryptography.fernet import Fernet
from fastapi import FastAPI, Form, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from common import config

DB_PATH = config.DATA_DIR / "edge_ai" / "edge_ai.db"
STATUSES = ("PRESENT", "ABSENT", "ON_DUTY", "NOT_IN_LIST")
OVERRIDE_REASONS = ("PAPER_PRESENTATION", "SPORTS", "OTHER_OFFICIAL_DUTY", "CORRECTION")


def now():
    return dt.datetime.now().replace(microsecond=0)


def ts():
    return now().isoformat(" ")


# =====================================================================  database
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS students(
    student_id TEXT PRIMARY KEY, name TEXT NOT NULL, class_name TEXT NOT NULL,
    enrolled_at TEXT NOT NULL, supervised_by TEXT, device_id TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE', deleted_at TEXT, deleted_by TEXT);
CREATE TABLE IF NOT EXISTS face_templates(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    embedding BLOB NOT NULL, db_image BLOB NOT NULL, quality REAL);
CREATE TABLE IF NOT EXISTS college_students(            -- student list sent by the central system
    student_id TEXT PRIMARY KEY, name TEXT NOT NULL, class_name TEXT NOT NULL, rf_card TEXT UNIQUE,
    updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lecture_sessions(
    session_id TEXT PRIMARY KEY, subject_code TEXT, subject_name TEXT, lecturer_id TEXT,
    lecturer_name TEXT, hall TEXT, date TEXT NOT NULL, start_time TEXT, end_time TEXT,
    origin TEXT NOT NULL,                                 -- CENTRAL or LOCAL (not from central system)
    state TEXT NOT NULL DEFAULT 'SCHEDULED',              -- SCHEDULED, RUNNING, ENDED
    mode TEXT NOT NULL DEFAULT 'CAMERA',                  -- CAMERA, STANDBY_CAMERA, RF_FALLBACK
    mode_reason TEXT, started_at TEXT, ended_at TEXT, unknown_faces INTEGER DEFAULT 0,
    received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS session_students(            -- who the central system expects
    session_id TEXT NOT NULL, student_id TEXT NOT NULL, PRIMARY KEY(session_id, student_id));
CREATE TABLE IF NOT EXISTS session_attendance(
    session_id TEXT NOT NULL, student_id TEXT NOT NULL, status TEXT NOT NULL,
    method TEXT NOT NULL,                                 -- FACE, RF, LECTURER_OVERRIDE, NONE
    in_session_list INTEGER NOT NULL, marked_at TEXT NOT NULL, confidence REAL,
    override_by TEXT, override_reason TEXT, override_note TEXT, original_status TEXT,
    PRIMARY KEY(session_id, student_id));
CREATE TABLE IF NOT EXISTS audit_log(
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
    detail TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
"""
STUDENT_COLUMNS = {"supervised_by": "TEXT", "device_id": "TEXT", "status": "TEXT NOT NULL DEFAULT 'ACTIVE'",
                   "deleted_at": "TEXT", "deleted_by": "TEXT"}


class EdgeDB:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        problem = self.integrity_problem()
        if problem:
            sys.exit(f"\n!! The Edge AI database {path} is damaged: {problem}\n"
                     f"   Restore the latest good backup:  .venv\\Scripts\\python tools\\restore_backup.py --restore latest\n")
        self.con.executescript(SCHEMA)
        have = {r["name"] for r in self.con.execute("PRAGMA table_info(students)")}
        for col, decl in STUDENT_COLUMNS.items():          # database from the previous demo version
            if col not in have:
                self.con.execute(f"ALTER TABLE students ADD COLUMN {col} {decl}")
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.commit()
        self.dirty = False                                  # face data changed since the last backup
        self.index = None
        self.index_ids = []
        self.rebuild_index()

    def integrity_problem(self):
        try:
            res = self.con.execute("PRAGMA integrity_check").fetchone()[0]
            return None if res == "ok" else res
        except sqlite3.DatabaseError as exc:
            return str(exc)

    def q(self, sql, args=()):
        with self.lock:
            return self.con.execute(sql, args).fetchall()

    def x(self, sql, args=()):
        with self.lock:
            cur = self.con.execute(sql, args)
            self.con.commit()
            return cur

    # ---- tamper-evident audit log: every entry carries the hash of the one before
    def audit(self, actor, action, detail):
        with self.lock:
            last = self.con.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            prev = last["hash"] if last else "GENESIS"
            at = ts()
            detail = json.dumps(detail, sort_keys=True) if not isinstance(detail, str) else detail
            h = hashlib.sha256(f"{prev}|{at}|{actor}|{action}|{detail}".encode()).hexdigest()
            self.con.execute("INSERT INTO audit_log(at,actor,action,detail,prev_hash,hash) VALUES(?,?,?,?,?,?)",
                             (at, actor, action, detail, prev, h))
            self.con.commit()

    def audit_chain_ok(self):
        prev = "GENESIS"
        for r in self.q("SELECT * FROM audit_log ORDER BY id"):
            h = hashlib.sha256(f"{prev}|{r['at']}|{r['actor']}|{r['action']}|{r['detail']}".encode()).hexdigest()
            if r["prev_hash"] != prev or r["hash"] != h:
                return False, r["id"]
            prev = r["hash"]
        return True, None

    # ---- FAISS index (active students only): inner product of length-1 codes = cosine similarity
    def rebuild_index(self):
        with self.lock:
            rows = self.con.execute("SELECT t.student_id, t.embedding FROM face_templates t "
                                    "JOIN students s USING(student_id) WHERE s.status='ACTIVE'").fetchall()
            if not rows:
                self.index, self.index_ids = None, []
                return
            vecs = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
            index = faiss.IndexFlatIP(vecs.shape[1])
            index.add(vecs)
            self.index, self.index_ids = index, [r["student_id"] for r in rows]

    def search(self, vecs, k=10):
        """Best student for each face code: [(student_id, score), ...]."""
        with self.lock:
            if self.index is None:
                return [(None, 0.0)] * len(vecs)
            k = min(k, self.index.ntotal)
            scores, idx = self.index.search(np.ascontiguousarray(vecs, dtype=np.float32), k)
            out = []
            for s_row, i_row in zip(scores, idx):
                best = {}
                for s, i in zip(s_row, i_row):
                    if i >= 0:
                        sid = self.index_ids[i]
                        best[sid] = max(best.get(sid, -1.0), float(s))
                sid, score = max(best.items(), key=lambda kv: kv[1]) if best else (None, 0.0)
                out.append((sid, score))
            return out


db = None
backup_state = {"last": None, "last_file": None, "error": None, "count": 0}
app = FastAPI(title="PTZ demo - Edge AI service",
              description="Face database lives only here. The college central system sends students and "
                          "lecture sessions, and pulls each session's attendance (no photos, no face codes).")


# =====================================================================  encrypted backups
def backup_key():
    path = config.BACKUP_KEY_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Fernet.generate_key())
        print(f"[edge] new backup key made: {path}  (real system: key kept offline, split between "
              f"our office and the college)")
    return Fernet(path.read_bytes().strip())


def backup_dirs():
    return [config.BACKUP_DIR] + ([Path(config.BACKUP_DIR2)] if config.BACKUP_DIR2 else [])


def backup_now(reason="scheduled"):
    """Consistent copy of the whole database -> integrity check -> encrypt -> write to every backup folder."""
    stamp = now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    tmp = DB_PATH.parent / f"backup_tmp_{stamp}.db"
    try:
        with db.lock:
            dst = sqlite3.connect(str(tmp))
            db.con.backup(dst)
            dst.close()
        chk = sqlite3.connect(str(tmp))
        ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
        students = chk.execute("SELECT COUNT(*) FROM students WHERE status='ACTIVE'").fetchone()[0]
        templates = chk.execute("SELECT COUNT(*) FROM face_templates").fetchone()[0]
        chk.close()
        if ok != "ok":
            raise RuntimeError(f"copy failed the integrity check: {ok}")
        plain = tmp.read_bytes()
        token = backup_key().encrypt(plain)
        name = f"edge_ai_{stamp}.db.enc"
        entry = {"file": name, "at": ts(), "reason": reason, "students": students, "templates": templates,
                 "sha256_encrypted": hashlib.sha256(token).hexdigest(),
                 "sha256_plain": hashlib.sha256(plain).hexdigest()}
        written = []
        for d in backup_dirs():
            try:
                d.mkdir(parents=True, exist_ok=True)
                (d / name).write_bytes(token)
                man_path = d / "manifest.json"
                man = json.loads(man_path.read_text()) if man_path.exists() else []
                man.append(entry)
                for old in man[:-config.BACKUP_KEEP]:              # keep the newest BACKUP_KEEP copies
                    (d / old["file"]).unlink(missing_ok=True)
                man_path.write_text(json.dumps(man[-config.BACKUP_KEEP:], indent=1))
                written.append(str(d))
            except OSError as exc:
                backup_state["error"] = f"{d}: {exc}"
        if not written:
            raise RuntimeError(backup_state["error"] or "no backup folder writable")
        backup_state.update(last=entry["at"], last_file=name, count=backup_state["count"] + 1,
                            error=None if len(written) == len(backup_dirs()) else backup_state["error"])
        db.dirty = False
        db.audit("system", "BACKUP", {"file": name, "reason": reason, "students": students, "folders": written})
        print(f"[edge] backup {name}: {students} students, {templates} face templates -> {', '.join(written)}")
        return entry
    except Exception as exc:                                       # report, never crash the service
        backup_state["error"] = str(exc)
        print(f"[edge] BACKUP FAILED: {exc}")
        return None
    finally:
        tmp.unlink(missing_ok=True)


def backup_loop():
    while True:
        time.sleep(config.BACKUP_CHECK_SEC)
        if db.dirty:
            backup_now("face database changed")


# =====================================================================  request models
class Template(BaseModel):
    embedding: list[float]
    image_jpg_b64: str
    quality: float = 0.0


class EnrolRequest(BaseModel):
    student_id: str = Field(pattern=r"^[A-Za-z0-9_\-]{1,32}$")
    name: str = Field(min_length=1, max_length=80)
    class_name: str = Field(min_length=1, max_length=40)
    templates: list[Template] = Field(min_length=1, max_length=20)
    supervised_by: str = Field(min_length=1, max_length=32)
    device_id: str = Field(min_length=1, max_length=40)


class CollegeStudent(BaseModel):
    student_id: str = Field(pattern=r"^[A-Za-z0-9_\-]{1,32}$")
    name: str
    class_name: str
    rf_card: str | None = None


class LectureSession(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9_\-]{1,48}$")
    subject_code: str
    subject_name: str = ""
    lecturer_id: str
    lecturer_name: str = ""
    hall: str
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    students: list[str] = Field(description="IDs of the students expected in this session")


class LocalSessionRequest(BaseModel):
    class_name: str = Field(min_length=1, max_length=40)
    hall: str = config.HALL
    lecturer_id: str = "LOCAL"


class IdentifyRequest(BaseModel):
    embeddings: list[list[float]]


class MarkRequest(BaseModel):
    student_id: str
    confidence: float = 0.0


class ModeRequest(BaseModel):
    mode: str = Field(pattern=r"^(CAMERA|STANDBY_CAMERA|RF_FALLBACK)$")
    reason: str = ""


class RfTap(BaseModel):
    card: str


class EndRequest(BaseModel):
    unknown_faces: int = 0


class OverrideRequest(BaseModel):
    lecturer_id: str
    pin: str
    student_id: str
    new_status: str = Field(pattern=r"^(ON_DUTY|PRESENT|ABSENT)$")
    reason: str = Field(pattern=r"^(PAPER_PRESENTATION|SPORTS|OTHER_OFFICIAL_DUTY|CORRECTION)$")
    note: str = Field(default="", max_length=200)


class DeleteRequest(BaseModel):
    requested_by: str
    requested_pin: str
    approved_by: str
    approved_pin: str
    reason: str = Field(min_length=3, max_length=200)


def check_key(key):
    if key != config.EDGE_PUSH_KEY:
        raise HTTPException(401, "Wrong or missing X-Edge-Key")


def check_college(key):
    if key != config.COLLEGE_API_KEY:
        raise HTTPException(401, "Wrong or missing X-College-Key")


def check_staff(staff_id, pin):
    if config.STAFF_ACCOUNTS.get((staff_id or "").upper()) != pin:
        raise HTTPException(403, f"Staff {staff_id}: wrong ID or PIN")
    return staff_id.upper()


# =====================================================================  enrolment (from the office PC)
@app.post("/api/enrol")
def enrol(req: EnrolRequest, x_edge_key: str = Header(default="")):
    check_key(x_edge_key)
    sid = req.student_id
    staff = req.supervised_by.upper()
    if staff not in config.STAFF_ACCOUNTS:
        raise HTTPException(403, f"{staff} is not a registered college staff member")
    if req.device_id.upper() not in config.ENROLMENT_DEVICES:
        raise HTTPException(403, f"{req.device_id} is not a registered college enrolment phone")
    master = db.q("SELECT * FROM college_students WHERE student_id=?", (sid,))
    if db.q("SELECT 1 FROM college_students LIMIT 1") and not master:
        raise HTTPException(409, f"{sid} is not in the college student list sent by the central system")
    name = master[0]["name"] if master else req.name.strip()
    cls = master[0]["class_name"] if master else req.class_name.strip().upper()
    vecs = np.array([t.embedding for t in req.templates], dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    # 1) refuse if these faces already belong to a DIFFERENT student (one person, two IDs)
    for other, score in db.search(vecs):
        if other and other != sid and score >= config.DUPLICATE_THRESHOLD:
            oname = db.q("SELECT name FROM students WHERE student_id=?", (other,))[0]["name"]
            db.audit(staff, "ENROL_REFUSED", {"student_id": sid, "reason": f"face already enrolled as {other}"})
            raise HTTPException(409, f"This face is already enrolled as {other} ({oname}), similarity {score:.2f}")
    # 2) re-enrolment of an existing student must be the SAME face (stops swapping a student's face)
    old = db.q("SELECT t.embedding FROM face_templates t JOIN students s USING(student_id) "
               "WHERE s.student_id=? AND s.status='ACTIVE'", (sid,))
    if old:
        old_vecs = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in old])
        best = float(np.max(vecs @ old_vecs.T))
        if best < config.SAME_PERSON_MIN:
            db.audit(staff, "ENROL_REFUSED", {"student_id": sid, "reason": "different face on re-enrolment",
                                              "similarity": round(best, 3)})
            raise HTTPException(409, f"{sid} is already enrolled with a different face (similarity {best:.2f}). "
                                     f"Two staff must delete the old enrolment first.")
    with db.lock:
        db.con.execute("DELETE FROM face_templates WHERE student_id=?", (sid,))
        db.con.execute("INSERT INTO students(student_id,name,class_name,enrolled_at,supervised_by,device_id,status) "
                       "VALUES(?,?,?,?,?,?,'ACTIVE') ON CONFLICT(student_id) DO UPDATE SET name=excluded.name, "
                       "class_name=excluded.class_name, enrolled_at=excluded.enrolled_at, "
                       "supervised_by=excluded.supervised_by, device_id=excluded.device_id, status='ACTIVE', "
                       "deleted_at=NULL, deleted_by=NULL",
                       (sid, name, cls, ts(), staff, req.device_id.upper()))
        for t, v in zip(req.templates, vecs):
            db.con.execute("INSERT INTO face_templates(student_id,embedding,db_image,quality) VALUES(?,?,?,?)",
                           (sid, v.tobytes(), base64.b64decode(t.image_jpg_b64), t.quality))
        db.con.commit()
        db.rebuild_index()
        db.dirty = True
    db.audit(staff, "RE_ENROL" if old else "ENROL", {"student_id": sid, "templates": len(vecs),
                                                    "device": req.device_id.upper()})
    print(f"[edge] stored {sid} {name} ({len(vecs)} database images), supervised by {staff}")
    return {"status": "stored", "student_id": sid, "templates": len(vecs)}


@app.get("/api/students")
def students(include_deleted: bool = False):
    rows = db.q("SELECT s.student_id, s.name, s.class_name, s.enrolled_at, s.supervised_by, s.device_id, "
                "s.status, COUNT(t.id) AS templates FROM students s LEFT JOIN face_templates t USING(student_id) "
                + ("" if include_deleted else "WHERE s.status='ACTIVE' ") +
                "GROUP BY s.student_id ORDER BY s.class_name, s.student_id")
    return [dict(r) for r in rows]


@app.post("/api/students/{student_id}/delete")
def delete_student(student_id: str, req: DeleteRequest, x_edge_key: str = Header(default="")):
    """Two different staff members must approve. The face data is kept (soft delete) so it can be restored."""
    check_key(x_edge_key)
    a = check_staff(req.requested_by, req.requested_pin)
    b = check_staff(req.approved_by, req.approved_pin)
    if a == b:
        raise HTTPException(403, "A second, different staff member must approve a deletion")
    if not db.q("SELECT 1 FROM students WHERE student_id=? AND status='ACTIVE'", (student_id,)):
        raise HTTPException(404, "No such enrolled student")
    db.x("UPDATE students SET status='DELETED', deleted_at=?, deleted_by=? WHERE student_id=?",
         (ts(), f"{a}+{b}", student_id))
    db.rebuild_index()
    db.dirty = True
    db.audit(f"{a}+{b}", "DELETE_STUDENT", {"student_id": student_id, "reason": req.reason})
    return {"status": "deleted (can be restored)", "student_id": student_id}


@app.post("/api/students/{student_id}/restore")
def restore_student(student_id: str, staff_id: str = Form(...), pin: str = Form(...),
                    x_edge_key: str = Header(default="")):
    check_key(x_edge_key)
    staff = check_staff(staff_id, pin)
    if not db.q("SELECT 1 FROM students WHERE student_id=? AND status='DELETED'", (student_id,)):
        raise HTTPException(404, "No deleted student with this ID")
    db.x("UPDATE students SET status='ACTIVE', deleted_at=NULL, deleted_by=NULL WHERE student_id=?", (student_id,))
    db.rebuild_index()
    db.dirty = True
    db.audit(staff, "RESTORE_STUDENT", {"student_id": student_id})
    return {"status": "restored", "student_id": student_id}


@app.get("/local/db_image/{template_id}")
def db_image(template_id: int):
    """Database image for the local dashboard on this machine only."""
    rows = db.q("SELECT db_image FROM face_templates WHERE id=?", (template_id,))
    if not rows:
        raise HTTPException(404)
    return Response(rows[0]["db_image"], media_type="image/jpeg")


# =====================================================================  college central system -> Edge AI
@app.put("/api/v1/students", summary="Central system sends the college student list (with RF card numbers)")
def put_college_students(items: list[CollegeStudent], x_college_key: str = Header(default="")):
    check_college(x_college_key)
    with db.lock:
        for s in items:
            db.con.execute("INSERT INTO college_students(student_id,name,class_name,rf_card,updated_at) "
                           "VALUES(?,?,?,?,?) ON CONFLICT(student_id) DO UPDATE SET name=excluded.name, "
                           "class_name=excluded.class_name, rf_card=excluded.rf_card, updated_at=excluded.updated_at",
                           (s.student_id, s.name.strip(), s.class_name.strip().upper(),
                            (s.rf_card or "").strip() or None, ts()))
        db.con.commit()
    db.audit("central", "STUDENT_LIST", {"students": len(items)})
    return {"status": "stored", "students": len(items)}


@app.post("/api/v1/sessions", summary="Central system sends lecture sessions with their student lists")
def post_sessions(items: list[LectureSession], x_college_key: str = Header(default="")):
    check_college(x_college_key)
    out = []
    with db.lock:
        for s in items:
            cur = db.con.execute("SELECT state FROM lecture_sessions WHERE session_id=?", (s.session_id,)).fetchone()
            if cur and cur["state"] != "SCHEDULED":
                out.append({"session_id": s.session_id, "status": f"not changed: session already {cur['state']}"})
                continue
            db.con.execute("INSERT OR REPLACE INTO lecture_sessions(session_id,subject_code,subject_name,lecturer_id,"
                           "lecturer_name,hall,date,start_time,end_time,origin,state,mode,received_at) "
                           "VALUES(?,?,?,?,?,?,?,?,?,'CENTRAL','SCHEDULED','CAMERA',?)",
                           (s.session_id, s.subject_code, s.subject_name, s.lecturer_id.upper(), s.lecturer_name,
                            s.hall, s.date, s.start_time, s.end_time, ts()))
            db.con.execute("DELETE FROM session_students WHERE session_id=?", (s.session_id,))
            db.con.executemany("INSERT OR IGNORE INTO session_students VALUES(?,?)",
                               [(s.session_id, st) for st in s.students])
            out.append({"session_id": s.session_id, "status": "stored", "students": len(set(s.students))})
        db.con.commit()
    db.audit("central", "SESSIONS", {"sessions": [o["session_id"] for o in out]})
    return out


def session_row(session_id):
    s = db.q("SELECT * FROM lecture_sessions WHERE session_id=?", (session_id,))
    if not s:
        raise HTTPException(404, "No such session")
    return s[0]


def attendance_report(session_id):
    s = dict(session_row(session_id))
    expected = {r["student_id"] for r in db.q("SELECT student_id FROM session_students WHERE session_id=?",
                                              (session_id,))}
    enrolled = {r["student_id"] for r in db.q("SELECT student_id FROM students WHERE status='ACTIVE'")}
    marks = {r["student_id"]: dict(r) for r in db.q("SELECT * FROM session_attendance WHERE session_id=?",
                                                     (session_id,))}
    names = {r["student_id"]: r["name"] for r in db.q("SELECT student_id, name FROM college_students")}
    names.update({r["student_id"]: r["name"] for r in db.q("SELECT student_id, name FROM students")})
    records = []
    for sid in sorted(expected | set(marks)):
        m = marks.get(sid)
        if m:
            status = m["status"]
        else:
            status = "ABSENT" if s["state"] == "ENDED" else "NOT_YET_SEEN"
        records.append({"student_id": sid, "name": names.get(sid, ""), "status": status,
                        "method": m["method"] if m else "NONE", "in_session_list": sid in expected,
                        "face_enrolled": sid in enrolled, "time": m["marked_at"] if m else None,
                        "override": ({"by": m["override_by"], "reason": m["override_reason"],
                                      "note": m["override_note"], "original_status": m["original_status"]}
                                     if m and m["override_by"] else None)})
    counts = {k: sum(r["status"] == k for r in records) for k in STATUSES + ("NOT_YET_SEEN",)}
    return {"session": {k: s[k] for k in ("session_id", "subject_code", "subject_name", "lecturer_id",
                                           "lecturer_name", "hall", "date", "start_time", "end_time", "origin",
                                           "state", "mode", "mode_reason", "started_at", "ended_at",
                                           "unknown_faces")},
            "override_open_until": override_deadline(s),
            "counts": counts, "records": records}


def override_deadline(s):
    if not s["ended_at"]:
        return None
    end = dt.datetime.fromisoformat(s["ended_at"])
    return (end + dt.timedelta(hours=config.OVERRIDE_WINDOW_HOURS)).isoformat(" ")


@app.get("/api/v1/sessions", summary="List sessions (central system or dashboard)")
def list_sessions_api(date: str | None = Query(None, description="YYYY-MM-DD"), hall: str | None = None,
                      state: str | None = None):
    return list_sessions(date, hall, state)


def list_sessions(date=None, hall=None, state=None):
    sql, args = "SELECT * FROM lecture_sessions WHERE 1=1", []
    for col, val in (("date", date), ("hall", hall), ("state", state)):
        if val:
            sql += f" AND {col}=?"
            args.append(val)
    rows = db.q(sql + " ORDER BY date DESC, start_time DESC", args)
    out = []
    for r in rows:
        c = {k: v for k, v in db.q("SELECT status, COUNT(*) FROM session_attendance WHERE session_id=? "
                                   "GROUP BY status", (r["session_id"],))}
        exp = db.q("SELECT COUNT(*) n FROM session_students WHERE session_id=?", (r["session_id"],))[0]["n"]
        out.append({**dict(r), "expected": exp, "present": c.get("PRESENT", 0), "on_duty": c.get("ON_DUTY", 0),
                    "not_in_list": c.get("NOT_IN_LIST", 0)})
    return out


@app.get("/api/v1/sessions/{session_id}/attendance",
         summary="PULL API: the central system gets one session's attendance at any time (no photos)")
def get_session_attendance(session_id: str, x_college_key: str = Header(default="")):
    check_college(x_college_key)
    return attendance_report(session_id)


@app.get("/api/v1/sessions/{session_id}/attendance.csv", response_class=PlainTextResponse)
def get_session_attendance_csv(session_id: str, key: str = Query("", description="college API key")):
    check_college(key)
    rep = attendance_report(session_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    s = rep["session"]
    w.writerow(["session_id", "subject_code", "date", "hall", "lecturer_id", "student_id", "name", "status",
                "method", "in_session_list", "time", "override_reason"])
    for r in rep["records"]:
        w.writerow([s["session_id"], s["subject_code"], s["date"], s["hall"], s["lecturer_id"], r["student_id"],
                    r["name"], r["status"], r["method"], r["in_session_list"], r["time"] or "",
                    (r["override"] or {}).get("reason", "")])
    return buf.getvalue()


@app.get("/api/v1/attendance", summary="PULL API: attendance of many sessions by date / subject / hall")
def get_attendance(date: str = Query(..., description="YYYY-MM-DD"), subject_code: str | None = None,
                   hall: str | None = None, x_college_key: str = Header(default="")):
    check_college(x_college_key)
    return [attendance_report(s["session_id"]) for s in list_sessions(date=date, hall=hall)
            if not subject_code or s["subject_code"] == subject_code]


# =====================================================================  attendance engine (app 4)
@app.post("/api/identify")
def identify(req: IdentifyRequest):
    if not req.embeddings:
        return []
    vecs = np.array(req.embeddings, dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    names = {r["student_id"]: (r["name"], r["class_name"]) for r in db.q("SELECT * FROM students")}
    out = []
    for sid, score in db.search(vecs):
        if sid and score >= config.MATCH_THRESHOLD:
            out.append({"student_id": sid, "name": names[sid][0], "class_name": names[sid][1],
                        "score": round(score, 3)})
        else:
            out.append({"student_id": None, "name": None, "class_name": None, "score": round(score, 3)})
    return out


@app.get("/api/sessions/current", summary="The session app 4 should run now in this hall")
def current_session(hall: str = config.HALL):
    today, hhmm = now().date().isoformat(), now().strftime("%H:%M")
    rows = db.q("SELECT * FROM lecture_sessions WHERE hall=? AND date=? AND state!='ENDED' ORDER BY start_time",
                (hall, today))
    if not rows:
        raise HTTPException(404, f"No session sent by the central system for {hall} today ({today})")
    running = [r for r in rows if r["state"] == "RUNNING"]
    on_now = [r for r in rows if r["start_time"] <= hhmm <= r["end_time"]]
    return dict((running or on_now or rows)[0])


@app.post("/api/sessions/local", summary="Lecturer starts a session the central system did not send")
def start_local_session(req: LocalSessionRequest):
    cls = req.class_name.strip().upper()
    sid = now().strftime("LOCAL-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    with db.lock:
        db.con.execute("INSERT INTO lecture_sessions(session_id,subject_code,subject_name,lecturer_id,hall,date,"
                       "start_time,end_time,origin,state,mode,received_at) "
                       "VALUES(?,?,?,?,?,?,?,?,'LOCAL','SCHEDULED','CAMERA',?)",
                       (sid, f"LOCAL-{cls}", f"Session not sent by the central system ({cls})",
                        req.lecturer_id.upper(), req.hall, now().date().isoformat(), now().strftime("%H:%M"),
                        (now() + dt.timedelta(hours=1)).strftime("%H:%M"), ts()))
        roster = [r["student_id"] for r in db.con.execute(
            "SELECT student_id FROM college_students WHERE class_name=? UNION "
            "SELECT student_id FROM students WHERE class_name=? AND status='ACTIVE'", (cls, cls))]
        db.con.executemany("INSERT OR IGNORE INTO session_students VALUES(?,?)", [(sid, r) for r in roster])
        db.con.commit()
    db.audit(req.lecturer_id.upper(), "LOCAL_SESSION", {"session_id": sid, "class": cls})
    return dict(session_row(sid))


@app.post("/api/sessions/{session_id}/start")
def start_session(session_id: str):
    s = session_row(session_id)
    if s["state"] == "ENDED":
        raise HTTPException(409, "Session already ended")
    if s["state"] == "SCHEDULED":
        db.x("UPDATE lecture_sessions SET state='RUNNING', started_at=? WHERE session_id=?", (ts(), session_id))
    exp = db.q("SELECT COUNT(*) n FROM session_students WHERE session_id=?", (session_id,))[0]["n"]
    return {**dict(session_row(session_id)), "expected": exp}


@app.post("/api/sessions/{session_id}/mode")
def set_mode(session_id: str, req: ModeRequest):
    session_row(session_id)
    db.x("UPDATE lecture_sessions SET mode=?, mode_reason=? WHERE session_id=?", (req.mode, req.reason, session_id))
    db.audit("attendance", "MODE", {"session_id": session_id, "mode": req.mode, "reason": req.reason})
    return {"session_id": session_id, "mode": req.mode}


def _mark(session_id, student_id, method, confidence=0.0):
    s = session_row(session_id)
    if s["state"] != "RUNNING":
        raise HTTPException(409, f"Session is {s['state']}, not RUNNING")
    if not db.q("SELECT 1 FROM students WHERE student_id=? UNION SELECT 1 FROM college_students WHERE student_id=?",
                (student_id, student_id)):
        raise HTTPException(404, "Unknown student")
    listed = bool(db.q("SELECT 1 FROM session_students WHERE session_id=? AND student_id=?", (session_id, student_id)))
    status = "PRESENT" if listed else "NOT_IN_LIST"
    cur = db.x("INSERT OR IGNORE INTO session_attendance(session_id,student_id,status,method,in_session_list,"
               "marked_at,confidence) VALUES(?,?,?,?,?,?,?)",
               (session_id, student_id, status, method, int(listed), ts(), confidence))
    return {"student_id": student_id, "status": status, "method": method, "new": cur.rowcount == 1}


@app.post("/api/sessions/{session_id}/mark")
def mark(session_id: str, req: MarkRequest):
    return _mark(session_id, req.student_id, "FACE", req.confidence)


@app.post("/api/sessions/{session_id}/rf_tap", summary="RF reader tap - accepted only when both cameras failed")
def rf_tap(session_id: str, req: RfTap):
    s = session_row(session_id)
    if s["mode"] != "RF_FALLBACK":
        raise HTTPException(409, "RF reader attendance is used only when both PTZ cameras have failed")
    st = db.q("SELECT student_id, name FROM college_students WHERE rf_card=?", (req.card.strip(),))
    if not st:
        raise HTTPException(404, f"Card {req.card} is not in the college student list")
    return {**_mark(session_id, st[0]["student_id"], "RF"), "name": st[0]["name"]}


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: str, req: EndRequest | None = None):
    s = session_row(session_id)
    t = ts()
    if s["state"] != "ENDED":
        db.x("UPDATE lecture_sessions SET state='ENDED', ended_at=?, unknown_faces=? WHERE session_id=?",
             (t, (req.unknown_faces if req else 0), session_id))
        # everyone on the central system's list who was not seen is ABSENT
        db.x("INSERT OR IGNORE INTO session_attendance(session_id,student_id,status,method,in_session_list,marked_at) "
             "SELECT session_id, student_id, 'ABSENT', 'NONE', 1, ? FROM session_students WHERE session_id=?",
             (t, session_id))
        db.audit("attendance", "SESSION_END", {"session_id": session_id, "mode": s["mode"]})
    return attendance_report(session_id)


# =====================================================================  lecturer override (official duty)
def do_override(session_id, req: OverrideRequest):
    lec = req.lecturer_id.upper()
    if config.LECTURER_ACCOUNTS.get(lec) != req.pin:
        raise HTTPException(403, "Wrong lecturer ID or PIN")
    s = session_row(session_id)
    if s["lecturer_id"] != lec:
        raise HTTPException(403, f"Only the session's lecturer ({s['lecturer_id']}) may override it")
    if s["state"] != "ENDED":
        raise HTTPException(409, "Override is possible after the session has ended")
    deadline = override_deadline(s)
    if ts() > deadline:
        raise HTTPException(409, f"The {config.OVERRIDE_WINDOW_HOURS} h override window closed at {deadline}")
    row = db.q("SELECT * FROM session_attendance WHERE session_id=? AND student_id=?", (session_id, req.student_id))
    if not row or not row[0]["in_session_list"]:
        raise HTTPException(404, "Student is not on this session's list")
    original = row[0]["original_status"] or row[0]["status"]
    db.x("UPDATE session_attendance SET status=?, method='LECTURER_OVERRIDE', override_by=?, override_reason=?, "
         "override_note=?, original_status=?, marked_at=? WHERE session_id=? AND student_id=?",
         (req.new_status, lec, req.reason, req.note, original, ts(), session_id, req.student_id))
    db.audit(lec, "OVERRIDE", {"session_id": session_id, "student_id": req.student_id, "from": row[0]["status"],
                               "to": req.new_status, "reason": req.reason, "note": req.note})
    return {"session_id": session_id, "student_id": req.student_id, "status": req.new_status,
            "original_status": original, "override_open_until": deadline}


@app.post("/api/v1/sessions/{session_id}/override", summary="Lecturer override within 2 days of the session")
def override(session_id: str, req: OverrideRequest):
    return do_override(session_id, req)


@app.get("/lecturer", response_class=HTMLResponse)
def lecturer_page(session_id: str = "", msg: str = ""):
    e = html.escape
    sessions = [s for s in list_sessions() if s["state"] == "ENDED"][:20]
    opts = "".join(f"<option value='{e(s['session_id'])}' {'selected' if s['session_id'] == session_id else ''}>"
                   f"{e(s['date'])} {e(s['start_time'])} {e(s['subject_code'])} ({e(s['lecturer_id'])})</option>"
                   for s in sessions)
    table = ""
    if session_id:
        rep = attendance_report(session_id)
        table = "<table><tr><th>ID</th><th>Name</th><th>Status</th><th>Method</th><th>Override</th></tr>" + "".join(
            f"<tr><td>{e(r['student_id'])}</td><td>{e(r['name'])}</td><td>{e(r['status'])}</td>"
            f"<td>{e(r['method'])}</td><td>{e((r['override'] or {}).get('reason') or '')}</td></tr>"
            for r in rep["records"]) + f"</table><p>Override open until {e(rep['override_open_until'] or '-')}</p>"
    reasons = "".join(f"<option>{r}</option>" for r in OVERRIDE_REASONS)
    return f"""<!doctype html><html><head><meta charset=utf-8><title>Lecturer override</title><style>
body{{font-family:Arial,sans-serif;font-size:15px;margin:24px;background:#f5f7fa;color:#1b2430}}
table{{border-collapse:collapse;background:#fff;margin-top:12px}} td,th{{border:1px solid #cfd6df;padding:5px 9px}}
label{{display:block;margin-top:8px}} input,select{{font-size:15px}} .msg{{font-weight:bold;color:#7a3b00}}</style>
</head><body><h1>Lecturer override (official duty, within {config.OVERRIDE_WINDOW_HOURS} hours)</h1>
<p class=msg>{e(msg)}</p>
<form method=get action=/lecturer><label>Session <select name=session_id>{opts}</select>
<button>Show</button></label></form>{table}
<form method=post action=/lecturer><input type=hidden name=session_id value='{e(session_id)}'>
<label>Lecturer ID <input name=lecturer_id size=8></label><label>PIN <input name=pin type=password size=6></label>
<label>Student ID <input name=student_id size=10></label>
<label>New status <select name=new_status><option>ON_DUTY</option><option>PRESENT</option><option>ABSENT</option>
</select></label><label>Reason <select name=reason>{reasons}</select></label>
<label>Note (event, letter number) <input name=note size=40></label><p><button>Save override</button></p></form>
<p><a href=/>Back to the dashboard</a></p></body></html>"""


@app.post("/lecturer")
def lecturer_submit(session_id: str = Form(...), lecturer_id: str = Form(...), pin: str = Form(...),
                    student_id: str = Form(...), new_status: str = Form(...), reason: str = Form(...),
                    note: str = Form("")):
    try:
        r = do_override(session_id, OverrideRequest(lecturer_id=lecturer_id, pin=pin, student_id=student_id.strip(),
                                                    new_status=new_status, reason=reason, note=note))
        msg = f"Saved: {r['student_id']} is now {r['status']} (was {r['original_status']})"
    except HTTPException as exc:
        msg = f"Not saved: {exc.detail}"
    return RedirectResponse(f"/lecturer?session_id={quote(session_id)}&msg={quote(msg)}", status_code=303)


# =====================================================================  admin: backups and audit
@app.post("/api/admin/backup")
def admin_backup(x_edge_key: str = Header(default="")):
    check_key(x_edge_key)
    entry = backup_now("requested")
    if not entry:
        raise HTTPException(500, f"Backup failed: {backup_state['error']}")
    return entry


@app.get("/api/admin/backups")
def admin_backups():
    out = {}
    for d in backup_dirs():
        man = d / "manifest.json"
        out[str(d)] = json.loads(man.read_text()) if man.exists() else []
    return out


@app.get("/api/admin/audit")
def admin_audit(limit: int = 100):
    ok, bad = db.audit_chain_ok()
    rows = db.q("SELECT id, at, actor, action, detail FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    return {"chain_ok": ok, "first_bad_entry": bad, "entries": [dict(r) for r in rows]}


@app.get("/api/health")
def health():
    return {"status": "ok", "students": len(db.q("SELECT 1 FROM students WHERE status='ACTIVE'")),
            "face_templates": db.index.ntotal if db.index is not None else 0,
            "last_backup": backup_state["last"], "backup_error": backup_state["error"]}


# =====================================================================  dashboard
@app.get("/", response_class=HTMLResponse)
def dashboard():
    e = html.escape
    studs = students()
    thumbs = {}
    for r in db.q("SELECT id, student_id FROM face_templates ORDER BY id"):
        thumbs.setdefault(r["student_id"], []).append(r["id"])
    srows = "".join(
        f"<tr><td>{e(s['student_id'])}</td><td>{e(s['name'])}</td><td>{e(s['class_name'])}</td>"
        f"<td>{''.join(f'<img src=/local/db_image/{i} width=56>' for i in thumbs.get(s['student_id'], []))}</td>"
        f"<td>{e(s['enrolled_at'])}</td><td>{e(s['supervised_by'] or '-')}</td><td>{e(s['device_id'] or '-')}</td></tr>"
        for s in studs) or "<tr><td colspan=7>No students yet</td></tr>"
    sess = list_sessions()[:12]
    sesrows = "".join(
        f"<tr><td>{e(s['session_id'])}</td><td>{e(s['subject_code'])}</td><td>{e(s['lecturer_id'] or '')}</td>"
        f"<td>{e(s['date'])} {e(s['start_time'] or '')}-{e(s['end_time'] or '')}</td><td>{e(s['origin'])}</td>"
        f"<td>{e(s['state'])}</td><td>{e(s['mode'])}</td><td>{s['expected']}</td><td>{s['present']}</td>"
        f"<td>{s['on_duty']}</td><td>{s['not_in_list']}</td>"
        f"<td><a href='/api/v1/sessions/{e(s['session_id'])}/attendance.csv?key={e(config.COLLEGE_API_KEY)}'>CSV</a></td></tr>"
        for s in sess) or "<tr><td colspan=12>No sessions yet. Send them with APP 5 (college central system).</td></tr>"
    ok, _ = db.audit_chain_ok()
    n_master = db.q("SELECT COUNT(*) n FROM college_students")[0]["n"]
    return f"""<!doctype html><html><head><meta charset=utf-8><meta http-equiv=refresh content=5>
<title>Edge AI service</title><style>
body{{font-family:Arial,sans-serif;font-size:15px;margin:24px;background:#f5f7fa;color:#1b2430}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:28px}} table{{border-collapse:collapse;background:#fff}}
td,th{{border:1px solid #cfd6df;padding:6px 10px;text-align:left;vertical-align:middle}} th{{background:#e4eaf2}}
img{{margin-right:4px;border-radius:4px}} .note{{color:#4a5868}} .bad{{color:#a23a10;font-weight:bold}}</style></head><body>
<h1>APP 3 &middot; Edge AI service (face database lives only here)</h1>
<p class=note>Enrolled students: {len(studs)} &middot; face templates: {db.index.ntotal if db.index is not None else 0}
&middot; college student list: {n_master} &middot; database: {e(str(DB_PATH))} &middot; page refreshes every 5 s</p>
<p>Last encrypted backup: <b>{e(backup_state['last'] or 'none yet')}</b> {e(backup_state['last_file'] or '')}
{f"<span class=bad>BACKUP PROBLEM: {e(backup_state['error'])}</span>" if backup_state['error'] else ''}
&middot; audit log chain: {'<b>intact</b>' if ok else '<span class=bad>BROKEN - investigate</span>'}
&middot; <a href=/api/admin/backups>backups</a> &middot; <a href=/api/admin/audit>audit log</a></p>
<p><a href=/lecturer>Lecturer override page</a> &middot; <a href=/docs>API documentation</a></p>
<h2>Lecture sessions (latest 12)</h2>
<table><tr><th>Session</th><th>Subject</th><th>Lecturer</th><th>Time</th><th>From</th><th>State</th><th>Mode</th>
<th>Expected</th><th>Present</th><th>On duty</th><th>Not in list</th><th>Pull</th></tr>{sesrows}</table>
<h2>Enrolled students and their database images (112 x 112)</h2>
<table><tr><th>ID</th><th>Name</th><th>Class</th><th>Database images</th><th>Enrolled</th><th>Supervised by</th>
<th>Device</th></tr>{srows}</table>
</body></html>"""


def main():
    global db
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=config.EDGE_PORT)
    ap.add_argument("--host", default=config.EDGE_HOST)
    args = ap.parse_args()
    db = EdgeDB(DB_PATH)
    ok, bad = db.audit_chain_ok()
    if not ok:
        print(f"!! WARNING: the audit log was changed outside the software (entry {bad}). Investigate.")
    db.audit("system", "START", {"students": len(db.q("SELECT 1 FROM students WHERE status='ACTIVE'"))})
    backup_now("service start")
    threading.Thread(target=backup_loop, daemon=True).start()
    print(f"\n=== APP 3: EDGE AI SERVICE ({config.HALL}) ===\nDatabase : {DB_PATH}\n"
          f"Backups  : {', '.join(str(d) for d in backup_dirs())}\nDashboard: http://{args.host}:{args.port}\n"
          f"Lecturer : http://{args.host}:{args.port}/lecturer\nPress Ctrl+C to stop.\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
