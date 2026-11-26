@echo off
rem SIMULATION step 6: session 3 (BIOC103). BOTH cameras fail: attendance from the RF card taps in sim\rf_taps.txt
cd /d "%~dp0"
.venv\Scripts\python app4_attendance.py --subject BIOC103 --source fail --standby fail --rf-taps sim\rf_taps.txt
pause
