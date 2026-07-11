# Azure for Students — Claim Guide

Standalone content block. Reused verbatim (or near-verbatim) in three places:
`/renter/onboarding` Step 1, Email #1, and the setup script's printed output
on failure. Keeping one source of truth here avoids the three drifting out of
sync.

## Before running the script

**Step 1 — Claim Azure for Students ($100 credit)**

1. Go to `https://azure.microsoft.com/free/students`
2. Click **Activate now**
3. Sign in with your school email (`.edu`, `.ac.uk`, or your institution's
   verified domain)
4. Complete verification (SheerID or your school's process)
5. Confirm you see **Azure for Students** with **$100 credit** in
   `portal.azure.com` → Cost Management

**Step 2 — Confirm the right subscription**

```powershell
az login
az account list --output table
```

You must see a subscription named something like **Azure for Students**. If
you only see "Pay-As-You-Go" with $0, your student credit is not active — go
back to Step 1.

**Step 3 — Set it as default**

```powershell
az account set --subscription "Azure for Students"
```

**Step 4 — Run the setup script**

Only after Steps 1–3. The script checks the subscription name and warns if it
looks wrong.

## Common failures

| Problem | Fix |
|---|---|
| "No student subscription found" | Finish verification at azure.microsoft.com/free/students |
| "Insufficient quota" | Student credit exhausted — you can't join the pool until it renews |
| "Model not available in region" | Script auto-retries Sweden Central / East US |
| "Setup token expired" | Log in and generate a new token from `/renter/onboarding` |
| "Estimated contribution below $5/month" | Your remaining credit is too small to qualify as a renter — subscribe instead |
