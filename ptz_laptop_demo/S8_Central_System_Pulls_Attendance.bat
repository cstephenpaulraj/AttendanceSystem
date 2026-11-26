@echo off
rem SIMULATION step 8: APP 5 (college central system) pulls the attendance of all of today's sessions and saves a CSV
cd /d "%~dp0"
.venv\Scripts\python app5_central_system.py pull --csv attendance_today.csv
pause
