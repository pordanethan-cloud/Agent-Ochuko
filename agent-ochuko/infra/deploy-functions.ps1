<#
.SYNOPSIS
    Deploys all 6 Azure Functions cron tasks to the agent-ochuko-functions Function App.
.DESCRIPTION
    Publishes the contents of agent-ochuko/functions/ to the Azure Function App using the
    Azure Functions Core Tools (func) CLI. This is the standard publish method for Python
    v2 Function Apps on the Consumption plan.

    What gets deployed:
      CRON 1 — token_quota_reset       (daily midnight UTC)     — token budget reset
      CRON 2 — agent_quota_reset       (monthly 1st midnight)   — agent quota reset
      CRON 3 — usage_aggregation       (every hour)             — materializes usage_stats
      CRON 4 — conversation_archiver   (2am daily UTC)          — soft-archives stale convos
      CRON 5 — model_expiry_monitor    (9am daily UTC)          — auto-swaps expired models
      CRON 6 — conversation_summarizer (3am daily UTC)          — GPT-o4-mini compaction

.NOTES
    Prerequisites (run once before this script):
      1. Azure CLI logged in              : az login
      2. Azure Functions Core Tools       : npm install -g azure-functions-core-tools@4 --unsafe-perm
      3. Function App exists in Azure     : agent-ochuko-functions (Consumption plan, Python 3.11)
      4. Managed Identity granted Key Vault access (done separately in Azure Portal)
      5. App Settings configured in Azure Portal → Function App → Configuration:
           SUPABASE_URL
           SUPABASE_SERVICE_ROLE_KEY
           AZURE_APP_CONFIG_CONNECTION_STRING
           AZURE_OPENAI_ENDPOINT
           AZURE_OPENAI_API_KEY
           AZURE_OPENAI_API_VERSION

.EXAMPLE
    .\deploy-functions.ps1

.EXAMPLE
    .\deploy-functions.ps1 -FunctionAppName "agent-ochuko-functions" -ResourceGroup "rg-ochuko"
#>

param (
    [string]$FunctionAppName = "agent-ochuko-functions",
    [string]$ResourceGroup   = "rg-ochuko",
    [string]$FunctionsDir    = "$PSScriptRoot\..\functions"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Agent Ochuko — Azure Functions Deployment ===" -ForegroundColor Cyan
Write-Host "Function App  : $FunctionAppName" -ForegroundColor Gray
Write-Host "Resource Group: $ResourceGroup"   -ForegroundColor Gray
Write-Host "Source Dir    : $FunctionsDir"    -ForegroundColor Gray
Write-Host ""

# ── 1. Validate Azure CLI ─────────────────────────────────────────────────────
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Error "Azure CLI not found. Install from https://aka.ms/installazurecliwindows"
    exit 1
}

# ── 2. Validate Azure Functions Core Tools ────────────────────────────────────
if (-not (Get-Command func -ErrorAction SilentlyContinue)) {
    Write-Error "Azure Functions Core Tools not found. Run: npm install -g azure-functions-core-tools@4 --unsafe-perm"
    exit 1
}

# ── 3. Validate source directory ──────────────────────────────────────────────
$resolvedDir = Resolve-Path $FunctionsDir -ErrorAction SilentlyContinue
if (-not $resolvedDir) {
    Write-Error "Functions directory not found: $FunctionsDir"
    exit 1
}

if (-not (Test-Path "$resolvedDir\function_app.py")) {
    Write-Error "function_app.py not found in $resolvedDir. Check the path."
    exit 1
}

# ── 4. Confirm Function App exists ────────────────────────────────────────────
Write-Host "Verifying Function App '$FunctionAppName' exists in Azure..." -NoNewline
$appCheck = az functionapp show --name $FunctionAppName --resource-group $ResourceGroup --query "name" -o tsv 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host " NOT FOUND" -ForegroundColor Red
    Write-Error "Function App '$FunctionAppName' not found in resource group '$ResourceGroup'. Create it in Azure Portal first."
    exit 1
}
Write-Host " Found ($appCheck)" -ForegroundColor Green

# ── 5. Publish ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Publishing functions to Azure..." -ForegroundColor Cyan
Write-Host "(This packages your code, uploads it, and restarts the Function App runtime.)"
Write-Host ""

Push-Location $resolvedDir
try {
    func azure functionapp publish $FunctionAppName --python

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Error "Deployment failed. See errors above."
        exit 1
    }
} finally {
    Pop-Location
}

# ── 6. Post-deploy: list deployed functions ───────────────────────────────────
Write-Host ""
Write-Host "Deployed functions:" -ForegroundColor Cyan
az functionapp function list `
    --name           $FunctionAppName `
    --resource-group $ResourceGroup `
    --query          "[].{Name:name, State:properties.isDisabled}" `
    --output         table 2>&1

# ── 7. Summary ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Deployment complete." -ForegroundColor Green
Write-Host ""
Write-Host "Verification steps:" -ForegroundColor Cyan
Write-Host "  1. Azure Portal → Function App '$FunctionAppName' → Functions"
Write-Host "     → Confirm all 6 appear: token_quota_reset, agent_quota_reset,"
Write-Host "       usage_aggregation, conversation_archiver, model_expiry_monitor,"
Write-Host "       conversation_summarizer"
Write-Host ""
Write-Host "  2. Manually trigger a test run (optional - fires the function immediately):"
Write-Host "     az rest --method post --url https://management.azure.com/subscriptions/{sub}/resourceGroups/$ResourceGroup/providers/Microsoft.Web/sites/$FunctionAppName/functions/{functionName}/listKeys?api-version=2022-03-01"
Write-Host ""
Write-Host "  3. Check Application Insights for cron execution logs"
Write-Host "     Azure Portal -> Application Insights -> Logs -> traces"
Write-Host "     | where message contains 'cron trigger started'"
