' run_workstation_bridge.vbs - Silent Background Launcher for Agent Ochuko Workstation Bridge
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
' Go up two levels to backend directory
backendDir = fso.GetParentFolderName(fso.GetParentFolderName(scriptDir))

WshShell.CurrentDirectory = backendDir
cmd = "cmd /c python -m app.connectors.workstation_bridge"
WshShell.Run cmd, 0, False
