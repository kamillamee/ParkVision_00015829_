@echo off
REM =====================================================================
REM Primary public tunnel via ngrok.
REM Run AFTER start_demo.bat is up on port 8000.
REM Looks for ngrok in: PATH, the ParkVision folder, then your Desktop.
REM =====================================================================
cd /d "%~dp0"

REM ---- Locate ngrok.exe ----
set "NGROK="
where ngrok >nul 2>&1
if not errorlevel 1 set "NGROK=ngrok"

if not defined NGROK if exist ".\ngrok.exe" set "NGROK=.\ngrok.exe"
if not defined NGROK if exist "%USERPROFILE%\Desktop\ngrok-v3-stable-windows-amd64\ngrok.exe" set "NGROK=%USERPROFILE%\Desktop\ngrok-v3-stable-windows-amd64\ngrok.exe"
if not defined NGROK if exist "%USERPROFILE%\Desktop\ngrok.exe" set "NGROK=%USERPROFILE%\Desktop\ngrok.exe"

if not defined NGROK (
    echo [ngrok] ngrok.exe not found.
    echo [ngrok] Tried PATH, this folder, and Desktop\ngrok-v3-stable-windows-amd64\.
    echo [ngrok] Either copy ngrok.exe next to start_ngrok.bat,
    echo [ngrok] or install via:  winget install ngrok.ngrok
    pause
    exit /b 1
)

echo [ngrok] Using: %NGROK%
echo.
echo [ngrok] Forwarding  http://localhost:8000  -^>  https://*.ngrok-free.app
echo [ngrok] Copy the "Forwarding" https URL printed below and share it.
echo [ngrok] Press Ctrl+C to stop the tunnel.
echo.

"%NGROK%" http 8000
