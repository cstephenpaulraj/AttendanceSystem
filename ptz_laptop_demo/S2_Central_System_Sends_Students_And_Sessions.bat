@echo off
rem SIMULATION step 2: APP 5 (college central system) sends the student list with RF cards and today's 3 sessions
cd /d "%~dp0"
.venv\Scripts\python app5_central_system.py students --csv sim\college_students.csv
.venv\Scripts\python app5_central_system.py sessions --csv sim\timetable.csv
.venv\Scripts\python app5_central_system.py list
pause
