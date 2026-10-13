$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop "IRIS.lnk"

$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"C:\kirtan\IRIS\start-iris-app.vbs`""
$shortcut.WorkingDirectory = "C:\kirtan\IRIS"
$shortcut.IconLocation = "C:\kirtan\IRIS\desktop\assets\icon.ico"
$shortcut.Description = "IRIS - Intelligent Responsive Information System"
$shortcut.Save()

Write-Host "IRIS desktop shortcut created at: $shortcutPath"
