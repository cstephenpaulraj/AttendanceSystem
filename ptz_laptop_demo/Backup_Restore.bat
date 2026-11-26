@echo off
rem Lists the encrypted face database backups and, if you type YES, restores the newest good one (close APP 3 first)
cd /d "%~dp0"
.venv\Scripts\python tools\restore_backup.py --list
set /p OK=Restore the newest good backup now? Type YES: 
if /i not "%OK%"=="YES" exit /b 0
.venv\Scripts\python tools\restore_backup.py --restore latest
pause
