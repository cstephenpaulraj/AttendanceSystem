# PTZ laptop demo (PTZ taught-point concept)

Five apps that run together on one Windows laptop. The laptop webcam stands in for the PTZ camera and for the camera of the dedicated college enrolment phone; the laptop is also the office PC, the Edge AI server and the college central system. Every camera app works with the live webcam or with sample photos / video.

| App | Role | Start |
|---|---|---|
| `app1_face_capture.py` | Enrolment app on the dedicated college phone, supervised by college staff (staff login, ID card check) | `1_Face_Capture.bat` |
| `app2_enrolment_converter.py` | Enrolment Converter (office PC), http://127.0.0.1:8001 | `0_Start_Servers.bat` |
| `app3_edge_ai_server.py` | Edge AI service: face DB (SQLite + FAISS), sessions from the central system, attendance, lecturer override, encrypted backups, audit log, pull API, http://127.0.0.1:8002 | `0_Start_Servers.bat` |
| `app4_attendance.py` | Attendance for one lecture session: primary camera, standby camera, RF reader fallback | `4_Attendance.bat` |
| `app5_central_system.py` | College central system simulator: sends students and sessions, pulls attendance | `5_Central_System.bat` |

Quick start: double-click `setup_windows.bat` once, then `0_Start_Servers.bat`, `5_Central_System.bat` (send students and sessions), `1_Face_Capture.bat` and `4_Attendance.bat`.
Simulation from photos: `S1_Make_Simulation.bat` to `S8_Central_System_Pulls_Attendance.bat`. Restore the face database: `Backup_Restore.bat`.

Full instructions: [USER_GUIDE.md](USER_GUIDE.md) (also as [PDF](PTZ_Laptop_Demo_User_Guide.pdf)). Design: [docs/PTZ_Implementation.md](../docs/PTZ_Implementation.md).

Technology: OpenCV YuNet (detector, MIT) + SFace (recogniser, Apache-2.0) on CPU, FAISS, SQLite, FastAPI, cryptography (Fernet) for encrypted backups. No NVIDIA GPU needed; about 0.5 GB installed.
