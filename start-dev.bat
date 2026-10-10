@echo off
title IRIS - Intelligent Responsive Information System
echo ===================================================
echo   Starting IRIS Development Environment
echo ===================================================

cd /d "%~dp0"

echo [1/2] Starting Backend (FastAPI + Uvicorn on 0.0.0.0:8000)...
start "IRIS Backend (Port 8000)" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo [2/2] Starting Frontend (Vite on 0.0.0.0:5173)...
start "IRIS Frontend (Port 5173)" cmd /k "cd /d %~dp0frontend && npm run dev -- --host 0.0.0.0 --port 5173"

echo.
echo ===================================================
echo   IRIS is launching!
echo   Frontend (Laptop)   : http://localhost:5173
echo   Mobile Phone Access : Check your Wi-Fi IP (e.g. 192.168.1.5:5173)
echo   Mobile Companion    : http://192.168.1.5:8000/companion
echo   Backend             : http://localhost:8000
echo   API Docs            : http://localhost:8000/docs
echo ===================================================
