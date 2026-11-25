# PTZ Laptop Demo: User Guide

AI-Driven Classroom Attendance System, PTZ taught-point concept. Four apps that run together on one Windows laptop.

## 1. What this demo is

One laptop plays every part of the PTZ concept. The laptop webcam stands in for the PTZ camera, and the laptop itself is the face capturing hardware, the office PC and the Edge AI server. The four apps are separate programs. They talk to each other over the laptop's own network address (127.0.0.1), exactly as they would talk over the college network in the real system.

| App | Plays the part of | What it does | Window / address |
|---|---|---|---|
| APP 1 Face capture | Face capturing hardware (laptop webcam = PTZ camera) | Takes 5 enrolment photos of a student and sends them to the office PC | Camera window + console |
| APP 2 Enrolment Converter | Office PC | Checks the photos, converts them to standard 112 x 112 database images and face codes, pushes them to the Edge AI, then wipes the photos | http://127.0.0.1:8001 |
| APP 3 Edge AI service | Edge AI server | Stores the face database (SQLite + FAISS), answers "who is this?", keeps attendance, offers the pull API for the college central system | http://127.0.0.1:8002 |
| APP 4 Attendance | Attendance software on the Edge AI | Looks at the camera, recognises 5 to 6 people at once and marks them PRESENT | Camera window + console |

Data rules followed by the demo:

- Student photos are kept on the office PC only until the Edge AI confirms it has stored them. Then the office PC deletes them.
- The face database (database images and face codes) is stored ONLY in the Edge AI service.
- The college central system gets attendance records only: student ID, class, session, time and status. It never gets photos or face codes.

Every app can use the live webcam or sample photos. Sections 5 to 8 use the live webcam. Section 9 uses your own sample photos or video, and Section 10 builds a whole simulated classroom from photos.

## 2. Can all four apps run on my laptop?

Yes. All four apps run at the same time on one laptop, and none of them needs an NVIDIA graphics card. Your "GPU 0" is fine because the face models run on the CPU.

| Item | Needed |
|---|---|
| Windows | Windows 10 or 11, 64-bit |
| Python | 3.10, 3.11, 3.12 or 3.13 (python.org, or your existing Anaconda) |
| Disk space | About 0.5 GB (Python packages about 350 MB, face models 39 MB, code and data less than 50 MB). Your 6.75 GB free is plenty. |
| Memory | 4 GB RAM or more |
| Camera | The built-in laptop webcam (or any USB webcam) |
| Internet | Only during setup, to install the Python packages |

Only one app can use the webcam at a time. Close APP 1 before you start APP 4, and close Teams, Zoom or the Windows Camera app.

## 3. One-time setup

1. Open https://github.com/cstephenpaulraj/AttendanceSystem, click the green **Code** button, then **Download ZIP**.
2. Extract the ZIP. Copy the folder `ptz_laptop_demo` to a short path, for example `C:\Users\<you>\dev\ptz_laptop_demo`.
3. If Python is not installed, install Python 3.12 from https://www.python.org/downloads/windows/ and tick **Add python.exe to PATH**. If you prefer your Anaconda, open the **Anaconda Prompt**, go to the folder with `cd C:\Users\<you>\dev\ptz_laptop_demo`, and run `setup_windows.bat` from there.
4. Double-click **setup_windows.bat**. It creates a private Python environment in the `.venv` folder, installs the packages and checks the two face models. It takes about 5 minutes. When it says **Setup complete**, press a key to close it.

The face models are already in the `models` folder: YuNet (face detector, MIT licence) and SFace (face recogniser, Apache-2.0 licence). Both are free for commercial use. The setup checks their checksums and downloads them again only if they are missing or damaged.

## 4. Start the two servers (APP 3 and APP 2)

1. Double-click **0_Start_Servers.bat**.
2. Two black windows open: **APP 3 - Edge AI service** and **APP 2 - Enrolment Converter (office PC)**. Leave both open while you use the demo.
3. Your browser opens two dashboards: http://127.0.0.1:8002 (Edge AI) and http://127.0.0.1:8001 (office PC). They refresh by themselves.
4. If Windows Firewall asks, click **Allow**. The apps only use the laptop's own address.

To stop a server, click its black window and press **Ctrl+C**, or close the window.

## 5. APP 1: Face capture with the live webcam

1. Double-click **1_Face_Capture.bat**.
2. In the console type the **Student ID** (for example S001), press Enter, then the **Student name**, then the **Class** (for example MBBS1, press Enter to keep the default).
3. The camera window opens. Sit 50 to 80 cm from the laptop, face the camera, with light on your face.
4. The message at the top tells you what to fix: *no face*, *only one person in front of the camera*, *face too small - come closer*, *too dark*, *too bright*, *blurred - hold still*. When the box turns green and it says **READY**, press **SPACE** to take a photo.
5. Take 5 photos. Turn your head slightly (a little left, right, up) between photos. Or press **A** to switch on auto-capture, which takes a photo every second while the face is good.
6. After the 5th photo the app sends them to the office PC and prints the answer, for example `Office PC: 5 of 5 photos good -> STORED ON EDGE AI - local photos wiped`.
7. Enter the next student, or leave the Student ID empty and press Enter to quit.

Keys in the camera window: **SPACE** take photo, **A** auto-capture on or off, **ESC** cancel this student.

If APP 2 is not running, the photos are kept in `data\capture_outbox`. Start the servers, then run `1_Face_Capture.bat --resend` from a Command Prompt in the folder, or `.venv\Scripts\python app1_face_capture.py --resend`. Sent photos are deleted from the outbox.

## 6. APP 2: Enrolment Converter (office PC)

APP 2 works by itself. You only watch its dashboard at http://127.0.0.1:8001. For every student it:

1. receives the photos from APP 1;
2. checks each photo: exactly one face, face at least 90 pixels wide, not blurred, not too dark or bright, face clearly visible;
3. checks that all photos show the same person;
4. converts each good photo into a standard database image (the face straightened and cut to 112 x 112 pixels) and a face code (128 numbers);
5. needs at least 3 good photos, otherwise it rejects the student and asks for a new capture;
6. pushes the database images to the Edge AI with a shared key;
7. when the Edge AI confirms, deletes the photos from the office PC. The dashboard shows **photos currently stored on this PC: 0**.

| Status on the dashboard | Meaning |
|---|---|
| STORED ON EDGE AI - local photos wiped | Done |
| REJECTED - only N good photo(s) | Capture this student again; the reason for each photo is listed |
| REJECTED - Edge AI refused: This face is already enrolled as ... | The same face is already enrolled under another ID |
| WAITING FOR EDGE AI | The Edge AI is off; APP 2 retries every 30 seconds and keeps the photos until then |

The job list (`data\office_pc\jobs.json`) keeps names, times and results only, never photos.

## 7. APP 3: Edge AI service

Open http://127.0.0.1:8002. The dashboard shows every enrolled student with their database images and the latest attendance sessions. The database file is `data\edge_ai\edge_ai.db`.

Pull API for the college central system (no photos, no face codes):

| Request | Returns |
|---|---|
| GET /api/attendance | All attendance records (JSON) |
| GET /api/attendance?date=2026-11-25 | Records of one day |
| GET /api/attendance?session_id=S2026... | Records of one session |
| GET /api/attendance?class_name=MBBS1 | Records of one class |
| GET /api/attendance.csv | The same as a CSV file |
| GET /docs | Interactive documentation of every API |

Each record has `student_id`, `class_name`, `session_id`, `time` and `status` (PRESENT or ABSENT). Open http://127.0.0.1:8002/docs and use **Try it out** to call the API from the browser.

To remove one student, use `DELETE /api/students/{student_id}` from the /docs page with the key `ptz-demo-key` in the X-Edge-Key box.

## 8. APP 4: Attendance with the live webcam

1. Close APP 1 if it is open (it holds the webcam). APP 3 must be running.
2. Double-click **4_Attendance.bat**. Type the class (for example MBBS1) and press Enter.
3. The window shows the camera picture and a side panel. Sit 5 or 6 people in front of the laptop, about 1 to 2 m away, all facing the camera.
4. Box colours: **red** = unknown face; **yellow** = recognised, being confirmed (for example 2/3), or enrolled in a different class; **green** = marked PRESENT. A student is marked PRESENT after being recognised in 3 frames, so one bad frame cannot mark anyone.
5. The side panel lists the students present with the time.
6. Press **Q** to end the session. Every enrolled student of that class who was not seen is marked ABSENT. The console prints the full list and the pull API link for the session.

Options (add after the file name in a Command Prompt, for example `4_Attendance.bat --class MBBS1 --duration 120`):

| Option | Meaning |
|---|---|
| --class MBBS1 | Class of this session (skips the question) |
| --source camera | Live webcam (default); `--source 1` uses webcam number 1 |
| --source photo.jpg / folder / video.mp4 | Sample pictures instead of the webcam (Section 9) |
| --confirm 3 | Frames needed before PRESENT |
| --duration 120 | End the session automatically after 120 seconds |

## 9. Using sample photos instead of the webcam

Both camera apps accept sample photos. APP 2 and APP 3 work the same way in both cases.

APP 1 with sample photos (open a Command Prompt in the folder):

| Command | Use |
|---|---|
| `.venv\Scripts\python app1_face_capture.py --photos D:\photos\S001_Asha --class MBBS1` | One student. The folder name gives ID S001 and name Asha, or add `--id` and `--name` |
| `.venv\Scripts\python app1_face_capture.py --batch D:\photos --class MBBS1` | Many students: one sub-folder per student, named `<ID>_<Name>` (for example `S002_Ravi_Kumar`) |

Each student folder needs 3 to 5 clear photos of that person alone (phone photos are fine). The app shows each photo with its face box, then sends them.

APP 4 with sample pictures:

| Command | Use |
|---|---|
| `.venv\Scripts\python app4_attendance.py --class MBBS1 --source D:\photos\group.jpg` | One group photo |
| `.venv\Scripts\python app4_attendance.py --class MBBS1 --source D:\photos\classroom` | A folder of pictures, shown one by one |
| `.venv\Scripts\python app4_attendance.py --class MBBS1 --source D:\videos\class.mp4` | A video (mp4, avi, mov, mkv, wmv) |

Each picture is looked at for 15 frames (change with `--hold 30`). At the end of the pictures or the video the session ends by itself and the result is printed.

## 10. Simulation through photo synthesis

The simulation builds a complete test classroom from ordinary portrait photos, so you can run the whole flow without gathering people in front of the laptop. The tool `tools\make_simulation.py` synthesises:

- **enrolment shots**: 5 photos per student made from their portraits with small head turns, light changes and zoom (as if taken by APP 1);
- **classroom pictures**: 6 pictures of a classroom with 6 people seated in two rows, at different sizes, angles and lighting, some with camera blur;
- **a PTZ video**: a wide classroom with everyone seated, and a camera view that moves to each taught point, stops for 1.5 seconds, then moves on, as the PTZ camera does;
- **expected.txt**: who is in every picture, to check the result.

When a person has 2 or more photos, the last photo is never used for enrolment. It is used only in the classroom pictures, so the test checks recognition on a photo the system has never seen.

Step by step:

1. **Collect photos.** Make the folder `sim\people` inside `ptz_laptop_demo`. Add one folder per person named `<ID>_<Name>`, for example `S001_Asha`, `S002_Ravi`. Put 2 to 5 clear photos of that person in it, each with only that person's face (phone photos are fine, taken on different days or in different light if possible). Use photos of yourself, family or colleagues who agree to it. For 6 students you need 6 people. You may also use AI-generated portrait images. A generated face usually has only one picture, so the classroom test then uses that same picture.
2. **Add a stranger (optional).** Add a folder `UNKNOWN_visitor` with a photo of someone who must not be recognised. Strangers appear in the classroom pictures but are never enrolled.
3. **Start the servers.** Double-click **0_Start_Servers.bat**.
4. **Synthesise.** Double-click **S1_Make_Simulation.bat**. It creates `sim\enrol`, `sim\classroom`, `sim\classroom.mp4` and `sim\expected.txt`, then opens the `sim` folder so you can look at them.
5. **Enrol.** Double-click **S2_Enrol_From_Photos.bat** and type the class (MBBS1). APP 1 sends every student's shots to APP 2, which converts them and pushes them to APP 3. Watch both dashboards.
6. **Attendance from pictures.** Double-click **S3_Attendance_From_Photos.bat**. APP 4 goes through the 6 classroom pictures and marks students PRESENT. Students not in any picture are marked ABSENT at the end.
7. **Attendance from the PTZ video.** Double-click **S4_Attendance_From_Video.bat**. APP 4 follows the camera across the taught points.
8. **Check.** Double-click **S5_Check_Recognition.bat**. For each classroom picture it prints how many faces were found, how many students were recognised, any wrong matches, and whether strangers stayed unknown. Compare with `sim\expected.txt`.
9. **Pull API.** Open http://127.0.0.1:8002/api/attendance to see the records the college central system would receive.

To start again from an empty database, close APP 2 and APP 3 and run **Reset_Demo_Data.bat**.

## 11. Test results

The apps were tested end to end on a Linux test machine with the same packages (OpenCV 4.14, FAISS 1.16, CPU only). The test faces were publicly available sample photos: 6 enrolled people and 1 stranger, with 2 to 6 photos per person, so classroom faces were always taken from a photo that was not used for enrolment.

| Test | Result |
|---|---|
| APP 1 sample photo batch to APP 2 to APP 3 | 6 of 6 students stored; 29 of 30 photos accepted (1 rejected correctly: 2 faces) |
| Office photos wiped after the Edge AI confirmed | Yes, 0 photos left on the office PC |
| Same face enrolled under a second ID | Refused correctly ("already enrolled as S001") |
| Edge AI switched off during enrolment | Job waited, retried after 30 s, stored, then photos wiped |
| Office PC switched off during capture | Photos kept in the outbox, sent with --resend, outbox emptied |
| Wrong push key | Refused (401) |
| Recognition in single classroom pictures (one frame each) | 30 of 31 student faces recognised, 0 wrong matches, 5 of 5 strangers left unknown |
| APP 4 on the 6 classroom pictures | 6 of 6 students PRESENT, stranger not marked |
| APP 4 on the PTZ video | 6 of 6 students PRESENT |
| APP 4 on one picture without one student | 5 PRESENT, the missing student ABSENT |
| Pull API | Returns only student_id, class_name, session_id, time, status; JSON and CSV work |
| Live-webcam code paths (simulated camera, scripted keys) | Capture window, auto-capture, upload and attendance window all worked |
| Speed | About 8 frames per second with 6 faces on a cloud CPU; a laptop CPU should be similar |

One miss: in one classroom picture a student who had only 2 photos (1 for enrolment) scored 0.38, just under the 0.40 match threshold. He was recognised in the other pictures and in the video, so he was still marked PRESENT. More enrolment photos raise the score.

Not tested here: a real laptop webcam and real Windows, because the test machine has neither. The live-webcam path was tested with a simulated camera. Please run Sections 5 and 8 on your laptop.

## 12. Settings

Settings are in `common\config.py`. You can also set them for one run in a Command Prompt, for example `set MATCH_THRESHOLD=0.45` before starting an app.

| Setting | Default | Meaning |
|---|---|---|
| MATCH_THRESHOLD | 0.40 | Similarity needed to recognise a face (higher = stricter) |
| CONFIRM_FRAMES | 3 | Frames before a student is marked PRESENT |
| PHOTOS_PER_STUDENT | 5 | Photos APP 1 takes |
| MIN_GOOD_PHOTOS | 3 | Good photos APP 2 needs |
| MIN_FACE_PX_ENROL | 90 | Smallest face width for enrolment (pixels) |
| MIN_FACE_PX_ATTEND | 40 | Smallest face width looked at during attendance |
| DUPLICATE_THRESHOLD | 0.55 | Similarity at which a new enrolment is refused as a duplicate |
| CAMERA_INDEX | 0 | Webcam number |
| EDGE_PORT / OFFICE_PORT | 8002 / 8001 | Ports of APP 3 / APP 2 |
| EDGE_PUSH_KEY | ptz-demo-key | Key APP 2 must show to push faces to APP 3 |

## 13. Troubleshooting

| Problem | Fix |
|---|---|
| "Python 3.10 or newer was not found" | Install Python 3.12 with "Add python.exe to PATH", or run setup_windows.bat from the Anaconda Prompt |
| "Could not open camera 0" | Close APP 1 / APP 4, Teams, Zoom, Camera app. Try `--camera 1` (APP 1) or `--source 1` (APP 4). Check Windows Settings > Privacy > Camera |
| "Office PC not reachable" in APP 1 | Start 0_Start_Servers.bat; photos are kept, send them with --resend |
| "Edge AI service not reachable" in APP 4 | Start APP 3 (0_Start_Servers.bat) |
| A student is never recognised | Enrol again with more light and 5 good photos; sit closer; lower MATCH_THRESHOLD to 0.36 |
| Two students mixed up | Raise MATCH_THRESHOLD to 0.45 and enrol again with better photos |
| "Model file missing" | Run setup_windows.bat again (needs internet) |
| Port already in use | Another copy is running; close it, or set EDGE_PORT / OFFICE_PORT |

## 14. What this demo does not do (compared with the real PTZ system)

- It does not move a real PTZ camera or store taught points. The webcam is fixed; the simulation video imitates the camera visiting taught points.
- It has no liveness (anti-photo) check at enrolment, and no standby camera.
- All four apps run on one machine with a simple shared key, not over the college network with VPN and certificates.
- The pull API format is a placeholder until the college shares its own API specification.

## 15. Files in this folder

| File | What it is |
|---|---|
| setup_windows.bat | One-time setup |
| 0_Start_Servers.bat | Starts APP 3 and APP 2 and opens their dashboards |
| 1_Face_Capture.bat ... 4_Attendance.bat | Start each app |
| S1_ ... S5_ .bat | Simulation steps 1 to 5 (Section 10) |
| Reset_Demo_Data.bat | Deletes all demo data |
| app1_face_capture.py ... app4_attendance.py | The four apps |
| common\ | Shared settings, face engine (YuNet + SFace) and picture sources |
| tools\make_simulation.py | Photo synthesis for the simulation |
| tools\download_models.py | Checks and, if needed, downloads the face models |
| tests\check_scenes.py | Recognition check against sim\expected.txt |
| models\ | The two face models (YuNet MIT, SFace Apache-2.0) |
| data\ | Created when the apps run: Edge AI database, office job log, unsent photos |
