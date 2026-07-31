# OCHUKO.CFO Excel Add-in — Deploy Guide

## Architecture: Where the Add-in Lives in Production

```
Azure Blob Storage (agentochukostore)
  └── $web/                  ← Public Static Website Container
        ├── (frontend app)
        └── addin/           ← Excel Add-in (public static host)
              ├── src/
              │   ├── taskpane/
              │   │   ├── taskpane.html
              │   │   ├── taskpane.css
              │   │   ├── taskpane.js      (API URL patched to prod at deploy time)
              │   │   └── markdown.js
              │   ├── auth/
              │   │   └── callback.html
              │   └── commands/
              │       └── commands.html
              ├── assets/
              │   ├── icon-16.png
              │   ├── icon-32.png
              │   └── icon-80.png
              └── manifest.xml             (manifest.production.xml uploaded here)
```

**Add-in URL (production):**
`https://agentochukostore.z1.web.core.windows.net/addin/src/taskpane/taskpane.html`

**Manifest URL (for sideloading or AppSource):**
`https://agentochukostore.z1.web.core.windows.net/addin/manifest.xml`

---

## Files Created

| File | Purpose |
|---|---|
| [deploy_local.ps1](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/infra/build/deploy_local.ps1) | Full local deploy script (deploys Backend + Frontend + Add-in) |
| [deploy_addin.ps1](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/infra/build/deploy_addin.ps1) | Add-in standalone deploy script |
| [manifest.production.xml](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/excel-addin/manifest.production.xml) | Production manifest pointing to Blob Storage |
| [manifest.xml](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/excel-addin/manifest.xml) | Dev manifest pointing to localhost:3000 |

---

## How to Deploy

### Prerequisites (one-time)

```powershell
# 1. Log in to Azure
az login

# 2. Verify you can see the storage account
az storage account show --name agentochukostore --resource-group rg-ochuko
```

### Option A: Full Deployment (Backend + Frontend + Add-in)

To build and deploy the entire workspace, run the unified script:

```powershell
cd "c:\Users\T14 GEN 5\Documents\WORK AND PLAN\AZURE SYSTEM-AUTH AT SCALE\agent-ochuko\infra\build"
.\deploy_local.ps1
```

### Option B: Standalone Add-in Deployment

If you only want to update the Excel Add-in:

```powershell
# Run the standalone script
cd "c:\Users\T14 GEN 5\Documents\WORK AND PLAN\AZURE SYSTEM-AUTH AT SCALE\agent-ochuko\infra\build"
.\deploy_addin.ps1

# OR run from the excel-addin folder:
cd "c:\Users\T14 GEN 5\Documents\WORK AND PLAN\AZURE SYSTEM-AUTH AT SCALE\excel-addin"
npm run deploy
```

### What the Add-in deploy sequence does — step by step

| Step | Action |
|---|---|
| 1 | Validates `manifest.production.xml` schema (fails fast if broken) |
| 2 | Patches `taskpane.js`: replaces `http://localhost:8000` with the production API URL |
| 3 | Fetches Azure storage key via `az storage account keys list` |
| 4 | Creates the `addin` blob container (public blob access) if it doesn't exist |
| 5 | Uploads `src/` to `addin/src/` and `assets/` to `addin/assets/` |
| 6 | Uploads `manifest.production.xml` as `addin/manifest.xml` |
| 7 | Sets correct `Content-Type` headers on all JS, CSS, HTML, XML, PNG blobs |
| 8 | Restores `taskpane.js` to `localhost:8000` so local dev keeps working |

> The URL patch is always reverted at the end (even on error), so your local dev environment is never broken by a deployment.

---

## After Deploying: Sideload in Excel

### Option A — Desktop Excel (one-time per machine)

1. Download the manifest: `https://agentochukostore.blob.core.windows.net/addin/manifest.xml`
2. In Excel: **Insert -> Add-ins -> My Add-ins -> Upload My Add-in**
3. Browse to the downloaded `manifest.xml`
4. Click **Open Ochuko** in the Home ribbon

### Option B — Excel on the Web

1. Go to [office.com](https://office.com) and open a workbook
2. **Insert -> Add-ins -> More Add-ins -> Upload My Add-in**
3. Paste the manifest URL or upload the file

---

## CORS: Backend Already Updated

The production storage static website origin is already in `main.py`:

```python
prod_origins = [
    "https://agentochukostore.z1.web.core.windows.net",   # <-- Excel Add-in & Web App (production)
    "https://localhost:3000",                             # <-- Excel Add-in (local dev)
    ...
]
```

You **do not** need to redeploy the backend for CORS to work — it is already safe-listed.

---

## Dev vs Production

| | Local Dev | Production |
|---|---|---|
| **Manifest** | `manifest.xml` | `manifest.production.xml` |
| **Taskpane URL** | `https://localhost:3000/src/taskpane/taskpane.html` | `https://agentochukostore.z1.web.core.windows.net/addin/src/taskpane/taskpane.html` |
| **API URL** | `http://localhost:8000` | `https://agent-ochuko-api.azurecontainerapps.io` |
| **Start command** | `npm run dev` | `npm run deploy` |
| **Auth callback** | `https://localhost:3000/src/auth/callback.html` | `https://agentochukostore.z1.web.core.windows.net/addin/src/auth/callback.html` |

> Make sure the production callback URL is added as an **Authorized Redirect URI** in your Google OAuth2 credentials in Google Cloud Console.
