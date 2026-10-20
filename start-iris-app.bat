@echo off
title Launching IRIS Desktop App...
cd /d "%~dp0"

:: 1. Ensure backend daemon on port 8000 is listening; start silently if needed
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue)) { wscript.exe '%~dp0start-mesh-silent.vbs' }"

:: 2. Launch Electron Native Desktop App
cd /d "%~dp0desktop"
npm start
