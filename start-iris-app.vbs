Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\kirtan\IRIS"
WshShell.Run "cmd.exe /c start-iris-app.bat", 0, False
