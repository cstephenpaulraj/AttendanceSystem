@echo off
rem APP 5 - College central system simulator (send students and sessions, pull attendance)
cd /d "%~dp0"
.venv\Scripts\python app5_central_system.py %*
pause
