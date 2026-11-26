# PTZ Implementation: AI-Driven Classroom Attendance System (PTZ taught-point concept)

Single source of truth for the PTZ concept. Kept up to date with every change. Last updated: 26 November 2026 (version 2).

This document covers the PTZ taught-point concept ONLY. It is kept separate from the fixed multi-camera BOM solution; the two will be compared later in a separate piece of work.

## 1. What changed in version 2 (26 November 2026)

| # | Change requested | Where it is now |
|---|---|---|
| 1 | Enrolment no longer on students' own phones: the enrolment app runs on a dedicated college phone under college staff supervision. Enrolment camera specified. | Sections 5 and 6, diagrams 01 and 03, demo APP 1 and APP 2 |
| 2 | The college central system tells the Edge AI server each lecture session (subject, lecturer, hall, time) and the students expected; many sessions a day. The Edge AI marks attendance per session and reports students who attend without the central system's knowledge. | Sections 4 and 7, diagrams 01, 02 and 04, demo APP 3, APP 4, APP 5 |
| 3 | The central system can get a session's attendance at any time through the API, by session. | Sections 7.8 and 8, diagrams 01, 02 and 04, demo APP 3 and APP 5 |
| 4 | Face database backup and protection against corruption, misuse by students or staff, and system failure. | Section 9, diagrams 01, 02 and 03, demo APP 3 and Backup_Restore |
| 5 | Existing RF readers are the fallback when both PTZ cameras fail. | Section 7.5, diagrams 01, 02 and 04, demo APP 4 |
| 6 | Lecturer can override a student's attendance (official duty: paper presentation, sports) within 2 days. | Section 7.7, diagram 04, demo APP 3 lecturer page |
| 7 | Technology stack shows the central system's role. | Section 10, diagram 02 |

Unchanged from version 1: no tone or beep; photos pass through our office only (Enrolment Converter on the office PC pushes to the Edge AI server over VPN); the face database lives only on the Edge AI server, never on the college central system; the central system pulls attendance through our API.

## 2. The concept in one paragraph

Each 300-seat hall has one primary PTZ camera and one standby PTZ camera (Matrix SATATYA PTZ5040P, 5 MP, 38x zoom, made in India). Like a vision camera on a robot arm, each camera is taught once: 75 bench points of 4 students each, plus a home point. In every lecture session the camera visits the taught points in a fixed order, captures 3 frames at each, and the Edge AI server recognises the faces against the face database. One Edge AI server with a GPU serves many halls. The college central system supplies the sessions and student lists and pulls the attendance.

| Figure | Value |
|---|---|
| Seats per hall | 300 (15 rows x 20 seats) |
| Students per taught point | 4 |
| Taught points per camera | 76 (75 bench points + home); the user's earlier "400" is still to be confirmed |
| Cameras per hall | 2 (primary + standby), each with its own taught points |
| Halls in the pilot design | 5, scanning in parallel |
| Time to scan all 1,500 students once | about 2 min 10 s (5 halls in parallel) |
| With the revisit pass | about 2 min 47 s |
| Fallback when both cameras fail | the hall's existing RF card readers |

## 3. Diagrams (editable draw.io, Arial, minimum font 11)

| File (repository folder `architecture/`) | Shows |
|---|---|
| PTZ_01_Overall_architecture.drawio | Enrolment desk and office, 5 halls with cameras and RF readers, Edge AI server layers, backups, college central system |
| PTZ_02_Technology_stack.drawio | Technologies per device and layer, including the existing RF readers and the central system's role and API |
| PTZ_03_Face_enrolment_workflow.drawio | Staff-supervised enrolment on the college phone, office conversion, Edge AI checks, backup, camera specification |
| PTZ_04_Attendance_marking_workflow.drawio | Session from the central system, primary / standby / RF fallback, revisit, NOT IN LIST, lecturer override, pull API |

Each diagram also has a PDF next to it (same name, .pdf). Copies are in the project files folder `ptz_concept/` (named 01_ to 04_).

Low-level design of the four software products (Enrolment App, Enrolment Converter, Edge AI Service, Attendance Engine): [PTZ_Low_Level_Design.md](PTZ_Low_Level_Design.md) (PDF copy in the project files folder `ptz_concept/`).

## 4. Who does what

| Party | Role |
|---|---|
| College central system | Owns the timetable and the student records. Sends the Edge AI the student list (ID, name, class, RF card number) and every lecture session with the students expected. Pulls each session's attendance at any time. Never receives photos, face images or face templates. |
| College enrolment desk | A college staff member operates the dedicated college enrolment phone, checks each student's ID card, and supervises the capture. |
| Our office | The Enrolment Converter checks and converts the photos, pushes face templates to the Edge AI, and wipes the photos after the Edge AI's receipt. |
| Edge AI server (college server room) | Holds the only live face database. Runs the cameras, recognition, sessions, attendance, RF fallback, lecturer overrides, backups, audit log and the APIs. |
| Lecturers | Start a session early with the Scan button if they wish, watch progress, confirm the short review list, and override attendance for official duty within 2 days. |
| College admin | Adds halls and cameras, teaches points, approves deletions (second person), keeps one half of the backup key. |
| Students | Attend the enrolment desk once with their ID card. Nothing to install or do in lectures. |

## 5. Enrolment under college staff supervision

### 5.1 Why

A student enrolling on their own phone could enrol a friend's face, use a photo or video, or enrol twice under different IDs. Enrolment therefore happens only on a dedicated college phone, in front of a college staff member, at an enrolment desk with fixed lighting.

### 5.2 Steps

1. The staff member logs in on the college phone with their staff ID and PIN or OTP. The phone runs only the enrolment app (kiosk mode) and is registered by device ID.
2. The student shows the college ID card. The staff member checks that the face matches the card and records the student's consent (DPDP Act 2023).
3. Guided capture of 5 angles (front, slight left, slight right, slight up, slight down) with a liveness check, the phone on a tripod, ring light on.
4. The app encrypts the photo package (AES-256) and sends it from the registered phone to our office. Nothing stays on the phone.
5. The Enrolment Converter decrypts it, checks the phone ID, the staff ID and that the student ID is on the college student list.
6. It checks each photo (one face, size, sharpness, light, pose). If a photo fails, the staff member is asked to retake it.
7. It aligns and crops each face to the standard 112 x 112 database image and builds the face templates (same model version as the Edge AI).
8. It pushes a signed batch over the VPN. The Edge AI checks again: ID on the college list, the face not already enrolled under another ID, and, for a re-enrolment, the same face as before.
9. The Edge AI stores the templates and database images and sends a receipt. The office PC wipes the photos and writes an audit entry.
10. The Edge AI makes an encrypted backup within minutes. The student is ready to be scanned.

### 5.3 Recommended enrolment camera (college phone kit)

The face database is only as good as the enrolment photos, so the phone and its set-up are specified, not left to chance.

| Item | Specification | Budgetary price (INR, to be quoted) |
|---|---|---|
| Phone | **Samsung Galaxy A36 5G** (or an equivalent with the same specification): 50 MP main camera with optical image stabilisation (OIS), f/1.8, phase-detection autofocus; 8 GB RAM; Android 15 with Android Enterprise / Samsung Knox for kiosk mode and remote management; long security-update support | about 30,000 to 33,000 |
| Camera used | Rear main camera (much better than the front camera), operated by the staff member | |
| Capture settings | 12 MP (4000 x 3000) photos, HDR off, beauty filters off, digital zoom off, fixed white balance under the ring light | |
| Distance and framing | 1.0 to 1.2 m from the student, phone at eye level on a tripod; head and shoulders fill the frame; the face is then 600 pixels or more wide (the converter needs at least 90) | |
| Lighting | 10-inch (or larger) LED ring light behind the phone, daylight colour, about 500 lux on the face, no window behind the student | about 2,500 |
| Background | Plain light-grey backdrop or wall | about 1,000 |
| Tripod | With phone holder, height up to 1.6 m | about 1,000 |
| Registration | Phone enrolled in mobile device management with a fixed device ID; only registered phones can send enrolments | |

Why not a webcam on a PC: the phone gives a better sensor and autofocus, an on-device liveness check, and can be moved between enrolment desks; the kiosk lock and device registration stop misuse. One phone kit enrols about 30 students an hour (2 minutes each), so 1,500 students need about 50 desk-hours; two kits halve that.

### 5.4 What the enrolment records

Student ID, name and class (taken from the college student list), the database images and face templates, the model version, the quality scores, the supervising staff ID, the phone ID, and the time. Every refusal is recorded too.

## 6. Data the college central system sends

### 6.1 Student list

| Field | Example | Use |
|---|---|---|
| student_id | S001 | Key for everything |
| name | Asha | Shown to staff and lecturers |
| class_name | MBBS1 | Reports |
| rf_card | RF10001 | Maps an RF reader tap to the student in the RF fallback |

Enrolment is refused for an ID that is not on this list.

### 6.2 Lecture sessions (many a day)

| Field | Example |
|---|---|
| session_id | 20261126-H1-0900-ANAT101 (any unique ID chosen by the central system) |
| subject_code, subject_name | ANAT101, Anatomy |
| lecturer_id, lecturer_name | L01, Dr Lecturer One |
| hall | Hall 1 |
| date, start_time, end_time | 2026-11-26, 09:00, 10:00 |
| students | the IDs of every student expected in this session |

A session can be sent days ahead and corrected until it starts. Once it is running or ended it cannot be changed by a re-send.

## 7. Attendance marking

### 7.1 Trigger

The scan starts at the session's start time (plus a configurable delay, for example 10 minutes), or earlier when the lecturer taps Scan. There is no tone; the class carries on.

### 7.2 Scan

Home check against a fixed target, then pass 1 over the 75 points (move to stored pan, tilt, zoom; set stored focus; settle about 0.5 s; capture 3 frames; keep the sharpest). The GPU recognises faces while the camera keeps moving.

### 7.3 Matching against the session

Every recognised face is checked against the session's student list:

| Result | Meaning |
|---|---|
| PRESENT (method FACE) | On the session list and recognised with confidence in several frames |
| NOT_IN_LIST | An enrolled student recognised in the hall who is not on the session's list. Reported to the central system so it learns about students attending without its knowledge |
| Unknown face | Not enrolled. Counted (most seen at once) and reported with the session; never marked |

The system also flags a LOCAL session: a session a lecturer started at the Edge AI that the central system never sent. It is reported with origin LOCAL.

### 7.4 Revisit and review

Points with fewer faces than expected, hidden or poor faces, or unsure matches are revisited at tighter zoom (2 students per frame) after 20 to 30 s. Still unresolved students go to the lecturer's review list for a one-tap confirm or absent. A missing face always gets a second look before it counts as absent.

### 7.5 Camera failure and RF reader fallback

| Situation | What happens | Recorded as |
|---|---|---|
| Primary camera healthy | Normal scan | mode CAMERA |
| Primary camera fails (health check every 10 s, or a move that does not reach its point) | The standby camera runs the same scan from its own taught points | mode STANDBY_CAMERA |
| Both cameras fail | The session switches to the hall's existing RF card readers; students tap their cards as they do today; each tap is matched to the student through the central system's RF card list | mode RF_FALLBACK, method RF |

RF taps are accepted only while the session is in RF fallback, so cards cannot be used to add marks while the cameras work. Unknown cards are refused. RF marks are flagged, because a card can be tapped by someone else. How the Edge AI reads the readers (reader network interface, USB, or the RF log the central system already collects) is to be confirmed with college IT.

### 7.6 Ending the session

At the end time (or when the lecturer ends it), every listed student not seen is ABSENT. The result is saved on the edge database with method, time and confidence, written to the audit log and backed up.

### 7.7 Lecturer override for official duty

A student who was away officially, for example presenting a paper or in a sports event, can be marked ON_DUTY by the lecturer.

| Rule | Value |
|---|---|
| Who | Only the lecturer of that session (logged in) |
| For whom | Only students on that session's list |
| When | From the end of the session until 48 hours (2 days) after it; then closed |
| Statuses | ON_DUTY (paper presentation, sports, other official duty), or PRESENT / ABSENT to correct a mistake |
| Required | Reason category and a note (event, letter number) |
| Kept | The original status, the lecturer ID, the time; every override is in the audit log and visible to the central system |

### 7.8 The central system gets the attendance

The central system pulls any session's attendance at any time, during or after the session, as often as it needs, by session ID; or all sessions of a date, optionally filtered by subject or hall. Attendance stays on the Edge AI until it is pulled, so nothing is lost if the college network is down.

### 7.9 Scan time

| Item | Value |
|---|---|
| Home check | 10 s |
| Time per point | 1.6 s (move, focus, settle, 3 frames) |
| Pass 1 per hall | 10 s + 75 x 1.6 s, about 130 s |
| Revisit pass | about 30 s (about 15 points) |
| All 1,500 students in 5 halls, in parallel | about 2 min 10 s once; about 2 min 47 s with revisits |
| Optional: primary and standby split each hall | about 1 min 11 s once; about 1 min 31 s with revisits |

## 8. API between the Edge AI server and the college central system

HTTPS (TLS 1.3) on the college LAN, with a college API key (or mutual TLS) agreed with college IT. Our proposal until the college shares its own specification.

| Direction | Request | Purpose |
|---|---|---|
| Central to Edge | PUT /api/v1/students | Student list with RF card numbers |
| Central to Edge | POST /api/v1/sessions | Lecture sessions with their student lists |
| Central from Edge | GET /api/v1/sessions?date=YYYY-MM-DD | Sessions with state, mode and counts |
| Central from Edge | GET /api/v1/sessions/{session_id}/attendance | One session's attendance, at any time |
| Central from Edge | GET /api/v1/sessions/{session_id}/attendance.csv | The same as CSV |
| Central from Edge | GET /api/v1/attendance?date=&subject_code=&hall= | Many sessions at once |
| Lecturer to Edge | POST /api/v1/sessions/{session_id}/override | Official duty override (also on the web page) |

Example attendance answer (shortened):

```json
{
  "session": {"session_id": "20261126-H1-0900-ANAT101", "subject_code": "ANAT101", "lecturer_id": "L01",
              "hall": "Hall 1", "date": "2026-11-26", "start_time": "09:00", "end_time": "10:00",
              "origin": "CENTRAL", "state": "ENDED", "mode": "CAMERA", "unknown_faces": 1},
  "override_open_until": "2026-11-28 10:00:00",
  "counts": {"PRESENT": 287, "ABSENT": 9, "ON_DUTY": 4, "NOT_IN_LIST": 2},
  "records": [
    {"student_id": "S001", "name": "Asha", "status": "PRESENT", "method": "FACE", "in_session_list": true,
     "face_enrolled": true, "time": "2026-11-26 09:12:41", "override": null},
    {"student_id": "S006", "name": "Karthik", "status": "ON_DUTY", "method": "LECTURER_OVERRIDE",
     "in_session_list": true, "override": {"by": "L01", "reason": "SPORTS", "note": "Inter-college meet",
     "original_status": "ABSENT"}}
  ]
}
```

The API never returns photos, face images or face templates.

## 9. Protecting the face database

The face database is the one thing that is expensive to rebuild: losing it means enrolling every student again. It is protected in layers.

### 9.1 Against hardware failure and corruption

| Layer | What | Recovers from |
|---|---|---|
| RAID-1 mirror | Two SSDs in the Edge AI server, mirrored | One disk failing, with no downtime |
| Database safety | PostgreSQL with write-ahead log; daily integrity check; the service refuses to start on a damaged database and alerts | Power cuts, crashes, silent corruption |
| Encrypted backups on change | Within minutes of any enrolment, re-enrolment or deletion, plus nightly, an encrypted backup (restic, AES-256) of the whole database: templates, database images, sessions, attendance, audit log | Software fault, mistaken change, ransomware on the server |
| Backup NAS in the server room | A separate 2-bay NAS receives the encrypted backups; 14 daily, 8 weekly and 12 monthly copies kept | Loss of the whole Edge AI server |
| Offline copy | Monthly encrypted copy on an external drive kept in the college safe, disconnected | Fire, theft or an attack that reaches the NAS |
| Restore drill | A restore is tested every month on a spare machine and the result logged | Backups that look fine but do not restore |
| Templates can be rebuilt | The 112 x 112 database images are kept, so face templates can be rebuilt for a new model without re-enrolment | Model upgrade |

All backups are encrypted before they leave the Edge AI server, and the backup key is split between our office and the college (two halves held separately). A backup copy alone does not reveal any face, so the rule "the face database lives only on the Edge AI server" still holds for any readable copy. Backups never go to the college central system.

### 9.2 Against misuse

| Who | Risk | Protection |
|---|---|---|
| Student | Enrols a friend's face or a photo; enrols on their own phone; enrols twice | Staff-supervised enrolment on a registered college phone; ID card check; liveness check; ID must be on the college list; duplicate face refused |
| Student | Shows a photo or screen to the PTZ camera | Several frames needed; face size and quality checks; unknown or unsure faces never marked; liveness at scan planned after the pilot |
| Student | Proxy RF tap in the RF fallback | RF taps accepted only when both cameras are down; marks flagged RF; reported to the central system |
| College staff | Enrols the wrong person or replaces a student's face | Every enrolment records staff ID and phone; re-enrolment must match the existing face, otherwise two staff must first delete the old one |
| College staff | Deletes students or the database | Deletion needs two different staff; soft delete with 30-day restore; database user rights limited; backups and offline copy |
| Lecturer | Marks friends present by override | Only own sessions, only listed students, only within 48 hours, reason required, original kept, audited, reported to the central system and HOD |
| Anyone | Changes records directly in the database | Tamper-evident audit log (each entry carries the hash of the one before); daily chain check; alert if broken |
| Anyone | Steals the server, disk or a backup | Encrypted disk (LUKS); encrypted backups with a split key; server in a locked room |

### 9.3 Against unforeseen system failure

| What can fail | Detection | Response |
|---|---|---|
| Primary camera | Health check every 10 s; move not reaching its point | Standby camera runs the scan |
| Both cameras | Health check alarm | RF reader fallback for the session |
| Camera drift | Home check before every scan | Auto re-home; alert to re-teach if it stays |
| Power cut | UPS signal | UPS carries server and switch; services restart by themselves |
| College network down | Central system cannot reach the API | Attendance stays on the edge until pulled |
| Edge software fault | Watchdog on every service | Restart; a missed scan is re-run in the same window |
| Edge server lost | Monitoring alarm | Restore the latest backup from the NAS to a replacement server; no re-enrolment |
| Unsure face match | Confidence below threshold | Revisit, then the lecturer's review list; never marked automatically |

## 10. Technology stack

| Device / layer | Technologies |
|---|---|
| College enrolment phone | Flutter (Android) app in kiosk mode (Android Enterprise / Knox); staff login and ID card check; on-device liveness; AES-256 encrypted package |
| Office PC: Enrolment Converter | Python 3.12 + PySide6 desktop; ONNX Runtime (CPU); OpenCV align and crop; signed batches |
| Edge AI: user interface | React web UI; teach studio with live view; role-based login; lecturer override page |
| Edge AI: services | Python 3.12 + FastAPI; sequence and failover engine; session manager (sessions from the central system); RF fallback service; scheduler |
| Edge AI: vision | NVIDIA CUDA + TensorRT; face detector (SCRFD class) and recogniser (ArcFace class) with a commercial licence; quality and pose check |
| Edge AI: camera layer | ONVIF Profile S / T; Matrix SDK driver; RTSP and JPEG snapshot; driver plug-in interface |
| Edge AI: data | PostgreSQL 16 with pgvector; encrypted disk (LUKS); sessions, attendance and audit log tables |
| Edge AI: backup and safety | RAID-1 (2 SSDs); restic encrypted backups; backup NAS and offline drive; hash-chained audit log |
| Edge AI: platform | Ubuntu 24.04 LTS; Docker Compose; systemd watchdog; Prometheus health alerts |
| Existing RF readers | Reader network or USB interface (to confirm); card-to-student from the central list; used only when both cameras fail |
| Network | WireGuard VPN (edge dials out to our office); TLS 1.3 HTTPS API; camera VLAN; PoE++ gigabit switch |
| College central system | Owns timetable and student records; sends students and sessions; pulls session attendance through the API |

## 11. Hardware

| Item | Specification |
|---|---|
| PTZ camera (2 per hall) | Matrix SATATYA PTZ5040P: 5 MP (2592 x 1944), 38x optical zoom, motorised focus, 300 presets, ONVIF Profile S |
| Edge AI server | Intel Core i7-14700, 64 GB DDR5, NVIDIA RTX 4060 Ti 16 GB; 2 x 1 TB NVMe in RAID-1 (changed from 1 x 1 TB), 4 TB HDD for the image archive; 2 x 1 GbE; 1 kVA online UPS |
| Per hall | Gigabit PoE++ switch, brackets, Cat6, 6U wall rack; existing RF card reader reused |
| Enrolment | College phone kit (Section 5.3), one or two kits |
| Backup | 2-bay NAS with 2 x 4 TB (mirrored) in the server room; 2 external drives rotated monthly to the college safe |

### 11.1 Budget impact of version 2 (budgetary, before GST, not yet in the deck's pilot price)

| Change | Effect |
|---|---|
| Enrolment phone kit (phone, ring light, backdrop, tripod) | about +37,000 per kit |
| Second 1 TB NVMe for RAID-1 | about +8,000 |
| Backup NAS with 2 x 4 TB | about +55,000 |
| 2 external backup drives | about +12,000 |
| Enrolment app: Android only, kiosk mode (no iOS, no store accounts) | development about the same; Apple and Google store accounts (11,000) no longer needed |
| Software: sessions from the central system, NOT IN LIST, RF fallback, lecturer override, backup and restore, audit log | about +1.5 person-months, to be confirmed |

The pilot price in the PTZ deck (Rs 24.99 lakh before GST) has not been changed yet.

## 12. Laptop demo status

The demo in `ptz_laptop_demo/` runs every part on one Windows laptop (webcam = PTZ camera and college phone camera). Version 2 has five apps:

| App | Plays | Version 2 features |
|---|---|---|
| APP 1 Face capture | Enrolment app on the college phone | Staff login (ID + PIN), ID card confirmation per student, registered phone ID |
| APP 2 Enrolment Converter | Office PC | Refuses unregistered phones, wrong staff login, unconfirmed ID card; records staff and phone |
| APP 3 Edge AI service | Edge AI server | Student list and sessions from the central system; per-session attendance with PRESENT / ABSENT / ON_DUTY / NOT_IN_LIST; LOCAL sessions flagged; RF taps only in RF fallback; lecturer override page (own session, 48 h, reason); duplicate and different-face re-enrolment refused; two-person soft delete and restore; encrypted backups to two folders within 30 s of a change; integrity check at start; hash-chained audit log; pull API by session or date |
| APP 4 Attendance | Attendance on the Edge AI | Runs one session; primary camera, standby camera on failure, RF fallback (keyboard-wedge reader or file) when both fail |
| APP 5 College central system | Central system simulator | Sends students and sessions from CSV; lists sessions; pulls attendance by session or date; saves CSV |
| Backup_Restore | Admin tool | Lists and verifies backups (checksum, decryption, integrity); restores the newest good one |

Tested end to end on a Linux test machine (OpenCV 4.14, FAISS 1.16, CPU) with 6 enrolled people and 1 stranger: all sessions correct in all three camera modes, every misuse case refused, damaged database detected and restored from the second backup folder, tampered audit entry detected; single-frame recognition 29 of 31, 0 wrong matches, 5 of 5 strangers unknown. Not tested on a real Windows laptop or webcam. Details: `ptz_laptop_demo/USER_GUIDE.md` (and the PDF).

## 13. Assumptions and open points

| # | Point | Status |
|---|---|---|
| 1 | Point count: 76 (75 + home), not 400 | To confirm with the user |
| 2 | How the Edge AI reads the existing RF readers (network, USB, or the central system's RF log) and the card number format | To confirm with college IT |
| 3 | The central system's API: whether it can push sessions and student lists to us, its authentication, and session ID format | To agree with college IT |
| 4 | Backup key custody (two halves: our office and the college) and the location of the offline copy (college safe) | Proposed; to confirm with the college |
| 5 | Override window: 48 hours from the end of the session, lecturer of the session only | As requested; HOD approval for later changes is an option |
| 6 | Enrolment phone model and price | Recommended Samsung Galaxy A36 5G or equivalent; to be quoted |
| 7 | VPN from the edge server out to our office | College IT to allow |
| 8 | Hall geometry: 15 rows x 20 seats, back row about 18 m | Site survey |
| 9 | Face model with a commercial licence | Required before production |
| 10 | Prices are budgetary and before GST | Quotation needed |

## 14. Change log

| Date | Version | Change |
|---|---|---|
| 25 November 2026 | 1 | Concept, deck, four diagrams, laptop demo with four apps; tone removed; office enrolment path; face database only on the Edge AI |
| 26 November 2026 | 2.2 | Low-level design document for the four software products added; converter now treats a 403 refusal from the Edge AI as final |
| 26 November 2026 | 2.1 | PDF versions of the four diagrams added; small layout fixes (box borders, enrolment diagram labels) |
| 26 November 2026 | 2 | Staff-supervised enrolment on a dedicated college phone with camera specification; sessions and student lists from the central system; NOT_IN_LIST and LOCAL sessions; pull API by session at any time; RF reader fallback; lecturer override within 2 days; face database backup and misuse protection; central system role in the stack; diagrams, demo (five apps) and user guide updated |
