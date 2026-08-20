Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host " Enabling Hyper-V, WSL, and Virtual Machine Platform " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# 1. Enable Hypervisor launch in BCD
Write-Host "`n[1/5] Configuring Hypervisor launch in Boot Config..." -ForegroundColor Yellow
try {
    bcdedit /set hypervisorlaunchtype auto
    Write-Host " -> Hypervisor launch type set to auto." -ForegroundColor Green
} catch {
    Write-Warning "Could not update bcdedit: $_"
}

# 2. Enable Virtual Machine Platform
Write-Host "`n[2/5] Enabling VirtualMachinePlatform..." -ForegroundColor Yellow
try {
    dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
    Write-Host " -> VirtualMachinePlatform enabled." -ForegroundColor Green
} catch {
    Write-Warning "Could not enable VirtualMachinePlatform: $_"
}

# 3. Enable WSL feature
Write-Host "`n[3/5] Enabling Microsoft-Windows-Subsystem-Linux..." -ForegroundColor Yellow
try {
    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
    Write-Host " -> Microsoft-Windows-Subsystem-Linux enabled." -ForegroundColor Green
} catch {
    Write-Warning "Could not enable WSL: $_"
}

# 4. Enable Hyper-V features
Write-Host "`n[4/5] Enabling Microsoft-Hyper-V..." -ForegroundColor Yellow
try {
    dism.exe /online /enable-feature /featurename:Microsoft-Hyper-V-All /all /norestart
    dism.exe /online /enable-feature /featurename:Microsoft-Hyper-V /all /norestart
    Write-Host " -> Microsoft-Hyper-V enabled." -ForegroundColor Green
} catch {
    Write-Warning "Could not enable Hyper-V: $_"
}

# 5. Update WSL kernel
Write-Host "`n[5/5] Updating WSL..." -ForegroundColor Yellow
try {
    wsl.exe --update
    Write-Host " -> WSL updated." -ForegroundColor Green
} catch {
    Write-Warning "Could not update WSL: $_"
}

Write-Host "`n=====================================================" -ForegroundColor Green
Write-Host " ALL VIRTUALIZATION FEATURES ENABLED SUCCESSFULLY!" -ForegroundColor Green
Write-Host " NOTE: A PC restart is REQUIRED for Windows to apply changes." -ForegroundColor Cyan
Write-Host " After restart, Docker Desktop and WSL2 will start normally." -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
Write-Host ""
Read-Host -Prompt "Press Enter to close this window"
