# Implementation Plan — Two-Tier Monetization

Each phase below uses the same structure:

- **What & how** — what exists today, what this phase accomplishes, and the directives
  that govern how you build it. Decisions you still own are called out explicitly.
- **What must be implemented** — files, schema, endpoints, checkpoints. No code yet
  unless noted as existing in the repo.

Deep-dive specs for the gaps flagged in the initial review live in `09`–`16`.
This file is the phase map; those files are the build sheets.

---

## Stack (locked)

| Layer | Choice | Why |
|---|---|---|
| Auth | Supabase Auth (existing) | `user_metadata.signup_type` distinguishes renter vs subscriber at signup |
| DB | Supabase Postgres, raw SQL migrations | Matches existing `docs/` + migration pattern; no ORM |
| Backend | FastAPI (existing) | New routers under `backend/app/api/v1/endpoints/` |
| Encryption | AES-256-GCM, master key in App Config/env | v1 scope — no Key Vault dependency yet |
| Email | Resend | No email sender exists today; simplest transactional fit |
| Payments | Paystack primary, Flutterwave fallback | NGN settlement without Stripe Atlas |
| Renter script | PowerShell + Bash twins wrapping `az` CLI | Renters run locally on their own subscription |
| Frontend | React/TSX, existing Tailwind design system | Extend `Login.tsx`, new onboarding pages |
| Admin | Separate `admin/` SPA (existing) | One new page, not a new app |

---

## Access model

```
access_tier: NULL | 'renter' | 'subscriber' | 'admin'
renter_onboarding_status: NULL | 'pending_setup' | 'validating' | 'active' | 'failed' | 'suspended'
```

`NULL` access_tier is normal — an account can exist for days with zero chat access.
Signup creates an identity. Access is earned by finishing one of two paths.

`role` (guest/user/admin/superadmin) stays unchanged. It answers admin-app access only.
`access_tier` answers chat capacity billing only. Never overload one for the other.

---

## Phase 0 — Schema & Access Model

### What & how

**What exists today:** `profiles`, `conversations`, `token_budgets`, `agent_quotas`,
`usage_stats`. Single Azure deployment via `AZURE_OPENAI_*` env vars.
`get_openai_client()` in `chat.py` is a global singleton. No monetization tables.

**What this phase accomplishes:** A database layer every other phase can write to,
without changing how chat works yet. The platform's current env-based credentials
get a row in `capacity_providers` so Phase 5 has something to route to on day one.

**How (directives):**
- Apply schema before any UI work — you cannot issue setup tokens without the table.
- Seed the platform row manually on first deploy; do not hardcode live keys in SQL files.
- All writes to monetization tables go through the FastAPI service role, not user JWT.
  RLS is read-scoping for renters/subscribers, not the write path.
- `renter_onboarding_status` must be `NULL` for subscribers and unknown signups —
  not `pending_setup` on every profile. See `16-schema-decisions.md`.
- Nothing routes through new tables in this phase. Existing chat must keep working.

### What must be implemented

| Item | Detail |
|---|---|
| Migration | Apply `06-schema.sql` (+ amendments in `16-schema-decisions.md`) as `scripts/023_monetization_core.sql` in the agent-ochuko repo |
| Profile trigger | `handle_new_user` or equivalent: on signup, set `access_tier = NULL`; set `renter_onboarding_status = 'pending_setup'` only when `raw_user_meta_data->>'signup_type' = 'renter'` |
| Platform seed | One `capacity_providers` row: `type='platform'`, `owner_id=NULL`, encrypted key from env, `priority=100` |
| Seed script | `scripts/seed_platform_capacity.py` — reads env, encrypts, inserts. Run once per environment. |
| Service module stub | `backend/app/services/encryption_service.py` — encrypt/decrypt only; no callers yet |

**Checkpoint:** Migration applies on a prod data copy. Platform row seeded. Chat
unchanged. A test renter signup produces `access_tier=NULL`,
`renter_onboarding_status='pending_setup'`. A test subscriber signup produces
`renter_onboarding_status=NULL`.

**Spec:** `06-schema.sql`, `16-schema-decisions.md`, `15-env-and-deploy.md`

---

## Phase 1 — Unified `/login` Portal

### What & how

**What exists today:** `frontend/src/pages/Login.tsx` — single funnel, email/password
+ Google OAuth, no tier selection. `AuthCallback.tsx` always redirects to `/`.
`ProtectedRoute` only checks session, not access tier.

**What this phase accomplishes:** One front door with two explicit paths. The user
chooses *how they will earn access* at signup time. The choice is stored in
`user_metadata.signup_type` and drives every post-auth redirect.

**How (directives):**
- One page, two tabs: **Subscribe** and **Contribute Azure Quota**. Not two login URLs.
- Tab choice must be visible *before* signup — the renter explanation lives on the
  Contribute tab, not buried in onboarding.
- Signup always succeeds at the auth layer. Access is never granted at signup.
- Google OAuth must carry `signup_type` — store the selected tab in `sessionStorage`
  before redirect, read it in `AuthCallback`, write to `user_metadata` if first login.
- Returning users: redirect logic runs on every login, not just signup. Renters
  mid-setup go to `/renter/onboarding`, not `/`.
- Do not build checkout in this phase. Subscriber tab signup lands on a
  "complete payment" screen (Phase 7 stub is fine).

### What must be implemented

| Item | Detail |
|---|---|
| `Login.tsx` | Segmented control; tab-specific subtitle copy; pass `signup_type` in `signUp` options |
| `AuthCallback.tsx` | Read `signup_type` from sessionStorage or existing metadata; route via access resolver |
| `accessResolver.ts` | Pure function: given profile fields → `/`, `/renter/onboarding`, `/subscribe/checkout`, `/login` |
| `ProtectedRoute.tsx` | After session check, call access resolver — block `/` for `access_tier=NULL` |
| `SubscribeCheckout.tsx` | Stub page at `/subscribe/checkout` — "payment coming in Phase 7" or early Paystack link |
| Routes | Add `/renter/onboarding`, `/renter/status`, `/subscribe/checkout` in `App.tsx` |

**Checkpoint:** Renter email signup → `/renter/onboarding`. Subscriber email signup
→ `/subscribe/checkout`. Google signup with Contribute tab selected → same as renter.
Returning renter with `pending_setup` → `/renter/onboarding`, not chat.

**Spec:** `09-unified-login-spec.md`

---

## Phase 2 — Renter Steps Page

### What & how

**What exists today:** Nothing. Renters have no onboarding surface.

**What this phase accomplishes:** The renter's entire self-serve loop in one linear
page. A person with no Azure experience should finish using only this screen plus
a terminal — no admin, no email dependency for the token.

**How (directives):**
- Five steps, one expanded at a time. Completed steps collapse. Future steps locked.
- The setup token appears on Step 3, not in Email #1. Tokens in email get forwarded.
- Step 4 polls `GET /v1/renter/status` every 3s — the page is the progress UI.
- Failures render inline with a fix action, not a link to external docs.
- `active` status auto-redirects to `/` after 3 seconds.
- This page is renter-only. Subscribers never see it.

### What must be implemented

| Item | Detail |
|---|---|
| `RenterOnboarding.tsx` | `/renter/onboarding` — full copy in `03-renter-onboarding-steps.md` |
| Setup token UI | Copy button; regenerate via `POST /v1/renter/setup-token` when expired |
| Script download | Static files served from `public/renter-setup/` or API download endpoint |
| Status polling | 3s interval during Step 4; stop on `active` or `failed` |
| Step persistence | `localStorage` key `renter_onboarding_step` — resume on return |

**Checkpoint:** Fresh renter can read Steps 1–3 without API errors. Token issued on
load of Step 3. Polling shows `validating` when script POSTs.

**Spec:** `03-renter-onboarding-steps.md`

---

## Phase 3 — Setup Script

### What & how

**What exists today:** `docs/01_azure_foundry_setup.md` — manual setup docs, not
automated. No `scripts/renter-setup/`.

**What this phase accomplishes:** The renter runs one command locally. Azure
resources are created in *their* subscription. The platform receives only endpoint
+ key via HTTPS. You never hold credentials that can act on their Azure account
beyond the inference key they submit.

**How (directives):**
- Script runs on renter machine only. No remote provisioning.
- Minimum scope: one resource group, one hub, one project, one deployment
  (`gpt-5.4-nano`). No TTS, no code executor, no multi-model.
- Reject locally before any API call if estimated 10% donation < $5/month.
- Region fallback: Sweden Central first, East US second. SA North is not a target.
- Exit codes map 1:1 to API `error` codes in `07-api-endpoints.md`.
- `.ps1` and `.sh` must be twins — same steps, same payload, same validation.

### What must be implemented

| Item | Detail |
|---|---|
| `scripts/renter-setup/setup-renter-azure.ps1` | Full automation — see `12-setup-script-spec.md` |
| `scripts/renter-setup/setup-renter-azure.sh` | Bash twin |
| `scripts/renter-setup/lib/preflight.ps1` | az CLI check, student subscription detection |
| `scripts/renter-setup/lib/register.ps1` | HTTPS POST to `/v1/renter/register-capacity` |
| Public hosting | Copy or symlink into `frontend/public/renter-setup/` for download |

**Checkpoint:** Fresh student account → script completes → `capacity_providers`
row exists → renter sees `active` on onboarding page. Below-minimum credit →
script exits 6 before POST. Wrong subscription → exits 2 with printed fix.

**Spec:** `12-setup-script-spec.md`, `04-student-bonus-guide.md`

---

## Phase 4 — Backend: Registration, Encryption, Validation

### What & how

**What exists today:** `verify_jwt` on chat/admin routes. `audit_log` table and
admin audit page. No credential storage, no renter endpoints.

**What this phase accomplishes:** The trust boundary. The moment a renter's key
enters your system, it is validated, encrypted, stored, and audited. Invalid keys
never touch the database.

**How (directives):**
- `register-capacity` authenticates via setup token hash, not JWT.
- One live test inference call against their endpoint before any DB write.
- Plaintext key exists only in request memory for the duration of that request.
- On success: set `access_tier='renter'`, `renter_onboarding_status='active'`,
  mark token used, trigger Email #2 (Phase 6 can stub with log line initially).
- On failure: set `renter_onboarding_status='failed'` with retriable errors only.
- Renters read their own row via RLS. They cannot read other renters' keys or usage.

### What must be implemented

| Item | Detail |
|---|---|
| `backend/app/services/encryption_service.py` | AES-256-GCM; key from `ENCRYPTION_MASTER_KEY` env |
| `backend/app/api/v1/endpoints/renter.py` | All five renter endpoints — `07-api-endpoints.md` |
| `backend/app/services/renter_service.py` | Token issue/validate, capacity row create, status transitions |
| Router registration | `main.py` — mount renter router |
| Audit entries | `credential_registered`, `credential_deactivated` on each action |
| Test call | Minimal `chat.completions.create` or `responses.create` against submitted endpoint |

**Checkpoint:** Expired token → 401. Bad key → 422, no DB row. Valid key → encrypted
row, status `active`. RLS test: renter A cannot SELECT renter B's `capacity_providers`.

**Spec:** `07-api-endpoints.md`, `15-env-and-deploy.md`

---

## Phase 5 — Capacity Router

### What & how

**What exists today:** `get_openai_client()` singleton in `chat.py` (~5 call sites).
`model_router.py` picks deployment names from App Configuration. `TokenBudgetMiddleware`
on `/v1/responses/stream`. `reconcile_token_budget` RPC after stream completes.

**What this phase accomplishes:** Chat inference routes through the correct Azure
credential based on who is asking. Usage is logged per provider. Platform and
renters are the same kind of thing — one table, one router.

**How (directives):**
- Replace `get_openai_client()` in the **chat stream path only** for v1.
  `audio.py`, code executor, and Azure Functions stay on platform env creds.
- Subscriber: platform rows by `priority DESC`, overflow to renter pool if platform
  quota exhausted.
- Renter: any active pool row with remaining quota (own key is fine for their traffic).
- No capacity anywhere → HTTP 503 with explicit message. Never silent fallback to
  a broken or wrong client.
- Cache `AsyncAzureOpenAI` per `capacity_provider_id`, not one global instance.
- `deployment_mapping` on each provider row resolves model aliases — renters may
  use different deployment names than platform.
- Log usage in the same post-stream block as `reconcile_token_budget` (~line 1847
  in `chat.py`).
- **Legal gate:** do not route paying subscriber traffic through renter keys until
  Phase 9 checklist is cleared. Until then, subscriber overflow can be disabled
  with a feature flag.

### What must be implemented

| Item | Detail |
|---|---|
| `backend/app/services/capacity_router.py` | `get_client_for_request`, `log_usage`, `reset_quotas` |
| `backend/app/services/access_gate.py` | Central chat gate — access_tier + subscription status |
| `chat.py` changes | Replace `get_openai_client()` in stream generator; pass `capacity_provider_id` to log |
| Middleware | Extend `TokenBudgetMiddleware` or add `AccessGateMiddleware` before budget check |
| Cron | `reset_quotas()` in existing Azure Functions pattern or FastAPI scheduled task |
| Feature flag | `RENTER_POOL_OVERFLOW_ENABLED=false` until legal cleared |

**Checkpoint:** Subscriber chat hits platform row. Renter chat hits pool. All
providers exhausted → 503. Usage row written per stream. Platform env fallback
removed from chat stream path.

**Spec:** `11-capacity-router-spec.md`

---

## Phase 6 — Email Service

### What & how

**What exists today:** No email sender. No transactional email dependency.

**What this phase accomplishes:** Two emails that nudge renters through setup and
confirm connection. The API key never appears in any email payload.

**How (directives):**
- Resend for delivery. Templates are plain language, not HTML-heavy marketing.
- Email #1 on renter signup — links to `/renter/onboarding`, not the token.
- Email #2 on `register-capacity` success — endpoint + quota summary only.
- Fail email send gracefully — onboarding must not break if Resend is down.
- Optional stretch: failure nudge email after 48h `failed` status.

### What must be implemented

| Item | Detail |
|---|---|
| `backend/app/services/email_service.py` | Resend client; `send_renter_welcome`, `send_renter_connected` |
| Trigger hooks | Renter signup (auth webhook or post-signup API call); `register-capacity` success |
| Templates | Copy in `05-email-templates.md` — no key in template variables |
| Env | `RESEND_API_KEY`, `EMAIL_FROM` — see `15-env-and-deploy.md` |

**Checkpoint:** Signup triggers Email #1. Successful registration triggers Email #2.
Code review confirms no template variable accepts `azure_key`.

**Spec:** `05-email-templates.md`, `15-env-and-deploy.md`

---

## Phase 7 — Subscriber Payments

### What & how

**What exists today:** No `subscriptions` table usage, no payment provider, no
checkout, no webhook. Subscribers cannot pay.

**What this phase accomplishes:** The revenue path. Payment provider is source of
truth for subscriber access — not `access_tier` alone.

**How (directives):**
- Paystack primary for v1. You need to decide: plan price, currency (NGN vs USD),
  billing interval. Document your numbers in `10-subscriber-checkout-spec.md`
  before writing code.
- One webhook endpoint. Provider handles retries and dunning — do not rebuild billing.
- Gate on `subscriptions.status IN ('active')` everywhere. Decide `past_due` grace
  separately — document the choice.
- `access_tier = 'subscriber'` is set by webhook, cleared on cancel.
- Checkout is a separate page, not embedded in `/login`.
- No trial tier. First payment = first access.

### What must be implemented

| Item | Detail |
|---|---|
| `backend/app/api/v1/endpoints/subscriptions.py` | Webhook + checkout session init |
| `frontend/src/pages/SubscribeCheckout.tsx` | Paystack inline or redirect; success/failure states |
| Paystack dashboard | One plan, webhook URL pointing to `/v1/webhooks/payments` |
| Webhook handler | Event map — see `10-subscriber-checkout-spec.md` |
| Access gate | Wire into `access_gate.py` and `ProtectedRoute` paywall |
| JWT metadata sync | On tier change, update `app_metadata.access_tier` — see `16-schema-decisions.md` |

**Checkpoint:** Test payment → `subscriptions.status='active'`, chat unlocked.
Cancel webhook → access revoked on next request, not next login.

**Spec:** `10-subscriber-checkout-spec.md`

---

## Phase 8 — Admin Visibility + Renter Self-View

### What & how

**What exists today:** `admin/` SPA with Users, Usage, Budgets, Settings, Audit.
No capacity or subscription visibility. No renter-facing usage page.

**What this phase accomplishes:** You can see and intervene on the pool from one
admin screen. Renters can see aggregate usage of their own donation — trust, not
surveillance.

**How (directives):**
- Admin: one page, two tabs (Capacity Providers / Subscribers). Usage charts fold
  in as a third tab — not separate pages.
- No admin endpoint for manually pasting renter keys. Renters enter only via script.
- Admin can deactivate, adjust priority/quota, comp-extend a subscriber.
- Renter self-view: aggregate numbers only. Never other users' conversations.
- Renter deactivate pauses access; does not delete the encrypted key row.

### What must be implemented

| Item | Detail |
|---|---|
| `admin/src/pages/CapacityPool.tsx` | Three tabs — see `13-admin-capacity-pool-spec.md` |
| `admin/src/components/Layout.tsx` | Nav item: Capacity |
| Admin API routes | `GET/PATCH /v1/admin/capacity`, `GET /v1/admin/subscriptions` |
| `frontend/src/pages/RenterStatus.tsx` | `/renter/status` — see `14-renter-status-page-spec.md` |
| CSV export | `GET /v1/admin/capacity/usage?format=csv` |

**Checkpoint:** Admin sees all providers with quota bars. Deactivate renter → their
chat returns 403. Renter sees own `quota_used_usd` only.

**Spec:** `13-admin-capacity-pool-spec.md`, `14-renter-status-page-spec.md`

---

## Phase 9 — Legal & Launch Gate

### What & how

**What exists today:** `08-legal-launch-checklist.md` — unchecked items.

**What this phase accomplishes:** Explicit go/no-go before subscriber traffic can
flow through renter Azure keys. This is a business decision phase, not a code phase.

**How (directives):**
- Phase 5 can ship with `RENTER_POOL_OVERFLOW_ENABLED=false` while legal is pending.
  Renters and platform-only subscriber routing can still work.
- Every checklist item needs an owner and a date, not just a checkbox.
- Renter agreement can be informal but must be written before first real renter.
- Privacy disclosure to subscribers is a product decision — pick one approach and
  document it.

### What must be implemented

| Item | Detail |
|---|---|
| Checklist completion | All items in `08-legal-launch-checklist.md` |
| Renter agreement | One-page doc renters accept at Step 1 or signup |
| Subscriber ToS update | Disclosure if renter-pool overflow is enabled |
| `RENTER_POOL_OVERFLOW_ENABLED` | Flip to `true` only after checklist cleared |

**Checkpoint:** Written sign-off. Overflow flag enabled. First paying subscriber
onboarded with eyes open.

**Spec:** `08-legal-launch-checklist.md`

---

## Build order

| Week | Phases | Notes |
|---|---|---|
| 1 | 0, 1, 2 | Schema + login tabs + onboarding page skeleton |
| 2 | 3, 4 | Script twins + registration backend |
| 3 | 6 | Email live; portal content complete |
| 4 | 5 | Capacity router — highest risk |
| 5 | 7, 8 | Payments + admin + renter status (parallel) |
| 6 | 9 | Legal + end-to-end first renter + first subscriber |

---

## Doc index (gap specs)

| Doc | Covers |
|---|---|
| `09-unified-login-spec.md` | Phase 1 — login tabs, OAuth, redirects |
| `10-subscriber-checkout-spec.md` | Phase 7 — Paystack, webhooks, paywall |
| `11-capacity-router-spec.md` | Phase 5 — routing algorithm, call sites |
| `12-setup-script-spec.md` | Phase 3 — az commands, exit codes |
| `13-admin-capacity-pool-spec.md` | Phase 8 — admin page |
| `14-renter-status-page-spec.md` | Phase 8 — renter self-view |
| `15-env-and-deploy.md` | All phases — secrets, seed, migration order |
| `16-schema-decisions.md` | Phase 0 — triggers, RLS, JWT sync, edge cases |
