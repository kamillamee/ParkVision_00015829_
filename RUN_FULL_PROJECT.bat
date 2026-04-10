@echo off
cd /d "%~dp0"

echo Starting Smart Vision (server + embedded MJPEG + YOLO)...
echo Optional: set PARKING_VISION_ENABLED=false to disable in-process vision.
start "Smart Vision" cmd /k "python run.py"

echo.
echo Server at http://localhost:8000
echo Live video: MJPEG at /api/stream/mjpeg/{lotId} — no separate AI window needed.
echo Standalone AI (legacy): python ai_module/inference.py --legacy-disk-frames
echo Close the window or press Ctrl+C to stop.
