# scripts/register_ochuko_protocol.ps1
# Registers the custom Windows protocol ochuko:// so the browser web app can
# launch the Workstation Bridge silently on-demand without keeping it running 24/7.

$ErrorActionPreference = "Stop"

$repoRoot = (Get-Item -Path $PSScriptRoot).Parent.FullName
$vbsPath = Join-Path $repoRoot "agent-ochuko\run_workstation_bridge.vbs"

if (-not (Test-Path $vbsPath)) {
    Write-Error "Could not find run_workstation_bridge.vbs at: $vbsPath"
}

$commandVal = "wscript.exe `"$vbsPath`" `"%1`""

$protocolKey = "HKCU:\Software\Classes\ochuko"
New-Item -Path $protocolKey -Force | Out-Null
Set-ItemProperty -Path $protocolKey -Name "(Default)" -Value "URL:Agent Ochuko Workstation Protocol" -Force
Set-ItemProperty -Path $protocolKey -Name "URL Protocol" -Value "" -Force

$cmdKey = "$protocolKey\shell\open\command"
New-Item -Path $cmdKey -Force | Out-Null
Set-ItemProperty -Path $cmdKey -Name "(Default)" -Value $commandVal -Force

Write-Host "Success: ochuko:// protocol registered in HKCU." -ForegroundColor Green
Write-Host "Command: $commandVal" -ForegroundColor Gray
Write-Host "Browser calls to ochuko://start will now launch the local bridge on-demand silently." -ForegroundColor Cyan
