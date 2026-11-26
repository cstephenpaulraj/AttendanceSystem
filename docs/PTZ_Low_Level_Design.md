# PTZ Low-Level Design: the four software products

AI-Driven Classroom Attendance System, PTZ taught-point concept. Version 1.0, 26 November 2026.

This document gives the low-level design of the four software products of the PTZ concept. It follows [PTZ_Implementation.md](PTZ_Implementation.md) (the design) and the laptop demo in `ptz_laptop_demo/` (the reference implementation). For each product it gives the modules, data, interfaces, algorithms, states, error handling, configuration and tests. Where the production build differs from the demo, both are stated.

| # | Software | Runs on | Production technology | Demo reference |
|---|---|---|---|---|
| S1 | Enrolment App | Dedicated college enrolment phone (Android, kiosk) | Flutter (Android), on-device liveness, AES-256 | `app1_face_capture.py` |
| S2 | Enrolment Converter | Our office PC (Windows) | Python 3.12 + PySide6, ONNX Runtime (CPU), OpenCV | `app2_enrolment_converter.py` |
| S3 | Edge AI Service | Edge AI server (Ubuntu, GPU) in the college server room | Python 3.12 + FastAPI, PostgreSQL 16 + pgvector, restic, React web UI | `app3_edge_ai_server.py` |
| S4 | Attendance Engine | Edge AI server (same machine as S3) | Python 3.12 services, CUDA + TensorRT, ONVIF / Matrix SDK camera drivers | `app4_attendance.py` |

The college central system is not our software. The demo plays it with `app5_central_system.py` (Section 8) so that the four products can be tested end to end.

## 1. Context and data flow

```
 College enrolment phone (S1) --(1) encrypted photo package--> Office PC: Enrolment Converter (S2)
 Office PC (S2) --(2) signed face templates over VPN--> Edge AI Service (S3)
 College central system --(3) student list + lecture sessions--> Edge AI Service (S3)
 Attendance Engine (S4) <--(4) identify / mark / RF taps / session state--> Edge AI Service (S3)
 PTZ cameras (primary, standby) --(5) frames--> Attendance Engine (S4)
 Existing RF readers --(6) card taps, only in RF fallback--> Attendance Engine (S4)
 College central system <--(7) session attendance (pull)-- Edge AI Service (S3)
 Lecturers (browser) --(8) override within 48 h--> Edge AI Service (S3)
 Edge AI Service (S3) --(9) encrypted backups--> backup disk / NAS / offline drive
```

Rules that every product enforces:

| Rule | Enforced by |
|---|---|
| Enrolment only on a registered college phone, under a logged-in college staff member who has checked the ID card | S1, S2, S3 |
| Photos never stay on the phone; they stay on the office PC only until S3 confirms storage | S1, S2 |
| The live face database exists only in S3; backups are encrypted | S3 |
| The central system receives attendance only, never photos, face images or templates | S3 |
| RF taps are accepted only when both PTZ cameras have failed | S3, S4 |
| Lecturer override only for the session's own lecturer, listed students, within 48 hours | S3 |

## 2. Shared components

### 2.1 Face engine (S1 quality checks, S2, S4)

| Function | Input | Output | Notes |
|---|---|---|---|
| detect(image) | BGR image | N x 15 array: x, y, w, h, 5 landmarks (10 numbers), score | Demo: OpenCV YuNet (MIT). Production: SCRFD-class detector with a commercial licence, TensorRT FP16 |
| quality(image, face) | image, face row | size (min of w, h), sharpness (Laplacian variance of the face resized to 112 x 112, grey), brightness (mean grey), score | Same formula in S1 (live guidance) and S2 (acceptance) |
| quality_problem(q) | quality figures | first failing reason or none | Order: size, dark, bright, blurred, detector score |
| align(image, face) | image, face row | 112 x 112 aligned face (the "database image") | 5-point similarity transform |
| embed_aligned(aligned) | 112 x 112 face | 128-float face code, L2-normalised | Demo: SFace (Apache-2.0). Production: ArcFace-class model, 512 floats, commercial licence |

Model version: every template carries the model name and version. S3 refuses templates whose model version differs from its own (production; the demo has one fixed model).

### 2.2 Thresholds (demo defaults in `common/config.py`, all overridable by environment variables)

| Name | Value | Used in | Meaning |
|---|---|---|---|
| MIN_FACE_PX_ENROL | 90 | S1, S2 | Smallest face width for enrolment (the phone kit gives 600 or more) |
| MIN_SHARPNESS | 60.0 | S1, S2 | Laplacian variance of the 112 x 112 face |
| MIN_BRIGHTNESS / MAX_BRIGHTNESS | 50 / 215 | S1, S2 | Mean grey of the face |
| MIN_DETECTION_SCORE | 0.85 | S1, S2 | Detector confidence for an enrolment photo |
| PHOTOS_PER_STUDENT / MIN_GOOD_PHOTOS | 5 / 3 | S1 / S2 | Photos taken / good photos needed |
| SAME_PERSON_MIN | 0.45 | S2, S3 | Each photo against the mean of the set; re-enrolment against the old templates |
| DUPLICATE_THRESHOLD | 0.55 | S3 | A new student's face matching another ID at or above this is refused |
| MATCH_THRESHOLD | 0.40 | S3 | Cosine similarity needed to identify a face in a lecture |
| CONFIRM_FRAMES | 3 | S4 | Frames a student must be identified in before marking |
| MIN_FACE_PX_ATTEND / DETECTOR_SCORE | 40 / 0.80 | S4 | Faces smaller or less certain are ignored |
| OVERRIDE_WINDOW_HOURS | 48 | S3 | Lecturer override window after the session end |
| BACKUP_CHECK_SEC / BACKUP_KEEP | 30 / 14 | S3 | Backup delay after a change / copies kept per folder |

Production values are tuned in the pilot with the production model; the demo values suit SFace.

### 2.3 Enumerations

| Enumeration | Values |
|---|---|
| Attendance status | PRESENT, ABSENT, ON_DUTY, NOT_IN_LIST (and NOT_YET_SEEN in reports of a running session) |
| Attendance method | FACE, RF, LECTURER_OVERRIDE, NONE |
| Session origin | CENTRAL (sent by the central system), LOCAL (started at the Edge AI) |
| Session state | SCHEDULED, RUNNING, ENDED |
| Session mode | CAMERA, STANDBY_CAMERA, RF_FALLBACK |
| Override reason | PAPER_PRESENTATION, SPORTS, OTHER_OFFICIAL_DUTY, CORRECTION |
| Student status | ACTIVE, DELETED (soft delete) |
| Converter job status | RECEIVED, STORED ON EDGE AI, WAITING FOR EDGE AI, REJECTED (with reason) |

## 3. S1 Enrolment App (dedicated college phone)

### 3.1 Purpose

Capture 5 good enrolment photos of one student at a time, only under a logged-in college staff member, on a registered college phone, and deliver them encrypted to the Enrolment Converter. Nothing is kept on the phone after delivery.

### 3.2 Modules

| Module | Responsibility | Demo function |
|---|---|---|
| Kiosk shell | Locks the phone to the app (Android Enterprise / Knox), blocks screenshots and gallery | (not in demo) |
| Staff session | Staff ID + PIN (production: college login + OTP); idle timeout 5 minutes; one staff member per sitting | `staff_login()` |
| Student identification | Student ID entry or ID card barcode scan; ID card confirmation by staff (Y/N) | `live_mode()`, `id_card_confirmed()` |
| Guided capture | Live preview, face box, quality guidance, 5 poses, manual or auto shutter (1 per second while good) | `capture_live()` |
| Liveness | Passive liveness on device (production); refuses photos of photos and screens | (not in demo) |
| Packager | JPEG quality 95; AES-256-GCM package with the office public key; HMAC with the device key | `send_to_office()` (multipart upload in the demo) |
| Outbox | Keeps undelivered packages encrypted; resend on reconnect; deletes after the converter's answer | `report()`, `resend()` (`data/capture_outbox`) |
| Batch import (demo only) | Sends sample photo folders for testing | `photo_mode()`, `read_photos()` |

### 3.3 Capture state machine (per student)

| State | Event | Next state |
|---|---|---|
| IDLE | staff enters student ID and name | ID_CHECK |
| ID_CHECK | staff confirms ID card matches | CAPTURING |
| ID_CHECK | staff answers No | IDLE (nothing captured) |
| CAPTURING | good frame and SPACE (or auto, 1 s apart) | CAPTURING (photo n + 1) |
| CAPTURING | 5 photos taken | SENDING |
| CAPTURING | ESC | IDLE (photos discarded) |
| SENDING | converter answers | RESULT (stored, waiting or rejected with reasons) |
| SENDING | converter not reachable | QUEUED (outbox) |
| RESULT / QUEUED | | IDLE |

Live guidance messages, in order: "no face - look at the camera", "only one person in front of the camera", then the quality_problem() reasons. The shutter works only when there is exactly one face and no quality problem.

### 3.4 Interface: upload to the Enrolment Converter

`POST {OFFICE_URL}/api/upload` (multipart form; production: HTTPS with client certificate of the phone)

| Field | Type | Rule |
|---|---|---|
| student_id | text | `^[A-Za-z0-9_-]{1,32}$` |
| name, class_name | text | required |
| staff_id, staff_pin | text | valid college staff account (production: signed staff token instead of the PIN) |
| device_id | text | registered enrolment phone, for example COLLEGE-PHONE-01 |
| id_card_checked | boolean | must be true |
| photos | 1 to 20 JPEG files | 5 in normal use |

Answer: the converter job (Section 4.4). HTTP 403 for an unregistered phone or wrong staff login, 400 for a missing ID card confirmation.

### 3.5 Errors

| Situation | Behaviour |
|---|---|
| Wrong staff login | App stops before any capture |
| Camera cannot open | Message; staff may retry or switch camera |
| Office not reachable | Package kept in the encrypted outbox; resend later; deleted after the answer |
| Converter rejects photos | Reasons shown per photo; staff recaptures |

### 3.6 Configuration and tests

Configuration: OFFICE_URL, ENROLMENT_DEVICE_ID, PHOTOS_PER_STUDENT, camera index and resolution (demo); production adds the office public key, device key and MDM policy.

| Test | Expected |
|---|---|
| Wrong PIN | Stops; nothing sent |
| ID card not confirmed | Student skipped |
| Unregistered device ID | Converter refuses (403) |
| Office PC down | Package in outbox; resend delivers and empties the outbox |

## 4. S2 Enrolment Converter (office PC)

### 4.1 Purpose

Accept enrolment packages only from registered college phones and logged-in staff, check every photo, convert good photos into standard database images and face templates, push them to the Edge AI Service, and wipe the photos once the Edge AI confirms.

### 4.2 Modules

| Module | Responsibility | Demo function |
|---|---|---|
| Receiver | HTTPS endpoint (production: also the secure upload folder); validates device, staff, ID card flag, ID format; writes photos to the job inbox | `upload()` |
| Converter | Per photo: exactly one face, quality_problem(), alignment, template; then same-person check over the set | `convert()` |
| Job processor | Needs MIN_GOOD_PHOTOS good photos; builds the push batch | `process()` |
| Pusher | Sends the signed batch to S3; classifies the answer | `push_to_edge()`, `try_push()` |
| Retry loop | Every 30 s retries jobs WAITING FOR EDGE AI | `retry_loop()` |
| Wiper | Deletes the job folder after S3's receipt or after a final rejection | inside `try_push()`, `process()` |
| Job log | JSON log of jobs without photos (ID, name, class, staff, device, counts, reasons, status, times) | `save_log()`, `jobs.json` |
| Dashboard | Job list, photos currently on disk (should be 0) | `dashboard()` |

### 4.3 Conversion algorithm

1. For each photo: decode; detect; reject "no face found" or "N faces - only the student may be in the photo"; compute quality; reject with the quality reason.
2. For each good photo: align to 112 x 112; template = embed_aligned().
3. If 2 or more good photos: mean of the templates, normalised; reject photos whose similarity to the mean is below SAME_PERSON_MIN ("does not look like the same person as the other photos").
4. If fewer than MIN_GOOD_PHOTOS remain: job REJECTED, photos wiped, retake requested.
5. Otherwise build the batch: student ID, name, class, supervised_by, device_id, and for each photo the template, the quality (sharpness) and the database image (JPEG, base64).

### 4.4 Job record

| Field | Example |
|---|---|
| job_id | 20261126091512-a3f9c1 |
| student_id, name, class_name | S001, Asha, MBBS1 |
| supervised_by, device_id | STAFF01, COLLEGE-PHONE-01 |
| received_at, pushed_at | times |
| photos, accepted | 5, 5 |
| rejected | list of {photo, reason} |
| status | STORED ON EDGE AI - local photos wiped |

### 4.5 Interface: push to the Edge AI Service

`POST {EDGE_URL}/api/enrol`, header `X-Edge-Key` (production: WireGuard VPN plus mutual TLS and a signed batch).

Answer handling:

| S3 answer | Converter action |
|---|---|
| 200 stored | Wipe photos; status STORED |
| 400, 401, 403, 409, 422 (refused: duplicate face, different face on re-enrolment, ID not on the college list, unknown staff or phone, wrong key, bad data) | Final: status REJECTED with S3's reason; wipe photos |
| Not reachable or 5xx | Keep photos; status WAITING; retry every 30 s; jobs found WAITING or RECEIVED at start-up are processed again |

### 4.6 Other interfaces

| Request | Returns |
|---|---|
| GET /api/jobs | Job list (no photos) |
| GET /api/health | status, photos_on_disk |
| GET / | Dashboard |

### 4.7 Tests

| Test | Expected |
|---|---|
| Photo with 2 faces | That photo rejected with the reason |
| Fewer than 3 good photos | Job rejected, photos wiped |
| Edge AI off during push | WAITING, retried after 30 s, then stored and wiped |
| Edge refuses (duplicate) | REJECTED with "already enrolled as ..." |
| After a successful push | photos_on_disk = 0 |

## 5. S3 Edge AI Service (Edge AI server)

### 5.1 Purpose

Hold the only live face database; receive the student list and lecture sessions from the central system; serve identification to the Attendance Engine; keep per-session attendance with method and overrides; give the central system attendance at any time; protect everything with backups, integrity checks and an audit log.

### 5.2 Modules

| Module | Responsibility | Demo function / object |
|---|---|---|
| Storage | Database access with one lock; schema creation and migration; integrity check at start | `EdgeDB.__init__`, `q()`, `x()`, `integrity_problem()` |
| Face index | In-memory search index over ACTIVE students' templates; best score per student | `rebuild_index()`, `search()` (FAISS IndexFlatIP; production pgvector or FAISS on GPU) |
| Enrolment API | Validates staff, device, college list, duplicate face, same face on re-enrolment; stores templates and database images | `enrol()` |
| Student admin | List; two-person soft delete; restore | `students()`, `delete_student()`, `restore_student()` |
| Central system API | Student list in; sessions in; sessions and attendance out (JSON, CSV) | `put_college_students()`, `post_sessions()`, `list_sessions_api()`, `get_session_attendance()`, `get_session_attendance_csv()`, `get_attendance()` |
| Session manager | Current session for a hall; LOCAL sessions; start; mode changes; end (ABSENT fill) | `current_session()`, `start_local_session()`, `start_session()`, `set_mode()`, `end_session()` |
| Marking | Identify faces; mark FACE; accept RF taps only in RF_FALLBACK; PRESENT vs NOT_IN_LIST | `identify()`, `_mark()`, `mark()`, `rf_tap()` |
| Reports | Session report with counts, records, override details | `attendance_report()`, `list_sessions()` |
| Override | Lecturer checks, 48 h window, history, audit; web page | `do_override()`, `override()`, `lecturer_page()`, `lecturer_submit()` |
| Backup | Consistent copy, integrity check, encrypt, write to every backup folder, manifest, retention | `backup_now()`, `backup_loop()`, `backup_key()` |
| Audit | Hash-chained log; chain verification | `audit()`, `audit_chain_ok()`, `admin_audit()` |
| Web UI | Dashboard, lecturer page, health | `dashboard()`, `health()` |

### 5.3 Data model

Demo: SQLite (WAL). Production: PostgreSQL 16 with pgvector on an encrypted disk (LUKS), RAID-1.

| Table | Columns | Keys and notes |
|---|---|---|
| students | student_id, name, class_name, enrolled_at, supervised_by, device_id, status (ACTIVE / DELETED), deleted_at, deleted_by | PK student_id. Enrolled students only |
| face_templates | id, student_id, embedding (float32 blob; production vector(512)), db_image (112 x 112 JPEG), quality | FK student_id (cascade). Production adds model_version |
| college_students | student_id, name, class_name, rf_card, updated_at | PK student_id; rf_card unique. Sent by the central system |
| lecture_sessions | session_id, subject_code, subject_name, lecturer_id, lecturer_name, hall, date, start_time, end_time, origin, state, mode, mode_reason, started_at, ended_at, unknown_faces, received_at | PK session_id |
| session_students | session_id, student_id | PK both. The central system's list for the session |
| session_attendance | session_id, student_id, status, method, in_session_list, marked_at, confidence, override_by, override_reason, override_note, original_status | PK (session_id, student_id). First mark wins (insert-or-ignore) |
| audit_log | id, at, actor, action, detail (JSON), prev_hash, hash | hash = SHA-256(prev_hash, at, actor, action, detail); first prev_hash = GENESIS |

Production adds: halls, cameras, taught_points (Section 6.3), users and roles, model_versions, and the backup run log.

### 5.4 Interfaces

Central system (header `X-College-Key`; production: mutual TLS or OAuth client credentials agreed with college IT):

| Method and path | Body / parameters | Answer |
|---|---|---|
| PUT /api/v1/students | [{student_id, name, class_name, rf_card}] | {status, students} |
| POST /api/v1/sessions | [{session_id, subject_code, subject_name, lecturer_id, lecturer_name, hall, date, start_time, end_time, students[]}] | per session: stored, or "not changed: session already RUNNING / ENDED" |
| GET /api/v1/sessions | date, hall, state (all optional) | sessions with expected, present, on_duty, not_in_list |
| GET /api/v1/sessions/{session_id}/attendance | | {session, override_open_until, counts, records[]} |
| GET /api/v1/sessions/{session_id}/attendance.csv | key | CSV: session_id, subject_code, date, hall, lecturer_id, student_id, name, status, method, in_session_list, time, override_reason |
| GET /api/v1/attendance | date (required), subject_code, hall | list of session reports |

Attendance record fields: student_id, name, status, method, in_session_list, face_enrolled, time, override {by, reason, note, original_status} or null.

Enrolment Converter (header `X-Edge-Key`):

| Method and path | Body | Answer / refusals |
|---|---|---|
| POST /api/enrol | {student_id, name, class_name, supervised_by, device_id, templates[{embedding, image_jpg_b64, quality}]} | 200 stored; 403 unknown staff or phone; 409 not on the college list, duplicate face, different face on re-enrolment |
| POST /api/students/{id}/delete | {requested_by, requested_pin, approved_by, approved_pin, reason} | 403 if the same person or a wrong PIN; soft delete |
| POST /api/students/{id}/restore | form: staff_id, pin | restored |

Attendance Engine (internal, Edge AI server only; production: local socket or loopback with a service token):

| Method and path | Body | Answer |
|---|---|---|
| GET /api/sessions/current?hall= | | Running session, else the one on now, else the next one today; 404 if none |
| POST /api/sessions/local | {class_name, hall, lecturer_id} | New LOCAL session; list = college students and enrolled students of the class |
| POST /api/sessions/{id}/start | | SCHEDULED to RUNNING (409 if ENDED); returns the session and expected count |
| POST /api/sessions/{id}/mode | {mode, reason} | Mode stored and audited |
| POST /api/identify | {embeddings[][]} | per face: {student_id, name, class_name, score} or student_id null |
| POST /api/sessions/{id}/mark | {student_id, confidence} | {status PRESENT or NOT_IN_LIST, method FACE, new} |
| POST /api/sessions/{id}/rf_tap | {card} | 409 unless mode is RF_FALLBACK; 404 unknown card; else as mark with method RF |
| POST /api/sessions/{id}/end | {unknown_faces} | ENDED; listed students without a mark become ABSENT; session report |

Lecturers and admin:

| Method and path | Use |
|---|---|
| GET/POST /lecturer | Override web page |
| POST /api/v1/sessions/{id}/override | {lecturer_id, pin, student_id, new_status, reason, note} |
| POST /api/admin/backup, GET /api/admin/backups | Backup now; list manifests |
| GET /api/admin/audit | Audit entries and chain status |
| GET /api/health, GET / | Health; dashboard |

### 5.5 Enrolment checks (in this order)

1. X-Edge-Key valid (401).
2. supervised_by is a registered staff member; device_id is a registered enrolment phone (403).
3. If the college student list is loaded, the ID must be on it (409); name and class are taken from the list.
4. Templates normalised. For each template, the best other student in the index: if similarity is at least DUPLICATE_THRESHOLD, refuse ("already enrolled as ...") and audit ENROL_REFUSED.
5. If the student is already ACTIVE: the best similarity between new and old templates must be at least SAME_PERSON_MIN, otherwise refuse ("two staff must delete the old enrolment first").
6. In one transaction: replace the student's templates, upsert the student (ACTIVE, staff, device, time); rebuild the index; set the backup-dirty flag; audit ENROL or RE_ENROL.

### 5.6 Marking rules

| Input | Rule | Result |
|---|---|---|
| Face identified (score at least MATCH_THRESHOLD, seen in CONFIRM_FRAMES frames) | Student on session list | PRESENT, FACE |
| Same | Enrolled but not on the list | NOT_IN_LIST, FACE (reported to the central system) |
| Score below MATCH_THRESHOLD | | Unknown; counted (most at once) in unknown_faces |
| RF tap | Session mode must be RF_FALLBACK; card must map to a college student | PRESENT or NOT_IN_LIST, RF |
| Session end | Listed students without a mark | ABSENT, NONE |
| Repeated marks | First mark wins | unchanged |

### 5.7 Session state machine

| From | Event | To |
|---|---|---|
| (none) | central system sends the session, or a lecturer starts a LOCAL session | SCHEDULED |
| SCHEDULED | central system re-sends | SCHEDULED (details and list replaced) |
| SCHEDULED | Attendance Engine starts it | RUNNING |
| RUNNING | mode change (camera failure) | RUNNING (mode CAMERA, STANDBY_CAMERA or RF_FALLBACK) |
| RUNNING | end time, lecturer ends, or engine ends | ENDED |
| RUNNING / ENDED | central system re-sends | unchanged ("not changed: session already ...") |
| ENDED | lecturer override within 48 h | ENDED (records changed, history kept) |

### 5.8 Override algorithm

1. Lecturer ID and PIN valid (production: college login with lecturer role); else 403.
2. Lecturer must equal the session's lecturer_id; else 403.
3. Session must be ENDED; else 409.
4. Now must be before ended_at + OVERRIDE_WINDOW_HOURS; else 409 with the closing time.
5. Student must be on the session's list; else 404.
6. Keep original_status (the first status before any override), set the new status, method LECTURER_OVERRIDE, override_by, reason, note, time; audit OVERRIDE with from and to.

### 5.9 Backup and recovery

| Step | Detail |
|---|---|
| Trigger | At start; within BACKUP_CHECK_SEC of any face data change (enrol, delete, restore); on request. Production adds a nightly run |
| Copy | Online backup API into a temporary file (production: pg_dump or a restic snapshot) |
| Verify | integrity_check on the copy; counts of ACTIVE students and templates |
| Encrypt | Fernet (AES-128-CBC + HMAC-SHA256) in the demo; restic AES-256 in production. Key file kept apart from the data (production: split key, offline) |
| Write | To every backup folder (BACKUP_DIR, optional BACKUP_DIR2; production: NAS and the monthly offline drive) with manifest.json {file, at, reason, students, templates, sha256_encrypted, sha256_plain} |
| Retain | Newest BACKUP_KEEP per folder (production: 14 daily, 8 weekly, 12 monthly) |
| Report | Dashboard and /api/health show the last backup and any error; audit BACKUP |
| Restore | `tools/restore_backup.py`: list and verify each copy (file present, checksum, decrypt, content checksum, integrity_check); refuse while S3 runs; restore the newest good copy; keep the damaged database as edge_ai.db.damaged-time |
| Start-up guard | If the database fails integrity_check, S3 refuses to start and points to the restore tool |

### 5.10 Security

Keys per caller (X-Edge-Key, X-College-Key; production mutual TLS); staff and lecturer accounts (production: college login with roles and OTP); photos and templates never in any central-system answer; database images served only to the local dashboard; two-person delete; audit of every change; encrypted disk and backups.

### 5.11 Tests

| Test | Expected |
|---|---|
| Student list and 3 sessions sent | Stored; sessions listed |
| Pull without key | 401 |
| Enrol ID not on the list / duplicate face / different face on re-enrolment | 409 each |
| Delete with the same staff twice | 403; with two staff: soft delete, index rebuilt; restore works |
| RF tap while a camera works | 409 |
| Override by another lecturer / after 48 h | 403 / 409 |
| Damaged database | Refuses to start; restore brings back all students and sessions |
| Audit entry changed in the database | Chain reported broken at that entry |

## 6. S4 Attendance Engine (Edge AI server)

### 6.1 Purpose

Run each lecture session in each hall: drive the primary PTZ camera through its taught points (or the standby camera), recognise faces on the GPU, mark students through S3, switch to the RF readers if both cameras fail, and end the session.

### 6.2 Modules

| Module | Responsibility | Demo function |
|---|---|---|
| Session picker | Session by ID, by subject, the current session of the hall, or a LOCAL session | `pick_session()` |
| Scheduler | Starts each session at its start time plus a delay, or on the lecturer's Scan button (production) | (demo: started by hand) |
| Camera driver layer | Interface: move_to(pan, tilt, zoom, focus), capture(), read_position(), health(); ONVIF and Matrix SDK drivers | `FrameSource` (webcam, photos, video, or "fail") |
| Health and failover | Health check every 10 s; a move that does not reach its point; read failure: switch primary to standby to RF | `CameraFailure`, camera loop in `main()` |
| Sequence engine | Home check, pass 1 over the taught points, revisit pass | (demo: video imitates taught points) |
| Vision pipeline | Detect, size and score filter, align, embed, identify through S3 | inside `run_camera()` |
| Confirmation | Count frames per student; mark after CONFIRM_FRAMES | `state["hits"]` in `run_camera()` |
| RF fallback | Reads card taps (reader interface; demo keyboard wedge or file), posts them to S3 | `run_rf_fallback()` |
| Live view | Picture with coloured boxes and a side panel | `side_panel()` |
| Finaliser | Ends the session with the unknown-face count; prints the report | end of `main()` |

### 6.3 Taught point data (production)

| Field | Example |
|---|---|
| point_id | R07-G3 (row 7, bench group 3) |
| camera_id | HALL1-PRIMARY |
| order | 38 of 76 |
| pan, tilt, zoom | +12.4 degrees, -18.6 degrees, 4.2x |
| focus | stored motor position (locked; no autofocus hunting) |
| seats, expected_faces | R7-S09 to R7-S12, 4 |
| home_target | for point 0 only: reference image and position tolerance |

### 6.4 Session run algorithm

1. Pick the session and call start (SCHEDULED to RUNNING). Load the expected count.
2. Open the primary camera. On failure, set mode STANDBY_CAMERA and open the standby camera. If that fails too, go to step 7.
3. Home check (production): move to point 0, compare with the home target, re-home on drift; alert if the drift stays.
4. Pass 1 (production): for each taught point in order: move to the stored pan, tilt and zoom; set the stored focus; settle about 0.5 s; capture 3 frames; keep the sharpest. About 1.6 s per point.
5. For each frame: detect; drop faces smaller than MIN_FACE_PX_ATTEND; embed; identify through S3. For each identified student, count once per frame; when the count reaches CONFIRM_FRAMES, mark through S3 (PRESENT or NOT_IN_LIST). Track the most unknown faces seen at once.
6. Revisit (production): points with fewer faces than expected, poor faces or unsure matches are visited again at tighter zoom (2 students per frame) after 20 to 30 s. Unresolved students go to the lecturer's review list.
7. If a camera fails during the run (CameraFailure), switch to the next camera; marks already made are kept. If no camera is left: set mode RF_FALLBACK and accept card taps until the session ends. Unknown cards are reported and skipped.
8. End the session in S3 with the unknown-face count. Print or show the report and the override deadline.

### 6.5 Timing (production, one 300-seat hall)

| Step | Time |
|---|---|
| Home check | 10 s |
| Pass 1 | 75 points x 1.6 s, about 120 s (about 130 s including home) |
| Revisit | about 30 s |
| Total | about 2 min 47 s; all 5 halls in parallel. Every student is scanned once in about 2 min 10 s |

### 6.6 Live view colours (demo and production web UI)

Red: unknown face. Yellow: identified, being confirmed (n of 3). Green: PRESENT. Blue: NOT IN LIST.

### 6.7 Errors

| Situation | Behaviour |
|---|---|
| S3 not reachable at start | Stops with a message (production: retries; the scan is re-run in the same window) |
| No session for the hall today | Stops with a hint (send the timetable, or start a LOCAL session) |
| Primary camera fails | Standby camera; mode recorded |
| Both cameras fail | RF fallback; mode recorded |
| RF tap refused (unknown card) | Shown; the session continues |

### 6.8 Configuration and tests

Configuration: EDGE_URL, HALL, CONFIRM_FRAMES, MIN_FACE_PX_ATTEND, DETECTOR_SCORE; demo options --session, --subject, --local-class, --source, --standby, --rf-taps, --hold, --confirm, --duration, --no-window. Production adds the camera list per hall, taught points, scan delay and revisit settings.

| Test | Expected |
|---|---|
| Session 1, primary camera (6 classroom pictures) | 6 of 6 PRESENT, stranger not marked |
| Session 2, primary "fail", standby video | mode STANDBY_CAMERA; 5 PRESENT, 1 NOT_IN_LIST |
| Session 3, both "fail", RF taps file | mode RF_FALLBACK; 5 PRESENT (RF), 1 ABSENT; unknown card refused |
| No webcam present | Both cameras fail; typed cards marked |
| LOCAL session | origin LOCAL in the report |

## 7. End-to-end sequences

### 7.1 Enrolment

1. S1: staff login; student ID; ID card confirmed; 5 photos; encrypted package sent.
2. S2: device, staff and ID card flag checked; photos checked and converted; batch pushed.
3. S3: staff, device, college list, duplicate and re-enrolment checks; stored; receipt; backup within 30 s; audit.
4. S2: photos wiped; job STORED.

### 7.2 Lecture session

1. Central system: PUT students (once and on change); POST sessions (daily or ahead).
2. S4: picks the session at its time; start; camera loop (primary, standby) or RF fallback; marks through S3; end.
3. S3: ABSENT for listed students not seen; report ready.
4. Lecturer: overrides for official duty within 48 hours.
5. Central system: GET the session's attendance at any time, as often as needed.

### 7.3 Recovery

1. S3 refuses to start on a damaged database.
2. Admin runs the restore tool: newest good encrypted backup restored; damaged file kept.
3. S3 starts; no re-enrolment needed.

## 8. Test harness: college central system simulator (`app5_central_system.py`)

Not one of our products; it plays the college's system for tests. Commands: `students --csv` (PUT /api/v1/students), `sessions --csv [--date]` (POST /api/v1/sessions; `{date}` in session IDs is replaced), `list`, `pull --session | --date [--csv] [--json]`, and a menu. The simulation tool `tools/make_simulation.py` produces `college_students.csv`, `timetable.csv` (3 sessions) and `rf_taps.txt` for it.

## 9. Demo to production gaps

| Area | Demo | Production |
|---|---|---|
| Enrolment device | Laptop webcam, console | College Android phone, kiosk, liveness, encrypted package |
| Accounts | Fixed IDs and PINs in config | College login, roles, OTP |
| Transport | HTTP on 127.0.0.1 with shared keys | WireGuard VPN, TLS 1.3, mutual TLS |
| Face models | YuNet + SFace on CPU | Commercially licensed SCRFD / ArcFace class on GPU (TensorRT) |
| Database | SQLite + FAISS | PostgreSQL 16 + pgvector, LUKS, RAID-1 |
| Backups | Fernet files in two folders, key file beside the data | restic to NAS + offline drive, nightly + on change, split key, monthly restore drill |
| Cameras | Webcam, photos or video; "fail" simulates failure | Matrix PTZ5040P via ONVIF / SDK, taught points, home check, revisit |
| RF readers | Keyboard entry or file | Reader interface or the central system's RF log (to confirm with college IT) |
| Scheduling | Started by hand | Timetable scheduler and the Scan button |
| UI | Simple HTML pages | React web UI (teach studio, live monitor, review list, reports) |
