# Environment, Secrets & Deploy — Spec

Cross-cutting. Reference for all phases.

---

## What & how

### What exists today

Platform Azure creds live in env / Azure App Configuration:
`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`. Supabase:
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. No encryption master key, no Resend,
no Paystack.

### What this doc accomplishes

One place listing every new secret, where it lives, and the order you apply
changes in each environment (local → staging → prod).

### How (directives)

1. **Never commit secrets** to SQL files or git. `06-schema.sql` uses placeholders.
2. **Platform capacity row** is seeded by script reading env — not hand-inserted
   in prod with plaintext key.
3. **Encryption master key** is the highest-sensitivity new secret. Rotation
   procedure is manual in v1 — document steps even if you don't automate.
4. **Webhook secrets** differ per environment. Paystack dashboard gets staging
   and prod URLs separately.

---

## What must be implemented

### New environment variables

| Variable | Phase | Required | Purpose |
|---|---|---|---|
| `ENCRYPTION_MASTER_KEY` | 4 | Yes | 32-byte base64 AES-256-GCM key |
| `RESEND_API_KEY` | 6 | Yes | Transactional email |
| `EMAIL_FROM` | 6 | Yes | e.g. `onboarding@agent-ochuko.com` |
| `APP_URL` | 6 | Yes | Links in emails |
| `API_URL` | 3 | Yes | Script default `--api-url` |
| `PAYSTACK_SECRET_KEY` | 7 | Yes | Server-side Paystack |
| `PAYSTACK_PUBLIC_KEY` | 7 | Yes | Frontend inline checkout |
| `PAYSTACK_PLAN_CODE` | 7 | Yes | Subscription plan |
| `PAYSTACK_WEBHOOK_SECRET` | 7 | Recommended | Extra signature validation |
| `RENTER_POOL_OVERFLOW_ENABLED` | 5 | Yes | `false` until Phase 9 |
| `RENTER_MIN_DONATION_USD` | 4 | Optional | Default `5.00` |

Existing vars unchanged for platform fallback paths (`audio.py`, etc.).

### Generate encryption key (once per env)

```bash
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Store in Azure App Configuration or container env. Not in Supabase.

### Migration apply order

| Order | File | Phase |
|---|---|---|
| 1 | `scripts/023_monetization_core.sql` (from `06-schema.sql`) | 0 |
| 2 | Profile trigger patch (see `16-schema-decisions.md`) | 0 |
| 3 | Platform seed script run | 0 |

Apply on Supabase via SQL editor or migration pipeline. Verify RLS policies
applied.

### Platform seed script

`scripts/seed_platform_capacity.py`:

1. Read `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` from env.
2. Encrypt key with `ENCRYPTION_MASTER_KEY`.
3. `INSERT INTO capacity_providers` if no `type='platform'` row exists.
4. Set `deployment_mapping` from App Configuration deployment names.
5. Set `quota_limit_usd` from your monthly budget (you decide the number).
6. `quota_reset_date` = first day of next month.

Idempotent — safe to re-run.

### Resend setup

1. Verify domain in Resend dashboard.
2. Create API key.
3. Set `EMAIL_FROM` to verified address.

### Paystack setup

1. Create subscription plan → copy `PLN_xxx` to `PAYSTACK_PLAN_CODE`.
2. Set webhook URL: `https://api.{env}.agent-ochuko.com/v1/webhooks/payments`
3. Enable events: `charge.success`, `subscription.create`, `subscription.disable`,
   `invoice.payment_failed`.
4. Copy secret key to backend env.

### Script distribution

Copy `scripts/renter-setup/*` to `frontend/public/renter-setup/` on build or
deploy. Onboarding page links to `/renter-setup/setup-renter-azure.ps1`.

### Deploy checklist (per environment)

- [ ] Migration 023 applied
- [ ] Profile trigger active
- [ ] `ENCRYPTION_MASTER_KEY` set
- [ ] Platform capacity row seeded
- [ ] `RENTER_POOL_OVERFLOW_ENABLED=false`
- [ ] Resend domain verified (before Phase 6 go-live)
- [ ] Paystack webhook pointing to correct API URL (before Phase 7 go-live)
- [ ] Renter scripts in `public/renter-setup/`

### Local dev

Developers can run backend without Paystack/Resend if:
- Email service logs to console when `RESEND_API_KEY` missing.
- Checkout page shows "payments disabled in dev".
- Capacity router falls back to platform row only.

Document in backend `.env.example` — add vars without values.

### Rotation (v1 manual)

**Encryption key rotation:** decrypt all `azure_key_encrypted` with old key,
re-encrypt with new key, update env. Schedule maintenance window. No automation
required for v1 but write the steps before you have 10 renters.

---

## Files to create

| File | Purpose |
|---|---|
| `scripts/seed_platform_capacity.py` | Platform row seed |
| `agent-ochuko/backend/.env.example` | New vars documented |
| Deploy runbook section in infra docs | Optional pointer to this file |
