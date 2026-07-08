# -----------------------------------------------------------------------------
# Agent Ochuko - Full Local Deploy Script
# Deploys BOTH backend (Container App) and frontend (Static Website).
# Azure Functions are NOT touched by this script.
# -----------------------------------------------------------------------------

# Start logging
$LogPath = Join-Path $PSScriptRoot "deploy_local.log"
Write-Host "Logging to: $LogPath" -ForegroundColor Gray
Start-Transcript -Path $LogPath -Append -Force

# -- Resolve paths -------------------------------------------------------------
$RootPath     = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
$BackendPath  = Join-Path $RootPath "backend"
$FrontendPath = Join-Path $RootPath "frontend"
$DockerfilePath = Join-Path $BackendPath "Dockerfile"
$BackendEnv   = Join-Path $BackendPath ".env"

# -- Config --------------------------------------------------------------------
$DockerImage      = "ochair1/agent-ochuko-api:latest"
$ContainerAppName = "agent-ochuko-api"
$ResourceGroup    = "rg-ochuko"
$StorageAccount   = "agentochukostore"
$WebContainer     = '$web'   # Azure Static Website container

# =============================================================================
# PART 1 - BACKEND
# =============================================================================
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " BACKEND: Docker -> Docker Hub -> Azure Container App" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# 1a. Build Docker image
Write-Host "`n[1/3] Building Docker image..." -ForegroundColor Yellow
docker build -t $DockerImage -f $DockerfilePath $BackendPath
if ($LASTEXITCODE -ne 0) { Write-Error "Docker build failed!"; Stop-Transcript; exit 1 }

# 1b. Push to Docker Hub
Write-Host "`n[2/3] Pushing image to Docker Hub..." -ForegroundColor Yellow
docker push $DockerImage
if ($LASTEXITCODE -ne 0) { Write-Error "Docker push failed!"; Stop-Transcript; exit 1 }

# 1c. Read env vars from backend/.env (Google / Gemini keys only)
$EnvVars = @()
if (Test-Path $BackendEnv) {
    Get-Content $BackendEnv | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $key   = $parts[0].Trim()
            $val   = $parts[1].Trim()
            if ($key -in @("GOOGLE_API_KEY","GEMINI_API_KEY","GEMINI_API_KEY_2","GEMINI_API_KEY_3","GEMINI_API_KEY_4")) {
                $EnvVars += "$key=$val"
            }
        }
    }
}
$epoch = [int]([datetimeoffset](Get-Date)).ToUnixTimeSeconds()
$EnvVars += "DEPLOY_TIMESTAMP=$epoch"

# 1d. Update Azure Container App
Write-Host "`n[3/3] Updating Azure Container App..." -ForegroundColor Yellow
az containerapp update `
    --name $ContainerAppName `
    --resource-group $ResourceGroup `
    --image $DockerImage `
    --set-env-vars $EnvVars
if ($LASTEXITCODE -ne 0) { Write-Error "Container App update failed!"; Stop-Transcript; exit 1 }

Write-Host "`n[OK] Backend deployed successfully." -ForegroundColor Green

# =============================================================================
# PART 2 - FRONTEND
# =============================================================================
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " FRONTEND: npm build -> Azure Blob Storage (`$web)" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# 2a. Install dependencies (skip if node_modules already fresh)
Write-Host "`n[1/3] Installing frontend dependencies..." -ForegroundColor Yellow
Push-Location $FrontendPath
npm ci
if ($LASTEXITCODE -ne 0) { Write-Error "npm ci failed!"; Pop-Location; Stop-Transcript; exit 1 }

# 2b. Build (uses .env.production automatically - points to Azure Container App URL)
Write-Host "`n[2/3] Building frontend..." -ForegroundColor Yellow
npm run build
if ($LASTEXITCODE -ne 0) { Write-Error "Frontend build failed!"; Pop-Location; Stop-Transcript; exit 1 }
Pop-Location

# 2c. Upload dist/ to Azure Blob Storage $web container
Write-Host "`n[3/3] Uploading to Azure Blob Storage..." -ForegroundColor Yellow
$StorageKey = az storage account keys list `
    --resource-group $ResourceGroup `
    --account-name $StorageAccount `
    --query "[0].value" `
    --output tsv
if ($LASTEXITCODE -ne 0) { Write-Error "Failed to get storage key!"; Stop-Transcript; exit 1 }

az storage blob upload-batch `
    --account-name $StorageAccount `
    --account-key $StorageKey `
    --source (Join-Path $FrontendPath "dist") `
    --destination $WebContainer `
    --overwrite true
if ($LASTEXITCODE -ne 0) { Write-Error "Frontend upload failed!"; Stop-Transcript; exit 1 }

Write-Host "`n[OK] Frontend deployed successfully." -ForegroundColor Green

# =============================================================================
Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host " ALL DONE - Backend + Frontend deployed." -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Stop-Transcript
