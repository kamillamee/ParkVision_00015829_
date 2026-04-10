@echo off
cd /d "%~dp0"
echo ========================================
echo Smart Vision System - Setup and Run
echo ========================================
echo.

echo Step 1: Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Virtual environment not found!
    echo Please create it first: python -m venv venv
    pause
    exit /b 1
)

echo.
echo Step 2: Installing/updating dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies!
    pause
    exit /b 1
)

echo.
echo Step 3: Verifying uvicorn installation...
venv\Scripts\python.exe -c "import uvicorn; print('uvicorn version:', uvicorn.__version__)"
if errorlevel 1 (
    echo ERROR: uvicorn is not installed!
    echo Installing uvicorn directly...
    venv\Scripts\python.exe -m pip install uvicorn[standard]
)

echo.
echo Step 4: Initializing database...
venv\Scripts\python.exe backend\init_db.py
if errorlevel 1 (
    echo WARNING: Database initialization had issues
)

echo.
echo Step 5: Seeding parking slots...
venv\Scripts\python.exe backend\seed_slots.py
if errorlevel 1 (
    echo WARNING: Slot seeding had issues
)

echo.
echo ========================================
echo Starting Server...
echo ========================================
echo.
venv\Scripts\python.exe run.py
pause
