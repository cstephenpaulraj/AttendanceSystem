@echo off
rem APP 3 - Edge AI service - dashboard http://127.0.0.1:8002 - pull API /api/attendance
cd /d "%~dp0"
.venv\Scripts\python app3_edge_ai_server.py %*
pause
