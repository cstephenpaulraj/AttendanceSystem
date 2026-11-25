@echo off
rem APP 2 - Enrolment Converter (office PC) - dashboard http://127.0.0.1:8001
cd /d "%~dp0"
.venv\Scripts\python app2_enrolment_converter.py %*
pause
