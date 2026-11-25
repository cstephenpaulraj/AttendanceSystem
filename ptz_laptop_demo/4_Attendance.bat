@echo off
rem APP 4 - Attendance (live webcam). Extra options can be added after the file name.
cd /d "%~dp0"
.venv\Scripts\python app4_attendance.py %*
pause
