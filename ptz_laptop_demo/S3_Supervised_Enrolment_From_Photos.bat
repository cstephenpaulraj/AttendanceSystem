@echo off
rem SIMULATION step 3: APP 1 on the college enrolment phone, supervised by staff STAFF01, sends every student's photos to the office PC
cd /d "%~dp0"
.venv\Scripts\python app1_face_capture.py --batch sim\enrol --class MBBS1 --staff STAFF01 --pin 1111 --id-card-checked
pause
