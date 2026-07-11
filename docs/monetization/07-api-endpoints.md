# API Endpoints

## Renter endpoints — `backend/app/api/v1/endpoints/renter.py`

### `POST /v1/renter/setup-token`
**Auth:** JWT (renter's own session)
**Does:** Issues a new setup token. Invalidates any prior unused token for
that user. Stores only `token_hash` (SHA-256) — the plaintext token is
returned once in the response body and never persisted.

**Response:**
```json
{ "setup_token": "rent_xxxxxxxxxxxxxxxx", "expires_at": "2026-07-12T14:00:00Z" }
```

---

### `POST /v1/renter/register-capacity`
**Auth:** Setup token (not JWT) — the script never needs the renter's
password. Token passed in body, validated against `token_hash`, must be
unexpired and unused.
**Does:**
1. Look up `user_id` from the token.
2. Make one live test call against the submitted `azure_endpoint` /
   `azure_key` to confirm it works before accepting anything.
3. Reject if `estimated_monthly_quota_usd * 0.10 < 5.00` (minimum-quota gate).
4. AES-256-GCM encrypt the key.
5. Create the `capacity_providers` row (`type='renter'`, `owner_id=user_id`).
6. Mark the token `used_at = now()`.
7. Set `profiles.access_tier = 'renter'`, `renter_onboarding_status = 'active'`.
8. Trigger Email #2.
9. Write an `audit_log` entry.

**Request:**
```json
{
  "setup_token": "rent_xxxxxxxxxxxxxxxx",
  "azure_endpoint": "https://....openai.azure.com/",
  "azure_key": "sk-...",
  "subscription_name": "Azure for Students",
  "region": "swedencentral",
  "deployments": ["gpt-5.4-nano"],
  "estimated_monthly_quota_usd": 10.00
}
```

**Failure responses map directly to the failure states in
`03-renter-onboarding-steps.md`:**

| Condition | HTTP | `error` code |
|---|---|---|
| Token expired/used/invalid | 401 | `invalid_token` |
| Test call to Azure fails | 422 | `invalid_credentials` |
| Below minimum quota | 422 | `below_minimum_quota` |
| Model not available in region | 422 | `model_unavailable` |

---

### `GET /v1/renter/status`
**Auth:** JWT
**Does:** Returns current `renter_onboarding_status` and, if `active`, a
summary of their `capacity_providers` row (region, deployment, donated
quota — no key).

**Response:**
```json
{
  "renter_onboarding_status": "active",
  "region": "swedencentral",
  "deployment": "gpt-5.4-nano",
  "quota_limit_usd": 10.00
}
```

Polled every 3s by the onboarding page during Step 4.

---

### `GET /v1/renter/usage`
**Auth:** JWT
**Does:** Aggregate-only usage of the renter's own donated quota. Never
exposes other users' conversation content — this is the transparency
mechanism, not a monitoring one.

**Response:**
```json
{ "quota_limit_usd": 10.00, "quota_used_usd": 3.42, "period_end": "2026-08-01" }
```

---

### `POST /v1/renter/deactivate`
**Auth:** JWT
**Does:** Sets `capacity_providers.is_active = false` for the renter's row.
Access pauses — does not delete the row or the encrypted key, allowing
reactivation. Writes to `audit_log`.

---

## Subscription endpoints — `backend/app/api/v1/endpoints/subscriptions.py`

### `POST /v1/webhooks/payments`
**Auth:** Provider signature verification (Paystack/Flutterwave HMAC), not
JWT. Exclude this path from any maintenance/auth-block middleware.
**Does:** Single entry point for all payment provider events. On successful
payment/renewal → `subscriptions.status = 'active'`,
`profiles.access_tier = 'subscriber'`. On cancellation/failure →
`status = 'canceled'` or `'past_due'`.

**Access gate everywhere in the app checks `subscription.status`, not
`access_tier` alone** — a canceled subscriber shouldn't keep access because
`access_tier` is stale.

---

## Admin endpoints (extend existing `admin.py` auth pattern)

```
GET   /v1/admin/capacity              # list all providers + quota status
PATCH /v1/admin/capacity/{id}          # edit quota/priority, deactivate
GET   /v1/admin/capacity/usage         # aggregate, ?provider_id= for detail
GET   /v1/admin/subscriptions          # list, status, MRR
```

No admin endpoint for *adding* a renter's key manually — that path is
intentionally removed. Renters only enter the system through
`register-capacity`.
