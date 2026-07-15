# `/renter/onboarding` — Steps Page Spec

This is the exact content and behavior for `RenterOnboarding.tsx`. One thing
per screen state, no wall of text, live status underneath. Match the dark
Tailwind design system already used in `Dashboard.tsx` (`#0d0f11` surfaces,
`#1e2025` borders, `brand-text` / `brand-muted`).

## Layout

A vertical numbered list, 5 steps. Only the active step is expanded; completed
steps collapse to a checkmark + one-line summary; future steps are dimmed and
locked. This keeps a first-time renter from feeling the weight of the whole
flow at once.

```
● Step 1 — Claim your student credit         [expanded / active]
○ Step 2 — Confirm the right subscription    [dimmed]
○ Step 3 — Download the script               [dimmed]
○ Step 4 — Run it                            [dimmed]
○ Step 5 — Done                              [dimmed]
```

---

### Step 1 — Claim your student credit

**Header copy:**
> You need an active Azure for Students account with credit remaining. If
> you've already claimed it, skip to Step 2.

**Checklist (each item a static row, not interactive — informational):**
1. Go to `azure.microsoft.com/free/students`
2. Click **Activate now**
3. Sign in with your school email (`.edu`, `.ac.uk`, or your institution's
   verified domain)
4. Complete verification (SheerID or your school's process)
5. Confirm you see **Azure for Students** with **$100 credit** under
   `portal.azure.com` → Cost Management

**CTA:** `I've claimed my credit →` (advances to Step 2; no verification here,
verification happens in Step 2 via CLI)

---

### Step 2 — Confirm the right subscription

**Header copy:**
> Two commands. Run them in a terminal with Azure CLI installed.

```powershell
az login
az account list --output table
```

> You should see a subscription named something like **Azure for Students**.
> If you only see "Pay-As-You-Go" with $0, your student credit isn't active —
> go back to Step 1.

Set it as default:

```powershell
az account set --subscription "Azure for Students"
```

**CTA:** `My subscription is confirmed →`

---

### Step 3 — Download the script

**Header copy:**
> Your one-time setup token (expires in 24 hours):

```
rent_xxxxxxxxxxxxxxxx          [copy button]
```

**OS-detected download buttons:**
- `Download for Windows (.ps1)`
- `Download for Mac/Linux (.sh)`

**Note directly under the buttons:**
> This script creates a small Azure project in *your* subscription and sends
> us only the resulting endpoint and key — never your login credentials.

**CTA:** `I've downloaded it →`

---

### Step 4 — Run it

**Header copy:**
> Run this in the same terminal where you confirmed your subscription:

```powershell
.\setup-renter-azure.ps1 -SetupToken "rent_xxxxxxxxxxxxxxxx"
```

*(Mac/Linux equivalent shown if `.sh` was downloaded)*

**Live status block below the command — polls `GET /v1/renter/status` every
3s:**

```
Status: ● pending_setup
Status: ● validating       (script has POSTed, platform is testing the key)
Status: ● active           → auto-redirect to the main app in 3s
```

**Inline failure states** (replace the status block if `renter_onboarding_status = 'failed'`, keyed by the specific error the endpoint returns):

| Error | Message shown |
|---|---|
| No student subscription | "No student subscription found. Go back to Step 1 and finish verification at azure.microsoft.com/free/students." |
| Insufficient quota | "Your student credit is exhausted. You can't join the renter pool until it renews." |
| Model unavailable | "The model wasn't available in your region — the script is retrying in Sweden Central / East US automatically. If this persists, contact support." |
| Setup token expired | "Your setup token expired. [Generate a new one]" *(button re-issues via `POST /v1/renter/setup-token`)* |
| Below minimum quota | "Your estimated contribution is under $5/month, which is too small to join the pool. You're welcome to subscribe instead." *(link to `/login` Subscribe tab)* |

---

### Step 5 — Done

**Header copy:**
> You're connected. Here's what's donated:

```
Endpoint region:     Sweden Central
Deployment:          gpt-5.4-nano
Donated quota:       ~$10/month (10% of your estimated $100 student credit)
```

**CTA:** `Go to the app →` (routes to `/`)

**Secondary link:** `View my usage` → `/renter/status` (aggregate-only self
view, built in Phase 5)

---

## States the page must handle on load

- **Fresh signup, no token issued yet** → show Step 1 expanded, others locked.
- **Returning renter, `pending_setup`, token still valid** → resume at
  whichever step matches their furthest completed action (persist step
  progress client-side or infer from `renter_onboarding_status`).
- **Returning renter, token expired, still `pending_setup`** → Step 3, with
  a re-issue token button pre-surfaced.
- **`renter_onboarding_status = 'active'`** → redirect straight to `/`, this
  page has nothing left to show them.
- **`renter_onboarding_status = 'suspended'`** → replace the whole page with
  a support-contact message, not the step flow.
