Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\kirtan\IRIS\frontend"
WshShell.Run "cmd.exe /c npm run dev -- --host 0.0.0.0 --port 5173", 0, False
