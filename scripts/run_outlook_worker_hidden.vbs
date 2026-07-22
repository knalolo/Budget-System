Option Explicit

Dim fso, shell, scriptDir, repoRoot, pythonPath, managePath, logPath
Dim command, exitCode

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
repoRoot = fso.GetParentFolderName(scriptDir)
pythonPath = fso.BuildPath(repoRoot, ".venv\Scripts\python.exe")
managePath = fso.BuildPath(repoRoot, "manage.py")
logPath = fso.BuildPath(repoRoot, "outlook-worker.log")

shell.CurrentDirectory = repoRoot
command = "cmd.exe /d /c " & Chr(34) & Chr(34) & pythonPath & Chr(34) & _
    " " & Chr(34) & managePath & Chr(34) & _
    " send_outlook_outbox --send --limit 10 >> " & Chr(34) & logPath & Chr(34) & _
    " 2>&1" & Chr(34)

exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode
