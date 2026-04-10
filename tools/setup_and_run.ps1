# PowerShell script to setup and run the Smart Vision System
Set-Location $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Smart Vision System - Setup and Run" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Step 1: Activating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1
if (-not $?) {
    Write-Host "ERROR: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please create it first: python -m venv venv" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 2: Installing/updating dependencies..." -ForegroundColor Yellow
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not $?) {
    Write-Host "ERROR: Failed to install dependencies!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 3: Verifying uvicorn installation..." -ForegroundColor Yellow
.\venv\Scripts\python.exe -c "import uvicorn; print('uvicorn version:', uvicorn.__version__)"
if (-not $?) {
    Write-Host "ERROR: uvicorn is not installed!" -ForegroundColor Red
    Write-Host "Installing uvicorn directly..." -ForegroundColor Yellow
    .\venv\Scripts\python.exe -m pip install uvicorn[standard]
}

Write-Host ""
Write-Host "Step 4: Initializing database..." -ForegroundColor Yellow
.\venv\Scripts\python.exe backend\init_db.py

Write-Host ""
Write-Host "Step 5: Seeding parking slots..." -ForegroundColor Yellow
.\venv\Scripts\python.exe backend\seed_slots.py

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Server..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
.\venv\Scripts\python.exe run.py
