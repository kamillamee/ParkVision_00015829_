@echo off
REM =====================================================================
REM Backup public tunnel via Cloudflare quick-tunnel.
REM Use this if ngrok is rate-limited / down / acting up mid-demo.
REM No signup needed for the quick-tunnel mode.
REM Looks for cloudflared in: PATH, the ParkVision folder, then Desktop.
REM =====================================================================
cd /d "%~dp0"

REM ---- Locate cloudflared.exe ----
set "CFD="
where cloudflared >nul 2>&1
if not errorlevel 1 set "CFD=cloudflared"

if not defined CFD if exist ".\cloudflared.exe" set "CFD=.\cloudflared.exe"
if not defined CFD if exist "%USERPROFILE%\Desktop\cloudflared.exe" set "CFD=%USERPROFILE%\Desktop\cloudflared.exe"

if not defined CFD (
    echo [cloudflared] cloudflared.exe not found.
    echo [cloudflared] Tried PATH, this folder, and Desktop.
    echo [cloudflared] Install via:  winget install Cloudflare.cloudflared
    echo [cloudflared] Or download:  https://github.com/cloudflare/cloudflared/releases/latest
    pause
    exit /b 1
)

echo [cloudflared] Using: %CFD%
echo.
echo [cloudflared] Starting backup tunnel  http://localhost:8000  -^>  https://*.trycloudflare.com
echo [cloudflared] Look for the line printed below that contains "trycloudflare.com" and share that URL.
echo [cloudflared] Press Ctrl+C to stop.
echo.

"%CFD%" tunnel --url http://localhost:8000 --no-autoupdate
