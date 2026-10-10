# IRIS Development Environment Launcher
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Starting IRIS Development Environment" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

$root = $PSScriptRoot

$wifiIp = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Wi-Fi" -ErrorAction SilentlyContinue).IPAddress
if (-not $wifiIp) {
    $wifiIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch "^127\.|^169\.254\." } | Select-Object -First 1).IPAddress
}

Write-Host "`n[1/2] Starting Backend (FastAPI + Uvicorn on 0.0.0.0:8000)..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d `"$root\backend`" && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" -WindowStyle Normal

Write-Host "[2/2] Starting Frontend (Vite on 0.0.0.0:5173)..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d `"$root\frontend`" && npm run dev -- --host 0.0.0.0 --port 5173" -WindowStyle Normal

Write-Host "`n===================================================" -ForegroundColor Green
Write-Host "  IRIS is running!" -ForegroundColor Green
Write-Host "  Laptop (Local)   : http://localhost:5173" -ForegroundColor White
Write-Host "  Mobile Phone     : http://$($wifiIp):5173" -ForegroundColor Cyan
Write-Host "  Mobile Companion : http://$($wifiIp):8000/companion" -ForegroundColor Cyan
Write-Host "  Backend API      : http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs         : http://localhost:8000/docs" -ForegroundColor White
Write-Host "===================================================" -ForegroundColor Green
