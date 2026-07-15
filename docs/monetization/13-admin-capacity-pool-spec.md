# Admin Capacity Pool — Spec

Phase 8 build sheet. Admin app only — not `frontend/`.

---

## What & how

### What exists today

`admin/src/pages/` has Users, Usage, Budgets, Settings, AuditLog. `Layout.tsx`
sidebar nav lists those five. Admin auth requires `role IN ('admin', 'superadmin')`
via existing `admin.py` pattern.

There is no visibility into capacity providers, renter onboarding status, or
subscription MRR. The old `bringing-user.md` planned three separate friend pages —
this is one page with tabs.

### What this page must accomplish

You (the operator) can see the entire pool, intervene when something breaks, and
comp a subscriber — without ever pasting a renter's Azure key. Renters enter the
system only through the setup script.

### How (directives)

1. **One route, three tabs** — Capacity Providers / Subscribers / Usage.
2. **No "add renter key" form.** If a renter is stuck, you help them re-run the
   script or re-issue a token — you don't bypass the trust model.
3. **Deactivate, don't delete.** Turning off a provider sets `is_active=false`.
   Encrypted key stays for audit/reactivation.
4. **Manual subscriber override** for comps: extend `current_period_end`, force
   `status='active'`. Log every override to `audit_log`.
5. **Match admin visual language** — slate palette from `Layout.tsx`, not the
   warm `brand-*` tokens from user `Dashboard.tsx`.

---

## What must be implemented

### Route & nav

| Item | Value |
|---|---|
| Path | `/capacity` |
| File | `admin/src/pages/CapacityPool.tsx` |
| Nav label | Capacity |
| Icon | `Server` or `Layers` from lucide-react |

### Tab 1 — Capacity Providers

**Data source:** `GET /v1/admin/capacity`

**Table columns:**

| Column | Source |
|---|---|
| Type | `platform` / `renter` badge |
| Owner | email from `profiles` (NULL → "Platform") |
| Region | `capacity_providers.region` |
| Quota | progress bar `quota_used_usd / quota_limit_usd` |
| Priority | number |
| Status | `is_active` + `renter_onboarding_status` if renter |
| Onboarded | `created_at` |

**Row actions:**
- Edit priority / quota limit (PATCH)
- Deactivate / Reactivate (PATCH `is_active`)
- View usage detail → switches to Usage tab filtered by `provider_id`

**Platform row:** always visible, not deletable. Editable quota/priority.

**No action:** "Add renter manually"

### Tab 2 — Subscribers

**Data source:** `GET /v1/admin/subscriptions`

**Table columns:**

| Column | Source |
|---|---|
| User | email |
| Status | `active` / `past_due` / `canceled` / `inactive` |
| Plan | `plan_amount_usd` |
| Period end | `current_period_end` |
| Provider | Paystack ID (truncated) |
| MRR contribution | plan amount if active else 0 |

**Summary card above table:** Active count, MRR sum, past_due count.

**Row actions:**
- Comp extend: modal → new `current_period_end`, force `active`, audit log
- Cancel: set `canceled`, clear `access_tier`, audit log

### Tab 3 — Usage

**Data source:** `GET /v1/admin/capacity/usage?provider_id=&from=&to=`

Reuse chart patterns from `admin/src/pages/Usage.tsx` — hourly/daily cost by
provider. Provider filter dropdown from Tab 1 data.

**Export button:** `GET /v1/admin/capacity/usage?format=csv` — same date range.

### API endpoints (admin auth)

Extend existing admin JWT + role check:

```
GET   /v1/admin/capacity
PATCH /v1/admin/capacity/{id}     # { quota_limit_usd?, priority?, is_active? }
GET   /v1/admin/capacity/usage    # ?provider_id &from &to &format=csv
GET   /v1/admin/subscriptions
PATCH /v1/admin/subscriptions/{id}  # manual comp/cancel — document body schema
```

### PATCH body examples

```json
// Deactivate renter
{ "is_active": false }

// Comp subscriber +30 days
{ "status": "active", "current_period_end": "2026-08-11T00:00:00Z", "comp_reason": "support ticket #12" }
```

### Audit log entries

| Action | `audit_log.action` |
|---|---|
| Provider deactivated | `capacity_provider_deactivated` |
| Quota/priority changed | `capacity_provider_updated` |
| Subscriber comped | `subscription_comped` |
| Subscriber canceled | `subscription_canceled_admin` |

### Files

| File | Action |
|---|---|
| `admin/src/pages/CapacityPool.tsx` | New |
| `admin/src/components/Layout.tsx` | Add nav item |
| `admin/src/App.tsx` | Add route |
| `backend/app/api/v1/endpoints/admin.py` or `capacity.py` | New admin routes |

### Checkpoint

- [ ] All providers visible with quota bars
- [ ] Deactivate renter → their chat 403, row shows inactive
- [ ] Subscriber list shows MRR
- [ ] CSV export downloads
- [ ] Comp extend writes audit entry
