# PTZ Laptop Demo: User Guide

AI-Driven Classroom Attendance System, PTZ taught-point concept. Five apps that run together on one Windows laptop. Version 2 (26 November 2026): staff-supervised enrolment on a college phone, lecture sessions sent by the college central system, RF reader fallback, lecturer override, encrypted face database backups.

## 1. What this demo is

One laptop plays every part of the PTZ concept. The laptop webcam stands in for the PTZ camera and for the camera of the dedicated college enrolment phone. The laptop is also the office PC, the Edge AI server and the college central system. The five apps are separate programs. They talk to each other over the laptop's own network address (127.0.0.1), exactly as they would talk over the college network in the real system.

| App | Plays the part of | What it does | Window / address |
|---|---|---|---|
| APP 1 Face capture | Enrolment app on the dedicated college phone | A college staff member logs in, checks the student's ID card, takes 5 photos and sends them to the office PC | Camera window + console |
| APP 2 Enrolment Converter | Office PC | Accepts photos only from a registered college phone with a valid staff login, checks and converts them to database images and face codes, pushes them to the Edge AI, then wipes the photos | http://127.0.0.1:8001 |
| APP 3 Edge AI service | Edge AI server | Face database (only here), sessions and student lists from the central system, attendance, lecturer override, encrypted backups, audit log, pull API | http://127.0.0.1:8002 |
| APP 4 Attendance | Attendance software on the Edge AI | Runs one lecture session: primary camera, standby camera if the primary fails, RF card readers if both fail | Camera window + console |
| APP 5 College central system | The college's central system (simulator) | Sends the student list (with RF card numbers) and the day's lecture sessions; pulls each session's attendance at any time | Console |

Rules followed by the demo:

- Enrolment happens only on a registered college phone, under a logged-in college staff member who confirms the student's ID card. Students never use their own phones.
- Student photos stay on the office PC only until the Edge AI confirms it has stored them. Then the office PC deletes them.
- The face database (database images and face codes) is stored ONLY in the Edge AI service. Its encrypted backups are unreadable without the backup key.
- The college central system tells the Edge AI which sessions happen and which students are expected. It gets attendance only, never photos or face codes.

## 2. Can all five apps run on my laptop?

Yes. All apps run at the same time on one laptop, and none of them needs an NVIDIA graphics card. Your "GPU 0" is fine because the face models run on the CPU.

| Item | Needed |
|---|---|
| Windows | Windows 10 or 11, 64-bit |
| Python | 3.10, 3.11, 3.12 or 3.13 (python.org, or your existing Anaconda) |
| Disk space | About 0.5 GB (Python packages about 360 MB, face models 39 MB, code and data less than 50 MB) |
| Memory | 4 GB RAM or more |
| Camera | The built-in laptop webcam (or any USB webcam) |
| Internet | Only during setup, to install the Python packages |

Only one app can use the webcam at a time. Close APP 1 before you start APP 4, and close Teams, Zoom or the Windows Camera app.

## 3. One-time setup

1. Open https://github.com/cstephenpaulraj/AttendanceSystem, click the green **Code** button, then **Download ZIP**.
2. Extract the ZIP. Copy the folder `ptz_laptop_demo` to a short path, for example `C:\Users\<you>\dev\ptz_laptop_demo`. If you have the previous version, replace the whole folder, then run **Reset_Demo_Data.bat** once.
3. If Python is not installed, install Python 3.12 from https://www.python.org/downloads/windows/ and tick **Add python.exe to PATH**. If you prefer your Anaconda, open the **Anaconda Prompt**, go to the folder with `cd C:\Users\<you>\dev\ptz_laptop_demo`, and run `setup_windows.bat` from there.
4. Double-click **setup_windows.bat**. It creates a private Python environment in the `.venv` folder, installs the packages and checks the two face models. It takes about 5 minutes. When it says **Setup complete**, press a key to close it. Run it again after updating from version 1, because version 2 adds the `cryptography` package for encrypted backups.

The face models are already in the `models` folder: YuNet (face detector, MIT licence) and SFace (face recogniser, Apache-2.0 licence). Both are free for commercial use.

## 4. Demo accounts

The real system uses the college login with roles. The demo has fixed accounts, set in `common\config.py`.

| Who | ID | PIN | Used for |
|---|---|---|---|
| College staff | STAFF01 | 1111 | Supervises enrolment on the college phone |
| College staff | STAFF02 | 2222 | Supervises enrolment; second approver |
| College admin | ADMIN01 | 9999 | Second approver for deletions; restores a deleted student |
| Lecturer | L01, L02, L03 | 1001, 1002, 1003 | Overrides attendance of their own sessions |
| Registered enrolment phone | COLLEGE-PHONE-01 | | The device this laptop plays |
| Central system key | college-demo-key | | APP 5 and the pull API |

## 5. Start the two servers (APP 3 and APP 2)

1. Double-click **0_Start_Servers.bat**.
2. Two black windows open: **APP 3 - Edge AI service** and **APP 2 - Enrolment Converter (office PC)**. Leave both open while you use the demo.
3. Your browser opens two dashboards: http://127.0.0.1:8002 (Edge AI) and http://127.0.0.1:8001 (office PC). They refresh by themselves.
4. If Windows Firewall asks, click **Allow**. The apps only use the laptop's own address.

To stop a server, click its black window and press **Ctrl+C**, or close the window.

## 6. APP 5: the college central system sends students and sessions

The Edge AI needs two things from the central system before it can take attendance:

- **The student list**: ID, name, class and RF card number of every student. Enrolment is refused for an ID that is not on this list. The RF card numbers are used by the RF reader fallback.
- **The lecture sessions**: for every session of the day, the session ID, subject, lecturer, hall, start and end time, and the IDs of the students expected. There can be many sessions a day.

Double-click **5_Central_System.bat** for a menu:

| Choice | What it does |
|---|---|
| 1 Send student list | Sends a CSV file with the columns `student_id,name,class_name,rf_card` |
| 2 Send today's sessions | Sends a CSV file with the columns `session_id,subject_code,subject_name,lecturer_id,lecturer_name,hall,start_time,end_time,students` (students separated by spaces; `{date}` in the session ID becomes today's date) |
| 3 List sessions | Shows every session on the Edge AI with its state, mode and counts |
| 4 Pull one session's attendance | Asks for a session ID and prints the attendance |
| 5 Pull all of today's attendance | Prints every session of today and saves `attendance_<date>.csv` |

The simulation (Section 12) makes these CSV files for you. For your own people, copy `sim\college_students.csv` and `sim\timetable.csv` and edit them in Excel or Notepad. Use the hall name `Hall 1`.

## 7. APP 1: supervised face capture with the live webcam

1. Double-click **1_Face_Capture.bat**.
2. The supervising staff member types their **staff ID** (for example STAFF01) and **PIN** (1111). Without a valid staff login the app stops.
3. Type the **Student ID** (for example S001, it must be on the college student list), the **Student name**, then the **Class** (for example MBBS1).
4. The app asks the staff member: *does the student's college ID card match the student in front of you?* Type **Y** only after checking the card. **N** stops the enrolment of that student.
5. The camera window opens. The student sits 50 to 80 cm from the laptop, faces the camera, with light on the face.
6. The message at the top says what to fix: *no face*, *only one person in front of the camera*, *face too small - come closer*, *too dark*, *too bright*, *blurred - hold still*. When the box turns green and it says **READY**, press **SPACE** to take a photo.
7. Take 5 photos. The student turns the head slightly (a little left, right, up) between photos. Or press **A** to switch on auto-capture.
8. After the 5th photo the app sends them to the office PC and prints the answer, for example `Office PC: 5 of 5 photos good -> STORED ON EDGE AI - local photos wiped`.
9. Enter the next student, or leave the Student ID empty and press Enter to quit.

Keys in the camera window: **SPACE** take photo, **A** auto-capture on or off, **ESC** cancel this student.

If APP 2 is not running, the photos are kept in `data\capture_outbox`. Start the servers, then send them with `.venv\Scripts\python app1_face_capture.py --resend --staff STAFF01 --pin 1111`.

**The real enrolment camera.** In the real system APP 1 runs on a dedicated college phone. Recommended: Samsung Galaxy A36 5G or equivalent (50 MP main camera with optical image stabilisation, f/1.8 autofocus, Android Enterprise / Knox kiosk mode, 8 GB RAM), used with its rear camera on a tripod at eye level, 1.0 to 1.2 m from the student, a 10-inch LED ring light and a plain light-grey backdrop. See PTZ_Implementation.md for the full specification.

## 8. APP 2: Enrolment Converter (office PC)

APP 2 works by itself. You only watch its dashboard at http://127.0.0.1:8001. For every student it:

1. refuses the upload unless it comes from a registered college phone (COLLEGE-PHONE-01), with a valid staff ID and PIN, and the staff confirmation that the ID card was checked;
2. checks each photo: exactly one face, face at least 90 pixels wide, not blurred, not too dark or bright, face clearly visible;
3. checks that all photos show the same person;
4. converts each good photo into a standard database image (the face straightened and cut to 112 x 112 pixels) and a face code (128 numbers);
5. needs at least 3 good photos, otherwise it rejects the student and asks for a new capture;
6. pushes the database images to the Edge AI with a shared key, together with the staff ID and phone ID;
7. when the Edge AI confirms, deletes the photos from the office PC. The dashboard shows **photos currently stored on this PC: 0**.

| Status on the dashboard | Meaning |
|---|---|
| STORED ON EDGE AI - local photos wiped | Done |
| REJECTED - only N good photo(s) | Capture this student again; the reason for each photo is listed |
| REJECTED - Edge AI refused: This face is already enrolled as ... | The same face is already enrolled under another ID |
| REJECTED - Edge AI refused: ... already enrolled with a different face | Someone tried to replace a student's face. Two staff must delete the old enrolment first |
| REJECTED - Edge AI refused: ... not in the college student list | The ID was not sent by the central system |
| WAITING FOR EDGE AI | The Edge AI is off; APP 2 retries every 30 seconds and keeps the photos until then |

The job list (`data\office_pc\jobs.json`) keeps names, staff, phone, times and results only, never photos.

## 9. APP 3: Edge AI service

Open http://127.0.0.1:8002. The dashboard shows the lecture sessions (subject, lecturer, time, whether the central system sent them, state, camera mode, counts), every enrolled student with their database images, the supervising staff member and the phone, the time of the last encrypted backup and whether the audit log is intact. The database file is `data\edge_ai\edge_ai.db`.

APIs for the college central system (key `college-demo-key` in the `X-College-Key` header; open http://127.0.0.1:8002/docs and use **Try it out**):

| Request | Does |
|---|---|
| PUT /api/v1/students | Sends the student list with RF card numbers |
| POST /api/v1/sessions | Sends lecture sessions with their expected students |
| GET /api/v1/sessions?date=2026-11-26 | Lists sessions with counts |
| GET /api/v1/sessions/{session_id}/attendance | One session's attendance, at any time (during or after the session) |
| GET /api/v1/sessions/{session_id}/attendance.csv?key=college-demo-key | The same as CSV |
| GET /api/v1/attendance?date=2026-11-26 | Every session of a day (also `&subject_code=` and `&hall=`) |

Each record has `student_id`, `name`, `status`, `method`, `in_session_list`, `face_enrolled`, `time` and, if a lecturer changed it, `override` (by, reason, note, original status).

| Status | Meaning |
|---|---|
| PRESENT | Seen by a camera (method FACE) or tapped the RF card while both cameras were down (method RF) |
| ABSENT | On the session list, not seen |
| ON_DUTY | Lecturer override for official duty (paper presentation, sports, other) |
| NOT_IN_LIST | An enrolled student attended, but the central system did not list them for this session |
| NOT_YET_SEEN | The session is still running and the student has not been seen yet |

Each session also shows `origin`: **CENTRAL** (sent by the central system) or **LOCAL** (started at the Edge AI without the central system), and `mode`: CAMERA, STANDBY_CAMERA or RF_FALLBACK.

## 10. APP 4: attendance for a lecture session

1. Close APP 1 if it is open (it holds the webcam). APP 3 must be running and today's sessions must have been sent (Section 6).
2. Double-click **4_Attendance.bat**. It picks the session of Hall 1 that is on now, or the next one today. To choose, add `--session SIM-20261126-ANAT101` or `--subject ANAT101`.
3. The window shows the camera picture and a side panel with the subject, lecturer, session, camera in use and the counts.
4. Box colours: **red** = unknown face; **yellow** = recognised, being confirmed (for example 2/3); **green** = PRESENT; **blue** = NOT IN LIST (enrolled, but not on this session's list). A student is marked after being recognised in 3 frames, so one bad frame cannot mark anyone.
5. Press **Q** to end the session. Every listed student who was not seen is marked ABSENT. The console prints the full list, the time until which the lecturer may override, and the pull API link.

**Camera failure.** If the primary camera cannot be opened or stops giving pictures, APP 4 switches to the standby camera (`--standby`, a webcam number, photos or a video). If both cameras fail, the session switches to **RF reader fallback**: students tap their college RF cards on the reader. A USB RF reader types the card number like a keyboard, so in the demo you type the card number and press Enter (an empty line ends the session), or give a file with `--rf-taps`. Taps are refused while a camera works, and unknown cards are refused.

| Option | Meaning |
|---|---|
| --session ID / --subject CODE | Which session to run (default: the current session of the hall) |
| --local-class MBBS1 | Start a LOCAL session that the central system did not send (flagged LOCAL) |
| --source camera | Primary camera: live webcam (default), a webcam number, a photo, a folder, a video, or `fail` |
| --standby fail | Standby camera, same choices (default `fail`, because a laptop has one webcam) |
| --rf-taps file.txt | RF card numbers, one per line, used when both cameras failed |
| --confirm 3 | Frames needed before marking |
| --duration 120 | End the session automatically after 120 seconds |

## 11. Lecturer override (official duty, within 2 days)

A student who was away officially, for example presenting a paper or playing for the college, can be marked **ON_DUTY** by the session's lecturer within 2 days (48 hours) of the end of the session.

1. Open http://127.0.0.1:8002/lecturer (also linked from the dashboard).
2. Choose the session and click **Show** to see its attendance.
3. Type the lecturer ID and PIN (for example L01 and 1001 for the ANAT101 session), the student ID, the new status (ON_DUTY, or PRESENT / ABSENT to correct a mistake), the reason (PAPER_PRESENTATION, SPORTS, OTHER_OFFICIAL_DUTY, CORRECTION) and a note such as the event or letter number. Click **Save override**.

Only the lecturer of that session can override, only for students on the session's list, and only until 48 hours after the session ended. The original status is kept, the change is written to the audit log, and the central system sees the override in the pull API. The same is possible with `POST /api/v1/sessions/{session_id}/override`.

## 12. Simulation through photo synthesis

The simulation builds a complete test classroom and a day of the central system from ordinary portrait photos, so you can run the whole flow without gathering people. The tool `tools\make_simulation.py` synthesises:

- **enrolment shots**: 5 photos per student made from their portraits with small head turns, light changes and zoom;
- **classroom pictures**: 6 pictures of a classroom with 6 people seated in two rows, at different sizes, angles and lighting;
- **a PTZ video**: a wide classroom with everyone seated, and a camera view that moves to each taught point, stops for 1.5 seconds, then moves on;
- **central system files**: `college_students.csv` (students with RF cards RF10001, RF10002 ...), `timetable.csv` (3 sessions today in Hall 1: ANAT101 at 09:00 by L01 with all students, PHYS102 at 11:00 by L02 without the last student, BIOC103 at 14:00 by L03 with all students) and `rf_taps.txt` (cards tapped when both cameras fail, including one unknown card);
- **expected.txt**: who is in every picture.

When a person has 2 or more photos, the last photo is never used for enrolment. It is used only in the classroom pictures, so the test checks recognition on a photo the system has never seen.

Step by step (APP 2 and APP 3 must be running: **0_Start_Servers.bat**):

1. **Collect photos.** Make the folder `sim\people`. Add one folder per person named `<ID>_<Name>`, for example `S001_Asha`, with 2 to 5 clear photos of that person alone. Use photos of people who agree to it. Optionally add a folder `UNKNOWN_visitor` with a stranger who must not be recognised.
2. **S1_Make_Simulation.bat** creates everything in `sim` and opens the folder.
3. **S2_Central_System_Sends_Students_And_Sessions.bat**: APP 5 sends the student list and today's 3 sessions, then lists them.
4. **S3_Supervised_Enrolment_From_Photos.bat**: APP 1, logged in as STAFF01 on COLLEGE-PHONE-01, sends every student's shots. Watch both dashboards: each student shows "Supervised by STAFF01".
5. **S4_Attendance_Session1_Photos.bat**: session ANAT101 from the classroom pictures with the primary camera. All students PRESENT.
6. **S5_Attendance_Session2_Standby_Camera.bat**: session PHYS102. The primary camera is simulated as failed, the standby camera (the PTZ video) takes over. The student left out of the list is reported **NOT_IN_LIST**.
7. **S6_Attendance_Session3_RF_Fallback.bat**: session BIOC103. Both cameras fail; attendance comes from `sim\rf_taps.txt`. The student whose card is not tapped is ABSENT; the unknown card is refused.
8. **Lecturer override**: open http://127.0.0.1:8002/lecturer, choose BIOC103, and mark the absent student ON_DUTY with L03 / 1003, reason SPORTS.
9. **S7_Check_Recognition.bat**: for each classroom picture, how many faces were found and recognised, wrong matches, and whether strangers stayed unknown.
10. **S8_Central_System_Pulls_Attendance.bat**: APP 5 pulls the attendance of all 3 sessions and saves `attendance_today.csv`.

To start again from an empty database, close APP 2 and APP 3 and run **Reset_Demo_Data.bat**. It deletes the database, its backups and the backup key.

## 13. Backups, corruption and misuse

**Backups.** APP 3 writes an encrypted copy of its whole database (students, face templates, database images, sessions, attendance, audit log) at every start and within 30 seconds of any change to the face data. Each copy is checked for integrity before it is encrypted, written to every backup folder with a checksum, and the newest 14 are kept. In the demo the backup folder is `data\backup_disk` (it plays the second disk / backup NAS). To keep a second copy on a USB drive, set `BACKUP_DIR2` before starting APP 3, for example `set BACKUP_DIR2=E:\ptz_backup`. The key is `data\keys\backup.key`. In the real system the key is kept offline and split between our office and the college; without it the backups cannot be read, which is why a stolen backup does not expose any face.

**Corruption.** At every start APP 3 checks the database. If it is damaged, APP 3 refuses to start and tells you to restore. Close APP 3, then double-click **Backup_Restore.bat**: it lists every backup and checks each one (checksum, decryption, database check), and when you type YES it restores the newest good one, skipping damaged copies. The damaged database is kept as `edge_ai.db.damaged-<time>`. No student needs to be enrolled again.

**Misuse.** The demo stops these, and writes every attempt to the audit log:

| Risk | Protection |
|---|---|
| A student enrols someone else's face, or enrols on their own phone | Only staff-supervised enrolment on a registered college phone, with the ID card checked |
| An ID that does not exist | Refused unless it is on the central system's student list |
| One person under two IDs | Refused as a duplicate face |
| Staff replace a student's face | Re-enrolment must be the same face; otherwise two staff must delete first |
| Staff delete a student | Needs two different staff (`POST /api/students/{id}/delete` with both IDs and PINs); the face data is kept and can be restored (`/restore`) |
| Anyone changes the audit log directly | Every entry carries the hash of the one before; the dashboard shows **BROKEN** if one was changed (`/api/admin/audit`) |
| Lecturer override abuse | Only the session's lecturer, only within 48 hours, reason required, original status kept, audited |

## 14. Using sample photos instead of the webcam

APP 1 with sample photos (open a Command Prompt in the folder):

| Command | Use |
|---|---|
| `.venv\Scripts\python app1_face_capture.py --photos D:\photos\S001_Asha --class MBBS1 --staff STAFF01 --pin 1111 --id-card-checked` | One student. The folder name gives ID S001 and name Asha |
| `.venv\Scripts\python app1_face_capture.py --batch D:\photos --class MBBS1 --staff STAFF01 --pin 1111 --id-card-checked` | Many students: one sub-folder per student, named `<ID>_<Name>` |

Without `--id-card-checked` the app asks the staff member to confirm each student's ID card.

APP 4 with sample pictures:

| Command | Use |
|---|---|
| `.venv\Scripts\python app4_attendance.py --subject ANAT101 --source D:\photos\group.jpg` | One group photo |
| `.venv\Scripts\python app4_attendance.py --subject ANAT101 --source D:\photos\classroom` | A folder of pictures, shown one by one |
| `.venv\Scripts\python app4_attendance.py --subject ANAT101 --source D:\videos\class.mp4` | A video (mp4, avi, mov, mkv, wmv) |

## 15. Test results

The apps were tested end to end on a Linux test machine with the same packages (OpenCV 4.14, FAISS 1.16, CPU only). The test faces were publicly available sample photos: 6 enrolled people and 1 stranger, with 2 to 6 photos per person.

| Test | Result |
|---|---|
| Central system sends 6 students and 3 sessions | Stored; sessions listed with 6, 5 and 6 expected students |
| Enrolment with a wrong staff PIN | Stopped before any photo is sent |
| Supervised enrolment of 6 students | 6 of 6 stored, each recorded as supervised by STAFF01 on COLLEGE-PHONE-01; office photos wiped |
| Upload from an unregistered phone | Refused |
| ID not on the college student list | Refused |
| Same face under a second ID | Refused as a duplicate |
| Re-enrolment of a student with a different face | Refused |
| Delete approved by the same staff member twice | Refused; delete with STAFF01 + ADMIN01 worked, restore worked |
| Session 1, primary camera, classroom pictures | 6 of 6 PRESENT, stranger not marked |
| Session 2, primary camera failed, standby camera video | Switched to the standby camera; 5 PRESENT, the unlisted student NOT_IN_LIST |
| Session 3, both cameras failed, RF taps | Switched to RF fallback; 5 PRESENT (RF), 1 ABSENT, unknown card refused |
| Both webcams missing, RF cards typed on the keyboard | RF fallback started automatically and marked the typed cards |
| Lecturer override | Wrong lecturer refused; right lecturer changed ABSENT to ON_DUTY (SPORTS), original kept; override after 48 hours refused |
| Pull API | Refused without the key; JSON and CSV with status, method, list flag and override |
| LOCAL session (not from the central system) | Flagged LOCAL in the pull API |
| Database deliberately damaged | APP 3 refused to start; restore skipped a damaged backup copy and restored the newest good one from the second folder; all 6 students and sessions back |
| Audit log entry changed directly in the database | Detected: chain reported broken at that entry |
| Recognition in single classroom pictures (one frame each) | 29 of 31 student faces recognised, 0 wrong matches, 5 of 5 strangers left unknown |

The two single-frame misses were students recognised in other pictures and in the video, so they were still marked PRESENT. Not tested here: a real laptop webcam and real Windows. Please run Sections 7 and 10 on your laptop.

## 16. Settings

Settings are in `common\config.py`. You can also set them for one run in a Command Prompt, for example `set MATCH_THRESHOLD=0.45` before starting an app.

| Setting | Default | Meaning |
|---|---|---|
| MATCH_THRESHOLD | 0.40 | Similarity needed to recognise a face (higher = stricter) |
| CONFIRM_FRAMES | 3 | Frames before a student is marked |
| PHOTOS_PER_STUDENT / MIN_GOOD_PHOTOS | 5 / 3 | Photos APP 1 takes / good photos APP 2 needs |
| DUPLICATE_THRESHOLD | 0.55 | Similarity at which a new enrolment is refused as a duplicate |
| SAME_PERSON_MIN | 0.45 | Photos of one student, and a re-enrolment, must agree at least this much |
| HALL | Hall 1 | The hall this Edge AI plays |
| STAFF_ACCOUNTS / LECTURER_ACCOUNTS | see Section 4 | Demo accounts as `ID:PIN,ID:PIN` |
| ENROLMENT_DEVICES / ENROLMENT_DEVICE_ID | COLLEGE-PHONE-01 | Registered enrolment phones / the phone this laptop plays |
| OVERRIDE_WINDOW_HOURS | 48 | How long after a session the lecturer may override |
| BACKUP_DIR / BACKUP_DIR2 | data\backup_disk / empty | Backup folders (second one optional, for example a USB drive) |
| BACKUP_KEEP | 14 | Encrypted copies kept in each folder |
| COLLEGE_API_KEY / EDGE_PUSH_KEY | college-demo-key / ptz-demo-key | Keys of the central system and of the office PC |
| EDGE_PORT / OFFICE_PORT | 8002 / 8001 | Ports of APP 3 / APP 2 |

## 17. Troubleshooting

| Problem | Fix |
|---|---|
| "Python 3.10 or newer was not found" | Install Python 3.12 with "Add python.exe to PATH", or run setup_windows.bat from the Anaconda Prompt |
| "No module named cryptography" | Run setup_windows.bat again (version 2 adds this package) |
| "Wrong staff ID or PIN" | Use STAFF01 / 1111 (Section 4) |
| "not in the college student list" | Send the student list first (5_Central_System.bat, choice 1) |
| "No session sent by the central system for Hall 1 today" | Send today's sessions (choice 2), or use `--local-class MBBS1` |
| "Could not open camera 0" | Close APP 1 / APP 4, Teams, Zoom, Camera app. Try `--camera 1` (APP 1) or `--source 1` (APP 4). Without a camera, APP 4 goes to RF fallback |
| "The Edge AI database ... is damaged" | Close APP 3 and run Backup_Restore.bat |
| A student is never recognised | Enrol again with more light and 5 good photos; sit closer; lower MATCH_THRESHOLD to 0.36 |
| Two students mixed up | Raise MATCH_THRESHOLD to 0.45 and enrol again with better photos |
| Port already in use | Another copy is running; close it, or set EDGE_PORT / OFFICE_PORT |

## 18. What this demo does not do (compared with the real PTZ system)

- It does not move a real PTZ camera or store taught points. The simulation video imitates the camera visiting taught points; the standby camera is a second source on the same laptop.
- It reads RF cards typed on the keyboard or from a file, not from the hall's real RF readers, whose interface the college still has to confirm.
- It has no liveness (anti-photo) check at enrolment and no Android kiosk app; APP 1 on the laptop plays the college phone.
- Accounts and PINs are fixed demo values; the real system uses the college login with roles and OTP.
- The backup key sits next to the data; in the real system it is kept offline and split. There is no RAID mirror or backup NAS on a laptop.
- The central system API format is our proposal until the college shares its own specification.

## 19. Files in this folder

| File | What it is |
|---|---|
| setup_windows.bat | One-time setup |
| 0_Start_Servers.bat | Starts APP 3 and APP 2 and opens their dashboards |
| 1_Face_Capture.bat, 4_Attendance.bat, 5_Central_System.bat | Start APP 1, APP 4, APP 5 |
| S1_ ... S8_ .bat | Simulation steps 1 to 8 (Section 12) |
| Backup_Restore.bat | Lists, checks and restores the encrypted face database backups |
| Reset_Demo_Data.bat | Deletes all demo data |
| app1_face_capture.py ... app5_central_system.py | The five apps |
| common\ | Shared settings, face engine (YuNet + SFace) and picture sources |
| tools\make_simulation.py | Photo synthesis and central system files for the simulation |
| tools\restore_backup.py | Backup check and restore |
| tools\download_models.py | Checks and, if needed, downloads the face models |
| tests\check_scenes.py | Recognition check against sim\expected.txt |
| models\ | The two face models (YuNet MIT, SFace Apache-2.0) |
| data\ | Created when the apps run: Edge AI database, backups, backup key, office job log, unsent photos |
