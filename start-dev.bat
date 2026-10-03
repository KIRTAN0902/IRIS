@echo off
title IRIS - Intelligent Responsive Information System
echo ===================================================
echo   Starting IRIS Development Environment
echo ===================================================

cd /d "%~dp0"

echo [1/2] Starting Backend (FastAPI + Uvicorn)...
start "IRIS Backend (Port 8000)" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo [2/2] Starting Frontend (Vite)...
start "IRIS Frontend (Port 5173)" cmd /k "cd /d %~dp0frontend && npm run dev -- --host 127.0.0.1 --port 5173"

echo.
echo ===================================================
echo   IRIS is launching!
echo   Frontend : http://localhost:5173
echo   Backend  : http://127.0.0.1:8000
echo   API Docs : http://127.0.0.1:8000/docs
echo ===================================================
