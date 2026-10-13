@echo off
title Launching IRIS Desktop App...
cd /d "%~dp0"

:: 1. Check if backend on port 8000 is listening; start silently if needed
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue)) { wscript.exe '%~dp0start-mesh-silent.vbs' }"

:: 2. Check if frontend on port 5173 is listening; start if needed
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue)) { Start-Process cmd -ArgumentList '/c cd /d %~dp0frontend && npm run dev' -WindowStyle Hidden }"

:: 3. Launch Electron Desktop App
cd /d "%~dp0desktop"
npm start
