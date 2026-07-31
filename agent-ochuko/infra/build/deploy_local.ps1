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
$RootPath      = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
$WorkspaceRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../../.."))
$BackendPath   = Join-Path $RootPath "backend"
$FrontendPath  = Join-Path $RootPath "frontend"
$AddinPath     = Join-Path $WorkspaceRoot "excel-addin"
$DockerfilePath = Join-Path $BackendPath "Dockerfile"
$BackendEnv    = Join-Path $BackendPath ".env"

# -- Config --------------------------------------------------------------------
$DockerImage      = "ochair1/agent-ochuko-api:latest"
$ContainerAppName = "agent-ochuko-api"
$ResourceGroup    = "rg-ochuko"
$StorageAccount   = "agentochukostore"
$WebContainer     = '$web'   # Azure Static Website container
$AddinContainer   = '$web'  # Use the same static website container ($web) for public access
$DevApiUrl        = "http://localhost:8000"
$ProdApiUrl       = "https://agent-ochuko-api.azurecontainerapps.io"
if ($env:PROD_API_URL) {
    $ProdApiUrl   = $env:PROD_API_URL
}
$DevCallback      = "https://localhost:3000/src/auth/callback.html"
$ProdCallback     = "https://" + $StorageAccount + ".z1.web.core.windows.net/addin/src/auth/callback.html"

# =============================================================================
# PART 1 - BACKEND
# =============================================================================
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " BACKEND: Docker -> Docker Hub -> Azure Container App" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# 1a. Build Docker image
Write-Host "`n[1/3] Building Docker image..." -ForegroundColor Yellow
docker build --platform linux/amd64 --provenance=false -t $DockerImage -f $DockerfilePath $WorkspaceRoot
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
# PART 3 - EXCEL ADD-IN
# =============================================================================
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " EXCEL ADD-IN: validate -> patch -> Azure Blob Storage ($AddinContainer)" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

$TaskpaneJs   = Join-Path $AddinPath "src\taskpane\taskpane.js"
$AddinSrc     = Join-Path $AddinPath "src"
$AddinAssets  = Join-Path $AddinPath "assets"
$ProdManifest = Join-Path $AddinPath "manifest.production.xml"
$patched      = $false

try {
    # 3a. Validate production manifest
    Write-Host "`n[1/5] Validating production manifest..." -ForegroundColor Yellow
    Push-Location $AddinPath
    npx office-addin-manifest validate manifest.production.xml
    if ($LASTEXITCODE -ne 0) { throw "Manifest validation failed!" }
    Pop-Location

    # 3b. Patch API URL and OAuth Callback for production
    Write-Host "`n[2/5] Patching URLs in taskpane.js..." -ForegroundColor Yellow
    $jsContent = Get-Content $TaskpaneJs -Raw
    if ($jsContent -match [regex]::Escape($DevApiUrl) -or $jsContent -match [regex]::Escape($DevCallback)) {
        $jsContent = $jsContent -replace [regex]::Escape($DevApiUrl), $ProdApiUrl
        $jsContent = $jsContent -replace [regex]::Escape($DevCallback), $ProdCallback
        Set-Content $TaskpaneJs -Value $jsContent -NoNewline
        Write-Host "      Patched API URL and OAuth Callback for production." -ForegroundColor Green
        $patched = $true
    } else {
        Write-Host "      URLs already patched or not found - skipping." -ForegroundColor Gray
    }

    # 3c. Ensure addin container exists
    Write-Host "`n[3/5] Ensuring '$AddinContainer' blob container exists..." -ForegroundColor Yellow
    $exists = az storage container exists `
        --account-name $StorageAccount `
        --account-key $StorageKey `
        --name $AddinContainer `
        --query "exists" `
        --output tsv
    if ($exists -eq "false") {
        az storage container create `
            --account-name $StorageAccount `
            --account-key $StorageKey `
            --name $AddinContainer `
            --public-access blob | Out-Null
        Write-Host "      Container '$AddinContainer' created. Waiting 5s for propagation..." -ForegroundColor Green
        Start-Sleep -Seconds 5
    } else {
        Write-Host "      Container '$AddinContainer' already exists." -ForegroundColor Gray
    }

    # 3d. Upload build files to Azure Blob Storage
    Write-Host "`n[4/5] Uploading add-in files..." -ForegroundColor Yellow
    
    az storage blob upload-batch `
        --account-name $StorageAccount `
        --account-key $StorageKey `
        --source $AddinSrc `
        --destination $AddinContainer `
        --destination-path "addin/src" `
        --overwrite true
    if ($LASTEXITCODE -ne 0) { throw "Upload of src/ directory failed!" }

    az storage blob upload-batch `
        --account-name $StorageAccount `
        --account-key $StorageKey `
        --source $AddinAssets `
        --destination $AddinContainer `
        --destination-path "addin/assets" `
        --overwrite true
    if ($LASTEXITCODE -ne 0) { throw "Upload of assets/ directory failed!" }

    az storage blob upload `
        --account-name $StorageAccount `
        --account-key $StorageKey `
        --container-name $AddinContainer `
        --file $ProdManifest `
        --name "addin/manifest.xml" `
        --overwrite true
    if ($LASTEXITCODE -ne 0) { throw "Upload of production manifest failed!" }

    Write-Host "      All files uploaded." -ForegroundColor Green

    # 3e. Set Content-Type headers
    Write-Host "`n[5/5] Setting Content-Type headers on blobs..." -ForegroundColor Yellow
    $blobs = az storage blob list `
        --account-name $StorageAccount `
        --account-key $StorageKey `
        --container-name $AddinContainer `
        --output json | ConvertFrom-Json

    foreach ($blob in $blobs) {
        $name = $blob.name
        $ct   = $null

        if ($name -match '\.js$')   { $ct = 'application/javascript' }
        elseif ($name -match '\.css$')  { $ct = 'text/css' }
        elseif ($name -match '\.html$') { $ct = 'text/html' }
        elseif ($name -match '\.xml$')  { $ct = 'application/xml' }
        elseif ($name -match '\.png$')  { $ct = 'image/png' }

        if ($ct) {
            az storage blob update `
                --account-name $StorageAccount `
                --account-key $StorageKey `
                --container-name $AddinContainer `
                --name $name `
                --content-type $ct | Out-Null
        }
    }
    Write-Host "      Content-Type headers applied." -ForegroundColor Green
    Write-Host "`n[OK] Excel Add-in deployed successfully." -ForegroundColor Green

} catch {
    Write-Error $_
    if ($patched) {
        Write-Host "Rolling back taskpane.js patches..." -ForegroundColor Yellow
        $jsContent = Get-Content $TaskpaneJs -Raw
        $jsContent = $jsContent -replace [regex]::Escape($ProdApiUrl), $DevApiUrl
        $jsContent = $jsContent -replace [regex]::Escape($ProdCallback), $DevCallback
        Set-Content $TaskpaneJs -Value $jsContent -NoNewline
    }
    if ($AddinPath -and (Get-Location).Path -eq $AddinPath) {
        Pop-Location
    }
    Stop-Transcript
    exit 1
} finally {
    if ($patched) {
        $jsContent = Get-Content $TaskpaneJs -Raw
        $jsContent = $jsContent -replace [regex]::Escape($ProdApiUrl), $DevApiUrl
        $jsContent = $jsContent -replace [regex]::Escape($ProdCallback), $DevCallback
        Set-Content $TaskpaneJs -Value $jsContent -NoNewline
        Write-Host "taskpane.js restored to dev URLs for local development." -ForegroundColor Gray
    }
}

# =============================================================================
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host " ALL DONE - Backend + Frontend + Excel Add-in Deployed." -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
Write-Host (" Chat Web App URL: https://" + $StorageAccount + ".z1.web.core.windows.net") -ForegroundColor Cyan
Write-Host (" Excel Add-in URL:  https://" + $StorageAccount + ".z1.web.core.windows.net/addin/src/taskpane/taskpane.html") -ForegroundColor Cyan
Write-Host (" Manifest URL:      https://" + $StorageAccount + ".z1.web.core.windows.net/addin/manifest.xml") -ForegroundColor Cyan
Write-Host ""
Stop-Transcript
