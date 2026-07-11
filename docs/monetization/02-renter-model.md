# Renter Model

## Constraint that shapes everything

Azure resources must be created **inside the renter's own Azure for Students
subscription**. The platform cannot spin up their project remotely. The
script runs on their machine, they `az login` themselves, and the script
registers the *result* — endpoint + key — with Agent-Ochuko. The platform
never holds Azure credentials that can act on the renter's account beyond the
one key they hand over for pooled inference.

## Tiers (no trial)

| Tier | How they join | What they get |
|---|---|---|
| **Renter** | `/login` (Contribute tab) → account created immediately, `access_tier = NULL` → `/renter/onboarding` → run script → credentials registered → `access_tier = 'renter'` | Free app access in exchange for ~10% quota donation |
| **Subscriber** | `/login` (Subscribe tab) → checkout → payment webhook | Platform capacity (+ pool overflow) |
| **Admin** | Manual `role` assignment | Admin app |

Signup is **open** — no invite allowlist. What gates access is not who's
allowed to *start*, it's whether the process *finishes*: a renter account can
sit at `access_tier = NULL` indefinitely with zero app access until Azure
registration succeeds.

## `role` vs `access_tier` — do not conflate

- `role` — who can use the admin app (`admin` / `superadmin`). Unchanged.
- `access_tier` — how chat capacity is billed (`renter` / `subscriber` /
  `admin`). New, orthogonal.

A renter is not an admin. A subscriber is not an admin. Never overload `role`
for business tiering.

## Onboarding flow

```
Renter visits /login → Contribute tab → signs up
  → account created, access_tier = NULL
  → redirected to /renter/onboarding
  → Email #1: welcome + student bonus guide + script link
  → Renter runs setup-renter-azure.ps1 / .sh locally
  → az login with student account
  → Script creates hub / project / nano deployment
  → Script POSTs endpoint + key to POST /v1/renter/register-capacity
  → Platform validates key with live test call, encrypts, creates capacity_provider row
  → renter_onboarding_status: pending_setup → validating → active
  → Email #2: connected summary (no API key)
  → Renter is redirected to / (main app) — now unlocked
```

## Credential handling — non-negotiable rules

| Rule | Implementation |
|---|---|
| Never store plaintext keys | AES-256-GCM encrypt before DB write; master key in env/App Config |
| Never email API keys | Email #2 is endpoint + quota summary only |
| One-time setup tokens | Store `token_hash` (SHA-256), 24h expiry, single use |
| Validate before accepting | Test call against their endpoint before marking `active` |
| Renters never see other users' data | RLS: renters read only their own `capacity_providers` row + their own `usage_log` rows |
| Revocation | Renter can deactivate from `/renter/status` → `is_active = false`, access pauses |
| Audit | Every register/rotate/deactivate logged to `audit_log` |
| Minimum quota gate | Script rejects locally if estimated 10% donation < $5/month — prevents free-riders |

## Setup script — what it does

Runs entirely on the renter's machine. Sends only the final result over
HTTPS.

| Step | Action |
|---|---|
| 1 | Check `az` CLI installed |
| 2 | `az login` — must resolve to an **Azure for Students** subscription |
| 3 | Verify student subscription is active and has credit remaining |
| 4 | Create `rg-ochuko-renter-{shortId}` resource group |
| 5 | Create AI Foundry hub + project (Sweden Central, fallback East US) |
| 6 | Deploy one model: `gpt-5.4-nano` — renters don't need TTS, compaction, or the full think/solve stack |
| 7 | Read endpoint + API key |
| 8 | `POST /v1/renter/register-capacity` with setup token |
| 9 | Print success/failure in plain language |

Invocation:

```powershell
.\setup-renter-azure.ps1 -SetupToken "rent_abc123..." -ApiUrl "https://api.agent-ochuko.com"
```

Payload sent to the platform (HTTPS only):

```json
{
  "setup_token": "rent_abc123...",
  "azure_endpoint": "https://....openai.azure.com/",
  "azure_key": "sk-...",
  "subscription_name": "Azure for Students",
  "region": "swedencentral",
  "deployments": ["gpt-5.4-nano"],
  "estimated_monthly_quota_usd": 10.00
}
```

`deployment_mapping JSONB DEFAULT '{"nano": "gpt-5.4-nano"}'` is stored on the
`capacity_providers` row so `capacity_router` knows what to call for that
provider.

## Scope limits for v1

- Renter capacity routes **chat completions only**. `audio.py` (TTS) and the
  code executor (separate Azure AI Projects credential model) stay on
  platform credentials — renters likely don't have AI Projects access anyway.
- One deployment per renter (`gpt-5.4-nano`). No multi-model renter pool in
  v1.

## What changed from the original friend-pool draft

| Before | Now |
|---|---|
| Admin pastes renter Azure key | Renter self-serves via script |
| `friend_invitations` table | `renter_setup_tokens` (simpler, no email invite flow) |
| `access_tier` includes `trial` | `renter \| subscriber \| admin` only |
| Three admin pages for friends | One admin page, renter tab — no manual key entry |
| Separate `/renter` login | Unified `/login` with a Contribute tab |
| Invite-only signup | Open signup, gated on completion not admission |
