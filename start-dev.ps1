# IRIS Development Environment Launcher
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Starting IRIS Development Environment" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

$root = $PSScriptRoot

Write-Host "`n[1/2] Starting Backend (FastAPI + Uvicorn)..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d `"$root\backend`" && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload" -WindowStyle Normal

Write-Host "[2/2] Starting Frontend (Vite)..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d `"$root\frontend`" && npm run dev -- --host 127.0.0.1 --port 5173" -WindowStyle Normal

Write-Host "`n===================================================" -ForegroundColor Green
Write-Host "  IRIS is running!" -ForegroundColor Green
Write-Host "  Frontend : http://localhost:5173" -ForegroundColor White
Write-Host "  Backend  : http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  API Docs : http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "===================================================" -ForegroundColor Green
