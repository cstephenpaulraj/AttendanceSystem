@echo off
rem SIMULATION step 3: APP 4 takes attendance from the simulated classroom pictures
cd /d "%~dp0"
set /p CLS=Class name [MBBS1]: 
if "%CLS%"=="" set CLS=MBBS1
.venv\Scripts\python app4_attendance.py --class %CLS% --source sim\classroom
pause
