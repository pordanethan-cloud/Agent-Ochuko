# Unified `/login` — Spec

Phase 1 build sheet.

---

## What & how

### What exists today

`Login.tsx` is a single funnel: email/password signup or signin, plus Google OAuth.
There is no distinction between a future renter and a future subscriber. On success,
everyone reloads into `/` via `ProtectedRoute`, which only checks for a Supabase
session — not whether they have earned chat access.

`AuthCallback.tsx` sends all OAuth completions to `/` unconditionally.

### What this page must accomplish

One URL (`/login`), two explicit business paths. The user chooses at signup time
how they intend to earn access:

- **Subscribe** — they will pay. Account created, `access_tier` stays `NULL` until
  payment webhook fires.
- **Contribute Azure Quota** — they will donate ~10% of student credit. Account
  created, `access_tier` stays `NULL` until the setup script registers their key.

The Contribute tab must explain the barter model in plain language *before* signup.
A renter should not discover what they're committing to only after creating an account.

### How (directives)

1. **Tab is chosen before signup.** Store `signup_type` in component state. It must
   survive the Google OAuth redirect via `sessionStorage` (key: `ochuko_signup_type`).
2. **Signup never grants access.** `access_tier` remains `NULL` for both paths at
   account creation. Do not set `access_tier='renter'` at signup — only after
   `register-capacity` succeeds.
3. **Post-auth routing is centralized.** One `resolvePostAuthRoute(profile)` function
   used by `Login.tsx`, `AuthCallback.tsx`, and `ProtectedRoute`. Do not duplicate
   redirect logic in three places.
4. **Returning users re-resolve every login.** A renter who signed up yesterday but
   never ran the script must land on `/renter/onboarding`, not the chat app.
5. **Google OAuth inherits the active tab.** If the user clicks Google while on the
   Contribute tab, treat it as `signup_type: 'renter'`.
6. **Sign-in (not sign-up) skips tab for known users.** If email already exists,
   route by their profile state, not the currently selected tab. The tab only matters
   for new signups.

### Decisions you own before building

| Decision | Options | Recommendation |
|---|---|---|
| Subscriber stub before Paystack | Empty page vs "coming soon" vs early checkout link | Early checkout link if Phase 7 is same sprint |
| Email confirmation required? | Supabase email confirm on/off | Match existing behavior — if confirm is on, redirect after confirm, not at signup |
| Can a user switch paths? | Renter fails → subscribe without new account | Yes — same account, new checkout. `access_tier` flips on webhook |

---

## What must be implemented

### UI structure

```
/login
├── Tab: Subscribe
│   ├── Subtitle: "Pay monthly for full access on our Azure capacity."
│   ├── Sign up / Sign in form (existing)
│   └── Google button
└── Tab: Contribute Azure Quota
    ├── Subtitle: "Donate ~10% of your Azure for Students credit. Get free access."
    ├── Explainer (3 bullets, see copy below)
    ├── Sign up / Sign in form (existing)
    └── Google button
```

### Contribute tab — explainer copy (fixed)

> **How it works**
> 1. You claim Azure for Students ($100 credit) in your own account.
> 2. You run a setup script on your machine — it creates a small Azure project in
>    *your* subscription and sends us only the endpoint and key.
> 3. You get full app access. We use up to 10% of your monthly credit for the shared pool.
>
> You need an active student subscription with credit remaining. Setup takes about
> 15 minutes.

### `signup_type` in Supabase

Email/password signup:

```typescript
await supabase.auth.signUp({
  email,
  password,
  options: {
    data: {
      preferred_name: cleanName,
      signup_type: activeTab === 'contribute' ? 'renter' : 'subscriber',
    },
  },
})
```

Google OAuth — before redirect:

```typescript
sessionStorage.setItem('ochuko_signup_type', activeTab === 'contribute' ? 'renter' : 'subscriber')
await supabase.auth.signInWithOAuth({
  provider: 'google',
  options: { redirectTo: `${origin}/auth/callback` },
})
```

### `accessResolver.ts`

```typescript
type Profile = {
  access_tier: 'renter' | 'subscriber' | 'admin' | null
  renter_onboarding_status: string | null
  // subscription status fetched separately or joined
}

function resolvePostAuthRoute(profile: Profile, subscriptionStatus?: string): string {
  if (profile.access_tier === 'admin') return '/'
  if (profile.access_tier === 'renter' && profile.renter_onboarding_status === 'active') return '/'
  if (profile.access_tier === 'subscriber' && subscriptionStatus === 'active') return '/'
  if (profile.access_tier === null && profile.renter_onboarding_status) return '/renter/onboarding'
  if (profile.access_tier === null) return '/subscribe/checkout'  // or paywall
  if (profile.access_tier === 'renter') return '/renter/onboarding'
  if (profile.access_tier === 'subscriber') return '/subscribe/checkout'
  return '/login'
}
```

Fetch profile from `profiles` table after auth. For subscribers, also fetch
`subscriptions.status` or read from JWT `app_metadata` once Phase 7 sync exists.

### `AuthCallback.tsx` changes

1. On session established, read `ochuko_signup_type` from `sessionStorage`.
2. If first login (no `signup_type` in user metadata) and sessionStorage has a
   value → `supabase.auth.updateUser({ data: { signup_type } })`.
3. Clear `sessionStorage` key.
4. Fetch profile → `resolvePostAuthRoute` → `navigate(route)`.

### `ProtectedRoute.tsx` changes

After session confirmed:

1. Fetch `profiles` row for `auth.uid()`.
2. If `resolvePostAuthRoute(profile) !== '/'` → `<Navigate to={route} />`.
3. Otherwise render children.

This blocks chat access for accounts that exist but haven't finished a path.

### Paywall state (pre-Phase 7)

`/subscribe/checkout` shows:

> Your account is ready. Complete payment to unlock access.
>
> [Pay with Paystack] — disabled until Phase 7, or linked if ready.
>
> Want to contribute Azure quota instead? [Switch to renter setup →](/renter/onboarding)
> only if `renter_onboarding_status` is set; otherwise link back to `/login` Contribute tab.

### Files to touch

| File | Change |
|---|---|
| `frontend/src/pages/Login.tsx` | Tabs, explainer, `signup_type` |
| `frontend/src/pages/AuthCallback.tsx` | Metadata backfill, routed redirect |
| `frontend/src/components/ProtectedRoute.tsx` | Access-tier gate |
| `frontend/src/utils/accessResolver.ts` | New |
| `frontend/src/App.tsx` | Routes for onboarding, checkout, status |
| `frontend/src/pages/SubscribeCheckout.tsx` | New stub |

### Checkpoint

- [ ] New renter signup (email) → `/renter/onboarding`, `access_tier=NULL`
- [ ] New subscriber signup (email) → `/subscribe/checkout`, `access_tier=NULL`
- [ ] Google signup with Contribute tab → same as renter
- [ ] Returning renter `pending_setup` → `/renter/onboarding`, cannot reach `/`
- [ ] Active renter → `/`
- [ ] Active subscriber → `/`
