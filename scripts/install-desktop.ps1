# IRIS Desktop Reinstaller & Shortcut Provisioner
$ErrorActionPreference = "Stop"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "     Reinstalling IRIS Desktop Application   " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

$repoRoot = "C:\kirtan\IRIS"
$desktopExe = "$repoRoot\desktop\dist\IRIS-win32-x64\IRIS.exe"
$desktopWorkingDir = "$repoRoot\desktop\dist\IRIS-win32-x64"
$appResourceDir = "$desktopWorkingDir\resources\app"
$iconPath = "$repoRoot\desktop\assets\icon.ico"
$desktopLnk = "$([Environment]::GetFolderPath('Desktop'))\IRIS.lnk"
$startMenuLnk = "$([Environment]::GetFolderPath('Programs'))\IRIS.lnk"
$chromeAppLnk = "$([Environment]::GetFolderPath('Programs'))\Chrome Apps\IRIS.lnk"

# 1. Close any running IRIS instances
Write-Host "[1/6] Terminating running IRIS processes..." -ForegroundColor Yellow
Get-Process -Name "*electron*", "*iris*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800

# 2. Build live frontend and sync files
Write-Host "[2/6] Compiling production frontend bundle..." -ForegroundColor Yellow
Set-Location "$repoRoot\frontend"
npm run build

Write-Host "[3/6] Syncing desktop distribution resources..." -ForegroundColor Yellow
Set-Location $repoRoot
Copy-Item -Path "$repoRoot\desktop\main.cjs" -Destination "$appResourceDir\main.cjs" -Force
Copy-Item -Path "$repoRoot\desktop\preload.cjs" -Destination "$appResourceDir\preload.cjs" -Force
Copy-Item -Path "$repoRoot\desktop\loading.html" -Destination "$appResourceDir\loading.html" -Force
Copy-Item -Path "$repoRoot\desktop\assets\*" -Destination "$appResourceDir\assets" -Recurse -Force
Copy-Item -Path "$repoRoot\frontend\dist\*" -Destination "$appResourceDir\dist-frontend" -Recurse -Force

# 4. Clear old caches
Write-Host "[4/6] Purging stale Electron cache..." -ForegroundColor Yellow
$userData = "$env:APPDATA\IRIS-Desktop"
Remove-Item -Path "$userData\Cache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$userData\Code Cache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$userData\DawnGraphiteCache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$userData\DawnWebGPUCache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$userData\GPUCache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$userData\lockfile" -Force -ErrorAction SilentlyContinue

# 5. Remove obsolete Chrome PWA shortcut if present
if (Test-Path $chromeAppLnk) {
    Write-Host "Removing legacy Chrome PWA shortcut..." -ForegroundColor DarkGray
    Remove-Item -Path $chromeAppLnk -Force -ErrorAction SilentlyContinue
}

# 6. Create official Desktop & Start Menu Shortcuts
Write-Host "[5/6] Creating official Windows Desktop & Start Menu shortcuts..." -ForegroundColor Yellow
$wsh = New-Object -ComObject WScript.Shell

# Desktop Shortcut
$sDesktop = $wsh.CreateShortcut($desktopLnk)
$sDesktop.TargetPath = $desktopExe
$sDesktop.WorkingDirectory = $desktopWorkingDir
$sDesktop.IconLocation = "$iconPath,0"
$sDesktop.Description = "IRIS - Intelligent Responsive Information System"
$sDesktop.Save()

# Start Menu Shortcut
$sStart = $wsh.CreateShortcut($startMenuLnk)
$sStart.TargetPath = $desktopExe
$sStart.WorkingDirectory = $desktopWorkingDir
$sStart.IconLocation = "$iconPath,0"
$sStart.Description = "IRIS - Intelligent Responsive Information System"
$sStart.Save()

# Ensure Auto-start Daemon is enabled
$startupLnk = "$([Environment]::GetFolderPath('Startup'))\IRIS-Mesh-Daemon.lnk"
$vbs = "$repoRoot\start-mesh-silent.vbs"
$sAuto = $wsh.CreateShortcut($startupLnk)
$sAuto.TargetPath = "wscript.exe"
$sAuto.Arguments = "`"$vbs`""
$sAuto.WorkingDirectory = "$repoRoot\backend"
$sAuto.Description = "IRIS Sovereign Mesh Background Daemon"
$sAuto.Save()

# 7. Start Backend Daemon and Launch Application
Write-Host "[6/6] Launching IRIS Desktop Application..." -ForegroundColor Green
Start-Process -FilePath "wscript.exe" -ArgumentList "`"$vbs`"" -WorkingDirectory "$repoRoot\backend"
Start-Sleep -Milliseconds 1200
Start-Process -FilePath $desktopExe -WorkingDirectory $desktopWorkingDir

Write-Host "=============================================" -ForegroundColor Green
Write-Host "  IRIS has been successfully reinstalled!    " -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
