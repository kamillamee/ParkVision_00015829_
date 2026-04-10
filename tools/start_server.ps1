# PowerShell script to start the Smart Vision System
Set-Location $PSScriptRoot
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1
Write-Host ""
Write-Host "Running diagnostic and starting server..." -ForegroundColor Green
Write-Host ""
.\venv\Scripts\python.exe diagnose_and_run.py
