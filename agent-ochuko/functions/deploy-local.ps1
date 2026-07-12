# Local deployment script for Azure Functions (PowerShell)
# Usage: .\deploy-local.ps1
# Note: Azure Functions app is configured for Python 3.11
# Ensure Python 3.11 is in PATH or update the script to use py -3.11

Write-Host "=== Starting local Azure Functions deployment ===" -ForegroundColor Green

# Navigate to functions directory
$scriptPath = $PSScriptRoot
Set-Location $scriptPath

# Check Python version
Write-Host "Checking Python version..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
Write-Host "Current Python version: $pythonVersion" -ForegroundColor Cyan

# Install dependencies locally
Write-Host "Step 1: Installing dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install -r requirements.txt --target .python_packages/lib/site-packages

# Publish to Azure Functions
Write-Host "Step 2: Publishing to Azure Functions..." -ForegroundColor Yellow
func azure functionapp publish agent-ochuko-functions --python --build local

Write-Host "=== Deployment complete ===" -ForegroundColor Green
