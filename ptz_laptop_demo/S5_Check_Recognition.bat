@echo off
rem SIMULATION step 5: compare recognition on each classroom picture with sim\expected.txt
cd /d "%~dp0"
.venv\Scripts\python tests\check_scenes.py --sim sim
pause
