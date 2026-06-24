Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run chr(34) & scriptDir & "\start_jarvis.bat" & Chr(34), 0
Set WshShell = Nothing
