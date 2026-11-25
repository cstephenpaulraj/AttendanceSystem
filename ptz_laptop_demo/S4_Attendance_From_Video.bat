@echo off
rem SIMULATION step 4: APP 4 takes attendance from the simulated PTZ video (camera visits taught points)
cd /d "%~dp0"
set /p CLS=Class name [MBBS1]: 
if "%CLS%"=="" set CLS=MBBS1
.venv\Scripts\python app4_attendance.py --class %CLS% --source sim\classroom.mp4
pause
