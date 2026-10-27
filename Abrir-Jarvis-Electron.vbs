Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
jarvisDir = fso.GetParentFolderName(WScript.ScriptFullName)
electronExe = jarvisDir & "\electron\node_modules\electron\dist\electron.exe"
electronApp = jarvisDir & "\electron"
WshShell.Run """" & electronExe & """ """ & electronApp & """", 0, False
