@echo off
title IRIS Desktop Reinstaller
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-desktop.ps1"
pause
