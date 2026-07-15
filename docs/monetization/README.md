# Agent-Ochuko — Monetization

Two-tier access model: **Renter** (donate ~10% Azure quota → free access) and
**Subscriber** (pay → platform capacity). No trial tier. Signup does not equal
access — an account can exist for days with zero app access until a renter
finishes Azure registration or a subscriber's payment clears.

**Supersedes:** `docs/bringing-user.md` (friend-pool draft — never implemented).

---

## Doc structure

Every phase doc uses two layers:

1. **What & how** — what exists in the repo, what the phase accomplishes, directives,
   and decisions you still own.
2. **What must be implemented** — files, endpoints, schema, checkpoints.

`01-implementation-plan.md` is the phase map. `09`–`16` are the build sheets
for areas that were thin or missing in the first pass.

---

## Read order

| # | Doc | What it covers |
|---|---|---|
| 1 | [`01-implementation-plan.md`](./01-implementation-plan.md) | Phases 0–9: directive + technical per phase |
| 2 | [`02-renter-model.md`](./02-renter-model.md) | Renter mechanics overview |
| 3 | [`03-renter-onboarding-steps.md`](./03-renter-onboarding-steps.md) | `/renter/onboarding` UX copy |
| 4 | [`04-student-bonus-guide.md`](./04-student-bonus-guide.md) | Reusable student credit content |
| 5 | [`05-email-templates.md`](./05-email-templates.md) | Email #1 and #2 copy |
| 6 | [`06-schema.sql`](./06-schema.sql) | Reference migration |
| 7 | [`07-api-endpoints.md`](./07-api-endpoints.md) | Renter + subscription endpoint summary |
| 8 | [`08-legal-launch-checklist.md`](./08-legal-launch-checklist.md) | Launch gate |
| 9 | [`09-unified-login-spec.md`](./09-unified-login-spec.md) | Phase 1 — `/login` tabs, OAuth, redirects |
| 10 | [`10-subscriber-checkout-spec.md`](./10-subscriber-checkout-spec.md) | Phase 7 — Paystack, webhooks, paywall |
| 11 | [`11-capacity-router-spec.md`](./11-capacity-router-spec.md) | Phase 5 — routing, call sites |
| 12 | [`12-setup-script-spec.md`](./12-setup-script-spec.md) | Phase 3 — `az` automation, exit codes |
| 13 | [`13-admin-capacity-pool-spec.md`](./13-admin-capacity-pool-spec.md) | Phase 8 — admin page |
| 14 | [`14-renter-status-page-spec.md`](./14-renter-status-page-spec.md) | Phase 8 — renter self-view |
| 15 | [`15-env-and-deploy.md`](./15-env-and-deploy.md) | Secrets, seed, migration order |
| 16 | [`16-schema-decisions.md`](./16-schema-decisions.md) | Triggers, RLS, edge cases |

---

## The model, one paragraph

A user hits one unified `/login` page with two tabs — **Subscribe** or
**Contribute Azure Quota**. Subscribers pay and get access on webhook
confirmation. Renters sign up for free, land on a linear onboarding page,
download a script, run it locally against their own Azure for Students
subscription, and the script registers the resulting endpoint with the
platform over a one-time token. The platform never creates Azure resources on
a renter's behalf and never emails an API key. Access is binary: `renter`
(once `renter_onboarding_status = 'active'`) or `subscriber` (once
`subscription.status = 'active'`). Nothing in between.

---

## Key decisions locked

- **Unified login, not separate portals.** `/login` has a tab/toggle.
- **Open renter signup**, not invite-only. Access gated on completion, not admission.
- **No trial tier.** `access_tier` is `NULL` until a path completes.
- **No admin key pasting.** Renters enter only via setup script.
- **Subscriber overflow to renter pool** behind `RENTER_POOL_OVERFLOW_ENABLED`
  until legal checklist cleared.

## Decisions still open (fill before build)

| Decision | Where to record |
|---|---|
| Plan price + currency | `10-subscriber-checkout-spec.md` |
| `past_due` grace period | `10-subscriber-checkout-spec.md` |
| Deactivate field semantics | `16-schema-decisions.md` |
| Renter own-key routing preference | `11-capacity-router-spec.md` |
