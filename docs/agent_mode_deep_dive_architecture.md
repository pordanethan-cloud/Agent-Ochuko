# Agent Mode: End-to-End Architecture, Tool Orchestration & Website Engine Guide

This document explains everything happening under the hood in **Agent Mode** across the entire stack — from the user interface down through the Go Edge Gateway, FastAPI orchestration engine, tool execution loop, website generation, and delivery packaging.

---

## 1. Why Think Mode Felt "Sick" vs. Why Early Agent Mode Underwhelmed

| Dimension | Think Mode (Previous Gold Standard) | Early Agent Mode (What Needed Fixing) | Upgraded Agent Mode (Now) |
|---|---|---|---|
| **Planning & Architecture** | Produces an exhaustive, structured Implementation Plan (system design, UI tokens, component hierarchy, responsive layout). | Generated a mechanical, 3-step JSON checklist without surfacing the deep design blueprint to the user. | **Full Think-Mode Blueprinting**: generates the complete architectural and implementation plan directly in chat before and during execution. |
| **Website Aesthetics** | Rich typography (Google Fonts), Tailwind design tokens, sleek dark modes, micro-animations, interactive states. | Sometimes fell back to basic HTML or rigid code generation without rich aesthetic tokens. | **World-Class Web Design Contract**: enforces responsive breakpoints (360/768/1280px), Google Fonts, dynamic states, and modern design aesthetics. |
| **Output / Synthesis** | Rich, expansive markdown explanation with visual hierarchy and clear technical depth. | Choked by a prompt telling it: *"This reply is chat text: a short status and summary. NEVER include full file contents"*, resulting in dry 2-sentence outputs. | **Elite Synthesis**: outputs the full architectural breakdown, design rationale, verified file manifest, and interactive links. |
| **Website Preview** | Rendered via inline preview or artifact panel. | Showed **"agent-ochuko-api refused to connect"** inside the preview iframe due to Go Edge Gateway clickjacking headers. | **Fixed**: Go Gateway explicitly exempts `/v1/sites/*` from `X-Frame-Options: DENY`, enabling seamless iframe previews. |
| **Packaging & Files** | Single files presented directly. | Zipped arbitrarily, forcing users to download an archive even for individual files. | **Zip-for-Multi-File Only**: single files are never zipped; multi-file projects get a zip *and* every file is individually demandable. |

---

## 2. End-to-End Request Flow (UI &rarr; Gateway &rarr; Backend)

```mermaid
sequenceDiagram
    autonumber
    actor User as User (Browser UI)
    participant UI as React Frontend (Dashboard.tsx)
    participant GW as Go Edge Gateway (:8000)
    participant API as FastAPI Backend (:8001)
    participant Mgr as AgentTaskManager
    participant Box as Code Sandbox (/tmp/sandbox_...)
    participant Site as HostedSitesService (/v1/sites)

    User->>UI: Types: "Build a modern portfolio website" in Agent Mode
    UI->>GW: POST /v1/chat (mode: "agent", stream: true)
    Note over GW: Edge Gateway checks JWT, CORS, Circuit Breaker
    GW->>API: Reverse-proxies request to Python AI Worker
    API->>Mgr: Initializes AgentTaskManager(task, config)
    Mgr->>API: Generates structured plan (OODA)
    API-->>GW-->>UI: SSE event: 'agent_plan' (renders interactive timeline)

    loop Step Execution (Autonomous OODA Loop)
        Mgr->>API: Execute Step (e.g. sandbox_write: index.html, styles.css)
        API->>Box: Writes files to conversation sandbox directory
        API-->>GW-->>UI: SSE event: 'agent_step_complete'
    end

    Mgr->>Site: Deploys multi-file static site via deploy_site
    Site-->>Mgr: Returns slug & preview URL (/v1/sites/portfolio-xyz)
    Mgr->>API: Calls present_deliverable (uploads files + optional project.zip)
    API-->>GW-->>UI: SSE event: 'generated_files' + markdown synthesis

    UI->>GW: Iframe loads GET /v1/sites/portfolio-xyz
    Note over GW: /v1/sites bypasses X-Frame-Options DENY; sets CSP frame-ancestors
    GW->>API: Proxies GET /v1/sites/portfolio-xyz
    API-->>GW-->>UI: Returns HTML + CSS + JS (Renders in ArtifactPanel without error!)
```

---

## 3. UI Layer (React / TypeScript Frontend)

### A. Mode Selection & Prompt Dispatch
* Located in `agent-ochuko/frontend/src/pages/Dashboard.tsx`.
* When the user selects **Agent Mode**, the chat request payload sends `mode: "agent"`.
* The frontend initiates a Server-Sent Events (SSE) stream to `/v1/chat`.

### B. Real-Time Streaming Widgets
While the agent works, the UI does not show a blank loading spinner. It listens for real-time SSE event types:
1. `agent_plan`: Renders the step-by-step interactive timeline accordion.
2. `agent_step_start`: Highlights the current active step with an animated pulse and tool badge.
3. `agent_step_complete`: Marks the step finished with duration (ms) and token spend.
4. `agent_approval_required`: If a step touches a high-risk tool (e.g., email send or production deployment), pauses the orchestrator and renders an approval card with "Approve" and "Reject" buttons.
5. `agent_ask_user_input`: Renders an interactive decision form when the agent needs user preferences.
6. `generated_files`: Renders file cards and triggers the right-hand **Artifact Panel**.
7. `content_block_delta`: Streams the final markdown synthesis in real time.

### C. The Artifact Panel & Live Iframe Preview
* Located in `agent-ochuko/frontend/src/components/ArtifactPanel.tsx`.
* When an HTML or web project deliverable is produced, the panel splits into:
  * **Code view**: syntax-highlighted editor showing raw HTML/CSS/JS with file tabs.
  * **Preview view**: an embedded `<iframe>` with desktop and mobile responsive device toggles.
* **Why it failed before:** The iframe loaded `https://agent-ochuko-api.../v1/sites/{slug}`. The browser received `X-Frame-Options: DENY` from the Go gateway, causing the browser to block the iframe with *"refused to connect"*.
* **How it works now:** The gateway allows framing for `/v1/sites`, and the panel seamlessly renders the live interactive website.

---

## 4. Go Edge Gateway Layer (High-Performance Supervisor)

The container runs a single-container, dual-process model:
* **Go Edge Gateway** (`gateway/cmd/server/main.go`): runs on port **8000** (exposed to Azure).
* **Python AI Worker** (FastAPI / Uvicorn): runs on internal port **8001**.

```
                       ┌──────────────────────────────────────────────┐
                       │           Azure Container App                │
                       │           (agent-ochuko-api)                 │
Internet ──:443/8000──►│  ┌────────────────────────────────────────┐  │
                       │  │         Go Edge Gateway (:8000)        │  │
                       │  │  - JWT Auth Validation                 │  │
                       │  │  - In-Memory Hot Cache (HotCache)      │  │
                       │  │  - Circuit Breaker (worker protection) │  │
                       │  │  - Defensive Security Headers          │  │
                       │  └───────────────────┬────────────────────┘  │
                       │                      │ localhost:8001        │
                       │  ┌───────────────────▼────────────────────┐  │
                       │  │      FastAPI AI Worker (:8001)         │  │
                       │  │  - AgentTaskManager & Planner          │  │
                       │  │  - Code Sandbox & Bash Execution       │  │
                       │  │  - Hosted Sites Service                │  │
                       │  └────────────────────────────────────────┘  │
                       └──────────────────────────────────────────────┘
```

### The Clickjacking Fix in `security.go`
In `gateway/pkg/middleware/security.go`:
* **Standard API Routes** (`/v1/chat`, `/v1/agents`, `/v1/auth`): Keep `X-Frame-Options: DENY` and `frame-ancestors 'none'` to protect user sessions against clickjacking.
* **Hosted Site Routes** (`/v1/sites/*`): Explicitly **exempt** from `X-Frame-Options: DENY`. Sets:
  ```http
  Content-Security-Policy: default-src 'self' 'unsafe-inline' 'unsafe-eval' https: data: blob:; frame-ancestors 'self' http://localhost:* https://*;
  Cross-Origin-Resource-Policy: cross-origin
  Cross-Origin-Opener-Policy: unsafe-none
  ```
  This allows the Ochuko frontend and users to preview their deployed websites in iframes without browser refusal.

---

## 5. Backend Agent Orchestration Engine (`AgentTaskManager`)

When an agent request arrives in `agent-ochuko/backend/app/api/v1/endpoints/chat.py`:

### Step A: Plan Generation (OODA Loop)
`agent_planner.py` uses `_STRUCTURED_PLANNER_SYSTEM` to decompose the goal:
1. **Observe**: Hydrates sandbox context from Cloudflare R2 to see all existing project files.
2. **Orient**: Identifies the exact tools required (`sandbox_write`, `deploy_site`, `present_deliverable`).
3. **Decide**: Constructs sequential step objects with parameter hints.
4. **Act**: Formulates concrete verification criteria for each step.

### Step B: Execution & Cognitive Tool Feedback
In `agent_task_manager.py`:
* The manager loops through each step sequentially.
* If a step fails, the **Reflexion Engine** does not simply crash — it feeds the raw error output back to the model, which formulates an alternative approach and retries.
* Every file written to disk is validated against `VerificationGates` (e.g., verifying that responsive `<meta name="viewport">` tags exist and that buttons have interactive hover/focus states).

### Step C: Final Synthesis (The Think-Mode Upgrade)
* After completing tool execution, `AgentTaskManager` calls the synthesis model (`gpt-5.6-terra`).
* Instead of truncating to a 2-sentence summary, it generates a **comprehensive Implementation Plan & Architectural Blueprint**:
  * Architectural Overview
  * UI/UX Design System & Color Palette
  * Component & File Breakdown
  * Responsive & Accessibility Features
  * Live Preview & Verification Links

---

## 6. Complete Tool Catalog Under the Hood

| Tool Name | Risk Level | Purpose & Behavior |
|---|---|---|
| `sandbox_write` | Medium | Writes complete, unminified files directly to `/tmp/sandbox_{conversation_id}/data/`. Syncs deltas to Cloudflare R2. |
| `sandbox_edit` | Medium | Applies targeted regex or line-replacement edits to existing sandbox files without rewriting the entire file. |
| `sandbox_read` | Low | Reads the content of any file in the sandbox workspace to verify syntax or answer user questions. |
| `sandbox_ls` | Low | Lists all files and directory trees in the persistent workspace. |
| `terminal` / `execute_code` | High | Executes shell/bash scripts, Python, or Node.js in the sandbox with execution timeouts and safety filtering. |
| `deploy_site` | High | Deploys static websites (`index.html`, `css/styles.css`, `js/main.js`) to instant public URLs (`/v1/sites/{slug}`). |
| `present_deliverable` | Low | Surfaces the repository deliverable card in the chat UI with preview button and file explorer. |
| `fetch_stock_image` | Low | Searches Pexels for curated high-resolution photography and downloads assets directly into the sandbox. |
| `generate_image` | High | Generates bespoke custom art via image models and saves it directly into the project directory. |
| `search_web` / `deep_research` | Low | Performs real-time Google search and parallel multi-query research for grounded data. |
| `ask_user_input` | Low | Pauses execution and asks the user for preferences or architectural choices. |

---

## 7. Packaging & Individual File Access Rules

The user experience for software deliverables follows strict rules:

### Rule 1: Zip ONLY for Multi-File Software
* **Single-file deliverable** (e.g. `calculator.html`, `script.py`, `analysis.csv`, `report.md`):
  * **NEVER zipped.**
  * Uploaded and presented directly with its own file card, preview, and download link.
* **Multi-file software project** (e.g. `index.html` + `css/styles.css` + `js/main.js` + `README.md`):
  * The entire directory is packaged into `project.zip` for bulk download convenience.

### Rule 2: Every File is Individually Demandable
* The user is **never forced** to download or unzip an archive to view or edit code.
* In multi-file projects:
  1. Every single file is uploaded with its own individual URL.
  2. Every file appears in the repository file tree in the Artifact Panel.
  3. If the user asks: *"Show me styles.css"* or *"Give me the JavaScript file"*, the agent immediately reads and presents that specific file directly using `sandbox_read`.

---

## 8. Summary of Fixes Applied in this Release

1. **Fixed "Refused to Connect" Error:**
   * Updated [gateway/pkg/middleware/security.go](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/gateway/pkg/middleware/security.go) to exempt `/v1/sites` from `X-Frame-Options: DENY` and permit framing via CSP `frame-ancestors`.
2. **Upgraded Agent Mode to Think-Mode Caliber:**
   * Updated [_STRUCTURED_PLANNER_SYSTEM in agent_planner.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/core/agent_planner.py) to mandate architectural implementation planning and rich modern aesthetics.
   * Updated synthesis instructions in [app/core/agent_task_manager.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/core/agent_task_manager.py) to deliver full implementation blueprints rather than abbreviated summaries.
   * Enhanced `ULTRA_IDENTITY` and `TASK_APPROACH` in [app/core/skills.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/core/skills.py).
3. **Enforced Zip & File Demandability Rules:**
   * Explicit contracts ensuring single-file deliverables are never zipped, multi-file projects receive a clean zip bundle, and all individual files remain directly demandable.
4. **Verified via Tests:**
   * All 51 unit tests in `test_ultra_upgrade.py` and `test_phase5_upgrade.py` passed with 100% success.
