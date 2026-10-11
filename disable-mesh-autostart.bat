@echo off
title Disable IRIS Mesh Auto-Start
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT=%STARTUP_DIR%\IRIS-Mesh-Daemon.lnk

if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo [OK] Removed IRIS Mesh from Windows Startup.
) else (
    echo [INFO] IRIS Mesh was not set to auto-start.
)

pause
