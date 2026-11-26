@echo off
rem Deletes ALL demo data: the Edge AI database and its backups, attendance, office job history and unsent photos
cd /d "%~dp0"
echo Close APP 2 and APP 3 first.
set /p OK=Delete all demo data in "%~dp0data"? Type YES: 
if /i not "%OK%"=="YES" exit /b 0
rmdir /s /q data
echo Done.
pause
