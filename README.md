# Agent Ochuko

<!-- Cover image -->
<!-- ![Agent Ochuko](./AGENT ochuko(icon,favcon,img).png) -->

A production AI assistant platform built on Azure. Covers the full engineering surface: multi-model LLM orchestration, retrieval-augmented generation, streaming API design, event-driven background processing, role-based access control, and a multi-tenant data model -- deployed and actively used.

---

## What This Project Demonstrates

This is not a tutorial project or a wrapper around a single API call. It is a complete system that required making real architectural decisions under real constraints.

**AI Engineering:** Designing a routing layer that selects the right model for each turn, implementing hybrid retrieval-augmented generation across two AI providers, managing token budgets atomically across concurrent users, and handling the failure modes of streaming LLM APIs (partial responses, empty usage metadata, guardrail interruptions).

**Software Engineering:** A clean layered FastAPI backend with ASGI middleware for cross-cutting concerns, an SSE streaming API that persists to a database on completion, a queue-based async job system for long-running agent tasks, and a React frontend that handles progressive streaming, voice input, file uploads, and real-time job status subscriptions.

**Systems Architecture:** A multi-tier Azure deployment (Container Apps, Blob Storage, Azure Functions, Queue Storage, Key Vault, App Configuration), a PostgreSQL schema with Row Level Security enforced at the database layer, and an audit system that logs every access decision.

---

## Architecture

```
Browser (React + TypeScript)
    |
    |  HTTPS / Server-Sent Events
    v
Azure Static Website (Blob Storage)
    |
    |  REST API calls
    v
Azure Container Apps  --  FastAPI (Python)
    |
    |-- JWT validation middleware (every request)
    |-- Token budget middleware (chat requests only)
    |-- Rate limiting (SlowAPI)
    |
    |-- Model Router
    |       Think  -->  Azure OpenAI GPT-4o (deep reasoning)
    |       Solve  -->  Azure OpenAI GPT-4o-mini (fast synthesis)
    |       Discuss --> Azure OpenAI GPT-4o-nano (conversational)
    |
    |-- Hybrid Search
    |       Phase 1: Google Search grounding via Gemini 2.5 Flash
    |       Phase 2: Answer synthesis via Azure OpenAI with injected context
    |
    |-- Agent Job Dispatch --> Azure Queue Storage
    |
    v
Supabase (PostgreSQL + Auth)                  Azure Functions (Background Workers)
    Profiles, Conversations, Messages              Queue: OCR, Vision, Speech, Image Gen
    Token Budgets, Agent Quotas                    Timers: Budget reset, Usage aggregation,
    Audit Log, Blocked Identities                          Conversation archiving, Cleanup
    Row Level Security on all tables
```

---

## AI Engineering

### Multi-Model Routing

Each conversation turn is routed to one of three model tiers. The routing decision is made by a stateless `ModelRouter` that reads conversation context, the user-supplied mode hint, and feature flags from Azure App Configuration.

- **Think** (GPT-4o): Complex reasoning, analysis, code generation, structured output
- **Solve** (GPT-4o-mini): Fast synthesis, summarisation, tool-augmented responses
- **Discuss** (GPT-4o-nano): Conversational turns, quick questions, light context

The router applies a turn limit on the Discuss tier to prevent drift into complex territory, and falls back to Think if the deployment for a requested tier is unavailable. This makes the system resilient to partial outages without surfacing errors to users.

### Hybrid Retrieval-Augmented Generation

The hybrid search pathway runs in two phases:

**Phase 1 -- Retrieval:** The user query and conversation history are sent to Gemini 2.5 Flash with Google Search grounding enabled. This returns a factual answer grounded in live web content, plus source metadata (title, URL). The full conversation history is forwarded so follow-up queries like "who won" after a prior sports question resolve correctly.

**Phase 2 -- Synthesis:** The retrieved context and sources are injected into a system prompt alongside the conversation history, then passed to Azure OpenAI for synthesis. This keeps the final answer in the same model family as the rest of the platform and allows the same formatting, safety, and tone controls to apply.

This two-provider design means web grounding quality (Gemini + Google Search) and answer formatting quality (Azure OpenAI) are independently optimisable.

### Token Budget Management

Token budgets are enforced atomically using a Supabase RPC (`check_and_deduct_budget`) that wraps a `SELECT ... FOR UPDATE` to prevent race conditions under concurrent requests. The flow is:

1. Middleware estimates prompt tokens from the request body (characters / 4, minimum 50)
2. Atomic pre-deduction runs before the streaming response begins
3. After the stream completes, actual token counts are read from the API response
4. If the API returns zero counts (a known gap in the Azure OpenAI Responses API streaming), character-based estimates are computed from input messages and response content as a fallback
5. `reconcile_token_budget` RPC applies the diff between actual and estimated

This guarantees that token usage is always recorded and budget enforcement is always applied, even when the upstream API does not return usage metadata.

### Streaming API Design

The chat endpoint uses the Azure OpenAI Responses API in streaming mode and forwards events to the client as server-sent events. The generator function handles:

- Progressive delta accumulation into a full response string
- Detection of guardrail interruptions and content filter events
- Partial response persistence (if the stream is cut short, what was generated is still saved)
- Post-stream database writes and token reconciliation in a `finally`-equivalent block
- A structured `[DONE]` event that signals the client to stop rendering

### Prompt Engineering

System prompts are not hardcoded. They are stored in Azure App Configuration and loaded at request time, allowing prompt iteration without a redeploy. The prompts include:

- A hard instruction that prohibits the model from asking clarifying questions -- it continues when topics change
- Mode-specific persona and formatting instructions
- Dynamic injection of the current time, user locale, and search context

---

## Software Engineering

### Backend Structure

```
app/
  api/v1/endpoints/
    chat.py          -- Streaming chat, model routing, hybrid search dispatch
    search.py        -- Dedicated hybrid search endpoint
    admin.py         -- Admin REST API
    agents.py        -- Agent job dispatch
    audio.py         -- Speech transcription endpoint
    files.py         -- File upload and blob storage
    conversations.py -- Conversation CRUD
  core/
    jwt_validator.py -- JWT validation and user extraction
    model_router.py  -- Routing logic (stateless, testable)
  middleware/
    token_budget.py  -- ASGI middleware: budget check, pre-deduction
  services/
    admin_service.py     -- Admin data layer
    supabase_admin.py    -- Service role Supabase client
```

The middleware stack runs in order on every request. `token_budget.py` uses `BaseHTTPMiddleware` from Starlette and caches the `ensure_budget_row` RPC call per user per day using a thread-safe in-memory dictionary -- avoiding a database round trip on every request once the row is confirmed to exist.

### Database Access Pattern

All user-facing reads go through the Supabase anon key with Row Level Security enforced at the PostgreSQL level. Server-side writes (message persistence, token reconciliation, audit logging) use the service role key exclusively from the backend and functions -- never from the browser. The admin panel uses a separately issued short-lived admin JWT.

### Async Job Architecture

Long-running agent tasks (OCR, vision analysis, image generation) are non-blocking. The API dispatches a job record to Azure Queue Storage and returns a job ID immediately. The Azure Functions queue worker picks it up, processes it, updates the `jobs` table with status and result, and publishes a Supabase realtime event. The frontend subscribes to that event via a Supabase channel and updates the UI when the job completes.

This pattern keeps API response times predictable regardless of how long the underlying model call takes.

### Error Handling

The system is designed to degrade gracefully:

- If Google Search grounding fails, the chat falls back to Azure OpenAI with a note that live search was unavailable
- If the `reconcile_token_budget` RPC fails, a read-modify-write fallback applies the correction directly
- If a model tier deployment is unavailable, the router tries the next tier before returning an error
- If Supabase is unavailable for budget checks, the middleware fails open rather than blocking all users
- If the Azure Cost Management API is unavailable, the admin panel falls back to estimating cost from the token database

### Frontend Architecture

The frontend is a single-page React application with no server-side rendering requirement. Key decisions:

- Streaming is handled by reading from a `ReadableStream` on the fetch response body, parsing SSE events line by line, and appending deltas to a React state string -- no third-party streaming library
- Conversation state is persisted client-side in sessionStorage as a cache with a Supabase database as the source of truth
- Real-time job status is received via Supabase channel subscriptions rather than polling
- The voice dictation feature uses the browser Web Speech API directly, appending interim and final transcripts to the active input field without a backend round trip

---

## Systems Architecture

### Deployment Topology

| Component | Azure Service | Scaling |
|-----------|--------------|---------|
| Backend API | Container Apps (Consumption) | 0 to 10 replicas, HTTP-triggered |
| Frontend | Blob Storage Static Website | CDN-backed, no compute |
| Background Workers | Azure Functions (Consumption) | Event-triggered, scales to zero |
| Job Queue | Azure Queue Storage | Durable, at-least-once delivery |
| File Storage | Azure Blob Storage | Separate container per type |
| Secrets | Azure Key Vault | Referenced by managed identity |
| Feature Flags | Azure App Configuration | Hot-reloadable without redeploy |
| Observability | Azure Monitor + OpenTelemetry | Distributed traces and logs |

### Database Schema Design

The schema separates concerns cleanly. Conversations hold no message content -- they are a reference and counter. Messages hold content, token counts, model used, and routing metadata. Token budgets are keyed on `(user_id, period)` where period is a daily date string in WAT (West Africa Time), ensuring budget resets align with the user's timezone.

The blocked identities table is keyed on the Google OAuth subject ID, not the Supabase user ID. This means a blocked person cannot bypass the block by deleting their account and re-registering, because their Google identity remains the same.

The audit log is append-only. Nothing in the application deletes from it.

### Security Model

- All endpoints require a valid Supabase JWT (HS256, verified against the project JWT secret)
- Admin endpoints additionally require `app_metadata.role` to be `admin` or `superadmin`
- User suspension and blocklist checks run before any AI call is made
- Rate limiting is applied per IP at the API level (SlowAPI)
- CORS is configured to allow only the production frontend origin
- No credentials are stored in the Docker image or frontend bundle; secrets are resolved at runtime from Key Vault

---

## Data Model

| Table | Key Columns |
|-------|-------------|
| `profiles` | id, display_name, role, is_active, google_sub, last_seen |
| `conversations` | id, user_id, mode, message_count, is_archived, created_at |
| `messages` | id, conversation_id, role, content, model, tokens_input, tokens_output, routing_mode |
| `token_budgets` | user_id, period, tokens_used, budget_limit |
| `agent_quotas` | user_id, period, ocr_pages_used, vision_calls_used, speech_seconds_used, image_gen_used |
| `blocked_identities` | google_sub, blocked_by, reason, created_at |
| `audit_log` | user_id, action, resource_type, resource_id, policy_decision, metadata, created_at |
| `admin_settings` | key, value, updated_by, updated_at |
| `jobs` | id, type, status, result, user_id, created_at |
| `generated_files` | id, job_id, blob_url, filename, size_bytes |
| `usage_stats` | user_id, hour, tokens_input, tokens_output, model |

---

## Stack Summary

| Layer | Technology |
|-------|-----------|
| Backend runtime | Python 3.12, FastAPI, Uvicorn |
| AI providers | Azure OpenAI, Google Gemini 2.5 Flash, Hugging Face FLUX |
| Database | Supabase (PostgreSQL 15), Row Level Security, Supabase Auth |
| Background jobs | Azure Functions v2 (Python), Azure Queue Storage |
| Frontend | React 18, TypeScript, Vite |
| Container | Docker, Azure Container Apps |
| Storage | Azure Blob Storage |
| Secrets | Azure Key Vault |
| Config | Azure App Configuration |
| Observability | Azure Monitor, OpenTelemetry |
| Auth | Google OAuth 2.0, Supabase Auth, JWT (HS256) |
| CI/CD | GitHub Actions (four path-scoped workflows) |

---

## Running Locally

**Backend:**

```bash
cd agent-ochuko/backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Requires `.env` with Azure OpenAI, Supabase, Google GenAI, and Azure service credentials.

**Frontend:**

```bash
cd agent-ochuko/frontend
npm install && npm run dev
```

Requires `.env.local` with `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`.

**Azure Functions:**

```bash
cd agent-ochuko/functions
func start
```

Requires `local.settings.json` with Azure Storage and Supabase credentials. Azurite can be used for local queue and blob emulation.

**Full local deploy (Docker + Azure):**

```powershell
.\agent-ochuko\infra\build\deploy_local.ps1
```

Builds the Docker image, pushes to Docker Hub, updates the Azure Container App, builds the frontend, and uploads to Azure Blob Storage.
