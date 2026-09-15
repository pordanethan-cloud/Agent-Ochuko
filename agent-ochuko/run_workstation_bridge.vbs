' run_workstation_bridge.vbs - Silent Background Launcher for Agent Ochuko Workstation Bridge
' Runs python -m app.connectors.workstation_bridge with a completely hidden window (0).

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Resolve backend directory
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
backendDir = scriptDir & "\backend"

If fso.FolderExists(backendDir) Then
    WshShell.CurrentDirectory = backendDir
Else
    WshShell.CurrentDirectory = scriptDir
End If

' Run Python workstation bridge hidden (0 = hide window, False = do not wait)
venvPy = backendDir & "\.venv\Scripts\python.exe"
If fso.FileExists(venvPy) Then
    cmd = """" & venvPy & """ -m app.connectors.workstation_bridge"
Else
    cmd = "cmd /c python -m app.connectors.workstation_bridge"
End If

WshShell.Run cmd, 0, False
