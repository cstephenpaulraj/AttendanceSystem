@echo off
rem SIMULATION step 1: make enrolment shots, classroom pictures and a video from sim\people
cd /d "%~dp0"
if not exist sim\people (
  mkdir sim\people
  echo Put one folder per person in sim\people, named like S001_Asha, with 2-5 photos each.
  echo Add a folder UNKNOWN_visitor for a person who must NOT be recognised. Then run this again.
  start "" sim\people
  pause
  exit /b 1
)
.venv\Scripts\python tools\make_simulation.py --people sim\people --out sim
start "" sim
pause
