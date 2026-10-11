@echo off
title Enable IRIS Mesh Auto-Start
echo ========================================================
echo   Setting up IRIS Mesh Background Auto-Start on Windows
echo ========================================================
echo.

set SCRIPT_DIR=%~dp0
set TARGET_VBS=%SCRIPT_DIR%start-mesh-silent.vbs
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT=%STARTUP_DIR%\IRIS-Mesh-Daemon.lnk

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%TARGET_VBS%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%backend'; $s.Description = 'IRIS Sovereign Mesh Background Daemon'; $s.Save()"

if exist "%SHORTCUT%" (
    echo [OK] Auto-Start shortcut successfully created in Windows Startup folder!
    echo [OK] IRIS Mesh will now start automatically and silently whenever your laptop boots.
    echo.
    echo Starting IRIS Mesh daemon now in background...
    wscript.exe "%TARGET_VBS%"
    echo [OK] IRIS Mesh is now running in the background!
) else (
    echo [ERROR] Failed to create shortcut.
)

echo.
pause
