@echo off
rem Starts APP 3 (Edge AI service) and APP 2 (Enrolment Converter) in their own windows
cd /d "%~dp0"
start "APP 3 - Edge AI service" cmd /k 3_Edge_AI_Service.bat
timeout /t 3 /nobreak >nul
start "APP 2 - Enrolment Converter (office PC)" cmd /k 2_Enrolment_Converter.bat
timeout /t 5 /nobreak >nul
start "" http://127.0.0.1:8002
start "" http://127.0.0.1:8001
