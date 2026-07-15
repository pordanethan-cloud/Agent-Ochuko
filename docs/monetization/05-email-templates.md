# Email Templates

Sent via Resend from `backend/app/services/email_service.py`. No email
sender exists in the repo today — this is new infrastructure, not an
extension of anything existing.

**Hard rule for both templates:** the Azure API key is never included in an
email, in any form — not in the body, not in an attachment, not in a link
query param. The renter sees it once, on their own screen, when the script
prints it. State this explicitly in Email #1 so it isn't a surprise.

---

## Email #1 — Sent immediately on renter signup

**Subject:** Set up your Azure contribution for Agent-Ochuko

**Trigger:** `signup_type = 'renter'` account creation, before any onboarding
step is complete.

**Body (plain-language, short):**

> Hi {{first_name}},
>
> You signed up to contribute Azure quota to Agent-Ochuko in exchange for
> free access. Here's what that means: you donate about 10% of your Azure
> for Students credit to a shared pool, and in return you get full use of
> the app — no payment required.
>
> **Next step:** finish setup at {{onboarding_url}}. It's five short steps —
> claim your student credit if you haven't already, confirm it's active,
> download a small setup script, run it, and you're in.
>
> The script runs on your machine and creates a small Azure project inside
> *your own* subscription. It sends us only the resulting endpoint and key —
> never your Azure login, and we never email that key back to you once it's
> stored.
>
> Your setup token is waiting on the onboarding page — please run the script
> within 24 hours, since the token expires after that.
>
> Need help claiming your student credit first? Full instructions are on the
> onboarding page under Step 1.
>
> — Agent-Ochuko

**CTA button:** `Finish setup →` linking to `{{onboarding_url}}`

---

## Email #2 — Sent after `register-capacity` succeeds

**Subject:** Your Azure capacity is connected

**Trigger:** `renter_onboarding_status` transitions to `active`.

**Body (confirms, never exposes secrets):**

> Hi {{first_name}},
>
> You're connected. Here's a summary:
>
> - **Region:** {{region}}
> - **Deployment:** {{deployment_name}}
> - **Donated quota:** ~${{donated_amount}}/month
>   ({{donation_percent}}% of your estimated student credit)
>
> Your API key is stored securely, encrypted, on our servers. We never email
> keys — this confirmation only ever shows the endpoint and quota summary
> above.
>
> You now have full access to Agent-Ochuko: {{app_url}}
>
> You can view your own usage anytime at {{usage_dashboard_url}} — this only
> shows your own donated quota, never other users' conversations.
>
> If you ever want to stop contributing, you can deactivate from that same
> page and your access will pause.
>
> — Agent-Ochuko

**CTA button:** `Open Agent-Ochuko →` linking to `{{app_url}}`

---

## Failure notification (optional, Phase 6 stretch)

Not in the original two-email flow, but worth adding once Phase 6 is stable:
a single email if `renter_onboarding_status = 'failed'` and the renter hasn't
returned within, say, 48 hours — nudges them back with the specific failure
reason inline, reusing the failure-state copy from
`03-renter-onboarding-steps.md`.
