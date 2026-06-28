<#
.SYNOPSIS
    Updates the Supabase JWT secret in Azure Key Vault.
.DESCRIPTION
    This script logs into Azure (via Azure CLI or Azure PowerShell module) and updates the 
    specified secret with the Supabase JWT Secret. It will attempt to use Azure CLI (az) 
    by default, and fall back to the Azure PowerShell Az module if Az CLI is not installed.
.PARAMETER VaultName
    The name of the Azure Key Vault. Defaults to 'agent-ochuko-kv'.
.PARAMETER SecretName
    The name of the secret. Defaults to 'SUPABASE-JWT-SECRET'.
.PARAMETER SecretValue
    The JWT Secret value. Defaults to the legacy JWT secret configured in the environment.
.EXAMPLE
    .\update-jwt-kv.ps1
.EXAMPLE
    .\update-jwt-kv.ps1 -SecretValue "your-custom-jwt-secret-here"
#>

param (
    [string]$VaultName = "agent-ochuko-kv",
    [string]$SecretName = "SUPABASE-JWT-SECRET",
    [string]$SecretValue = "ts3CuzdPqhm5ezTi3nBNJK9UJVwz0c5m//UzanbIjHJl+4NRUKZa2EI2oNj9ZphIPC9Rd9AwT5bKoo/gcUyUQg=="
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Azure Key Vault Secret Sync - Agent Ochuko" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Vault Name:  $VaultName" -ForegroundColor Gray
Write-Host "Secret Name: $SecretName" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Try Azure CLI (az)
$azPath = Get-Command az -ErrorAction SilentlyContinue

if ($azPath) {
    Write-Host "[AZ CLI] Found Azure CLI at: $($azPath.Source)" -ForegroundColor Green
    try {
        # Check if logged in
        Write-Host "[AZ CLI] Checking Azure authentication status..." -ForegroundColor Gray
        $null = az account show --query name -o tsv 2>$null
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[AZ CLI] Not logged in. Triggering 'az login'..." -ForegroundColor Yellow
            az login
        } else {
            Write-Host "[AZ CLI] Already authenticated." -ForegroundColor Green
        }
        
        Write-Host "[AZ CLI] Setting secret '$SecretName' in Key Vault '$VaultName'..." -ForegroundColor Yellow
        $result = az keyvault secret set --vault-name $VaultName --name $SecretName --value $SecretValue | ConvertFrom-Json
        
        Write-Host "[SUCCESS] Secret successfully updated via Azure CLI!" -ForegroundColor Green
        Write-Host "Secret ID: $($result.id)" -ForegroundColor Gray
        return
    }
    catch {
        Write-Host "[AZ CLI] Failed during execution: $_" -ForegroundColor Red
        Write-Host "[INFO] Attempting fallback to Az PowerShell module..." -ForegroundColor Yellow
    }
} else {
    Write-Host "[AZ CLI] Azure CLI (az) not found on PATH." -ForegroundColor Yellow
}

# 2. Fallback to Azure PowerShell (Az Module)
$azModule = Get-Module -ListAvailable Az.KeyVault -ErrorAction SilentlyContinue

if ($azModule) {
    Write-Host "[Az PowerShell] Found Az.KeyVault module." -ForegroundColor Green
    try {
        # Check authentication context
        $context = Get-AzContext -ErrorAction SilentlyContinue
        if (-not $context) {
            Write-Host "[Az PowerShell] No active context. Triggering Connect-AzAccount..." -ForegroundColor Yellow
            $context = Connect-AzAccount
        } else {
            Write-Host "[Az PowerShell] Already authenticated as: $($context.Account.Id)" -ForegroundColor Green
        }

        # Set secret using Set-AzKeyVaultSecret
        Write-Host "[Az PowerShell] Converting secret value to secure string..." -ForegroundColor Gray
        $secureSecret = ConvertTo-SecureString $SecretValue -AsPlainText -Force

        Write-Host "[Az PowerShell] Setting secret '$SecretName' in Key Vault '$VaultName'..." -ForegroundColor Yellow
        $result = Set-AzKeyVaultSecret -VaultName $VaultName -Name $SecretName -SecretValue $secureSecret
        
        Write-Host "[SUCCESS] Secret successfully updated via Azure PowerShell!" -ForegroundColor Green
        Write-Host "Secret ID: $($result.Id)" -ForegroundColor Gray
        return
    }
    catch {
        Write-Host "[Az PowerShell] Failed: $_" -ForegroundColor Red
    }
} else {
    Write-Host "[Az PowerShell] Az.KeyVault module is not installed." -ForegroundColor Yellow
}

# 3. Direct Manual Instructions fallback if both tools fail
Write-Host ""
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Manual Secret Update Command (Azure CLI):" -ForegroundColor Yellow
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
Write-Host "az keyvault secret set --vault-name `"$VaultName`" --name `"$SecretName`" --value `"$SecretValue`"" -ForegroundColor White
Write-Host ""
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Manual Secret Update Command (Azure PowerShell):" -ForegroundColor Yellow
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
Write-Host "Set-AzKeyVaultSecret -VaultName `"$VaultName`" -Name `"$SecretName`" -SecretValue (ConvertTo-SecureString `"$SecretValue`" -AsPlainText -Force)" -ForegroundColor White
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
Write-Host ""
throw "Could not automate the Key Vault update. Please use one of the manual commands shown above."
