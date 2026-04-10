@echo off
cd /d "%~dp0"
if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
echo Starting Sensor Emulator (backend must be running on http://127.0.0.1:8000)
python tools/sensor_emulator.py %*
pause
