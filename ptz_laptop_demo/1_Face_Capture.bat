@echo off
rem APP 1 - Face capture (live webcam). Extra options can be added after the file name.
cd /d "%~dp0"
.venv\Scripts\python app1_face_capture.py %*
pause
