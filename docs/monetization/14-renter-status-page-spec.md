# Renter Status Page — Spec

Phase 8 build sheet. User app (`frontend/`), not admin.

---

## What & how

### What exists today

Nothing. `03-renter-onboarding-steps.md` Step 5 links to `/renter/status` as a
secondary CTA. `07-api-endpoints.md` defines `GET /v1/renter/usage` and
`POST /v1/renter/deactivate`. No page spec existed until this doc.

### What this page must accomplish

A renter who trusted you with their Azure key can see — in aggregate only — how
much of their donated quota has been consumed. They can deactivate without
contacting support. This is a trust mechanism, not ops monitoring.

### How (directives)

1. **Aggregate numbers only.** Show `quota_used_usd / quota_limit_usd`, period
   end, region, deployment. No other users' prompts, conversations, or token logs.
2. **Renter-only route.** Subscribers and NULL-tier users redirect away.
3. **Deactivate is reversible in principle** — `is_active=false` pauses access;
   reactivation requires re-running script or admin help (document which).
4. **Available before admin dashboard** — ship with Phase 4/5, not deferred.
5. **Same design system** as `RenterOnboarding.tsx` / `Dashboard.tsx`.

---

## What must be implemented

### Route

| Item | Value |
|---|---|
| Path | `/renter/status` |
| File | `frontend/src/pages/RenterStatus.tsx` |
| Auth | Session required |
| Guard | `access_tier === 'renter'` && `renter_onboarding_status === 'active'` |
| Else | Redirect to `/renter/onboarding` or `/login` |

### Page sections

**Header**
> Your Azure contribution

**Connection summary card** (from `GET /v1/renter/status`)

```
Region:           Sweden Central
Deployment:       gpt-5.4-nano
Donated quota:    $10.00 / month
Resets on:        1 Aug 2026
Status:           ● Active
```

**Usage card** (from `GET /v1/renter/usage`)

```
Used this period:     $3.42  (34%)
Remaining:            $6.58
```

Visual: progress bar, same pattern as admin quota bar but user-facing copy.

**Optional v1 stretch:** simple 7-day sparkline from daily aggregates — only if
backend exposes `GET /v1/renter/usage?granularity=daily`. Not required for
checkpoint.

**Transparency note** (static copy)

> This shows total usage against your donated quota. It does not include other
> users' conversations or message content.

**Deactivate section**

> Stop contributing
>
> This pauses your free access. Your encrypted key stays on file but won't be
> used. To contribute again, run the setup script from
> [onboarding](/renter/onboarding).

Button: **Deactivate my contribution** → confirm modal → `POST /v1/renter/deactivate`
→ redirect to `/login` with message.

### API consumption

| Endpoint | Use on page |
|---|---|
| `GET /v1/renter/status` | Connection summary |
| `GET /v1/renter/usage` | Usage numbers |
| `POST /v1/renter/deactivate` | Deactivate button |

### Post-deactivate behavior

Backend sets `capacity_providers.is_active = false`. Decide and document:

| Field | Value after deactivate |
|---|---|
| `access_tier` | stays `'renter'` or cleared to `NULL` — **pick one** |
| `renter_onboarding_status` | `'suspended'` recommended |
| Chat access | 403 until re-registered |

Document your choice in `16-schema-decisions.md` when decided.

### Navigation entry

Link from:
- `RenterOnboarding.tsx` Step 5 ("View my usage")
- User app settings/menu if one exists — optional

### Files

| File | Action |
|---|---|
| `frontend/src/pages/RenterStatus.tsx` | New |
| `frontend/src/App.tsx` | Route + guard |
| `backend/app/api/v1/endpoints/renter.py` | Endpoints from Phase 4 |

### Checkpoint

- [ ] Active renter sees correct quota numbers
- [ ] Page shows no conversation content
- [ ] Deactivate → chat blocked, provider inactive in admin
- [ ] Non-renter cannot access page
