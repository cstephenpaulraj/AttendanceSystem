@echo off
rem ===== PTZ laptop demo: one-time setup (about 5 minutes, about 0.5 GB) =====
cd /d "%~dp0"
echo.
echo === PTZ laptop demo - setup ===
set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.10 or newer was not found.
  echo Install Python 3.12 from https://www.python.org/downloads/windows/ and tick "Add python.exe to PATH",
  echo or run this file from the "Anaconda Prompt".
  pause
  exit /b 1
)
echo Using: %PY%
if not exist .venv\Scripts\python.exe %PY% -m venv .venv || goto fail
.venv\Scripts\python -m pip install --upgrade pip || goto fail
.venv\Scripts\python -m pip install -r requirements.txt || goto fail
.venv\Scripts\python tools\download_models.py || goto fail
echo.
echo Setup complete. Next: double-click 0_Start_Servers.bat
pause
exit /b 0
:fail
echo.
echo Setup FAILED - see the messages above.
pause
exit /b 1
