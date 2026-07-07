# Start logging transcript
$LogPath = Join-Path $PSScriptRoot "deploy_local.log"
Write-Host "Logging deployment details to: $LogPath" -ForegroundColor Gray
Start-Transcript -Path $LogPath -Append -Force

Write-Host "Starting local build and deploy..." -ForegroundColor Cyan

# Resolve parent paths relative to script directory
$BackendPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../../backend"))
$DockerfilePath = Join-Path $BackendPath "Dockerfile"
$EnvPath = Join-Path $BackendPath ".env"

# 1. Build the Docker image
Write-Host "Building Docker image..." -ForegroundColor Yellow
docker build -t ochair1/agent-ochuko-api:latest -f $DockerfilePath $BackendPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker build failed!"
    Stop-Transcript
    exit 1
}

# 2. Push to Docker Hub
Write-Host "Pushing image to Docker Hub..." -ForegroundColor Yellow
docker push ochair1/agent-ochuko-api:latest
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker push failed!"
    Stop-Transcript
    exit 1
}

# 3. Read Google API Keys from backend/.env and update Azure Container App
Write-Host "Deploying to Azure Container App..." -ForegroundColor Yellow

$GoogleVars = @()
if (Test-Path $EnvPath) {
    Get-Content $EnvPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $key = $parts[0].Trim()
            $val = $parts[1].Trim()
            if ($key -in @("GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4")) {
                $GoogleVars += "$key=$val"
            }
        }
    }
}

$epoch = [int]([datetimeoffset](Get-Date)).ToUnixTimeSeconds()
$GoogleVars += "DEPLOY_TIMESTAMP=$epoch"

Write-Host "Updating container app..." -ForegroundColor Yellow
# Pass the array directly so PowerShell passes them as individual arguments
az containerapp update --name agent-ochuko-api --resource-group rg-ochuko --image ochair1/agent-ochuko-api:latest --set-env-vars $GoogleVars

if ($LASTEXITCODE -ne 0) {
    Write-Error "Azure Container App update failed!"
    Stop-Transcript
    exit 1
}

Write-Host "Deployment completed successfully!" -ForegroundColor Green
Stop-Transcript
