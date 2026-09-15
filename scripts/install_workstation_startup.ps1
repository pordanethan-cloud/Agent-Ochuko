# scripts/install_workstation_startup.ps1
# Configures the Agent Ochuko Workstation Bridge to run automatically and silently
# in the background on Windows startup, giving the agent persistent PC directory access.

$ErrorActionPreference = "Stop"

$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.FullName
$vbsPath = Join-Path $repoRoot "agent-ochuko\run_workstation_bridge.vbs"
$backendDir = Join-Path $repoRoot "agent-ochuko\backend"

if (-not (Test-Path $vbsPath)) {
    Write-Error "Could not find run_workstation_bridge.vbs at: $vbsPath"
}

$wsh = New-Object -ComObject WScript.Shell
$startupPath = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupPath "Agent Ochuko Workstation Bridge.lnk"

$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"$vbsPath`""
$shortcut.WorkingDirectory = $backendDir
$shortcut.Description = "Agent Ochuko Silent Background Workstation Bridge"
$shortcut.Save()

Write-Host "Success: Workstation Bridge registered for Windows Startup." -ForegroundColor Green
Write-Host "Location: $shortcutPath" -ForegroundColor Cyan
