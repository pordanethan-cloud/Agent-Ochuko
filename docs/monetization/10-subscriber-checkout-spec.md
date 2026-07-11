# Subscriber Checkout & Payments — Spec

Phase 7 build sheet.

---

## What & how

### What exists today

Nothing. No `subscriptions` table in use, no payment provider integration, no
checkout page, no webhook handler. The refined plan's biggest gap versus
`bringing-user.md` is entirely here.

### What this path must accomplish

A user on the Subscribe tab creates an account, pays a flat monthly fee, and
gains chat access when the payment provider confirms — not when they click a
button. Cancellation must revoke access without waiting for next login.

### How (directives)

1. **Payment provider is source of truth.** `subscriptions.status` drives access.
   `access_tier='subscriber'` is a cache of that truth, not a substitute.
2. **One webhook endpoint.** `POST /v1/webhooks/payments`. Verify signature, map
   event → DB update. Do not build custom retry/dunning logic.
3. **No trial tier.** First successful charge = first access. No `trialing` status
   in v1 unless you explicitly add a Paystack trial plan later.
4. **Paystack primary** for Lagos NGN settlement. Flutterwave is fallback, not
   parallel — pick one for v1 to avoid two webhook implementations.
5. **Checkout is separate from login.** `/subscribe/checkout` is where payment
   happens after account exists.
6. **Gate everywhere chat can start** — not only `chat.py`. `TokenBudgetMiddleware`
   path on `/v1/responses/stream` must also check subscription status.

### Decisions you own before building

Fill these in this doc before writing code:

| Decision | Your call | Notes |
|---|---|---|
| Plan price | `₦_____ / month` or `$_____ / month` | Write the number here |
| Paystack plan code | `PLN_xxx` | Created in Paystack dashboard |
| `past_due` grace | 0 days / 3 days / until period end | Affects whether webhook or cron revokes access |
| Currency display | NGN only / NGN + USD estimate | Frontend checkout copy |
| Existing users | Can a renter later subscribe? | Yes — webhook overwrites `access_tier` to `subscriber` |

---

## What must be implemented

### User flow

```
/login (Subscribe tab) → sign up → /subscribe/checkout
  → Paystack inline or redirect
  → payment success → webhook → subscriptions.status='active'
  → access_tier='subscriber' → redirect to /
```

Returning subscriber with `status != 'active'` → `/subscribe/checkout` with
"renew or update payment" copy.

### Frontend — `SubscribeCheckout.tsx`

**Route:** `/subscribe/checkout`
**Auth:** Required (session)

**Layout:**
- Plan name + price (from env or static config — not hardcoded in component logic)
- What they get: "Full access on platform Azure capacity"
- Paystack button (Paystack Inline JS or redirect to Paystack hosted page)
- Link: "Contribute Azure quota instead?" → `/login` with note to use Contribute tab
  if they have no renter profile yet

**States:**
| State | UI |
|---|---|
| `access_tier=NULL`, no subscription row | "Complete payment to unlock" |
| `status='inactive'` | "Start your subscription" |
| `status='past_due'` | "Payment failed — update to restore access" |
| `status='active'` | Redirect to `/` |
| Payment in progress | Spinner |
| Payment failed (client-side) | Inline error + retry |

### Backend — checkout init

```
POST /v1/subscriptions/checkout
Auth: JWT
Body: (optional) { "plan_code": "PLN_xxx" }
Response: { "authorization_url": "...", "access_code": "..." }
  OR Paystack inline params for frontend JS
```

Creates or reuses `provider_customer_id` on Paystack. Inserts `subscriptions`
row with `status='inactive'` if first checkout.

### Backend — webhook

```
POST /v1/webhooks/payments
Auth: Paystack HMAC signature (header: x-paystack-signature)
```

**Exclude from:** maintenance middleware, JWT requirement, rate limit if it
blocks provider IPs.

#### Paystack event map (v1 minimum)

| Event | Action |
|---|---|
| `subscription.create` | Upsert `provider_subscription_id`, keep `inactive` until charge |
| `charge.success` | `status='active'`, `access_tier='subscriber'`, set `current_period_end` |
| `invoice.payment_failed` | `status='past_due'` — apply your grace decision |
| `subscription.disable` / `subscription.not_renew` | `status='canceled'`, `access_tier=NULL` |
| Unknown event | Log + 200 (don't retry-loop) |

#### Idempotency

Store `provider_event_id` or use Paystack event `id` to skip duplicate processing.

### JWT `app_metadata` sync

On every webhook tier change:

```python
supabase.auth.admin.update_user_by_id(
    user_id,
    {"app_metadata": {"access_tier": "subscriber"}}  # or null on cancel
)
```

Middleware can read `app_metadata.access_tier` for fast path; still verify
`subscriptions.status` on chat gate for subscribers (stale JWT case).

### Access gate (subscriber branch)

```python
if access_tier == "subscriber":
    sub = get_subscription(user_id)  # DB, not JWT alone
    if sub.status != "active":
        raise HTTPException(402, detail={
            "error": "subscription_inactive",
            "status": sub.status,
        })
```

Apply in:
- `backend/app/services/access_gate.py`
- `TokenBudgetMiddleware` (before budget check)
- `ProtectedRoute` equivalent on frontend (redirect to checkout)

### Database writes (webhook only)

All `subscriptions` INSERT/UPDATE via service role in webhook handler.
User JWT has SELECT-only via RLS (`06-schema.sql`).

### Files to create

| File | Purpose |
|---|---|
| `backend/app/api/v1/endpoints/subscriptions.py` | Checkout + webhook |
| `backend/app/services/paystack_service.py` | Signature verify, API calls |
| `frontend/src/pages/SubscribeCheckout.tsx` | Checkout UI |
| `frontend/src/hooks/useSubscription.ts` | Fetch status for ProtectedRoute |

### Env vars

See `15-env-and-deploy.md`: `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`,
`PAYSTACK_PLAN_CODE`, `PAYSTACK_WEBHOOK_SECRET`.

### Checkpoint

- [ ] Test card payment → webhook → `active` → chat works
- [ ] Cancel in Paystack dashboard → webhook → 402 on next chat request
- [ ] `past_due` behaves per your grace decision
- [ ] Duplicate webhook does not double-grant access
- [ ] Canceled subscriber `access_tier` cleared or stale tier still blocked by status check
