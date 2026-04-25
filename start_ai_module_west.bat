@echo off
echo Westminster standalone AI (optional). Prefer: python run.py (embedded vision for all is_live lots).
echo Pass --lot-id matching your DB Westminster row if slot updates target the wrong lot.
cd /d "%~dp0"
python ai_module/inference.py --lot-id 2 --video video/west.mp4 --slots-json config/west.json --no-gui %*
pause
