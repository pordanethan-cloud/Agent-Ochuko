# Agent Ochuko — Excel Add-in

A minimal, premium Excel task-pane add-in that brings **Agent Ochuko** directly into Microsoft Excel.

## Features

| Feature | Detail |
|---|---|
| 💬 **Chat** | SSE-streamed responses from the Ochuko backend |
| 🌐 **Web Search toggle** | One tap enables real-time web grounding via Google Search |
| 🔐 **Supabase Auth** | Email + password login, JWT persisted in localStorage |
| ⚙️ **Settings drawer** | Change API URL, Supabase URL, start a new chat, or sign out |

---

## Quick Start (Local Development)

### 1. Install dependencies

```powershell
cd excel-addin
npm install
```

### 2. Start the HTTPS dev server

```powershell
node server.js
```

On first run, this installs trusted TLS certificates via `office-addin-dev-certs`.
You may see a UAC prompt — accept it so Excel trusts `https://localhost:3000`.

The server prints:
```
✅ Agent Ochuko Add-in server running at https://localhost:3000
```

### 3. Sideload into Excel

1. Open **Microsoft Excel**
2. Go to **Insert → Add-ins → My Add-ins → Upload My Add-in**
3. Browse to `excel-addin/manifest.xml` and click **Upload**
4. Click **"Open Ochuko"** in the **Home** ribbon

> **Excel Online**: Insert → Add-ins → Upload My Add-in → Browse `manifest.xml`

---

## Signing In

Fill in all four fields on the sign-in screen:

| Field | Value |
|---|---|
| **Email** | Your Supabase Auth email |
| **Password** | Your Supabase Auth password |
| **Supabase URL** | `https://<your-project>.supabase.co` |
| **API URL** | `http://localhost:8000` (dev) or your Azure Container App URL |

---

## Web Search Toggle

The 🌐 toggle in the top-right of the add-in enables **real-time web search**:

- **Off** → Ochuko answers from its knowledge base (`mode: "think"`)
- **On** → Ochuko queries Google Search and cites sources (`mode: "solve"`)

The toggle state persists across sessions.

---

## Project Structure

```
excel-addin/
├── manifest.xml               Office Add-in manifest (sideload descriptor)
├── server.js                  Local HTTPS dev server
├── package.json
├── assets/
│   ├── icon-16.png
│   ├── icon-32.png
│   └── icon-80.png
└── src/
    ├── taskpane/
    │   ├── taskpane.html      Main UI
    │   ├── taskpane.css       Dark premium theme
    │   └── taskpane.js        Auth, chat, SSE streaming, toggle
    └── commands/
        └── commands.html      Ribbon command placeholder
```

---

## Backend Requirements

The add-in calls these endpoints on the Agent Ochuko FastAPI backend:

| Endpoint | Purpose |
|---|---|
| `POST /v1/responses/stream` | SSE chat stream |

Auth: `Authorization: Bearer <supabase-jwt>` on every request.

CORS: `https://localhost:3000` is already whitelisted in `main.py`.

---

## Production Deployment

For production, update `manifest.xml` to point to your Azure Static Web App URL instead of `https://localhost:3000`, then host the `excel-addin/` folder on Azure Blob Storage or Azure Static Web Apps.
