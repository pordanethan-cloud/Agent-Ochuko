@echo off
setlocal enabledelayedexpansion
title Agent Ochuko Workstation Companion Bridge

set SCRIPT_DIR=%~dp0
set BACKEND_DIR=%SCRIPT_DIR%backend

if exist "%BACKEND_DIR%" (
    cd /d "%BACKEND_DIR%"
) else (
    cd /d "%SCRIPT_DIR%"
)

if "%1"=="" goto help
if "%1"=="start" goto foreground
if "%1"=="background" goto background
if "%1"=="bg" goto background
if "%1"=="silent" goto background
if "%1"=="status" goto status
if "%1"=="stop" goto stop

:help
echo =========================================================================
echo  Agent Ochuko - Local Workstation Companion Bridge
echo =========================================================================
echo.
echo  Usage:
echo    run_workstation_bridge.bat background  - Launch bridge silently in background (No terminal window)
echo    run_workstation_bridge.bat start       - Launch bridge in this terminal window (Foreground)
echo    run_workstation_bridge.bat status      - Check if bridge is online on port 3920
echo    run_workstation_bridge.bat stop        - Stop the running bridge process
echo.
echo  Defaulting to silent background launch...
echo.
goto background

:background
echo Starting Agent Ochuko Workstation Bridge silently in background...
if exist "%SCRIPT_DIR%run_workstation_bridge.vbs" (
    wscript.exe "%SCRIPT_DIR%run_workstation_bridge.vbs"
) else (
    start /b python -m app.connectors.workstation_bridge
)
timeout /t 2 /nobreak >nul
goto status_check

:foreground
echo Starting Agent Ochuko Workstation Bridge in foreground on http://127.0.0.1:3920 ...
python -m app.connectors.workstation_bridge
goto end

:status
echo Checking Agent Ochuko Workstation Bridge status...
:status_check
powershell -Command "try { $res = Invoke-RestMethod -Uri 'http://127.0.0.1:3920/health' -TimeoutSec 2; Write-Host '[ONLINE] Workstation Bridge is active on port 3920.' -ForegroundColor Green; Write-Host ('  Platform: ' + $res.platform + ' | Hostname: ' + $res.hostname); exit 0 } catch { Write-Host '[OFFLINE] Workstation Bridge is not currently running.' -ForegroundColor Yellow; exit 1 }"
goto end

:stop
echo Stopping Agent Ochuko Workstation Bridge...
powershell -Command "$conns = Get-NetTCPConnection -LocalPort 3920 -ErrorAction SilentlyContinue; if ($conns) { $conns | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Write-Host '[STOPPED] Workstation Bridge stopped.' -ForegroundColor Green } else { Write-Host 'No process running on port 3920.' -ForegroundColor Yellow }"
goto end

:end
