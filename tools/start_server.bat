@echo off
cd /d "%~dp0"
echo Activating virtual environment...
call venv\Scripts\activate.bat
echo.

echo Checking uvicorn installation...
venv\Scripts\python.exe -c "import uvicorn" 2>nul
if errorlevel 1 (
    echo uvicorn not found! Installing...
    venv\Scripts\python.exe -m pip install uvicorn[standard]
)

echo.
echo Running diagnostic and starting server...
echo.
venv\Scripts\python.exe diagnose_and_run.py
pause
