@echo off
rem SIMULATION step 2: APP 1 sends every simulated student's photos to the office PC (APP 2 and 3 must be running)
cd /d "%~dp0"
set /p CLS=Class name [MBBS1]: 
if "%CLS%"=="" set CLS=MBBS1
.venv\Scripts\python app1_face_capture.py --batch sim\enrol --class %CLS%
pause
