' Starts CasuallyHedge in the background with no console window and opens it in your browser.
' To stop it, double-click "Stop CasuallyHedge.bat".
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
sh.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Environment("PROCESS")("TS_HIDDEN") = "1"
sh.Run "cmd /c start.bat", 0, False
