# Excel Add-in Implementation Plan
**Agent Ochuko — Microsoft Excel Task Pane Add-in**
*Phase 1 Status: COMPLETE — Phase 2 (Excel Interop Upgrade): COMPLETE*

---

## Overview

The Agent Ochuko Excel Add-in is a Microsoft Office Web Add-in that embeds the Agent Ochuko AI assistant directly inside Microsoft Excel as a task pane panel. It connects to the existing Agent Ochuko FastAPI backend using the same authentication system (Supabase Google OAuth) as the web application.

The add-in is intentionally minimal: a streaming chat interface with a single web-search toggle — no extra tools, complex UI panels, or separate personality modes.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                 Microsoft Excel (Desktop / Online)              │
│                                                                 │
│   ┌───────────────────────────────────────────────────────┐    │
│   │          Agent Ochuko Task Pane (HTTPS iframe)        │    │
│   │                                                       │    │
│   │   Auth Screen          Chat Screen                    │    │
│   │   ─────────────        ─────────────                  │    │
│   │   Google OAuth btn     Top bar (logo + Web toggle)    │    │
│   │                        SSE message stream             │    │
│   │                        Web source links               │    │
│   │                        Settings drawer                │    │
│   └──────────────────────────────┬────────────────────────┘    │
└─────────────────────────────────┼───────────────────────────────┘
                                  │ HTTPS
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
  Google OAuth             FastAPI Backend          Supabase Auth
  (via Supabase)     POST /v1/responses/stream    JWT validation
  accounts.google.com   SSE streaming             Row Level Security
```

### Auth Flow (Google OAuth via Office Dialog)

```
Task Pane                Office Dialog Popup             Supabase / Google
─────────                ────────────────────            ────────────────────
[Sign in] ──────────► Opens popup at:
                        supabase.../authorize
                        ?provider=google
                        &redirect_to=callback.html
                                                ───────► Google consent screen
                                                ◄─────── JWT in URL hash
                        callback.html parses token
                        messageParent(JWT)
◄─── receives JWT ──── dialog closes
Stores JWT, shows chat
```

---

## File Structure (Complete)

```
excel-addin/
│
├── manifest.xml                   Office Add-in manifest
│                                  Declares task pane, ribbon button, icons,
│                                  permissions (ReadWriteDocument), and all
│                                  allowed domains (Supabase, Google, localhost)
│
├── server.js                      Local HTTPS dev server
│                                  Auto-generates TLS certs via office-addin-dev-certs
│                                  Serves add-in at https://localhost:3000
│
├── package.json                   NPM config
│                                  devDependencies: office-addin-dev-certs,
│                                                   office-addin-manifest
│
├── README.md                      Developer setup guide
│
├── assets/
│   ├── icon-16.png                Agent Ochuko brand icon (16px)
│   ├── icon-32.png                Agent Ochuko brand icon (32px)
│   └── icon-80.png                Agent Ochuko brand icon (80px)
│                                  Custom AI-node icon generated for the add-in
│
└── src/
    │
    ├── auth/
    │   └── callback.html          OAuth callback page
    │                              Served from the same HTTPS origin (localhost:3000)
    │                              Supabase redirects here after Google login
    │                              Parses access_token from URL hash
    │                              Sends JWT back to task pane via
    │                              Office.context.ui.messageParent()
    │
    ├── commands/
    │   └── commands.html          Ribbon command entry-point (placeholder)
    │                              Required by the Office manifest spec
    │                              Contains Office.onReady() bootstrap only
    │
    └── taskpane/
        ├── taskpane.html          Main task pane UI
        │                         Two screens: Auth + Chat App
        │                         Settings: slide-up drawer (email, New Chat, Sign Out)
        │                         No URL config fields — all config is hardcoded
        │
        ├── taskpane.css           Dark glassmorphism theme
        │                         Navy/slate background (#0d1117, #161b22)
        │                         Electric blue accent (#58a6ff)
        │                         Animated live-status dot, floating welcome avatar
        │                         Sliding settings drawer, animated typing indicator
        │                         Web toggle with on/off glow effect
        │                         No emojis — all icons are inline SVG
        │
        └── taskpane.js           All add-in logic (vanilla JS, no framework)
                                  CONFIG object: Supabase URL, anon key, API URL
                                  Google OAuth via Office.context.ui.displayDialogAsync
                                  SSE streaming: POST /v1/responses/stream
                                  Web search toggle (mode: "think" / "solve")
                                  Source link rendering for grounded responses
                                  JWT persistence in localStorage
                                  Session restore on re-open
                                  New Chat: clears conversation_id and history
                                  Sign Out: clears JWT and resets UI
```

---

## Features Built

### Authentication
- **Google OAuth** — identical flow to the Agent Ochuko web app
- Opens Google consent screen in an **Office.js dialog popup** (required for sandboxed task pane iframes)
- Supabase redirects to `src/auth/callback.html` after consent
- Callback page sends JWT back to task pane via `Office.context.ui.messageParent()`
- JWT stored in `localStorage` — session persists across Excel restarts
- 401 responses automatically sign the user out and return to auth screen

### Chat
- Connects to `POST /v1/responses/stream` (existing backend endpoint)
- **Server-Sent Events (SSE)** — responses stream token by token in real time
- Full conversation history maintained locally (`S.history` array)
- `conversation_id` captured from SSE events and persisted for multi-turn context
- Animated typing indicator while streaming
- Error handling: network failures, expired tokens, HTTP errors

### Web Search Toggle
- Inline pill toggle in the top bar labelled "Web"
- **Off** (default): sends `{ mode: "think" }` — Ochuko answers from knowledge base
- **On**: sends `{ mode: "solve" }` — backend routes to Google Search grounding (Gemini 2.5 Flash retrieval + Azure OpenAI synthesis)
- When search is active, clickable source links are rendered below the response
- Toggle state persisted in `localStorage`

### Settings Drawer
- Slides up from bottom of the panel
- Shows the signed-in Google account (read-only)
- **New Chat** — clears active conversation, resets message history
- **Sign Out** — clears JWT and session, returns to auth screen
- No editable URL fields — all config hardcoded

---

## Configuration (Hardcoded)

| Setting | Value |
|---|---|
| Supabase URL | `https://mghydfaiggngeaspeotd.supabase.co` |
| Supabase Anon Key | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` |
| API URL | `http://localhost:8000` (dev) |
| OAuth Callback | `https://localhost:3000/src/auth/callback.html` |
| OAuth Scopes | `https://www.googleapis.com/auth/drive.file` |

---

## Backend Changes

### [`agent-ochuko/backend/app/main.py`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/main.py)

Added `https://localhost:3000` and `http://localhost:3000` to `prod_origins` so the locally-served add-in can call the API without CORS errors during development.

```python
# Excel Add-in local dev server (office-addin-dev-certs HTTPS)
"https://localhost:3000",
"http://localhost:3000",
```

---

## Manifest Allowed Domains

| Domain | Purpose |
|---|---|
| `https://localhost:3000` | Add-in dev server (task pane, callback) |
| `http://localhost:8000` | Backend API (dev) |
| `https://mghydfaiggngeaspeotd.supabase.co` | Supabase Auth OAuth endpoint |
| `https://accounts.google.com` | Google OAuth consent screen |

---

## How to Run (Developer)

```powershell
# 1. Install dependencies (one-time)
cd excel-addin
npm install

# 2. Start the HTTPS dev server
node server.js
# Generates TLS certs on first run (UAC prompt)
# Serves at https://localhost:3000

# 3. Sideload in Excel
#    Insert -> Add-ins -> My Add-ins -> Upload My Add-in
#    Browse to: excel-addin/manifest.xml
#    Click "Open Ochuko" in the Home ribbon
```

> The backend must be running on `http://localhost:8000` for the chat to work.

---

## API Endpoint Used

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/responses/stream` | POST | SSE chat stream (existing backend endpoint) |

**Request payload:**
```json
{
  "messages": [{ "role": "user", "content": "..." }],
  "mode": "think",
  "conversation_id": "<uuid>"
}
```

**Auth header:** `Authorization: Bearer <supabase-jwt>`

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Office dialog for OAuth | Task pane is a sandboxed iframe — full-page redirects are not possible. Office.js dialog is the official pattern for external auth flows. |
| Hardcoded config | Removes the need for URL settings in the UI — users should not need to configure the backend URL. Simplifies the auth screen to a single button. |
| `mode: "solve"` for web search | The existing backend routing already handles search grounding when mode is `solve`. No backend changes required. |
| Vanilla JS, no framework | Keeps the add-in lightweight, fast to load inside Excel, and free of build tooling complexity. |
| No emojis | All icons use inline SVG for consistency, cross-platform rendering, and a professional enterprise look. |

---

## Production Deployment Notes

To ship the add-in in production:

1. Update `CONFIG.API_URL` in `taskpane.js` to the Azure Container Apps URL
2. Update `CONFIG.OAUTH_CALLBACK` to the production static site URL (e.g. Azure Static Web Apps)
3. Update all `https://localhost:3000` references in `manifest.xml` to the production domain
4. Add the production domain to Supabase Auth > URL Configuration > Redirect URLs
5. Host the `excel-addin/` folder on Azure Blob Storage (`$web`) or Azure Static Web Apps
6. Distribute `manifest.xml` to users via Microsoft 365 Admin Center (centralized deployment) or direct sideloading

---

---

# Phase 2 — Excel Interop Upgrade
**Goal: Make Agent Ochuko function like Ochuko in Excel**
*Status: PLANNED*

---

## What Ochuko in Excel Does (Benchmark)

| Capability | Ochuko in Excel | Ochuko Phase 1 | Ochuko Phase 2 Target |
|---|---|---|---|
| Chat / Q&A | Yes | Yes | Yes |
| Web search | No | Yes (toggle) | Yes |
| Read selected cells as context | Yes | No | Yes |
| Write data / formulas into cells | Yes | No | Yes |
| Detect and render formulas in chat | Yes | No | Yes |
| One-click "Insert to Sheet" | Yes | No | Yes |
| Quick action buttons | Yes | No | Yes |
| Markdown rendering (bold, code, tables) | Yes | No | Yes |
| Copy response button | Yes | No | Yes |
| Active sheet / selection awareness | Yes | No | Yes |
| Explain a formula | Yes | No | Yes |
| Generate a table and insert it | Yes | No | Yes |
| Conversation history | Yes | Yes | Yes |
| Session persistence | Yes | Yes | Yes |

---

## Phase 2 Feature Groups

### 1. Excel Interop Layer

The core gap. Everything that makes Ochuko in Excel useful is its bidirectional connection to the spreadsheet. All Office.js Excel interop runs inside `Excel.run(async (ctx) => { ... })`.

#### 1a. Read Selection as Context

When the user sends a message, automatically capture the selected range and inject it into the message as structured context.

```
Selected: Sheet1!B2:D7
Headers:  Month | Revenue | Expenses
Row 1:    January | 45000 | 32000
Row 2:    February | 52000 | 38000
...
```

This context is prepended to the user message sent to the backend. Ochuko then has full awareness of the selected data without the user having to paste it.

**Implementation:**
- `Excel.run` → `ctx.workbook.getSelectedRange()` → `range.load(["values", "formulas", "address", "rowCount", "columnCount"])`
- Inject as a `[Excel Context: ...]` block at the top of the user message
- Show a "selection pill" in the input area indicating what range is loaded (e.g. `B2:D7 — 6 rows`)
- User can dismiss the pill to send without context

#### 1b. Write Data / Formulas Back to Cells

When Ochuko generates a formula or a table of data, provide an **"Insert to Sheet"** button on that response. Clicking it:

1. Targets the currently selected cell as the top-left anchor
2. Uses `Excel.run` to write the values or formula into the range
3. Confirms with a toast: "Inserted to B2"

**Formula detection:** Any AI response containing an Excel formula pattern (`=SUM(`, `=IF(`, `=VLOOKUP(`, etc.) automatically gets an **"Insert Formula"** button appended.

**Table detection:** Responses containing a markdown table (`| col | col |`) get an **"Insert Table"** button that parses the markdown and writes it to the sheet as a 2D array.

#### 1c. Active Sheet Metadata

Always inject lightweight context into the system prompt for every message:
- Active sheet name
- Used range dimensions (e.g. A1:Z200)
- Named ranges defined in the workbook

This costs very few tokens and dramatically improves the quality of formula suggestions.

---

### 2. Quick Action Buttons

A row of shortcut buttons above the input box. Each injects a specific prompt that includes the selected range context automatically.

| Button | Injected Prompt |
|---|---|
| Analyze | "Analyze the selected data and give me key insights." |
| Formula | "Write an Excel formula for the selected range to..." (then user completes) |
| Explain | "Explain what this formula does: [reads formula from selected cell]" |
| Clean | "Identify any data quality issues in the selected range." |
| Chart | "Suggest the best chart type for this data and explain why." |

---

### 3. Markdown Rendering

Currently responses are rendered as plain text (`el.textContent = text`). This must be upgraded to proper rich rendering.

**Required parser (lightweight, no external deps):**
- `**bold**` → `<strong>`
- `` `code` `` → `<code>`
- ` ```code block``` ` → `<pre><code>` with copy button
- `| table |` → `<table>` with insert button
- `## Heading` → `<h3>`
- `- list item` → `<ul><li>`
- `=FORMULA(...)` → styled formula chip with insert button

**Approach:** Implement a minimal inline renderer in `taskpane.js` — no external library, ~80 lines. Runs on every streamed chunk update.

---

### 4. Response Action Bar

Every completed assistant response gets an action bar below it:

```
[ Copy ]  [ Insert to Sheet ]  [ Regenerate ]
```

- **Copy** — copies raw text to clipboard
- **Insert to Sheet** — writes detected formula/table to selected cell
- **Regenerate** — resends the last user message with the same context

---

### 5. Selection Awareness Indicator

A persistent pill in the input bar shows what is currently selected in the spreadsheet:

```
[ Sheet1!B2:D7  6 x 3  — Click to refresh ]
```

- Updates when the user changes selection (Office.js `SelectionChanged` event)
- Clicking it refreshes the captured data
- Clicking the X dismisses it (sends without spreadsheet context)

---

### 6. Formula Assistant Mode

A dedicated quick mode triggered when the user types a formula question or clicks the "Formula" quick action:

1. Read the selected cell's existing formula (if any)
2. Pre-fill context: existing formula, surrounding cells, column headers
3. Stream a formula response
4. Render the formula in a styled chip: `` `=SUMIF(A:A,"Q1",B:B)` ``
5. One-click insert into the selected cell

---

## Phase 2 Files to Change / Add

### Modified Files

#### [`src/taskpane/taskpane.js`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/excel-addin/src/taskpane/taskpane.js)
- Add `captureSelection()` — reads selected range via `Excel.run`
- Add `injectExcelContext(userText)` — prepends selection data to message
- Add `watchSelection()` — listens to `SelectionChanged` event, updates pill
- Add `insertToSheet(data, type)` — writes formula or 2D array to selected cell
- Add `renderMarkdown(text)` — lightweight markdown-to-HTML renderer
- Add `extractFormulas(text)` — regex detects Excel formulas in response
- Add `extractTables(text)` — parses markdown tables to 2D arrays
- Add quick action button handlers
- Update `updateBubble()` to use `innerHTML` with rendered markdown
- Add response action bar after each completed response

#### [`src/taskpane/taskpane.html`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/excel-addin/src/taskpane/taskpane.html)
- Add quick action button row (`#quick-actions`)
- Add selection pill (`#selection-pill`) in the input area
- Update `#search-pill` area to accommodate both pills

#### [`src/taskpane/taskpane.css`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/excel-addin/src/taskpane/taskpane.css)
- Quick action button row styles
- Selection pill styles
- Markdown rendering styles: `code`, `pre`, `table`, formula chip
- Response action bar styles
- Insert-to-sheet button styles

### New Files

#### `src/taskpane/markdown.js`
Standalone lightweight markdown renderer (~100 lines). No external deps. Handles: bold, italic, inline code, code blocks, headers, lists, tables, and formula chips. Used by `taskpane.js` for response rendering.

---

## Phase 2 Architecture (Upgraded)

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Microsoft Excel                                   │
│                                                                     │
│  Active Sheet: Sheet1          Selected: B2:D7 (Revenue table)      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │   Agent Ochuko Task Pane                                      │  │
│  │                                                               │  │
│  │   [Analyze] [Formula] [Explain] [Clean] [Chart]  ← Quick     │  │
│  │                                                    Actions    │  │
│  │   ┌─────────────────────────────────────────────┐            │  │
│  │   │  Messages (Markdown rendered)               │            │  │
│  │   │                                             │            │  │
│  │   │  You: Analyze the revenue data              │            │  │
│  │   │                                             │            │  │
│  │   │  Ochuko:                                    │            │  │
│  │   │  **Revenue Summary (Jan–Jun)**              │            │  │
│  │   │  | Month | Revenue | Growth |              │            │  │
│  │   │  | Jan   | 45,000  | —      |              │            │  │
│  │   │  | Feb   | 52,000  | +15.6% |              │            │  │
│  │   │  [Insert Table] [Copy]                      │            │  │
│  │   │                                             │            │  │
│  │   │  Suggested formula:                         │            │  │
│  │   │  `=AVERAGEIF(A:A,"Q1",B:B)`                │            │  │
│  │   │  [Insert Formula]                           │            │  │
│  │   └─────────────────────────────────────────────┘            │  │
│  │                                                               │  │
│  │  [ Sheet1!B2:D7  6x3  x ]  [Web]                            │  │
│  │  [ Message Ochuko...              ] [Send]                    │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                          |                                          │
│           Excel.run() ◄──┘──► Write to cells                        │
│           Office.js SelectionChanged event                          │
└─────────────────────────────────────────────────────────────────────┘
                           |
                     HTTPS / SSE
                           |
              Agent Ochuko Backend (FastAPI)
              POST /v1/responses/stream
              Excel context injected in message
```

---

## Phase 2 Estimated Effort

| Feature | Effort | Priority |
|---|---|---|
| Read selection + inject as context | Small | Critical |
| Selection awareness pill | Small | Critical |
| Markdown rendering | Medium | Critical |
| Formula detection + insert button | Medium | High |
| Quick action buttons | Small | High |
| Response action bar (copy / insert) | Small | High |
| Table detection + insert | Medium | High |
| `SelectionChanged` live watcher | Small | Medium |
| Formula assistant mode | Medium | Medium |
| `markdown.js` standalone renderer | Medium | Critical |

**Total estimated implementation: 2–3 days of focused development.**

---

## Answer: Can it function like Ochuko in Excel?

**Yes — and it can go further.** Ochuko in Excel has no web search; Ochuko already has that. The gap is purely in the Office.js Excel interop layer: reading selections, writing back, and rendering responses richly.

The Phase 2 features above close that gap completely. Once shipped:

- Ochuko reads whatever you select in the spreadsheet
- It streams a formatted, markdown-rendered response with formula chips and tables
- You click one button to insert a formula or table directly into the sheet
- Web search stays available for real-world data lookups alongside sheet analysis
- All of this uses the existing backend with zero backend changes required

---

---

# Phase 3 — Teacher / Solver Mode
**Status: COMPLETE**

---

## Overview

Two AI personality modes switchable in the top bar. The user begins in Teacher Mode to build real mastery, and switches to Solver Mode once they no longer need explanations — only results.

| | Teacher Mode | Solver Mode |
|---|---|---|
| **Goal** | Build genuine mastery | Save time |
| **Persona** | Patient coach | Expert peer |
| **Response format** | Why → Breakdown → Example → Mastery Check | Answer → Brief context → Done |
| **Quick actions** | Explain, Breakdown, Analogy, Practice, Compare | Analyze, Formula, Explain, Clean, Chart |
| **Accent colour** | Amber / gold (`#f5a623`) | Electric azure (`#4db8ff`) |
| **Persistence** | `localStorage` key `ochuko_mode` | Same |

---

## Mode Toggle UI

A compact segmented pill control in the top bar between the title and settings icon:

```
[ Teacher | Solver ]
```

- Active segment has a filled pill — amber for Teacher, blue for Solver
- Inactive segment is ghost text
- Switching modes triggers: accent colour transition, quick action re-render, welcome block update, toast confirmation

---

## System Prompts

Injected as `{ role: "system" }` as the **first message in every API request**.
Not stored in `S.history` — fresh on every call, so it never accumulates in context.

### Teacher Mode
Instructs Ochuko to: explain WHY before WHAT, use first principles, break into steps, give a concrete example, always end with a "Mastery Check" question, encourage experimentation.

### Solver Mode
Instructs Ochuko to: lead with the answer immediately, maximum one sentence of context, bullet points, rank alternatives, no filler, assume expert-level understanding.

---

## Quick Actions Per Mode

### Teacher
| Button | Intent |
|---|---|
| Explain | First-principles explanation of the selected content |
| Breakdown | Step-by-step dissection of what the selected cells do |
| Analogy | Memorable analogy to make the concept click |
| Practice | Hands-on exercise to test understanding |
| Compare | Tradeoff comparison against alternative approaches |

### Solver
| Button | Intent |
|---|---|
| Analyze | Key insights, trends, anomalies from selected data |
| Formula | Best formulas for the selection |
| Explain | What the selected formula does |
| Clean | Data quality issues in range |
| Chart | Best chart recommendation |

---

## Implementation Notes

- `buildSystemPrompt()` in `taskpane.js` returns the correct prompt for the active mode
- `renderQuickActions()` dynamically builds the correct 5 buttons on mode switch
- `switchMode(mode)` applies `body.mode-teacher` or `body.mode-solver` CSS class, which swaps `--accent` and `--accent-glow` via CSS custom property cascade
- Mode default: **Teacher** (first-time users learn before they solve)
- Zero backend changes required
