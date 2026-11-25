"""APP 3 - EDGE AI SERVICE  (this laptop plays the Edge AI server in the hall)

* Receives the standard database images + face codes from the Enrolment Converter (office PC)
  and stores them ONLY here, in a local SQLite database, with a FAISS search index in memory.
* Answers "who is this face?" for the Attendance app.
* Keeps attendance sessions and records.
* Pull API for the college central system: GET /api/attendance gives ID, class, time and status
  only. Photos and face codes never leave this service.

Run:   python app3_edge_ai_server.py        (then open http://127.0.0.1:8002)
"""
import argparse
import base64
import csv
import datetime as dt
import html
import io
import sqlite3
import threading
import uuid

import faiss
import numpy as np
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from common import config

DB_PATH = config.DATA_DIR / "edge_ai" / "edge_ai.db"


def now():
    return dt.datetime.now().replace(microsecond=0)


# =====================================================================  database
class EdgeDB:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS students(
                student_id TEXT PRIMARY KEY, name TEXT NOT NULL, class_name TEXT NOT NULL,
                enrolled_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS face_templates(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
                embedding BLOB NOT NULL, db_image BLOB NOT NULL, quality REAL);
            CREATE TABLE IF NOT EXISTS sessions(
                session_id TEXT PRIMARY KEY, class_name TEXT NOT NULL, hall TEXT,
                started_at TEXT NOT NULL, ended_at TEXT);
            CREATE TABLE IF NOT EXISTS attendance(
                session_id TEXT NOT NULL, student_id TEXT NOT NULL, class_name TEXT NOT NULL,
                marked_at TEXT NOT NULL, status TEXT NOT NULL, confidence REAL,
                PRIMARY KEY(session_id, student_id));
        """)
        self.con.execute("PRAGMA foreign_keys=ON")
        self.index = None
        self.index_ids = []
        self.rebuild_index()

    def q(self, sql, args=()):
        with self.lock:
            return self.con.execute(sql, args).fetchall()

    def x(self, sql, args=()):
        with self.lock:
            cur = self.con.execute(sql, args)
            self.con.commit()
            return cur

    # FAISS index: inner product of length-1 face codes = cosine similarity
    def rebuild_index(self):
        with self.lock:
            rows = self.con.execute("SELECT student_id, embedding FROM face_templates").fetchall()
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
app = FastAPI(title="PTZ demo - Edge AI service",
              description="Face database lives only here. The college central system pulls "
                          "attendance (ID, class, time, status) from GET /api/attendance.")


# =====================================================================  models
class Template(BaseModel):
    embedding: list[float]
    image_jpg_b64: str
    quality: float = 0.0


class EnrolRequest(BaseModel):
    student_id: str = Field(pattern=r"^[A-Za-z0-9_\-]{1,32}$")
    name: str = Field(min_length=1, max_length=80)
    class_name: str = Field(min_length=1, max_length=40)
    templates: list[Template] = Field(min_length=1, max_length=20)
    replace: bool = True


class IdentifyRequest(BaseModel):
    embeddings: list[list[float]]


class SessionRequest(BaseModel):
    class_name: str = Field(min_length=1, max_length=40)
    hall: str = "Laptop hall"


class MarkRequest(BaseModel):
    student_id: str
    confidence: float = 0.0


def check_key(key):
    if key != config.EDGE_PUSH_KEY:
        raise HTTPException(401, "Wrong or missing X-Edge-Key")


# =====================================================================  enrolment (from office)
@app.post("/api/enrol")
def enrol(req: EnrolRequest, x_edge_key: str = Header(default="")):
    check_key(x_edge_key)
    vecs = np.array([t.embedding for t in req.templates], dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    # refuse if these faces already belong to a DIFFERENT student
    for sid, score in db.search(vecs):
        if sid and sid != req.student_id and score >= config.DUPLICATE_THRESHOLD:
            name = db.q("SELECT name FROM students WHERE student_id=?", (sid,))[0]["name"]
            raise HTTPException(409, f"This face is already enrolled as {sid} ({name}), similarity {score:.2f}")
    with db.lock:
        if req.replace:
            db.con.execute("DELETE FROM face_templates WHERE student_id=?", (req.student_id,))
        db.con.execute("INSERT INTO students(student_id,name,class_name,enrolled_at) VALUES(?,?,?,?) "
                       "ON CONFLICT(student_id) DO UPDATE SET name=excluded.name, class_name=excluded.class_name, "
                       "enrolled_at=excluded.enrolled_at",
                       (req.student_id, req.name.strip(), req.class_name.strip().upper(), now().isoformat(" ")))
        for t, v in zip(req.templates, vecs):
            db.con.execute("INSERT INTO face_templates(student_id,embedding,db_image,quality) VALUES(?,?,?,?)",
                           (req.student_id, v.tobytes(), base64.b64decode(t.image_jpg_b64), t.quality))
        db.con.commit()
        db.rebuild_index()
    print(f"[edge] stored {req.student_id} {req.name} ({len(vecs)} database images)")
    return {"status": "stored", "student_id": req.student_id, "templates": len(vecs)}


@app.get("/api/students")
def students():
    rows = db.q("SELECT s.student_id, s.name, s.class_name, s.enrolled_at, COUNT(t.id) AS templates "
                "FROM students s LEFT JOIN face_templates t USING(student_id) GROUP BY s.student_id "
                "ORDER BY s.class_name, s.student_id")
    return [dict(r) for r in rows]


@app.delete("/api/students/{student_id}")
def delete_student(student_id: str, x_edge_key: str = Header(default="")):
    check_key(x_edge_key)
    db.x("DELETE FROM face_templates WHERE student_id=?", (student_id,))
    db.x("DELETE FROM students WHERE student_id=?", (student_id,))
    db.rebuild_index()
    return {"status": "deleted", "student_id": student_id}


@app.get("/local/db_image/{template_id}")
def db_image(template_id: int):
    """Database image for the local dashboard on this machine only."""
    rows = db.q("SELECT db_image FROM face_templates WHERE id=?", (template_id,))
    if not rows:
        raise HTTPException(404)
    return Response(rows[0]["db_image"], media_type="image/jpeg")


# =====================================================================  recognition (for app 4)
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


# =====================================================================  sessions + attendance
@app.post("/api/sessions")
def start_session(req: SessionRequest):
    sid = now().strftime("S%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    db.x("INSERT INTO sessions(session_id,class_name,hall,started_at) VALUES(?,?,?,?)",
         (sid, req.class_name.strip().upper(), req.hall, now().isoformat(" ")))
    enrolled = db.q("SELECT COUNT(*) n FROM students WHERE class_name=?", (req.class_name.strip().upper(),))[0]["n"]
    return {"session_id": sid, "class_name": req.class_name.strip().upper(), "enrolled": enrolled}


@app.post("/api/sessions/{session_id}/mark")
def mark(session_id: str, req: MarkRequest):
    s = db.q("SELECT * FROM sessions WHERE session_id=?", (session_id,))
    if not s:
        raise HTTPException(404, "No such session")
    if s[0]["ended_at"]:
        raise HTTPException(409, "Session already ended")
    st = db.q("SELECT class_name FROM students WHERE student_id=?", (req.student_id,))
    if not st:
        raise HTTPException(404, "Unknown student")
    cur = db.x("INSERT OR IGNORE INTO attendance(session_id,student_id,class_name,marked_at,status,confidence) "
               "VALUES(?,?,?,?,?,?)", (session_id, req.student_id, st[0]["class_name"],
                                       now().isoformat(" "), "PRESENT", req.confidence))
    return {"status": "PRESENT", "new": cur.rowcount == 1}


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: str):
    s = db.q("SELECT * FROM sessions WHERE session_id=?", (session_id,))
    if not s:
        raise HTTPException(404, "No such session")
    t = now().isoformat(" ")
    if not s[0]["ended_at"]:
        db.x("UPDATE sessions SET ended_at=? WHERE session_id=?", (t, session_id))
        # everyone of this class who was not seen is ABSENT
        db.x("INSERT OR IGNORE INTO attendance(session_id,student_id,class_name,marked_at,status,confidence) "
             "SELECT ?, student_id, class_name, ?, 'ABSENT', 0 FROM students WHERE class_name=?",
             (session_id, t, s[0]["class_name"]))
    return session_report(session_id)


@app.get("/api/sessions")
def list_sessions():
    rows = db.q("SELECT s.*, SUM(a.status='PRESENT') AS present, SUM(a.status='ABSENT') AS absent "
                "FROM sessions s LEFT JOIN attendance a USING(session_id) GROUP BY s.session_id "
                "ORDER BY s.started_at DESC")
    return [dict(r) for r in rows]


@app.get("/api/sessions/{session_id}")
def session_report(session_id: str):
    s = db.q("SELECT * FROM sessions WHERE session_id=?", (session_id,))
    if not s:
        raise HTTPException(404, "No such session")
    rows = db.q("SELECT a.student_id, st.name, a.status, a.marked_at, a.confidence FROM attendance a "
                "LEFT JOIN students st USING(student_id) WHERE a.session_id=? ORDER BY a.status DESC, a.student_id",
                (session_id,))
    return {**dict(s[0]), "records": [dict(r) for r in rows]}


def _attendance_rows(date, session_id, class_name):
    sql = ("SELECT a.student_id, a.class_name, a.session_id, a.marked_at AS time, a.status "
           "FROM attendance a WHERE 1=1")
    args = []
    if date:
        sql += " AND substr(a.marked_at,1,10)=?"
        args.append(date)
    if session_id:
        sql += " AND a.session_id=?"
        args.append(session_id)
    if class_name:
        sql += " AND a.class_name=?"
        args.append(class_name.upper())
    return [dict(r) for r in db.q(sql + " ORDER BY a.marked_at, a.student_id", args)]


@app.get("/api/attendance", summary="PULL API for the college central system (no photos)")
def attendance(date: str | None = Query(None, description="YYYY-MM-DD"),
               session_id: str | None = None, class_name: str | None = None):
    return _attendance_rows(date, session_id, class_name)


@app.get("/api/attendance.csv", response_class=PlainTextResponse)
def attendance_csv(date: str | None = None, session_id: str | None = None, class_name: str | None = None):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["student_id", "class_name", "session_id", "time", "status"])
    w.writeheader()
    w.writerows(_attendance_rows(date, session_id, class_name))
    return buf.getvalue()


@app.get("/api/health")
def health():
    return {"status": "ok", "students": len(db.q("SELECT 1 FROM students")),
            "face_templates": db.index.ntotal if db.index is not None else 0}


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
        f"<td>{e(s['enrolled_at'])}</td></tr>" for s in studs) or "<tr><td colspan=5>No students yet</td></tr>"
    sess = list_sessions()[:10]
    sesrows = "".join(
        f"<tr><td><a href='/api/sessions/{e(s['session_id'])}'>{e(s['session_id'])}</a></td><td>{e(s['class_name'])}</td>"
        f"<td>{e(s['started_at'])}</td><td>{e(s['ended_at'] or 'running')}</td>"
        f"<td>{s['present'] or 0}</td><td>{s['absent'] or 0}</td></tr>" for s in sess) \
        or "<tr><td colspan=6>No sessions yet</td></tr>"
    return f"""<!doctype html><html><head><meta charset=utf-8><meta http-equiv=refresh content=5>
<title>Edge AI service</title><style>
body{{font-family:Arial,sans-serif;font-size:15px;margin:24px;background:#f5f7fa;color:#1b2430}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:28px}} table{{border-collapse:collapse;background:#fff}}
td,th{{border:1px solid #cfd6df;padding:6px 10px;text-align:left;vertical-align:middle}} th{{background:#e4eaf2}}
img{{margin-right:4px;border-radius:4px}} .note{{color:#4a5868}}</style></head><body>
<h1>APP 3 &middot; Edge AI service (face database lives only here)</h1>
<p class=note>Students: {len(studs)} &middot; face templates in FAISS: {db.index.ntotal if db.index is not None else 0}
&middot; database file: {e(str(DB_PATH))} &middot; page refreshes every 5 s</p>
<p>College pull API: <a href=/api/attendance>/api/attendance</a> (JSON) &middot;
<a href=/api/attendance.csv>/api/attendance.csv</a> &middot; <a href=/docs>API documentation</a></p>
<h2>Enrolled students and their database images (112 x 112)</h2>
<table><tr><th>ID</th><th>Name</th><th>Class</th><th>Database images</th><th>Enrolled</th></tr>{srows}</table>
<h2>Attendance sessions (latest 10)</h2>
<table><tr><th>Session</th><th>Class</th><th>Started</th><th>Ended</th><th>Present</th><th>Absent</th></tr>{sesrows}</table>
</body></html>"""


def main():
    global db
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=config.EDGE_PORT)
    ap.add_argument("--host", default=config.EDGE_HOST)
    args = ap.parse_args()
    db = EdgeDB(DB_PATH)
    print(f"\n=== APP 3: EDGE AI SERVICE ===\nDatabase : {DB_PATH}\nDashboard: http://{args.host}:{args.port}\n"
          f"Pull API : http://{args.host}:{args.port}/api/attendance\nPress Ctrl+C to stop.\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
