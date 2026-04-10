@echo off
echo Standalone AI module (optional). Embedded vision runs inside python run.py by default.
echo Use --legacy-disk-frames if you still need video/latest.jpg on disk.
cd /d "%~dp0"
python ai_module/inference.py %*
pause
