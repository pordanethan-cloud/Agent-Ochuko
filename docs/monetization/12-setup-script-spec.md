# Setup Script — Spec

Phase 3 build sheet. PowerShell and Bash twins.

---

## What & how

### What exists today

`docs/01_azure_foundry_setup.md` describes manual Azure Foundry setup for the
platform owner. No automated script. No `scripts/renter-setup/` directory.

### What the script must accomplish

A renter with Azure CLI and an active student subscription runs one command.
The script creates the minimum Azure resources in *their* subscription, extracts
endpoint + key, validates locally, and POSTs to Agent-Ochuko. The renter never
gives you their Azure login — only an inference API key.

### How (directives)

1. **Fail fast before touching Azure** if `az` is missing or user is not on a
   student subscription.
2. **Fail fast before POST** if estimated 10% monthly donation < $5.00 USD.
3. **Minimum footprint:** one RG, one hub, one project, one `gpt-5.4-nano`
   deployment. Nothing else.
4. **Region order:** `swedencentral` → `eastus`. Do not default to SA North.
5. **HTTPS only** for registration POST. No `--insecure`.
6. **Print student bonus steps** on subscription failure — reuse copy from
   `04-student-bonus-guide.md` verbatim.
7. **Never print the API key twice** — show once at end, warn user it won't be
   emailed. Platform stores encrypted copy.
8. **Exit codes are contractual** — onboarding page maps failures to user messages.

### Decisions you own

| Decision | Notes |
|---|---|
| Credit estimation method | Query `az consumption` / hardcode $100 student assumption / read Cost Management |
| Resource naming | `rg-ochuko-renter-{6char}` — must be unique enough |
| Idempotent re-run | If RG exists, resume or fail with clear message |
| Hub/project API version | Match `01_azure_foundry_setup.md` or latest stable `az` extension |

---

## What must be implemented

### File layout

```
scripts/renter-setup/
├── setup-renter-azure.ps1      # Entry point (Windows)
├── setup-renter-azure.sh       # Entry point (Mac/Linux)
├── lib/
│   ├── preflight.ps1 / .sh     # CLI + subscription checks
│   ├── provision.ps1 / .sh       # RG, hub, project, deployment
│   ├── register.ps1 / .sh      # POST to platform API
│   └── regions.json            # ["swedencentral", "eastus"]
└── README.md                   # One-paragraph pointer to /renter/onboarding
```

Also copy to `frontend/public/renter-setup/` for browser download.

### Invocation

```powershell
.\setup-renter-azure.ps1 -SetupToken "rent_abc..." -ApiUrl "https://api.agent-ochuko.com"
```

```bash
./setup-renter-azure.sh --setup-token "rent_abc..." --api-url "https://api.agent-ochuko.com"
```

### Step sequence

| Step | Action | On failure |
|---|---|---|
| 1 | `Get-Command az` / `command -v az` | Exit 1: "Install Azure CLI" |
| 2 | `az account show` — if not logged in, `az login` | Exit 2: print student bonus guide |
| 3 | Find subscription matching `Azure for Students` (name or offer ID) | Exit 2 + guide |
| 4 | `az account set --subscription <id>` | Exit 2 |
| 5 | Estimate monthly credit remaining | Exit 6 if 10% < $5 |
| 6 | Create `rg-ochuko-renter-{shortId}` in region try-order | Exit 4 on quota/region |
| 7 | Create AI Foundry hub + project | Exit 4 |
| 8 | Deploy model `gpt-5.4-nano` (name configurable) | Exit 5, retry next region |
| 9 | Read endpoint + key from project | Exit 3 |
| 10 | POST `/v1/renter/register-capacity` | Exit 7, print API error body |
| 11 | Print success summary + app URL | Exit 0 |

### Exit code table

| Code | Meaning | API `error` code | Onboarding message |
|---|---|---|---|
| 0 | Success | — | Step 5 / redirect |
| 1 | az CLI missing | — | "Install Azure CLI" |
| 2 | No student subscription | — | Step 1 link |
| 3 | Could not read endpoint/key | `invalid_credentials` | Contact support |
| 4 | Azure provision failed | `model_unavailable` | Region retry message |
| 5 | Model deploy failed all regions | `model_unavailable` | Region retry message |
| 6 | Below minimum quota | `below_minimum_quota` | Subscribe instead link |
| 7 | Registration API rejected | (from response) | Map `error` field inline |

### Registration payload

```json
{
  "setup_token": "rent_...",
  "azure_endpoint": "https://{resource}.openai.azure.com/",
  "azure_key": "{key}",
  "subscription_name": "Azure for Students",
  "region": "swedencentral",
  "deployments": ["gpt-5.4-nano"],
  "estimated_monthly_quota_usd": 10.00
}
```

Platform computes `quota_limit_usd = estimated_monthly_quota_usd * 0.10`.

### Credit estimation (v1 pragmatic)

Until you integrate Cost Management API:

```powershell
# Assume $100 student credit if subscription name matches
# Optional: az consumption budget list — if available
$estimatedMonthly = 100.00
$donation = $estimatedMonthly * 0.10
if ($donation -lt 5.00) { exit 6 }
```

Document in script header: estimation is conservative; platform re-validates on
register. You can tighten this later with real balance reads.

### Provision commands (outline)

Exact `az` commands must match your Foundry setup doc. Outline:

```bash
az group create --name "$RG" --location "$REGION"
# hub create — use extension/version from 01_azure_foundry_setup.md
# project create
# deployment create --model gpt-5.4-nano --sku GlobalStandard
```

Keep commands in `lib/provision.*` so both twins call the same sequence.

### Platform-side status during run

When POST received, backend sets `renter_onboarding_status = 'validating'` before
test call, then `'active'` or `'failed'`. Onboarding page polls this.

### Security notes for script README

- Token is single-use, 24h expiry.
- Key transmitted once over TLS.
- Renter can revoke from `/renter/status` anytime.

### Checkpoint

- [ ] Windows `.ps1` and `.sh` produce identical payload on same account
- [ ] Wrong subscription → exit 2, student guide printed
- [ ] $0 credit scenario → exit 6
- [ ] Success → API returns 200, onboarding shows `active`
- [ ] Expired token → API 401, script exit 7 with clear message
