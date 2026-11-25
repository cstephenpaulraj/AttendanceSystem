# PTZ laptop demo (PTZ taught-point concept)

Four apps that run together on one Windows laptop. The laptop webcam stands in for the PTZ camera; the laptop is also the face capturing hardware, the office PC and the Edge AI server. Every app works with the live webcam or with sample photos / video.

| App | Role | Start |
|---|---|---|
| `app1_face_capture.py` | Face capture (webcam = PTZ camera) | `1_Face_Capture.bat` |
| `app2_enrolment_converter.py` | Enrolment Converter (office PC), http://127.0.0.1:8001 | `0_Start_Servers.bat` |
| `app3_edge_ai_server.py` | Edge AI service: face DB (SQLite + FAISS), pull API, http://127.0.0.1:8002 | `0_Start_Servers.bat` |
| `app4_attendance.py` | Attendance (recognises 5-6 people at once) | `4_Attendance.bat` |

Quick start: double-click `setup_windows.bat` once, then `0_Start_Servers.bat`, `1_Face_Capture.bat`, and `4_Attendance.bat`.
Simulation from photos: `S1_Make_Simulation.bat` to `S5_Check_Recognition.bat`.

Full instructions: [USER_GUIDE.md](USER_GUIDE.md) (also as [PDF](PTZ_Laptop_Demo_User_Guide.pdf)).

Technology: OpenCV YuNet (detector, MIT) + SFace (recogniser, Apache-2.0) on CPU, FAISS, SQLite, FastAPI. No NVIDIA GPU needed; about 0.5 GB installed.
