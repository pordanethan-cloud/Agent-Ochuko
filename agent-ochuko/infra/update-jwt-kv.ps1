# SYNOPSIS
#     Updates the Supabase JWT, Storage, and Cognitive secrets in Azure Key Vault.
# DESCRIPTION
#     This script parses the local backend/.env file and updates the Azure Key Vault secrets.
#     It will attempt to use Azure CLI (az) by default, and fall back to the Azure PowerShell Az module.
# PARAMETER VaultName
#     The name of the Azure Key Vault. Defaults to 'agent-ochuko-kv'.
# EXAMPLE
#     .\update-jwt-kv.ps1

param (
    [string]$VaultName = "agent-ochuko-kv"
)

$ErrorActionPreference = "Stop"

# Locate and parse backend/.env file
$Secrets = @{}
$envPath = Join-Path $PSScriptRoot "..\backend\.env"

if (-not (Test-Path $envPath)) {
    throw "Could not find backend/.env file at: $envPath. Please make sure the file exists."
}

[Console]::WriteLine("Loading secrets from: {0}", $envPath)

Get-Content $envPath | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $val = $parts[1].Trim()
        
        # Map the .env keys to Key Vault secret names
        if ($key -eq "SUPABASE_JWT_SECRET") { $Secrets["SUPABASE-JWT-SECRET"] = $val }
        elseif ($key -eq "AZURE_STORAGE_CONNECTION_STRING") { $Secrets["AZURE-STORAGE-CONNECTION-STRING"] = $val }
        elseif ($key -eq "AZURE_DOCUMENT_INTELLIGENCE_KEY") { $Secrets["AZURE-DOCUMENT-INTELLIGENCE-KEY"] = $val }
        elseif ($key -eq "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT") { $Secrets["AZURE-DOCUMENT-INTELLIGENCE-ENDPOINT"] = $val }
        elseif ($key -eq "AZURE_VISION_KEY") { $Secrets["AZURE-VISION-KEY"] = $val }
        elseif ($key -eq "AZURE_VISION_ENDPOINT") { $Secrets["AZURE-VISION-ENDPOINT"] = $val }
        elseif ($key -eq "GOOGLE_API_KEY") { $Secrets["GOOGLE-API-KEY"] = $val }
        elseif ($key -eq "GEMINI_API_KEY") { $Secrets["GEMINI-API-KEY"] = $val }
        elseif ($key -eq "GEMINI_API_KEY_2") { $Secrets["GEMINI-API-KEY-2"] = $val }
        elseif ($key -eq "GEMINI_API_KEY_3") { $Secrets["GEMINI-API-KEY-3"] = $val }
        elseif ($key -eq "GEMINI_API_KEY_4") { $Secrets["GEMINI-API-KEY-4"] = $val }
    }
}

$RequiredKeys = @("SUPABASE-JWT-SECRET", "AZURE-STORAGE-CONNECTION-STRING", "AZURE-DOCUMENT-INTELLIGENCE-KEY", "AZURE-DOCUMENT-INTELLIGENCE-ENDPOINT", "AZURE-VISION-KEY", "AZURE-VISION-ENDPOINT")
foreach ($rKey in $RequiredKeys) {
    if (-not $Secrets.ContainsKey($rKey) -or [string]::IsNullOrEmpty($Secrets[$rKey])) {
        throw "Missing required configuration variable in backend/.env: $rKey"
    }
}

[Console]::WriteLine("==========================================================")
[Console]::WriteLine("Azure Key Vault Secret Sync - Agent Ochuko")
[Console]::WriteLine("==========================================================")
[Console]::WriteLine("Vault Name: {0}", $VaultName)
[Console]::WriteLine("Syncing {0} secrets...", $Secrets.Count)
[Console]::WriteLine("==========================================================")

# 1. Try Azure CLI (az)
$azPath = Get-Command az -ErrorAction SilentlyContinue

if ($azPath) {
    [Console]::WriteLine("[AZ CLI] Found Azure CLI at: {0}", $azPath.Source)
    try {
        # Check if logged in
        [Console]::WriteLine("[AZ CLI] Checking Azure authentication status...")
        $null = az account show --query name -o tsv 2>$null
        
        if ($LASTEXITCODE -ne 0) {
            [Console]::WriteLine("[AZ CLI] Not logged in. Triggering 'az login'...")
            az login
        } else {
            [Console]::WriteLine("[AZ CLI] Already authenticated.")
        }
        
        foreach ($key in $Secrets.Keys) {
            $val = $Secrets[$key]
            [Console]::WriteLine("[AZ CLI] Setting secret '{0}' in Key Vault '{1}'...", $key, $VaultName)
            $null = az keyvault secret set --vault-name $VaultName --name $key --value $val
        }
        
        [Console]::WriteLine("[SUCCESS] All secrets successfully updated via Azure CLI!")
        return
    }
    catch {
        [Console]::WriteLine("[AZ CLI] Failed during execution: {0}", $_)
        [Console]::WriteLine("[INFO] Attempting fallback to Az PowerShell module...")
    }
} else {
    [Console]::WriteLine("[AZ CLI] Azure CLI (az) not found on PATH.")
}

# 2. Fallback to Azure PowerShell (Az Module)
$azModule = Get-Module -ListAvailable Az.KeyVault -ErrorAction SilentlyContinue

if ($azModule) {
    [Console]::WriteLine("[Az PowerShell] Found Az.KeyVault module.")
    try {
        # Check authentication context
        $context = Get-AzContext -ErrorAction SilentlyContinue
        if (-not $context) {
            [Console]::WriteLine("[Az PowerShell] No active context. Triggering Connect-AzAccount...")
            $context = Connect-AzAccount
        } else {
            [Console]::WriteLine("[Az PowerShell] Already authenticated as: {0}", $context.Account.Id)
        }

        foreach ($key in $Secrets.Keys) {
            $val = $Secrets[$key]
            [Console]::WriteLine("[Az PowerShell] Setting secret '{0}' in Key Vault '{1}'...", $key, $VaultName)
            $secureSecret = ConvertTo-SecureString $val -AsPlainText -Force
            $null = Set-AzKeyVaultSecret -VaultName $VaultName -Name $key -SecretValue $secureSecret
        }
        
        [Console]::WriteLine("[SUCCESS] All secrets successfully updated via Azure PowerShell!")
        return
    }
    catch {
        [Console]::WriteLine("[Az PowerShell] Failed: {0}", $_)
    }
} else {
    [Console]::WriteLine("[Az PowerShell] Az.KeyVault module is not installed.")
}

# 3. Direct Manual Instructions fallback if both tools fail
[Console]::WriteLine("")
[Console]::WriteLine("----------------------------------------------------------")
[Console]::WriteLine("Manual Secret Update Commands (Azure CLI):")
[Console]::WriteLine("----------------------------------------------------------")
foreach ($key in $Secrets.Keys) {
    $val = $Secrets[$key]
    [Console]::WriteLine("az keyvault secret set --vault-name `"{0}`" --name `"{1}`" --value `"{2}`"", $VaultName, $key, $val)
}
[Console]::WriteLine("")
throw "Could not automate the Key Vault update. Please use the manual commands shown above."
