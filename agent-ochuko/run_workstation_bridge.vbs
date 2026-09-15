' run_workstation_bridge.vbs - Silent Background Launcher for Agent Ochuko Workstation Bridge
' Runs python -m app.connectors.workstation_bridge with completely hidden window (0).

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
backendDir = scriptDir & "\backend"

If fso.FolderExists(backendDir) Then
    WshShell.CurrentDirectory = backendDir
Else
    WshShell.CurrentDirectory = scriptDir
End If

venvPy = backendDir & "\.venv\Scripts\python.exe"
If fso.FileExists(venvPy) Then
    pyExe = venvPy
Else
    pyExe = "python.exe"
End If

args = ""
If WScript.Arguments.Count > 0 Then
    args = " " & Chr(34) & WScript.Arguments(0) & Chr(34)
End If

cmd = Chr(34) & pyExe & Chr(34) & " -m app.connectors.workstation_bridge" & args
WshShell.Run cmd, 0, False
