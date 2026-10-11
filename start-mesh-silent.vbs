Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\kirtan\IRIS\backend"
WshShell.Run """C:\kirtan\IRIS\backend\.venv\Scripts\pythonw.exe"" run_daemon.py", 0, False

