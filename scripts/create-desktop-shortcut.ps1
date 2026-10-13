$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop "IRIS.lnk"

$targetExe = "C:\kirtan\IRIS\desktop\dist\IRIS-win32-x64\IRIS.exe"
if (-not (Test-Path $targetExe)) {
    $targetExe = "C:\kirtan\IRIS\IRIS.exe"
}

$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetExe
$shortcut.WorkingDirectory = Split-Path -Path $targetExe -Parent
$shortcut.IconLocation = "C:\kirtan\IRIS\desktop\assets\icon.ico"
$shortcut.Description = "IRIS - Intelligent Responsive Information System"
$shortcut.Save()

Write-Host "IRIS desktop shortcut updated at: $shortcutPath -> $targetExe"
