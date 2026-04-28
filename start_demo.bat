@echo off
REM =====================================================================
REM ParkVision live-demo launcher.
REM Binds 0.0.0.0:8000 so ngrok / cloudflared / phones-on-LAN can reach it.
REM Keeps detection / DB / UI logic untouched.
REM =====================================================================
cd /d "%~dp0"

REM ---- Demo environment variables ----
set HOST=0.0.0.0
set PORT=8000
set DEBUG=False
set CORS_ALLOW_ORIGINS=*
set PARKING_VISION_ENABLED=true
set PARKING_VISION_DETECT_FPS=4
set PARKING_VISION_DEVICE=cpu
REM ---- Tunnel-friendly MJPEG settings (cuts bandwidth ~80%) ----
REM Drop these further if video still stutters over a tunnel.
set PARKING_VISION_DISPLAY_FPS=8
set PARKING_VISION_STREAM_QUALITY=55

REM ---- Sanity checks ----
if not exist "venv\Scripts\python.exe" (
    echo [demo] ERROR venv missing. Run:  python -m venv venv
    pause
    exit /b 1
)

if not exist "video\bmu.mp4" echo [demo] WARN video\bmu.mp4 missing
if not exist "video\west.mp4" echo [demo] WARN video\west.mp4 missing
if not exist "models\yolo11m.pt" echo [demo] INFO yolo11m.pt missing - will auto-download on first start

echo.
echo ======================================================================
echo  ParkVision DEMO - uvicorn starting on 0.0.0.0:%PORT%
echo  Local:    http://localhost:%PORT%
echo  LAN:      run 'ipconfig' then visit http://YOUR-IPv4:%PORT%
echo  ngrok:    open another terminal and run start_ngrok.bat
echo  Login:    +1234567890  /  admin123
echo  Press Ctrl+C in this window to stop.
echo ======================================================================
echo.

call venv\Scripts\activate.bat
python run.py

if errorlevel 1 (
    echo.
    echo [demo] uvicorn exited with errorlevel %errorlevel%
    pause
)
