# Schema Decisions & Edge Cases

Phase 0 build sheet. Amendments to `06-schema.sql`.

---

## What & how

### What exists today

`profiles` has `role` (guest/user/power_user/admin/superadmin). No `access_tier`.
No monetization tables. New users likely created via Supabase auth trigger
syncing to `profiles`.

### What this doc resolves

Gaps in `06-schema.sql` that would cause wrong behavior if applied verbatim:
subscriber profiles inheriting renter onboarding state, write path ambiguity,
JWT staleness, and deactivate semantics.

### How (directives)

1. **Defaults must not lie.** A subscriber should not have
   `renter_onboarding_status='pending_setup'` sitting on their profile forever.
2. **Writes use service role.** RLS is for read scoping when user JWT hits
   Supabase directly from frontend. FastAPI uses `SUPABASE_SERVICE_ROLE_KEY`
   for all monetization writes.
3. **`access_tier` and `subscriptions.status` are redundant by design.**
   Subscribers: status is truth. Renters: onboarding status + provider row is truth.
4. **JWT `app_metadata` is a cache**, not authority. Refresh on webhook and on
   `register-capacity` success.

---

## What must be implemented

### Amendment 1 — `renter_onboarding_status` nullable

**Problem:** `DEFAULT 'pending_setup'` on all profiles marks subscribers as
pending renters.

**Fix** — replace in migration:

```sql
ALTER TABLE profiles
  ADD COLUMN renter_onboarding_status TEXT
    DEFAULT NULL
    CHECK (renter_onboarding_status IS NULL OR renter_onboarding_status IN
      ('pending_setup', 'validating', 'active', 'failed', 'suspended'));
```

Only set `'pending_setup'` when `signup_type = 'renter'`.

### Amendment 2 — Profile creation trigger

On `auth.users` insert → `profiles` upsert:

```sql
-- Pseudologic for handle_new_user trigger
access_tier := NULL;
renter_onboarding_status := CASE
  WHEN NEW.raw_user_meta_data->>'signup_type' = 'renter' THEN 'pending_setup'
  ELSE NULL
END;
role := 'user';  -- unchanged default
```

If trigger cannot read `signup_type` (OAuth race), backend reconciliation
endpoint or `AuthCallback` metadata backfill sets it on first login.

### Amendment 3 — RLS write path

**Do not add INSERT/UPDATE policies for user JWT on:**
- `capacity_providers`
- `renter_setup_tokens`
- `subscriptions`
- `usage_log` (writes)

Document in migration comments:

```sql
-- Writes to monetization tables: FastAPI service role only.
-- RLS SELECT policies scope what renters/subscribers read via direct Supabase client.
```

Frontend should call backend APIs, not write these tables via Supabase client.

### Amendment 4 — `subscriptions.status` values

v1 set (no trial):

```
inactive | active | past_due | canceled
```

| Status | Chat access |
|---|---|
| `inactive` | Blocked (402) |
| `active` | Allowed |
| `past_due` | **You decide** — blocked immediately or grace until `current_period_end` |
| `canceled` | Blocked (402) |

Write your `past_due` decision in `10-subscriber-checkout-spec.md`.

### Amendment 5 — JWT `app_metadata` sync

When these change, call Supabase Admin API:

| Event | `app_metadata` |
|---|---|
| `register-capacity` success | `{ "access_tier": "renter" }` |
| Payment `charge.success` | `{ "access_tier": "subscriber" }` |
| Subscription canceled | `{ "access_tier": null }` |
| Renter deactivate | `{ "access_tier": null }` or keep — **decide** |

`verify_jwt` / middleware can read `app_metadata` for fast reject, but subscriber
path must still confirm `subscriptions.status` from DB on chat requests.

### Amendment 6 — Deactivate semantics

**Decision required** before Phase 4 ships:

| Field | On `POST /v1/renter/deactivate` |
|---|---|
| `capacity_providers.is_active` | `false` |
| `profiles.access_tier` | `NULL` (recommended — loses chat immediately) |
| `profiles.renter_onboarding_status` | `'suspended'` |
| Encrypted key row | Retained |

Re-entry: new setup token + re-run script → new or reactivated provider row.

### Amendment 7 — `usage_log` RLS read scope

Current policy lets renters `SELECT` only where `user_id = auth.uid()`. That
shows their *consumption as a chat user*, not *consumption against their donated
provider*.

Add a separate admin/RPC path for renter donation usage:

```sql
-- Renter donation usage: aggregate where capacity_provider_id = renter's own provider
-- Implement via GET /v1/renter/usage backend endpoint (service role query),
-- NOT direct RLS on other users' rows
```

Backend aggregates `usage_log` WHERE `capacity_provider_id = :their_provider_id`
— may include other users' token counts but never message content.

### Amendment 8 — Unique constraints

| Table | Constraint | Why |
|---|---|---|
| `subscriptions.user_id` | UNIQUE | One sub per user |
| `capacity_providers` | One active `type='renter'` per `owner_id` | v1: one donation per renter |
| `capacity_providers` | One `type='platform'` row per env | Seed script checks before insert |

Optional partial unique index:

```sql
CREATE UNIQUE INDEX idx_one_active_renter_provider
  ON capacity_providers (owner_id)
  WHERE type = 'renter' AND is_active = true;
```

### Amendment 9 — `audit_log` actions

Add to allowed action types (if enum/constrained):

- `credential_registered`
- `credential_deactivated`
- `setup_token_issued`
- `subscription_webhook_received`
- `subscription_comped`

### Migration file naming

Place amended SQL in agent-ochuko repo as:

```
scripts/023_monetization_core.sql      -- tables + RLS
scripts/024_monetization_triggers.sql  -- profile trigger + optional indexes
```

Keep `docs/monetization/06-schema.sql` as the reference copy; sync when amended.

### Checkpoint

- [ ] Subscriber signup → `renter_onboarding_status IS NULL`
- [ ] Renter signup → `renter_onboarding_status = 'pending_setup'`
- [ ] User JWT cannot INSERT into `capacity_providers`
- [ ] Webhook write succeeds via service role
- [ ] Deactivate behavior matches documented decision
