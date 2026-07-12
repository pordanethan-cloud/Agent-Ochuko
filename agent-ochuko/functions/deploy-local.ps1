# Local deployment script for Azure Functions (PowerShell)
# Usage: .\deploy-local.ps1

Write-Host "=== Starting local Azure Functions deployment ===" -ForegroundColor Green

# Navigate to functions directory
$scriptPath = $PSScriptRoot
Set-Location $scriptPath

# Install dependencies locally
Write-Host "Step 1: Installing dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install -r requirements.txt --target .python_packages/lib/site-packages

# Publish to Azure Functions
Write-Host "Step 2: Publishing to Azure Functions..." -ForegroundColor Yellow
func azure functionapp publish agent-ochuko-functions --python --build local

Write-Host "=== Deployment complete ===" -ForegroundColor Green
