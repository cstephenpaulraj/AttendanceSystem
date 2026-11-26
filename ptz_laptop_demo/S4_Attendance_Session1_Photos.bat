@echo off
rem SIMULATION step 4: session 1 (ANAT101) from the classroom pictures
cd /d "%~dp0"
.venv\Scripts\python app4_attendance.py --subject ANAT101 --source sim\classroom
pause
