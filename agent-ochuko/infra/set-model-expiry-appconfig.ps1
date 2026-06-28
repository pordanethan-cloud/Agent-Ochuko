<#
.SYNOPSIS
    Seeds model expiry date and fallback deployment keys into Azure App Configuration.
.DESCRIPTION
    Adds the 8 keys required by the model_expiry_monitor Azure Function cron (CRON 5).
    These keys tell the monitor WHEN each model deployment expires and WHAT to switch to
    if it has expired — enabling zero-downtime automatic model swaps without any redeploy.

    Keys added (label = production):
      THINK_MODEL_EXPIRY_DATE        — Expiry date of the THINK (gpt-5.4) deployment
      SOLVE_MODEL_EXPIRY_DATE        — Expiry date of the SOLVE (gpt-5.4-mini) deployment
      NANO_MODEL_EXPIRY_DATE         — Expiry date of the NANO/DISCUSS deployment
      COMPACTION_MODEL_EXPIRY_DATE   — Expiry date of the o4-mini compaction deployment
      THINK_FALLBACK_DEPLOYMENT      — Deployment name to auto-swap to when THINK expires
      SOLVE_FALLBACK_DEPLOYMENT      — Deployment name to auto-swap to when SOLVE expires
      NANO_FALLBACK_DEPLOYMENT       — Deployment name to auto-swap to when NANO expires
      COMPACTION_FALLBACK_DEPLOYMENT — Deployment name to auto-swap to when COMPACTION expires

.NOTES
    - Find expiry dates in Azure AI Foundry → your project → Deployments tab.
    - Fallback deployment names must already exist as deployments in Azure AI Foundry.
    - Run this once after deploying your models. Re-run whenever you rotate models.
    - Requires Azure CLI (az) to be installed and logged in: az login

.EXAMPLE
    .\set-model-expiry-appconfig.ps1

.EXAMPLE
    .\set-model-expiry-appconfig.ps1 `
        -AppConfigName "agent-ochuko-appconfig" `
        -ThinkExpiry "2027-06-01" `
        -ThinkFallback "gpt-5.4-v2"
#>

param (
    # ── Azure App Configuration resource name ─────────────────────────────────
    [string]$AppConfigName = "agent-ochuko-appconfig",

    # ── Label applied to all keys (must match what FastAPI / Functions read) ──
    [string]$Label = "production",

    # ── THINK model (gpt-5.4) ─────────────────────────────────────────────────
    # Find expiry in Azure AI Foundry → Deployments → gpt-5.4 → Expiry date
    [string]$ThinkExpiry   = "YYYY-MM-DD",
    [string]$ThinkFallback = "gpt-5.4-fallback",

    # ── SOLVE model (gpt-5.4-mini) ────────────────────────────────────────────
    [string]$SolveExpiry   = "YYYY-MM-DD",
    [string]$SolveFallback = "gpt-5.4-mini-fallback",

    # ── NANO / DISCUSS model (gpt-5.4-nano) ───────────────────────────────────
    [string]$NanoExpiry    = "YYYY-MM-DD",
    [string]$NanoFallback  = "gpt-5.4-nano-fallback",

    # ── COMPACTION model (o4-mini) ────────────────────────────────────────────
    [string]$CompactionExpiry    = "YYYY-MM-DD",
    [string]$CompactionFallback  = "o4-mini-fallback"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Validate placeholders ─────────────────────────────────────────────────────
$allExpiries = @($ThinkExpiry, $SolveExpiry, $NanoExpiry, $CompactionExpiry)
foreach ($d in $allExpiries) {
    if ($d -eq "YYYY-MM-DD") {
        Write-Warning "One or more expiry dates are still set to the placeholder 'YYYY-MM-DD'."
        Write-Warning "Find real expiry dates in Azure AI Foundry → your project → Deployments tab."
        Write-Warning "Run the script with explicit -ThinkExpiry, -SolveExpiry etc. parameters."
        $confirm = Read-Host "Continue anyway with placeholder dates? (y/N)"
        if ($confirm -ne "y") {
            Write-Host "Aborted. Fill in the real expiry dates and re-run." -ForegroundColor Yellow
            exit 1
        }
        break
    }
}

# ── Check az CLI is available ─────────────────────────────────────────────────
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Error "Azure CLI (az) not found. Install from https://aka.ms/installazurecliwindows and run 'az login'."
    exit 1
}

Write-Host ""
Write-Host "=== Agent Ochuko — Model Expiry Keys Setup ===" -ForegroundColor Cyan
Write-Host "App Configuration : $AppConfigName" -ForegroundColor Gray
Write-Host "Label             : $Label" -ForegroundColor Gray
Write-Host ""

# ── Key-value map to write ────────────────────────────────────────────────────
$keys = [ordered]@{
    "THINK_MODEL_EXPIRY_DATE"        = $ThinkExpiry
    "SOLVE_MODEL_EXPIRY_DATE"        = $SolveExpiry
    "NANO_MODEL_EXPIRY_DATE"         = $NanoExpiry
    "COMPACTION_MODEL_EXPIRY_DATE"   = $CompactionExpiry
    "THINK_FALLBACK_DEPLOYMENT"      = $ThinkFallback
    "SOLVE_FALLBACK_DEPLOYMENT"      = $SolveFallback
    "NANO_FALLBACK_DEPLOYMENT"       = $NanoFallback
    "COMPACTION_FALLBACK_DEPLOYMENT" = $CompactionFallback
}

$success = 0
$failed  = 0

foreach ($key in $keys.Keys) {
    $value = $keys[$key]
    Write-Host "  Setting $key = $value ..." -NoNewline

    $result = az appconfig kv set `
        --name  $AppConfigName `
        --key   $key `
        --value $value `
        --label $Label `
        --yes 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
        $success++
    } else {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Warning "  Error: $result"
        $failed++
    }
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "All $success keys written successfully to '$AppConfigName'." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Verify in Azure Portal → App Configuration → Configuration explorer (label=production)"
    Write-Host "  2. Replace 'YYYY-MM-DD' placeholders with real dates from Azure AI Foundry → Deployments"
    Write-Host "  3. Replace '*-fallback' values with the actual fallback deployment names you created"
    Write-Host "  4. Deploy model_expiry_monitor (CRON 5) — it reads these keys at 9am UTC daily"
} else {
    Write-Host "$success succeeded, $failed failed." -ForegroundColor Yellow
    Write-Host "Check the errors above. Common causes:" -ForegroundColor Yellow
    Write-Host "  - Not logged in: run 'az login'"
    Write-Host "  - Wrong resource name: confirm AppConfigName = '$AppConfigName' in Azure Portal"
    Write-Host "  - No access: confirm your account has 'App Configuration Data Owner' role"
}
