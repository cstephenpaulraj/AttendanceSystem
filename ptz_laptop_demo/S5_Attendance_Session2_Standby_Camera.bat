@echo off
rem SIMULATION step 5: session 2 (PHYS102). The primary camera fails, the standby camera (PTZ video) takes over.
rem One student is not on the central system's list for this session and is reported NOT_IN_LIST.
cd /d "%~dp0"
.venv\Scripts\python app4_attendance.py --subject PHYS102 --source fail --standby sim\classroom.mp4
pause
