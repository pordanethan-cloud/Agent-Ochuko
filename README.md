# Agent Ochuko: Enterprise Autonomous AI System & Scalable System-Auth Platform

[![Architecture Baseline](https://img.shields.io/badge/System_Architecture-Enterprise_Production-blue.svg)](https://azure.microsoft.com)
[![Deployment Pipeline](https://img.shields.io/badge/Azure_Container_Apps-Active-success.svg)](https://azure.microsoft.com/en-us/products/container-apps)
[![Security & Auth](https://img.shields.io/badge/Auth_Security-Zero_Trust_RLS-emerald.svg)](https://supabase.com)
[![Test Suite](https://img.shields.io/badge/Test_Suite-17%2F17_Passing-brightgreen.svg)](#system-verification--reliability)

Agent Ochuko is a production-grade autonomous AI engine and cloud system architecture engineered for high-availability enterprise applications. Built on Microsoft Azure, FastAPI, and React/TypeScript, the platform demonstrates system-level security, resilient multi-agent orchestration, stateless containerized code execution, and high-concurrency event-driven processing.

---

## Architecture Overview

```
                          ┌───────────────────────────────────────────────────────────┐
                          │         Client Layer: Single Page React (Vite)            │
                          │   Linear Glass HUD • Progressive SSE • Realtime Sync      │
                          └─────────────────────────────┬─────────────────────────────┘
                                                        │ HTTPS / SSE
                                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  Azure Infrastructure Boundary                                           │
│                                                                                                          │
│   ┌────────────────────────────────┐         ┌───────────────────────────────────────────────────────┐   │
│   │ Azure Static Web ($web Blob)   │         │ Azure Container Apps (FastAPI API Core)              │   │
│   └────────────────────────────────┘         │                                                       │   │
│                                              │  ┌─────────────────────────────────────────────────┐  │   │
│                                              │  │ JWT Auth & Token Budget Middleware Stack         │  │   │
│                                              │  └────────────────────────┬────────────────────────┘  │   │
│                                              │                           │                           │   │
│                                              │  ┌────────────────────────▼────────────────────────┐  │   │
│                                              │  │ Autonomous OODA Loop & ReWOO Execution Engine   │  │   │
│                                              │  │  - Observe/Orient: Multi-Model Fallback Router │  │   │
│                                              │  │  - Decide/Act: ReWOO Planner & Skill Store    │  │   │
│                                              │  │  - Guardrails: CircuitBreaker & Reflexion     │  │   │
│                                              │  └────────────────────────┬────────────────────────┘  │   │
│                                              │                           │                           │   │
│                                              │  ┌────────────────────────▼────────────────────────┐  │   │
│                                              │  │ Code & Document Sandbox (PyMuPDF/Pillow/AST)    │  │   │
│                                              │  └─────────────────────────────────────────────────┘  │   │
│                                              └───────────────────────────┬───────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┼───────────────────────────────┘
                                                                           │
               ┌───────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────┐
               ▼                                                           ▼                                                           ▼
┌───────────────────────────────┐                       ┌───────────────────────────────┐                       ┌───────────────────────────────┐
│ Database & Security Layer     │                       │ Hybrid Cloud Storage Layer    │                       │ Async Processing & Worker     │
│  - Supabase (PostgreSQL 15)   │                       │  - Cloudflare R2 (Hot Cache)  │                       │  - Azure Queue Storage        │
│  - Row Level Security (RLS)   │                       │  - User Google Drive Sync     │                       │  - Azure Functions v2 Workers │
│  - Azure Key Vault Isolation  │                       │  - Stateless Container Data   │                       │  - Realtime SSE & Webhooks    │
└───────────────────────────────┘                       └───────────────────────────────┘                       └───────────────────────────────┘
```

---

## Key Architectural Capabilities & Production Engineering

### 1. Autonomous Agent Execution Loop (OODA & ReWOO)
The engine executes complex multi-turn tasks using an explicit **Observe-Orient-Decide-Act (OODA)** state machine combined with **ReWOO (Reasoning Without Observation)** DAG planning:
- **Dynamic Action Budgets**: Enforces strict step quotas per request cycle to prevent infinite tool loops and unbudgeted API consumption.
- **Forced Final Step Synthesis Guard**: When approaching turn limits (`max_iterations - 1`), the engine automatically forces `"tool_choice": "none"`, guaranteeing structured markdown response completion without dropping output mid-stream.
- **Reflexion Self-Correction Engine**: Intercepts tool execution errors, feeds execution trace critique back into the agent context, and dynamically attempts alternative execution strategies.

### 2. Enterprise Resilience & Safety Controls
- **Circuit Breakers (`circuit_breaker.py`)**: Monitored turn execution bounds that trip immediately upon detecting repeating error patterns or resource threshold violations.
- **AST & Header Verification Gates (`verification_gates.py`)**: Programmatically validates Python code syntax via Abstract Syntax Trees before sandbox invocation, and enforces ZIP magic-byte header validation on generated `.docx` and `.pdf` files.
- **Prompt Injection Defense (`prompt_defense.py`)**: Scans incoming multi-modal inputs for prompt extraction attempts and isolates untrusted data blocks before feeding to LLM routing layers.
- **Safety Refusal Interceptors**: Captures upstream model content-safety overrides, strips raw error stack traces, and gracefully degrades to structured policy notifications.

### 3. Multi-Model Intelligent Fallback Router
The platform implements a multi-tiered LLM orchestration model:
- **Tier 1 (Think)**: High-capacity reasoning engines (`gpt-4o`, `gemini-3.5-pro`) for complex architectural analysis, code generation, and multi-file document manipulation.
- **Tier 2 (Solve)**: Low-latency synthesis engines (`gpt-4o-mini`, `gemini-2.5-flash`) for real-time web grounding and tool execution.
- **Tier 3 (Discuss & Audit)**: High-speed lightweight models (`gpt-5.4-nano`) for satisfaction auditing, intent classification, and conversational flow.
- **Automatic Fallback Routing**: If an upstream model endpoint encounters rate limits or availability drops, requests automatically cascade to redundant backup providers without interrupting user sessions.

### 4. Stateless Container Sandboxing & Hybrid Storage Sync
- **Code & File Isolation**: Code executions run in isolated sandbox paths (`/tmp/sandbox_{conversation_id}/`) segregated into script (`src/`) and data (`data/`) directories to enforce clean execution boundaries.
- **Document Processing Pipeline (`document_processor.py`)**: Programmatically processes binary Word (`.docx`) and PDF documents, extracts embedded vector/raster signatures via PyMuPDF (`fitz`), and overlays letterheads and signatory blocks.
- **Dual Cloud Sync**: Assets uploaded or generated by the agent are cached in Cloudflare R2 and asynchronously mirrored to user-hosted Google Drive accounts via OAuth 2.0 refresh token persistence.

### 5. High-Concurrency System-Auth & Observability
- **Zero-Trust JWT Auth**: Every request is validated against Supabase Auth (HS256 JWT tokens) with database-enforced Row Level Security (RLS).
- **Token Budget Middleware**: Atomic token tracking via PostgreSQL stored procedures (`check_and_deduct_budget`) with `SELECT ... FOR UPDATE` locks to eliminate race conditions under high concurrent request loads.
- **OpenTelemetry Instrumentation (`telemetry.py`)**: End-to-end GenAI span tracing integrated with Azure Monitor for request latencies, token consumption metrics, and tool execution success rates.

---

## Production Deployment Topology

The system is deployed using a fully automated infrastructure pipeline (`infra/build/deploy_local.ps1`):

| Layer | Component | Hosting Infrastructure | Security & Isolation |
|---|---|---|---|
| **API Core** | FastAPI Python 3.11 ASGI | Azure Container Apps (`agent-ochuko-api`) | Non-root container, Azure Managed Identity |
| **Frontend** | React + TypeScript + Vite | Azure Blob Storage (`$web`) Static Site | CDN distribution, HTTPS only, strict CORS |
| **Workers** | Azure Functions v2 | Azure Event-Driven Serverless | Queue-triggered scaling, stateless execution |
| **Database** | PostgreSQL 15 | Supabase Cloud | Database-level Row Level Security (RLS) |
| **Secrets** | Credential Store | Azure Key Vault & App Config | Zero plain-text secrets in source or containers |
| **Registry** | Container Registry | Docker Hub (`ochair1/agent-ochuko-api:latest`) | Multi-arch linux/amd64 provenance build |

---

## System Verification & Reliability

The platform undergoes automated unit, integration, and syntax verification prior to production deployment:

```bash
# Execute full backend integration and architecture test suite
cd agent-ochuko/backend
python -m pytest tests/test_document_pipeline.py tests/test_agent_architecture.py tests/test_model_router.py
```

### Verified Test Matrix (17/17 Passed)
- `test_full_document_processing_pipeline`: PDF signature extraction, DOCX signatory replacement, and output ZIP header verification.
- `test_agent_architecture`: OODA loop state machine, CircuitBreaker threshold enforcement, ReWOO DAG execution, and AST verification gates.
- `test_model_router`: Multi-tier fallback routing and prompt token budget pre-deductions.

```bash
# Verify frontend TypeScript compilation and production bundle
cd agent-ochuko/frontend
npx tsc --noEmit
npm run build
```

---

## Release Baseline & Version Control

- **Stable Release Baseline**: [`STABLE`](./STABLE)
- **Git Release Tag**: `v1.0.0-stable`
- **Deployment Script**: [`infra/build/deploy_local.ps1`](./agent-ochuko/infra/build/deploy_local.ps1)

---

## Local Development Setup

### Backend API
```powershell
cd agent-ochuko/backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

### Frontend Dashboard
```powershell
cd agent-ochuko/frontend
npm run dev
```

### Production Deployment
```powershell
cd agent-ochuko/infra/build
powershell -ExecutionPolicy Bypass -File .\deploy_local.ps1
```
