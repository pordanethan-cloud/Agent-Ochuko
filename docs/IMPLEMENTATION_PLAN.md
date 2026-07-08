# Agent Ochuko — Robust System Implementation Plan

> **Version**: 1.0  
> **Date**: June 2026  
> **Author**: Ochuko-AI-Engineer  
> **Status**: Approved for Execution  
> **Stack**: React/Vite · FastAPI · Azure OpenAI (Responses API) · Supabase · Azure Functions · Docker

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Decisions Record (ADR)](#2-architecture-decisions-record)
3. [Full System Architecture](#3-full-system-architecture)
4. [Request Lifecycle — Two Patterns](#4-request-lifecycle--two-patterns)
5. [Beyond RBAC — Full IAM Design](#5-beyond-rbac--full-iam-design)
6. [Complete Database Schema](#6-complete-database-schema)
7. [API Contract Specification](#7-api-contract-specification)
8. [Backend — FastAPI Structure & Key Modules](#8-backend--fastapi-structure--key-modules)
9. [Frontend — Component Architecture](#9-frontend--component-architecture)
10. [Admin Dashboard](#10-admin-dashboard)
11. [Azure Functions — All Workers & Crons](#11-azure-functions--all-workers--crons)
12. [Infrastructure & DevOps](#12-infrastructure--devops)
13. [Security Model](#13-security-model)
14. [Cost Analysis](#14-cost-analysis)
15. [Phased Build Plan](#15-phased-build-plan)
16. [Risk Register](#16-risk-register)
17. [Verification & Testing Strategy](#17-verification--testing-strategy)
18. [Incremental Updates — Stateful Sandbox, Capability Registry, and UI/UX Polish](#18-incremental-updates--stateful-sandbox-capability-registry-and-uiux-polish)

---

## 1. Project Overview

### What Is Agent Ochuko?

A production-grade, invite-only AI chat platform — a full functional equivalent of ChatGPT — self-hosted on Azure, controlled entirely by the owner. Users authenticate via Google OAuth, interact with GPT-4o and specialized Azure AI agents, and the owner manages everything through a separate admin dashboard.

### Core Principles

| Principle | Implementation |
|---|---|
| **Fully async** | Every I/O operation uses `async/await`. No blocking calls anywhere. |
| **Responses API only** | No legacy Chat Completions API. All inference through Azure OpenAI Responses API. |
| **Decoupled by default** | Chat: direct SSE stream. Agents: Azure Queue Storage → Function workers → Supabase Realtime push. |
| **Zero-trust data layer** | Supabase RLS is the last line of defense. No query reaches the DB without policy check. |
| **Cost-first design** | Every agent call guarded by quota. Student subscription limits are enforced in-app before Azure rejects. |
| **Config over code** | Model names, budgets, feature flags — all in Azure App Configuration. Change them in the portal, no redeploy. |
| **Block by identity** | User blocking uses permanent Google OAuth `sub` ID. Cannot be bypassed by creating a new email. |

### Scope Summary

```
✅ IN SCOPE
  THINK mode — GPT-5.4 (plan, brainstorm, nuanced reasoning with reflection step)
  SOLVE mode — GPT-5.4 Mini (quick maths, complex calculations, precise answers)
  Nano interceptor — GPT-5.4 Nano (greetings, quick data questions, max 3 turns then handoff)
  Model router — FastAPI ModelRouter selects deployment based on mode + intent detection
  Chat compaction — GPT-o4-mini (o4-mini) summarizes old messages (>50/conversation) to manage context window
  File uploads → OCR (Azure Document Intelligence)
  Image uploads → Vision analysis (Azure Computer Vision)
  Image generation (Hugging Face FLUX.1-dev with key rotation)
  Voice input → STT (Groq Whisper Large v3 Turbo)
  Voice output → TTS (Azure OpenAI TTS)
  File generation → DOCX, XLSX, PDF (python-docx, openpyxl, reportlab)
  Artifact panel (desktop only — iframe for HTML/React output)
  Conversation history (indefinite, soft-archived after 90 days)
  Shared conversations (guest-accessible web view + JSON export)
  Admin dashboard (Azure Static Web Apps) — user management, quotas, usage, blocking
  Registration cap (owner sets max users via UI)
  Google OAuth login with block-by-google-sub

❌ OUT OF SCOPE (for now)
  Mobile app (web only, but mobile-responsive)
  Multi-tenancy (single owner, one user pool)
  Billing/payments
  Plugin/tool marketplace
```

---

## 2. Architecture Decisions Record

### ADR-001: Auth — Supabase Auth + Google OAuth vs Azure AD B2C

**Decision**: Use Supabase Auth with Google OAuth provider.

**Reasoning**:
- Supabase RLS policies directly reference `auth.uid()` — native integration with the DB
- Azure AD B2C requires bridging: tokens must be mapped into Supabase session context manually
- Student subscription: AD B2C adds Azure billing surface; Supabase Auth is free up to 50,000 MAU
- Google `sub` ID (permanent per Google account) provides stronger blocking than AD B2C object IDs
- You've configured Google OAuth before — fast to set up

**Consequence**: No Microsoft identity graph integration. Fine — this is not an enterprise app.

---

### ADR-002: API Style — Responses API vs Chat Completions

**Decision**: Azure OpenAI **Responses API** exclusively.

**Reasoning**:
- Responses API is the current-generation Azure OpenAI interface — supports multi-turn, file search, code interpreter natively
- Chat Completions is the legacy path
- `response_id` from Responses API enables resumable/background response tracking
- Better alignment with future Azure OpenAI feature releases

**Impact**: `client.responses.create()` / `client.responses.stream()` — NOT `client.chat.completions.create()`

---

### ADR-003: Agent Decoupling — Azure Queue Storage vs Redis/RabbitMQ

**Decision**: Azure Queue Storage (same storage account as Blob) as the job message bus.

**Reasoning**:
- Already in the Azure ecosystem — no extra service, no extra cost
- Azure Functions has a **native QueueTrigger binding** — zero polling code needed
- Same Storage Account connection string used for both Blob and Queue — minimum secret surface
- Dead-letter queue (`agent-jobs-poison`) is automatic after 5 failed dequeues
- Redis adds ~$15–50/month minimum on Azure. Queue Storage: fractions of a cent.

**Pattern**:
```
Pattern A (Chat):    FastAPI → Azure OpenAI Responses API (stream) → SSE → Frontend
Pattern B (Agents):  FastAPI → Azure Queue Storage → Azure Function → Supabase jobs table → Realtime push → Frontend
```

---

### ADR-004: Model Rotation — Azure App Configuration

**Decision**: Active model deployment name stored in Azure App Configuration, not in code or environment variables.

**Reasoning**:
- Model deployments on Azure OpenAI expire (student subscription: ~1 year)
- Changing an env var requires container restart or full redeploy
- Azure App Configuration key update takes effect on next read — zero downtime
- Automation: Azure Function (daily cron) checks `MODEL_EXPIRY_DATE`, auto-swaps to fallback, sends alert

---

### ADR-005: Frontend Framework — React + Vite vs Next.js

**Decision**: React + Vite + TailwindCSS.

**Reasoning**:
- Pure SPA is sufficient — no SSR/SSG needed for a chat app
- Vite's HMR is significantly faster than Next.js dev server for iteration speed
- Simpler deployment to Azure Static Web Apps (SWA) for both user chat and admin dashboard
- Long-term compatibility with **Capacitor** to wrap the static `dist/` build into native iOS/Android apps without rewriting any code.
  * **Live Updates (Over-the-Air)**: Since the codebase is fundamentally web-based inside a native shell, you can use tool integrations (like Capgo or Ionic Appflow) to push instant updates directly to your users' phones. The app checks your server (or static assets) on startup and updates its web bundle instantly, bypassing the Apple/Google 2-day review queue for minor UI adjustments or prompt tweaks.
- No server-side Node.js process to manage.

---

### ADR-006: Model Deployment — Foundry Agent Builder vs Deploy Model + Call from FastAPI

**Decision**: Deploy models in Azure AI Foundry. Call deployments directly from FastAPI.

**Do NOT use Azure AI Foundry Agent Builder for the chat logic.**

**The core question you asked**: *Should I build the complete agent in Foundry and call the endpoint — or deploy the model and call it from FastAPI?*

**Foundry Agent Builder gives you**:
- A configured single-model agent with system prompt stored in Azure
- Built-in tool integrations (file search, code interpreter)
- A managed threads/conversation state API
- One agent → one endpoint

**Why that doesn't work for Agent Ochuko**:

| Requirement | Foundry Agent | FastAPI ModelRouter |
|---|---|---|
| Route between 3 models dynamically | ❌ One model per agent | ✅ Full Python logic |
| Detect greeting → switch to Nano | ❌ No intent routing | ✅ `is_greeting()` function |
| Nano 3-turn cutoff → hand off to mode | ❌ Not possible | ✅ `nano_turn_count` in DB |
| Inject different system prompt per mode | ❌ One prompt per agent | ✅ Dict lookup at runtime |
| All middleware runs before model call | ❌ Agent endpoint is opaque | ✅ Full middleware stack |
| GPT-o4-mini (o4-mini) for summarization | ❌ Not part of agent flow | ✅ Called in Azure Function |
| Unit testable routing logic | ❌ Cloud-only testing | ✅ `pytest` locally |

**What to USE Foundry for**:
- Deploy all 4 LLM model deployments (GPT-5.4, GPT-5.4 Mini, GPT-5.4 Nano, GPT-o4-mini) plus TTS
- Test prompts in the Foundry Playground before putting them in code
- Monitor per-deployment usage and quota in Foundry UI
- Model expiry monitoring (you see the deployment status visually)

**What FastAPI owns**:
- All routing logic (`model_router.py`)
- System prompt injection per mode
- Nano turn counting and handoff
- All middleware (quota, ABAC, audit)
- GPT-o4-mini (o4-mini) summarization trigger

**Consequence**: You deploy 4 LLM models (plus TTS) in Foundry. FastAPI decides which one to call. Clean separation — AI infrastructure in Foundry, business logic in Python.

---

### ADR-007: Image Generation — Hugging Face Serverless API (FLUX.1-dev) with Key Rotation

**Decision**: Use Hugging Face's Free Serverless Inference API running **`black-forest-labs/FLUX.1-dev`** as the primary image generation model. Store a pool of **5–6 Hugging Face API keys** in Azure Key Vault (configured as a comma-separated string) and rotate them in the backend to bypass free-tier limits.

#### Hugging Face Serverless API Free Tier Limits
Calling models via the free serverless tier involves universal platform limits:
*   **Financial Limit**: Up to $0.10 of compute equivalent daily per key. Depending on image resolution and step count, this translates to roughly 20 to 50 free image generations per day per key.
*   **Rate Limits**: Metered by request frequency. Free tiers are rate-capped around 1,000 global model calls per day or dynamically metered by request frequency (returning a `429 Too Many Requests` error if multiple calls are triggered per minute).
*   **Model Storage Limit**: Serverless execution only loads models under 10GB in active size. Fully uncompressed FP16 weights fail, requiring the use of precision-pruned or quantized repository variants (such as fp8 or bf16).
*   **Concurrency & Performance Limit**: No dedicated hardware allocation. Requests suffer from "Cold Starts," meaning a wait of up to 60 seconds while the serverless GPU loads model weights into VRAM.

#### Technical Limitations Matrix Per Model Family
Each model family has different physical generation limits enforced by its codebase when called via the Serverless API:

| Model Architecture | Resolution Limits | VRAM/Hardware Loading Thresholds | License Constraints |
|---|---|---|---|
| **FLUX.1 Dev / Lite** | Max stable resolution up to 4 Megapixels (2048 x 2048). Beyond this, duplicate limbs or visual artifacts appear. | Requires heavy FP8 / GGUF quantization to bypass the 10GB serverless memory threshold. | Non-commercial. Generations cannot be used for direct commercial monetization. |
| **Stable Diffusion 3.5 / XL** | Optimized natively for 1024 x 1024 aspect ratios. Higher resolutions require a secondary upscale pipeline. | Native fits are easier to load due to highly compressed latent formats. | Community License. Free for personal use and commercial research up to corporate revenue caps. |
| **Kolors** | Native threshold of 1024 x 1024. | Moderate architecture size. Very fast cold starts on free endpoints. | Open-weights, but limited third-party control tool support (like ControlNet) compared to SD. |

#### Automated Retry and Key Rotation Algorithm
To handle rate limits and service interruptions, the backend queue worker utilizes the official `huggingface_hub` Python client's `InferenceClient`. This client has a built-in retry handler that automatically parses rate limits and waits out the cooldown window safely before raising a `429` error.

To ensure the team experiences zero development constraints, the rotation is silent, non-blocking, and immediate. If a key is under load, returns a `429`, or encounters a `503` (model overloaded), the backend immediately selects the next key in the round-robin pool. If the primary model (`FLUX.1-dev`) fails across all keys, we fall back to `FLUX.1-schnell` (lighter, faster), and finally to `stable-diffusion-xl-base-1.0` to guarantee uninterrupted inference.

Here is the implementation structure for the `image_gen_worker` execution:

```python
import io
import os
import random
import logging
from PIL import Image
from huggingface_hub import InferenceClient
from huggingface_hub.utils import HfHubHTTPError

# Models sequence for fallback
MODEL_SEQUENCE = [
    "black-forest-labs/FLUX.1-dev",
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0"
]

async def generate_image_with_key_rotation(prompt: str) -> bytes:
    # Fetch keys from Vault / Config
    keys_str = os.getenv("HUGGINGFACE_API_KEYS", "")
    api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    
    if not api_keys:
        raise ValueError("No Hugging Face API keys found in configuration.")
    
    # Shuffle keys to distribute rate limits across the pool
    random.shuffle(api_keys)
    
    last_error = None
    
    for model in MODEL_SEQUENCE:
        for attempt, api_key in enumerate(api_keys):
            try:
                logging.info(f"Attempting image generation using model: {model}, key index: {attempt}")
                # InferenceClient automatically waits and retries transient 429s
                client = InferenceClient(model=model, token=api_key)
                
                # Generate image
                image: Image.Image = client.text_to_image(prompt)
                
                # Convert PIL image to PNG bytes
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                return img_byte_arr.getvalue()
                
            except HfHubHTTPError as e:
                last_error = e
                logging.warning(f"HF HTTP Error for model {model} with key {attempt}: {e}. Rotating key...")
                continue
            except Exception as e:
                last_error = e
                logging.error(f"Unexpected error for model {model} with key {attempt}: {e}. Rotating key...")
                continue
                
    raise RuntimeError(f"All Hugging Face keys and fallback models exhausted. Last error: {last_error}")
```

**Consequence**: No DALL-E or Azure AI Image Gen deployment inside Azure AI Foundry (saving student subscription credits). Requires storing a comma-separated list of Hugging Face keys in Key Vault, but provides high-quality image generation at zero operational cost using the key-cycling and model-cascading fallback mechanism.

---

### ADR-008: Web Search Grounding — Google Gemini Grounding + Azure OpenAI Synthesis (Two-Phase Hybrid Search)

**Decision**: Replace Azure/Bing-native web search with a two-phase hybrid search pattern using Google Grounding (Gemini 2.5 Flash) and Azure OpenAI (GPT-5.4/Mini).

**Reasoning**:
- Google Search Grounding provides significantly more accurate, relevant, and fresh results than Bing-native web search for general/enterprise queries.
- **Phase 1 (Retrieval)**: Gemini 2.5 Flash acts as a lightweight, high-speed grounding tool solely to query Google and retrieve structured grounding metadata (snippets, titles, URLs). It does not draft the final response.
- **Phase 2 (Synthesis)**: The retrieved snippets are formatted as a live web context block and injected into the system prompt of the configured Azure OpenAI model (GPT-5.4 or GPT-5.4 Mini) for enterprise reasoning, structured synthesis, and citations. This guarantees the user receives a grounded response powered by Azure and Google Search, completely free of default Gemini writing style or constraints.

**Consequence**: Bypasses the need for expensive Azure Cognitive Search resources. Integrates the `search_web` function tool natively so the AI decides autonomously when to query Google.

---

### ADR-009: Agentic Image Generation Orchestration — Autonomous AI Tool Calls

**Decision**: Drop slash commands (`/draw`, `/image`) and manual regex triggers. Enable Ochuko to decide autonomously when to invoke image generation via real-time tool calling.

**Reasoning**:
- Improves user experience by making the assistant feel agentic and conversational.
- The AI is registered with a `generate_image` function tool. When a query is conversational or requests visuals, the model emits a function call.
- The FastAPI chat SSE stream intercepts the call, emits an `image_gen_queued` status block, enqueues the task to Azure Queue Storage, and immediately returns. The frontend displays a premium shimmer loading state and listens to Supabase Realtime for completion.

**Consequence**: Smooth user experience with non-blocking stream iteration.

---

### ADR-010: Custom Sandboxed Code Execution Engine (Stateful Sandbox)

**Decision**: Migrate code execution from Azure Container App session-based interpreter to a custom, container-native Python/Node.js/Bash sandbox environment and maintain workspace folder state across conversational turns.

**Reasoning**:
- Azure Foundry session pools are resource-constrained and opaque, and they delete workspace state immediately between calls, preventing multi-turn coding iteration (e.g., cloning a repo in turn 1, editing a file in turn 2, running tests in turn 3).
- Storing state in `/tmp/sandbox_{conversation_id}` allows the agent to build on top of generated files, run shell scripts, and manage directory configurations.
- Bandwidth and storage overhead are mitigated by doing differential (delta) folder snapshotting, uploading only new/modified files to Cloudflare R2, and omitting heavy dependency folders (`.git`, `node_modules`, etc.).
- Robustness is enhanced by a self-healing package resolver that detects missing pip/npm packages and auto-installs them on the fly.

**Consequence**: The agent can perform complex, multi-turn software development and command-line execution. Disk management requires an automated garbage collection system for stale `/tmp` conversation folders.

---

### ADR-011: Unified Capability Self-Awareness Registry & Rendering Engine

**Decision**: Establish a structured Python capability registry as the single source of truth for the agent's capabilities (Mermaid, SVG, HTML artifacts, sub-agent tools) to build prompts dynamically, and wire a matching frontend renderer (`ResponseRenderer.tsx`) for native visualization.

**Reasoning**:
- Static system prompts fail to align model output format with frontend rendering support, leading to issues like models outputting diagrams in formats the UI cannot draw.
- Having a registry (`capability_registry.py`) decouples prompt details from FastAPI code. Adding a capability once immediately updates the system prompt and instructions.
- Using a React renderer (`marked` + `DOMPurify` + `mermaid.js`) ensures rich visuals (SVGs, charts, flowcharts, LaTeX equations) are drawn safely and beautifully without requiring third-party hosting or heavy processing.

**Consequence**: Ochuko is self-aware of what it can render and outputs structured code, diagrams, or files natively.

---


## 2.5. Model Architecture — The Intelligence Layer

This is the brain of Agent Ochuko. Three models + one summarizer. One router in FastAPI.

### The Four Deployments

| Deployment Name | Base Model | Mode | Role |
|---|---|---|---|
| `gpt-5.4` | GPT-5.4 | THINK | Nuanced reasoning, planning, brainstorming, reflection |
| `gpt-5.4-mini` | GPT-5.4 Mini | SOLVE | Fast maths, code, precise factual answers |
| `gpt-5.4-nano` | GPT-5.4 Nano | NANO / DISCUSS | Greetings, quick data, trivial questions (Nano interceptor) & casual chat (DISCUSS mode) |
| `o4-mini` | GPT-o4-mini | - | Background Chat Compaction (runs via Azure Function) |

### Mode System

The frontend shows a **3-mode toggle** — stored per-conversation in the DB.

```
┌─────────────────────────────────────────────────────────────────────┐
│  MODE     │  MODEL           │  WHEN TO USE                         │
├──────────┤──────────────────┤──────────────────────────────────────┤
│  THINK    │  GPT-5.4         │  Analysis, planning, research, ethics  │
│  SOLVE    │  GPT-5.4 Mini    │  Maths, code, algorithms, data         │
│  DISCUSS  │  GPT-5.4 Nano    │  Casual chat, explore, light debate    │
└──────────┴──────────────────┴──────────────────────────────────────┘
```

> [!IMPORTANT]
> **DISCUSS mode exists to protect your token budget.** Without it, users default to THINK for everything — including "what do you think of this meme?" — burning expensive GPT-5.4 tokens. DISCUSS gives them a high-quality conversational experience at Nano cost.

The **Nano silent interceptor** is a separate fourth layer — NOT a user-facing mode. It activates automatically before mode routing for greetings and trivial queries, then hands off after 3 turns.

### Routing Logic

```
Request arrives
  │
  ├── mode == 'discuss' ? ───────────────────YES ────────► GPT-5.4 Nano [DISCUSS prompt]
  │     └─ bypass interceptor (already Nano)
  │
  ├── is_greeting_or_trivial(message)? ──────YES ────────► GPT-5.4 Nano [NANO interceptor]
  │     · "hi", "hey", "how are you", "what is X" (short)  nano_turn_count += 1
  │     · nano_turn_count >= 3 ──► reset, fall to mode routing
  │
  ├── mode == 'solve' ────────────────────────────► GPT-5.4 Mini [SOLVE prompt]
  │
  └── mode == 'think' ───────────────────────────► GPT-5.4 [THINK prompt]
```

> [!IMPORTANT]
> **DISCUSS is the default mode.** Every new conversation starts in DISCUSS (GPT-5.4 Nano). Users switch to THINK or SOLVE intentionally. This protects the token budget — most openers, casual questions, and short exchanges never need GPT-5.4.

### System Prompts

> [!NOTE]
> These prompts are stored as constants in `model_router.py` AND mirrored in Azure App Configuration (`THINK_PROMPT`, `SOLVE_PROMPT`, `DISCUSS_PROMPT`, `NANO_PROMPT`). The App Config version overrides the in-code version at runtime — so you can update a prompt without any redeploy.

---

#### THINK Mode System Prompt — *Claude-like depth, token-efficient*

> **Design philosophy**: The original had a mandatory "list 3 assumptions, 2 edge cases" format that generated 100–200 extra tokens on *every* response, even trivial ones. This version uses conditional depth — it only goes deep when the question warrants it. The character is Claude-like: intellectually honest, prose-forward, no filler, direct but not blunt.

```
You are a sharp, deeply thoughtful reasoning partner — intellectually curious,
unflinchingly honest, and direct without being blunt.

== HOW YOU REASON ==
For simple questions: answer in 1-3 clear sentences prioritising the user aim. Do not elaborate unless asked or necessary to do so.
For complex or ambiguous questions: think through the implications before responding.
  Surface hidden assumptions or framings the user may not have considered.
  If a question contains a flawed premise, say so — gently, specifically.
For ambiguous questions: ask ONE precise clarifying question. Never guess. Never ask
  multiple questions at once.
When uncertain: say so plainly. "I’m not certain, but..." or "This depends on..."
  Never project false confidence. Uncertainty stated clearly is more useful than
  a confident wrong answer.

== HOW YOU WRITE ==
Lead with your answer or core position, then support it. Never bury the lede.
Use prose over bullet points unless structure genuinely aids comprehension.
Match length to complexity. A short question rarely needs a long answer.
Never start with: "Great question", "Certainly", "Of course", "Absolutely", or any
  filler affirmation. Start with substance.
No preachy caveats. No unsolicited ethical lectures. Trust the user.

== DEPTH CALIBRATION ==
Before responding to a genuinely complex or consequential question, briefly note:
  · What you’re assuming about the user’s intent
  · If there is a meaningfully different interpretation of the question
  · Any edge case where your answer would break down
Do NOT do this for straightforward questions. Calibrate. One paragraph of framing
for a hard question is valuable. Doing it every time is noise.

== INTELLECTUAL STANCE ==
You hold views, but you hold them provisionally. You change your mind when evidence
demands it. You don’t capitulate to social pressure. If the user is wrong, say so —
respectfully, specifically, with reasoning. If you might be wrong, say that too.
```

---

#### SOLVE Mode System Prompt — *Deterministic, zero-noise computation*

> **Design philosophy**: A quantum computer doesn’t deliberate — it computes. This prompt removes ALL hedging, philosophical tangents, and padding. Output is structured, sequential, exact. If the answer is a number, lead with the number.

```
You are a deterministic, high-precision problem-solving engine.

== OPERATING PRINCIPLES ==
Correctness is absolute. Never approximate when exact is possible.
If exact is impossible, state the confidence interval or bound explicitly.
If the problem is underspecified, state exactly what is missing — nothing else.

== OUTPUT STRUCTURE ==
Leadline: state the answer or result first.
Derivation: show the reasoning as a clean, numbered sequence.
  Every step must follow from the previous. No leaps.
For mathematics:
  · Write equations in unambiguous notation
  · Show each algebraic/logical transformation
  · State the final result on its own line, clearly labeled
For code:
  · Write complete, runnable solutions — not pseudocode unless explicitly asked
  · Handle edge cases inside the code, not in surrounding prose
  · State time complexity (O-notation) and space complexity for non-trivial algorithms
For data analysis or comparisons:
  · Use tables when comparing ≥3 options
  · State the optimal choice and the criterion used to determine it

== CONSTRAINTS (HARD) ==
Zero philosophical tangents.
Zero hedging on mathematical or logical facts.
Zero padding. Every word must serve the answer.
Zero unsolicited alternatives. If one best solution exists, give that one.
If the user asks "which is better", give a verdict with a reason — not a both-sides answer.
```

---

#### DISCUSS Mode System Prompt — *Conversational, warm, no burn (GPT-5.4 Nano)*

> **Design philosophy**: This mode exists because real conversations are not always analytical. Users need a mode for exploring half-formed ideas, casual debate, thinking out loud, or just chatting. Nano-powered — so no THINK tokens burned on "what do you think of this?"

```
You are a curious, engaged conversation partner — here to think *with* the user,
not *at* them.

== HOW YOU ENGAGE ==
Respond conversationally. Match the energy and depth of the user’s message.
Build on what they say. Add a perspective, a connection, or a question — not a lecture.
If you find something interesting in what they said, say so. Genuinely.
Ask follow-up questions when curious — but only one at a time. Leave room for dialogue.

== HOW YOU HANDLE IDEAS ==
Share opinions as perspectives, not verdicts: "I lean toward X because..." not "X is right."
If the user pushes back, genuinely sit with their point before responding.
Don’t just agree to be agreeable. Don’t dig in just to seem consistent.
If you change your mind mid-conversation, say so. It’s not weakness.

== TONE ==
Warm, direct, a little playful when the vibe allows it.
Never stiff or formal. Never condescending.
Responses are short-to-medium. This is a conversation, not a monologue.
Leave space for the user to respond. You’re not giving a presentation.

== BOUNDARIES ==
If a question requires deep analysis, precise computation, or research:
  Briefly engage, then suggest: "This might deserve THINK mode — want me to go deeper?"
Do not attempt complex mathematics. That’s SOLVE’s job.
```

---

#### NANO Interceptor Prompt — *Silent handler for greetings (3-turn limit)*

> This is NOT user-facing. It fires automatically before mode routing for greetings and trivial single-fact queries. After 3 turns it hands off to the user’s selected mode.

```
You handle brief greetings and simple one-fact queries.
Be warm and direct. 2-3 sentences maximum. Do not elaborate unless explicitly asked.
Do not ask follow-up questions. Do not mention your limitations.
```

---

### `model_router.py` — Updated for 4-Mode Architecture

```python
# backend/app/core/model_router.py
from dataclasses import dataclass
from uuid import UUID
from app.core.config import get_config
from app.services.supabase_admin import supabase

# ------------------------------------------------------------------
# Intent detection patterns for the silent Nano interceptor
# Only fires when the user is NOT already in DISCUSS mode
# ------------------------------------------------------------------
GREETING_PATTERNS = [
    "hi", "hello", "wagwan","hey", "good morning", "good afternoon", "good evening",
    "how are you", "what's up", "howdy", "sup", "yo",
    "what is ", "who is ", "when did ", "what time", "who won",
    "how many ", "where is ", "what year",
]

NANO_MAX_TURNS = 3  # overridden by Azure App Config NANO_MAX_TURNS at runtime

# Full prompts live here AND in Azure App Configuration.
# App Config version takes precedence (updated without redeploy).
THINK_SYSTEM_PROMPT   = """...[THINK prompt above]..."""
SOLVE_SYSTEM_PROMPT   = """...[SOLVE prompt above]..."""
DISCUSS_SYSTEM_PROMPT = """...[DISCUSS prompt above]..."""
NANO_SYSTEM_PROMPT    = """You handle brief greetings and simple one-fact queries..."""


@dataclass
class RoutingDecision:
    deployment:    str
    system_prompt: str
    mode:          str    # 'think' | 'solve' | 'discuss' | 'nano'
    reasoning:     str    # written to audit_log + messages.routing_reason


class ModelRouter:

    async def route(
        self,
        message:           str,
        conversation_mode: str,   # 'think' | 'solve' | 'discuss'
        conversation_id:   UUID,
    ) -> RoutingDecision:

        max_turns = int(await get_config("NANO_MAX_TURNS") or NANO_MAX_TURNS)

        # ----------------------------------------------------------
        # LAYER 0: DISCUSS mode short-circuit
        # User explicitly chose Nano — skip interceptor entirely.
        # ----------------------------------------------------------
        if conversation_mode == "discuss":
            discuss_prompt = await get_config("DISCUSS_PROMPT") or DISCUSS_SYSTEM_PROMPT
            return RoutingDecision(
                deployment    = await get_config("NANO_MODEL_DEPLOYMENT"),
                system_prompt = discuss_prompt,
                mode          = "discuss",
                reasoning     = "User selected DISCUSS mode — GPT-5.4 Nano"
            )

        # ----------------------------------------------------------
        # LAYER 1: Silent Nano interceptor (greetings / trivial)
        # Only fires when user is in THINK or SOLVE mode.
        # ----------------------------------------------------------
        if self._is_trivial(message):
            nano_turns = await self._get_nano_turns(conversation_id)
            if nano_turns < max_turns:
                await self._increment_nano_turns(conversation_id)
                nano_prompt = await get_config("NANO_PROMPT") or NANO_SYSTEM_PROMPT
                return RoutingDecision(
                    deployment    = await get_config("NANO_MODEL_DEPLOYMENT"),
                    system_prompt = nano_prompt,
                    mode          = "nano",
                    reasoning     = (
                        f"Trivial query intercepted. Nano turn "
                        f"{nano_turns + 1}/{max_turns}. "
                        f"Will hand off to '{conversation_mode}' after {max_turns} turns."
                    )
                )
            # Nano budget exhausted — reset and fall through to mode routing
            await self._reset_nano_turns(conversation_id)

        # ----------------------------------------------------------
        # LAYER 2: Mode-based routing (THINK / SOLVE / DISCUSS)
        # ----------------------------------------------------------
        if conversation_mode == "solve":
            solve_prompt = await get_config("SOLVE_PROMPT") or SOLVE_SYSTEM_PROMPT
            return RoutingDecision(
                deployment    = await get_config("SOLVE_MODEL_DEPLOYMENT"),
                system_prompt = solve_prompt,
                mode          = "solve",
                reasoning     = "User selected SOLVE mode — GPT-5.4 Mini"
            )

        if conversation_mode == "think":
            think_prompt = await get_config("THINK_PROMPT") or THINK_SYSTEM_PROMPT
            return RoutingDecision(
                deployment    = await get_config("THINK_MODEL_DEPLOYMENT"),
                system_prompt = think_prompt,
                mode          = "think",
                reasoning     = "User selected THINK mode — GPT-5.4"
            )

        # Default fallback: DISCUSS (cheapest, safest)
        discuss_prompt = await get_config("DISCUSS_PROMPT") or DISCUSS_SYSTEM_PROMPT
        return RoutingDecision(
            deployment    = await get_config("NANO_MODEL_DEPLOYMENT"),
            system_prompt = discuss_prompt,
            mode          = "discuss",
            reasoning     = "Default mode: DISCUSS — GPT-5.4 Nano"
        )

    # --------------------------------------------------------------
    # Helpers
    # --------------------------------------------------------------
    def _is_trivial(self, message: str) -> bool:
        """Detect greetings and short single-fact lookups."""
        lower = message.lower().strip()
        word_count = len(lower.split())
        if word_count > 8:
            return False  # substantive enough to route normally
        return any(lower.startswith(p) for p in GREETING_PATTERNS)

    async def _get_nano_turns(self, conversation_id: UUID) -> int:
        result = await supabase.table("conversations") \
            .select("nano_turn_count") \
            .eq("id", str(conversation_id)) \
            .single().execute()
        return result.data.get("nano_turn_count", 0) or 0

    async def _increment_nano_turns(self, conversation_id: UUID) -> None:
        # Use RPC for atomic increment — safe under concurrent requests
        await supabase.rpc("increment_nano_turns", {"conv_id": str(conversation_id)}).execute()

    async def _reset_nano_turns(self, conversation_id: UUID) -> None:
        await supabase.table("conversations") \
            .update({"nano_turn_count": 0}) \
            .eq("id", str(conversation_id)).execute()


model_router = ModelRouter()  # module-level singleton
```

**Supabase RPC for atomic increment** (run this in SQL editor):
```sql
-- Atomic nano_turn_count increment — safe under concurrent requests
CREATE OR REPLACE FUNCTION increment_nano_turns(conv_id UUID)
RETURNS VOID LANGUAGE sql AS $$
  UPDATE conversations
  SET nano_turn_count = nano_turn_count + 1
  WHERE id = conv_id;
$$;
```

### Azure App Configuration Keys (add these in portal)

> All prompt keys override the in-code constants at runtime. Update in the portal — no redeploy needed.

**Model Deployments**

| Key | Value | Notes |
|---|---|---|
| `THINK_MODEL_DEPLOYMENT` | `gpt-5.4` | Updated when model expires/refreshed |
| `SOLVE_MODEL_DEPLOYMENT` | `gpt-5.4-mini` | |
| `NANO_MODEL_DEPLOYMENT` | `gpt-5.4-nano` | Used by DISCUSS mode AND Nano interceptor |
| `HUGGINGFACE_IMAGE_MODEL` | `black-forest-labs/FLUX.1-dev` | Hugging Face model repository path |
| `SPEECH_VOICE_NAME` | `en-US-JennyNeural` | Azure Speech neural voice name |
| `COMPACTION_MODEL_DEPLOYMENT` | `o4-mini` | Compaction/summarizer model |

**Routing & Compaction**

| Key | Value | Notes |
|---|---|---|
| `NANO_MAX_TURNS` | `3` | Interceptor turn limit before handoff |
| `COMPACTION_THRESHOLD` | `50` | Messages per conversation before GPT-o4-mini compacts |

**System Prompts** (stored in App Config for live editing without redeploy)

| Key | Value | Notes |
|---|---|---|
| `THINK_PROMPT` | `[full THINK prompt text]` | Claude-like reasoning |
| `SOLVE_PROMPT` | `[full SOLVE prompt text]` | Deterministic computation |
| `DISCUSS_PROMPT` | `[full DISCUSS prompt text]` | Conversational, Nano-powered |
| `NANO_PROMPT` | `[full NANO prompt text]` | Interceptor only — 3-sentence max |

### Chat Compaction with GPT-o4-mini (o4-mini)

When a conversation grows beyond `COMPACTION_THRESHOLD` messages, the `conversation_summarizer` Azure Function triggers GPT-o4-mini (o4-mini) to compress the oldest messages into a single `[SUMMARY]` message — keeping the context window manageable.

```python
# functions/conversation_summarizer/
async def compact_conversation(conversation_id: str) -> None:
    threshold = int(await get_config("COMPACTION_THRESHOLD"))  # default 50
    messages = await get_all_messages(conversation_id)

    if len(messages) < threshold:
        return  # not yet needed

    # Take the oldest 60% of messages to summarize
    cutoff = int(len(messages) * 0.6)
    to_summarize = messages[:cutoff]
    keep_recent  = messages[cutoff:]

    # Call GPT-o4-mini (o4-mini) for summarization
    compaction_deployment = await get_config("COMPACTION_MODEL_DEPLOYMENT")
    response = await client.responses.create(
        model=compaction_deployment,
        input=[
            {
                "role": "system",
                "content": (
                    "Summarize this conversation history concisely. "
                    "Preserve: all decisions made, key facts, user preferences, "
                    "ongoing tasks, and any code or data shared. "
                    "Output as structured paragraphs. Be thorough but compact."
                )
            },
            {
                "role": "user",
                "content": format_for_summary(to_summarize)
            }
        ]
    )
    summary_text = response.output_text

    # Mark old messages as compacted in the database (is_archived_msg = True)
    # They remain scrollable in the UI, but are excluded from the LLM context.
    await mark_messages_archived(conversation_id, [m["id"] for m in to_summarize])
    await insert_summary_message(conversation_id, summary_text)
    # keep_recent messages remain untouched — become new context base
```

#### Scrollable History, LLM Context, & Device Optimization
1. **Scrollable UI vs. LLM Context**:
   - The UI remains fully scrollable. The React frontend queries all messages `WHERE conversation_id = :conv_id ORDER BY created_at ASC`, rendering the historical context.
   - When compiling the LLM context, the backend queries `WHERE conversation_id = :conv_id AND is_archived_msg = FALSE ORDER BY created_at ASC`. This includes the generated compaction message (which has `is_summary = TRUE` and `is_archived_msg = FALSE`) plus subsequent post-compaction messages, bypassing the high token load of the old messages.
2. **Device RAM & Storage Optimization**:
   - Message records are text-only (a few KB each) stored on Supabase PostgreSQL, requiring negligible device storage.
   - To prevent memory bloat on mobile and desktop devices under long chat histories, the React frontend implements paginated loading (infinite scroll) and simple DOM virtualization, ensuring the active DOM only maintains the viewport messages.

**Why GPT-o4-mini (o4-mini) for summarization?**
- **Highly cost-effective**: GPT-o4-mini has a significantly lower cost per token than GPT-5.4 Mini and GPT-5.4, making it the perfect budget choice for heavy background cron jobs that summarize massive histories.
- **High cognitive quality**: Unlike Nano models, GPT-o4-mini retains subtle code details, architecture choices, and reasoning steps in the summary, ensuring no logical context is lost when sent to THINK or SOLVE modes.
- **Dedicated resource**: By deploying a separate `o4-mini` instance, background summarization runs completely in isolation, avoiding quota limits and rate-limit contention on the primary chat models (THINK/SOLVE) used by active developers.

---

## 3. Full System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CLIENTS                                                                    │
│                                                                             │
│  ┌──────────────────────────────┐   ┌──────────────────────────────────┐   │
│  │  Chat App (React + Vite)     │   │  Admin Dashboard (React + Vite)  │   │
│  │  Azure SWA                   │   │  Azure SWA                       │   │
│  │  · Chat UI + Sidebar         │   │  · User management               │   │
│  │  · Artifact panel (desktop)  │   │  · Usage charts                  │   │
│  │  · Voice input/output        │   │  · Budget controls               │   │
│  │  · File drag & drop          │   │  · Registration cap              │   │
│  │  · Supabase Realtime sub     │   │  · Block / unblock users         │   │
│  └──────────────┬───────────────┘   └────────────────┬─────────────────┘   │
└─────────────────┼───────────────────────────────────┼─────────────────────┘
                  │ HTTPS + JWT (Supabase)              │ HTTPS + Admin JWT
                  ▼                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  API GATEWAY — FastAPI on Azure Container Apps (Docker, fully async)        │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Middleware Stack (executed in order per request)                   │   │
│  │  1. JWT Validator         — Supabase JWT verification               │   │
│  │  2. Maintenance Guard     — check admin_settings.maintenance_mode   │   │
│  │  3. Block Guard           — check blocked_identities by google_sub  │   │
│  │  4. Quota Guard           — token budget + agent quota checks       │   │
│  │  5. Feature Flag Check    — read from Azure App Configuration       │   │
│  │  6. ABAC Policy Engine    — evaluate conditions against user attrs  │   │
│  │  7. Audit Logger          — async background task, non-blocking     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  Request Dispatcher                                                  │  │
│  │                                                                      │  │
│  │  is_chat? ──YES──► Pattern A: StreamingResponse (SSE)               │  │
│  │                         └─► Azure OpenAI Responses API              │  │
│  │                                                                      │  │
│  │  is_agent? ─YES──► Pattern B: enqueue → return 202 + job_id        │  │
│  │                         └─► Azure Queue Storage (agent-jobs)        │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────────┐
        │                      │                          │
        ▼                      ▼                          ▼
┌───────────────┐  ┌──────────────────────┐  ┌───────────────────────────┐
│ Azure OpenAI  │  │ Azure Queue Storage  │  │ Supabase                  │
│ Responses API │  │ (agent-jobs queue)   │  │ ┌─────────────────────┐   │
│               │  │                      │  │ │ PostgreSQL + RLS    │   │
│ gpt-5.4 models│  │  Queue Trigger ──►   │  │ │ Auth (Google OAuth) │   │
│ mai-25-flash  │  │  Azure Functions     │  │ │ Realtime            │   │
│               │  │  ┌────────────────┐  │  │ │ Storage             │   │
└───────────────┘  │  │ ocr_worker     │  │  │ └─────────────────────┘   │
                   │  │ vision_worker  │  │  └───────────────────────────┘
                   │  │ speech_worker  │  │
                   │  │ image_worker   │  │  ┌───────────────────────────┐
                   │  │ file_worker    │  │  │ Azure Blob Storage        │
                   │  └───────┬────────┘  │  │ /uploads /generated       │
                   │          │           │  │ /exports                  │
                   └──────────┼───────────┘  └───────────────────────────┘
                              │ writes result
                              ▼
                    Supabase jobs table
                              │ Realtime row change
                              ▼
                    Frontend subscription
                    renders result in chat
```

---

## 4. Request Lifecycle — Two Patterns

### Pattern A — Chat (Direct SSE Streaming)

```
1. User types message → Frontend sends POST /v1/responses/stream
   Headers: { Authorization: "Bearer <supabase_jwt>" }
   Body:    { conversation_id, messages: [...], model: "gpt-4o-ochuko" }

2. FastAPI middleware stack runs (7 steps, <5ms combined)

3. Dispatcher detects: is_chat=True
   → Returns StreamingResponse(content_type="text/event-stream")

4. Azure OpenAI Responses API called with stream=True
   async with client.responses.stream(model=..., input=...) as stream:
       async for event in stream:
           yield f"data: {event.json()}\n\n"

5. Frontend reads SSE stream:
   const reader = response.body.getReader()
   while (true):
       const { done, value } = await reader.read()
       if done break
       parse chunk → append to message bubble

6. On stream end:
   → FastAPI writes complete message to Supabase (conversation_id, role, content, tokens_input, tokens_output, response_id)
   → FastAPI deducts tokens from token_budgets (atomic UPDATE with RETURNING)
   → Audit log written (background task — does not block response)

Total user-perceived latency: TTFT (time to first token) ~200–800ms from South Africa North
```

### Pattern B — Agent Tasks (Decoupled Queue)

```
1. User uploads PDF → Frontend sends POST /v1/agents/ocr
   Body: { conversation_id, file_id: "blob://uploads/abc123.pdf" }

2. FastAPI middleware stack runs (same 7 steps)

3. Dispatcher detects: is_agent=True, agent_type="ocr"
   → Creates job row in Supabase: { status: "pending", type: "ocr", user_id, conversation_id }
   → Enqueues message to Azure Queue Storage:
     { job_id, type: "ocr", blob_url: "...", user_id }
   → Returns: HTTP 202 { job_id: "uuid" }

4. Frontend receives 202 immediately (fast — user sees spinner)
   → Subscribes to Supabase Realtime:
     supabase.channel('job-xyz').on('postgres_changes', filter: id=eq.job_id, ...)

5. Azure Queue Storage triggers OCR worker Azure Function
   → Function reads message from queue
   → Updates job: { status: "processing", started_at: now() }
   → Calls Azure Document Intelligence SDK (async)
   → Gets extracted text + pages
   → Writes result to Supabase: { status: "done", result: { text, pages, confidence } }
   → Updates agent_quotas.ocr_pages_used += pages_processed

6. Supabase Realtime detects the UPDATE on jobs row
   → Pushes to subscribed Frontend channel
   → Frontend renders OCR result in chat as assistant message

7. If Azure Function fails 5 times:
   → Azure Queue routes message to agent-jobs-poison (dead-letter)
   → Separate poison handler Function reads it
   → Updates job: { status: "failed", error: "OCR failed after 5 attempts" }
   → Frontend receives failure via Realtime, shows error toast

Total user-perceived latency: 202 returned in ~50ms. Result arrives in 3–15 seconds depending on file size.
```

---

## 5. Beyond RBAC — Full IAM Design

### The Five Layers

```
REQUEST
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 1 — AUTHENTICATION                               │
│ "Who are you?"                                         │
│ · Supabase JWT verified with SUPABASE_JWT_SECRET       │
│ · Google OAuth sub extracted from JWT claims           │
│ · Token expiry checked                                 │
│ · Refresh token rotation enforced                      │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 2 — RBAC (Role-Based Access Control)             │
│ "What role do you have?"                               │
│                                                        │
│  guest       → view shared convos, export JSON         │
│  user        → chat, all agents, file upload           │
│  power_user  → larger context, priority queue          │
│  admin       → manage users, view usage, set budgets   │
│  superadmin  → all admin + model config, key rotation  │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 3 — ABAC (Attribute-Based Access Control)        │
│ "Do your attributes allow this specific action?"       │
│                                                        │
│  Evaluated from: user_attributes + access_policies     │
│                                                        │
│  Example policies (stored in access_policies table):   │
│  · ALLOW chat IF user.is_active AND budget > 0        │
│  · ALLOW ocr  IF ocr_pages_used < 500                 │
│  · ALLOW vision IF vision_calls < 5000                │
│  · DENY all   IF user.is_blocked                      │
│  · DENY all   IF maintenance_mode == true             │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 4 — ReBAC (Relationship-Based Access Control)    │
│ "What do you own, and who can see it?"                 │
│                                                        │
│  Enforced entirely by Supabase RLS:                    │
│  · User → owns → Conversation                         │
│  · User → owns → Messages (via conversation)          │
│  · User → owns → Jobs                                 │
│  · Conversation → is_shared → readable by anyone      │
│  · Admin → can_read → all audit_log rows              │
│                                                        │
│  Zero code in FastAPI for this layer —                 │
│  it's enforced at the DB query level by Postgres.     │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 5 — TOKEN BUDGET ENFORCEMENT                     │
│ "Do you have capacity left?"                           │
│                                                        │
│  Per-user daily token budget (default: 100,000)        │
│  Checked atomically before each inference call:        │
│                                                        │
│  UPDATE token_budgets                                  │
│    SET tokens_used = tokens_used + estimated_tokens    │
│    WHERE user_id = $1                                  │
│      AND period = CURRENT_DATE                         │
│      AND tokens_used + estimated_tokens <= budget_limit│
│    RETURNING tokens_used;                              │
│                                                        │
│  If 0 rows returned → budget exhausted → 429 error    │
│  Reconciliation: actual tokens deducted post-response  │
└─────────────────────────────────────────────────────────┘
```

### Blocking Strategy (Unbypassable)

```python
# On every login attempt, before session created:
async def check_blocked(google_sub: str) -> None:
    result = await supabase.table("blocked_identities") \
        .select("id") \
        .eq("google_sub", google_sub) \
        .execute()
    if result.data:
        raise HTTPException(403, "Account access revoked.")
```

Why this works:
- Google `sub` is **permanent per Google account** — cannot be changed
- Even if user creates a new Gmail, same Google account = same `sub`
- To fully bypass: they need a brand new Google account on a different device
- Device fingerprint (stored in `profiles.device_fingerprint`) catches that case

### Registration Cap

```python
# Supabase trigger on auth.users INSERT — runs before profile creation
async def check_registration_cap() -> None:
    settings = await get_admin_setting("registration_limit")
    current_count = await count_profiles()
    if current_count >= settings["registration_limit"]:
        raise Exception("Registration limit reached.")
    if not settings["registration_open"]:
        raise Exception("Registration is currently closed.")
```

---

## 6. Complete Database Schema

```sql
-- ============================================================
-- EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";  -- for query monitoring

-- ============================================================
-- PROFILES (extends Supabase auth.users)
-- ============================================================
CREATE TABLE profiles (
  id                  UUID PRIMARY KEY REFERENCES auth.users ON DELETE CASCADE,
  display_name        TEXT,
  avatar_url          TEXT,
  role                TEXT DEFAULT 'user'
                        CHECK (role IN ('guest','user','power_user','admin','superadmin')),
  is_active           BOOLEAN DEFAULT TRUE,
  google_sub          TEXT UNIQUE,                    -- permanent Google account ID
  device_fingerprint  TEXT,                           -- secondary block layer
  created_at          TIMESTAMPTZ DEFAULT now(),
  last_seen           TIMESTAMPTZ DEFAULT now()
);

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_limit int;
  v_open boolean;
  v_count int;
BEGIN
  -- 1. Safely extract settings using value::text casting
  SELECT (value::text)::int INTO v_limit FROM admin_settings WHERE key = 'registration_limit';
  SELECT (value::text)::boolean INTO v_open FROM admin_settings WHERE key = 'registration_open';
  
  -- Fallbacks if settings are missing
  IF v_limit IS NULL THEN v_limit := 100; END IF;
  IF v_open IS NULL THEN v_open := TRUE; END IF;

  -- 2. Check registration cap
  SELECT COUNT(*) INTO v_count FROM profiles;
  IF v_count >= v_limit THEN
    RAISE EXCEPTION 'Registration limit reached (Limit: %, Current: %)', v_limit, v_count;
  END IF;
  
  -- 3. Check if registration is open
  IF v_open = FALSE THEN
    RAISE EXCEPTION 'Registration is currently closed';
  END IF;

  -- 4. Insert profile with safe COALESCE for metadata
  INSERT INTO profiles (id, display_name, avatar_url, google_sub)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data, '{}'::jsonb)->>'full_name',
    COALESCE(NEW.raw_user_meta_data, '{}'::jsonb)->>'avatar_url',
    COALESCE(
      COALESCE(NEW.raw_user_meta_data, '{}'::jsonb)->>'sub',
      COALESCE(NEW.raw_user_meta_data, '{}'::jsonb)->>'provider_id'
    )
  );
  
  RETURN NEW;
EXCEPTION WHEN OTHERS THEN
  -- Log the error to postgres logs
  RAISE WARNING 'Error in handle_new_user trigger: %', SQLERRM;
  RAISE;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ============================================================
-- BLOCKED IDENTITIES
-- ============================================================
CREATE TABLE blocked_identities (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  google_sub  TEXT UNIQUE NOT NULL,
  email       TEXT,
  blocked_by  UUID REFERENCES profiles(id),
  reason      TEXT,
  blocked_at  TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- ADMIN SETTINGS (global config — replaces env vars for runtime config)
-- ============================================================
CREATE TABLE admin_settings (
  key         TEXT PRIMARY KEY,
  value       JSONB NOT NULL,
  description TEXT,
  updated_by  UUID REFERENCES profiles(id),
  updated_at  TIMESTAMPTZ DEFAULT now()
);

INSERT INTO admin_settings (key, value, description) VALUES
  ('registration_limit',       '100',    'Max number of registered users'),
  ('registration_open',        'true',   'Whether new registrations are allowed'),
  ('maintenance_mode',         'false',  'If true, all requests return 503'),
  ('global_daily_token_budget','100000', 'Default daily token budget for new users'),
  ('max_file_size_mb',         '10',     'Max file upload size in MB'),
  ('max_ocr_pages_per_user',   '50',     'Max OCR pages per user per month');

-- ============================================================
-- CONVERSATIONS
-- ============================================================
CREATE TABLE conversations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES profiles(id) ON DELETE CASCADE,
  title           TEXT DEFAULT 'New Chat',
  model           TEXT DEFAULT 'gpt-5.4-nano',
  mode            TEXT DEFAULT 'think' CHECK (mode IN ('think','solve')),
  nano_turn_count INT  DEFAULT 0,               -- resets after NANO_MAX_TURNS
  agent_type      TEXT DEFAULT 'chat',
  system_prompt   TEXT,
  is_archived     BOOLEAN DEFAULT FALSE,
  is_shared       BOOLEAN DEFAULT FALSE,
  share_token     TEXT UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),
  message_count   INT DEFAULT 0,                -- increment on each message; triggers compaction
  last_compacted_at TIMESTAMPTZ,               -- when compaction last ran on this conversation
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_conversation_timestamp()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;
CREATE TRIGGER conversations_updated_at
  BEFORE UPDATE ON conversations
  FOR EACH ROW EXECUTE FUNCTION update_conversation_timestamp();

-- ============================================================
-- MESSAGES
-- ============================================================
CREATE TABLE messages (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id  UUID REFERENCES conversations(id) ON DELETE CASCADE,
  role             TEXT CHECK (role IN ('user','assistant','system','tool')),
  content          TEXT,
  content_parts    JSONB,       -- [{type:"text",text:"..."},{type:"image_url",url:"..."}]
  response_id      TEXT,        -- Azure OpenAI Responses API response ID
  model            TEXT,        -- actual deployment used (e.g. gpt-5.4)
  routing_mode     TEXT CHECK (routing_mode IN ('think','solve','nano','summary')),
  routing_reason   TEXT,        -- from ModelRouter.reasoning — for audit/debugging
  is_summary       BOOLEAN DEFAULT FALSE,  -- TRUE for compaction summary messages
  is_archived_msg  BOOLEAN DEFAULT FALSE,  -- TRUE for messages replaced by summary
  tokens_input     INT DEFAULT 0,
  tokens_output    INT DEFAULT 0,
  latency_ms       INT DEFAULT 0,
  is_error         BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);

-- ============================================================
-- JOBS (async agent task queue — Pattern B)
-- ============================================================
CREATE TABLE jobs (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID REFERENCES profiles(id) ON DELETE CASCADE,
  conversation_id  UUID REFERENCES conversations(id) ON DELETE SET NULL,
  type             TEXT NOT NULL
                     CHECK (type IN ('ocr','vision','file_gen','image_gen','speech')),
  status           TEXT DEFAULT 'pending'
                     CHECK (status IN ('pending','processing','done','failed')),
  input_metadata   JSONB,     -- { blob_url, options, original_filename }
  result           JSONB,     -- final structured output from worker
  result_blob_url  TEXT,      -- populated for file_gen/image_gen results
  error            TEXT,
  queue_message_id TEXT,      -- Azure Queue message ID (for debugging)
  retry_count      INT DEFAULT 0,
  created_at       TIMESTAMPTZ DEFAULT now(),
  started_at       TIMESTAMPTZ,
  completed_at     TIMESTAMPTZ
);

CREATE INDEX idx_jobs_user_status ON jobs(user_id, status, created_at);

-- ============================================================
-- TOKEN BUDGETS (daily, per-user)
-- ============================================================
CREATE TABLE token_budgets (
  user_id       UUID REFERENCES profiles(id) ON DELETE CASCADE,
  period        DATE DEFAULT CURRENT_DATE,
  tokens_used   BIGINT DEFAULT 0,
  budget_limit  BIGINT DEFAULT 100000,   -- admin can override per user
  PRIMARY KEY (user_id, period)
);

-- Ensure budget row exists before deducting (upsert pattern)
CREATE OR REPLACE FUNCTION ensure_budget_row(p_user_id UUID)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO token_budgets (user_id, period, budget_limit)
  VALUES (
    p_user_id,
    CURRENT_DATE,
    (SELECT (value#>>'{}')::bigint FROM admin_settings WHERE key = 'global_daily_token_budget')
  )
  ON CONFLICT (user_id, period) DO NOTHING;
END;
$$;

-- ============================================================
-- AGENT QUOTAS (monthly, per-user)
-- ============================================================
CREATE TABLE agent_quotas (
  user_id             UUID REFERENCES profiles(id) ON DELETE CASCADE,
  period              TEXT,           -- 'YYYY-MM'
  ocr_pages_used      INT DEFAULT 0,
  vision_calls_used   INT DEFAULT 0,
  speech_seconds_used INT DEFAULT 0,
  image_gen_used      INT DEFAULT 0,
  PRIMARY KEY (user_id, period)
);

-- ============================================================
-- AUDIT LOG (append-only, never updated)
-- ============================================================
CREATE TABLE audit_log (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID REFERENCES profiles(id),
  action           TEXT NOT NULL,   -- 'response', 'ocr', 'vision', 'login', 'block', etc.
  resource_type    TEXT,
  resource_id      UUID,
  metadata         JSONB,           -- { model, response_id, tokens, job_id, etc. }
  policy_decision  TEXT CHECK (policy_decision IN ('ALLOW','DENY')),
  policy_reason    TEXT,
  ip_address       TEXT,
  user_agent       TEXT,
  created_at       TIMESTAMPTZ DEFAULT now()
);

-- Audit log is append-only — disable UPDATE and DELETE
CREATE RULE no_update_audit AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE RULE no_delete_audit AS ON DELETE TO audit_log DO INSTEAD NOTHING;

CREATE INDEX idx_audit_user ON audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action, created_at DESC);

-- ============================================================
-- USER ATTRIBUTES (ABAC key-value store)
-- ============================================================
CREATE TABLE user_attributes (
  user_id  UUID REFERENCES profiles(id) ON DELETE CASCADE,
  key      TEXT,
  value    JSONB,
  PRIMARY KEY (user_id, key)
);

-- ============================================================
-- ACCESS POLICIES (ABAC rules — stored as JSON expressions)
-- ============================================================
CREATE TABLE access_policies (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  description   TEXT,
  resource_type TEXT,           -- 'chat', 'ocr', 'vision', 'image_gen', 'file_gen', 'speech'
  conditions    JSONB,          -- evaluated by policy_engine.py
  effect        TEXT CHECK (effect IN ('allow','deny')),
  priority      INT DEFAULT 0,  -- higher priority evaluated first
  is_active     BOOLEAN DEFAULT TRUE,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- Seed default policies
INSERT INTO access_policies (name, resource_type, conditions, effect, priority) VALUES
  ('block-inactive-users', 'all', '{"user.is_active": false}', 'deny', 100),
  ('require-budget', 'chat', '{"user.token_budget_remaining_lte": 0}', 'deny', 90),
  ('allow-registered-users', 'all', '{"user.role": ["user","power_user","admin","superadmin"]}', 'allow', 0);

-- ============================================================
-- ROW-LEVEL SECURITY POLICIES
-- ============================================================
ALTER TABLE profiles        ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations   ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages        ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs            ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_budgets   ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_quotas    ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log       ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_attributes ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_settings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE blocked_identities ENABLE ROW LEVEL SECURITY;

-- Helper: is current user admin?
CREATE OR REPLACE FUNCTION is_admin() RETURNS BOOLEAN
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (
    SELECT 1 FROM profiles
    WHERE id = auth.uid()
    AND role IN ('admin', 'superadmin')
  );
$$;

-- PROFILES
CREATE POLICY "profiles_own"          ON profiles FOR SELECT  USING (auth.uid() = id);
CREATE POLICY "profiles_admin_all"    ON profiles FOR SELECT  USING (is_admin());
CREATE POLICY "profiles_own_update"   ON profiles FOR UPDATE  USING (auth.uid() = id);
CREATE POLICY "profiles_admin_update" ON profiles FOR UPDATE  USING (is_admin());

-- CONVERSATIONS
CREATE POLICY "convos_own"            ON conversations FOR ALL    USING (auth.uid() = user_id);
CREATE POLICY "convos_shared"         ON conversations FOR SELECT USING (is_shared = TRUE);
CREATE POLICY "convos_admin"          ON conversations FOR SELECT USING (is_admin());

-- MESSAGES
CREATE POLICY "msgs_own" ON messages FOR ALL USING (
  conversation_id IN (SELECT id FROM conversations WHERE user_id = auth.uid())
);
CREATE POLICY "msgs_shared" ON messages FOR SELECT USING (
  conversation_id IN (SELECT id FROM conversations WHERE is_shared = TRUE)
);

-- JOBS
CREATE POLICY "jobs_own"   ON jobs FOR ALL    USING (auth.uid() = user_id);
CREATE POLICY "jobs_admin" ON jobs FOR SELECT USING (is_admin());

-- TOKEN BUDGETS
CREATE POLICY "budget_own"   ON token_budgets FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "budget_admin" ON token_budgets FOR ALL    USING (is_admin());

-- AUDIT LOG
CREATE POLICY "audit_admin" ON audit_log FOR SELECT USING (is_admin());

-- ADMIN SETTINGS
CREATE POLICY "settings_admin"      ON admin_settings FOR ALL    USING (is_admin());
CREATE POLICY "settings_maintenance"ON admin_settings FOR SELECT USING (key = 'maintenance_mode');

-- BLOCKED IDENTITIES
CREATE POLICY "blocked_admin" ON blocked_identities FOR ALL USING (is_admin());
```

---

## 7. API Contract Specification

### Base URL
```
Production:  https://api.agent-ochuko.azurecontainerapps.io
Local dev:   http://localhost:8000
```

### Authentication Header
```
Authorization: Bearer <supabase_jwt_token>
```

### Endpoints

#### `POST /v1/responses/stream`
Chat completion with streaming SSE.

**Request**:
```json
{
  "conversation_id": "uuid",
  "messages": [
    { "role": "user", "content": "Explain async/await in Python" }
  ],
  "model": "gpt-4o-ochuko",
  "stream": true
}
```

**Response**: `text/event-stream`
```
data: {"type":"content_block_delta","delta":{"text":"Async"}}
data: {"type":"content_block_delta","delta":{"text":"/await"}}
data: {"type":"response.done","response_id":"resp_abc123","usage":{"input_tokens":12,"output_tokens":180}}
data: [DONE]
```

---

#### `POST /v1/agents/ocr`
Queue OCR job. Returns immediately.

**Request**:
```json
{
  "conversation_id": "uuid",
  "blob_url": "https://agentochukostore.blob.core.windows.net/uploads/abc.pdf",
  "options": { "extract_tables": true }
}
```

**Response** `202 Accepted`:
```json
{ "job_id": "uuid", "status": "pending" }
```

---

#### `POST /v1/agents/vision`
Queue image analysis job.

**Request**:
```json
{
  "conversation_id": "uuid",
  "blob_url": "...",
  "prompt": "What is in this image?"
}
```
**Response** `202 Accepted`: `{ "job_id": "uuid" }`

---

#### `POST /v1/audio/transcriptions`
Synchronous Speech-to-Text & Stitching (used for Claude-style dictation).
**Request**: `multipart/form-data` with:
- `file`: audio file chunk (webm)
- `existing_text`: optional string representing the current text input bar value
**Response** `200 OK`:
```json
{ "text": "Stitched and corrected sentence." }
```

---

#### `POST /v1/agents/speech/stt`
Speech-to-text. Queue heavy file transcribing job (async).
**Request**: multipart/form-data with audio file.
**Response** `202`: `{ "job_id": "uuid" }`

---

#### `POST /v1/agents/speech/tts`
Text-to-speech. Queue job.
**Request**: `{ "text": "...", "voice": "en-ZA-LeahNeural" }`
**Response** `202`: `{ "job_id": "uuid", "result_blob_url": null }`

---

#### `POST /v1/agents/image_gen`
Image generation. Queue job.
**Request**: `{ "prompt": "...", "size": "1024x1024" }`
**Response** `202`: `{ "job_id": "uuid" }`

---

#### `POST /v1/agents/file_gen`
Generate a downloadable file.
**Request**:
```json
{
  "conversation_id": "uuid",
  "format": "docx",
  "content": "...",
  "filename": "report.docx"
}
```
**Response** `202`: `{ "job_id": "uuid" }`

---

#### `GET /v1/conversations`
List user's conversations.
**Response**: `{ "data": [...conversations], "total": 42 }`

---

#### `GET /v1/conversations/{id}/messages`
Get messages for a conversation.
**Response**: `{ "data": [...messages] }`

---

#### `GET /v1/shared/{share_token}`
Public endpoint — no auth required. Returns shared conversation for guest view.

---

#### `GET /v1/admin/users`
Admin only. Returns all users with usage.

---

#### `PATCH /v1/admin/users/{id}/block`
Admin only. Block a user by their ID (internally blocks by google_sub).

---

#### `PATCH /v1/admin/settings`
Admin only. Update global settings.
```json
{ "key": "registration_limit", "value": 150 }
```

---

## 8. Backend — FastAPI Structure & Key Modules

### Project Layout
```
backend/
├── app/
│   ├── main.py                      # FastAPI app + lifespan + CORS
│   ├── api/
│   │   └── v1/
│   │       ├── responses.py         # /v1/responses/stream  ← calls model_router first
│   │       ├── agents.py            # /v1/agents/* (all queue to Pattern B)
│   │       ├── files.py             # /v1/files/upload (presigned URL upload)
│   │       ├── conversations.py     # CRUD for conversations + mode switch
│   │       ├── messages.py          # CRUD for messages
│   │       ├── shared.py            # /v1/shared/{token} (public, no auth)
│   │       └── admin.py             # /v1/admin/* (admin only)
│   ├── core/
│   │   ├── config.py                # reads from Azure App Configuration at startup
│   │   ├── dispatcher.py            # Pattern A vs Pattern B routing
│   │   ├── model_router.py          # ★ ModelRouter — THINK/SOLVE/NANO + compaction trigger
│   │   └── security.py             # JWT decode, role checks
│   ├── auth/
│   │   ├── jwt_validator.py         # Supabase JWT verification (JWKS)
│   │   └── policy_engine.py         # ABAC evaluation engine
│   ├── services/
│   │   ├── azure_openai.py          # Responses API streaming — takes deployment as param
│   │   ├── queue_dispatcher.py      # enqueue to Azure Queue Storage (Pattern B)
│   │   ├── azure_blob.py            # upload/download/presigned URL
│   │   └── supabase_admin.py        # service-role Supabase client
│   ├── middleware/
│   │   ├── maintenance_guard.py     # check maintenance_mode setting
│   │   ├── block_guard.py           # check blocked_identities table
│   │   ├── token_budget.py          # atomic budget check + deduction
│   │   ├── quota_guard.py           # agent quota enforcement
│   │   ├── feature_flags.py         # read from Azure App Configuration
│   │   └── audit_logger.py          # async background audit writer
│   └── models/
│       ├── requests.py              # Pydantic request models (includes mode field)
│       └── responses.py             # Pydantic response models
├── Dockerfile
├── requirements.txt
└── .env                             # local dev only (never committed)
```

### `main.py` — Application Setup
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import load_config
from app.services.supabase_admin import init_supabase

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load config from Azure App Configuration
    await load_config()
    await init_supabase()
    yield
    # Shutdown: cleanup connections

app = FastAPI(title="Agent Ochuko API", version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware registered in order (last registered = first executed)
app.add_middleware(AuditLogMiddleware)
app.add_middleware(ABACMiddleware)
app.add_middleware(QuotaGuardMiddleware)
app.add_middleware(FeatureFlagMiddleware)
app.add_middleware(BlockGuardMiddleware)
app.add_middleware(MaintenanceGuardMiddleware)
app.add_middleware(JWTValidatorMiddleware)   # ← runs first
```

### `config.py` — Live Config from Azure App Configuration
```python
from azure.appconfiguration.aio import AzureAppConfigurationClient

_config_cache: dict = {}

async def load_config():
    """Load all config keys from Azure App Configuration into memory."""
    client = AzureAppConfigurationClient.from_connection_string(
        os.getenv("AZURE_APP_CONFIG_CONNECTION_STRING")
    )
    async with client:
        async for setting in client.list_configuration_settings():
            _config_cache[setting.key] = setting.value

async def get_config(key: str) -> str:
    """Get a config value — refreshes from Azure if not in cache."""
    if key not in _config_cache:
        await load_config()
    return _config_cache.get(key)
```

### `policy_engine.py` — ABAC Engine
```python
async def evaluate(user: UserContext, resource_type: str) -> PolicyResult:
    """
    Evaluate all active ABAC policies for this user + resource.
    Policies are ordered by priority (highest first).
    First matching DENY = reject. All must ALLOW for proceed.
    """
    policies = await get_active_policies(resource_type)
    user_attrs = await get_user_attributes(user.id)
    env_context = get_environment_context()

    evaluation_context = {
        "user": {**user.__dict__, **user_attrs},
        "resource": {"type": resource_type},
        "env": env_context,
    }

    for policy in sorted(policies, key=lambda p: -p.priority):
        if matches(policy.conditions, evaluation_context):
            if policy.effect == "deny":
                return PolicyResult(
                    decision="DENY",
                    reason=f"Policy '{policy.name}' denied access"
                )
    return PolicyResult(decision="ALLOW", reason="All policies passed")
```

---

## 9. Frontend — Component Architecture

### Project Layout
```
frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx                    # Router: /login, /chat, /shared/:token
│   ├── lib/
│   │   ├── supabase.ts            # Supabase client (anon key)
│   │   ├── api.ts                 # FastAPI client (axios + JWT inject)
│   │   └── streaming.ts           # SSE reader / stream parser
│   ├── hooks/
│   │   ├── useAuth.ts             # Google OAuth sign-in/out, session
│   │   ├── useConversations.ts    # CRUD + Supabase subscription
│   │   ├── useStream.ts           # Pattern A: SSE streaming hook
│   │   ├── useJob.ts              # Pattern B: job 202 + Realtime poll
│   │   └── useVoice.ts            # Azure Speech STT + TTS
│   ├── stores/
│   │   ├── chatStore.ts           # Zustand: messages, active conversation
│   │   └── userStore.ts           # Zustand: current user, role
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppShell.tsx       # Sidebar + main panel layout
│   │   │   └── Sidebar.tsx        # Conversation list + new chat btn
│   │   ├── chat/
│   │   │   ├── ChatWindow.tsx     # Message list + scroll anchor
│   │   │   ├── MessageBubble.tsx  # Markdown + code highlight + copy
│   │   │   ├── InputBar.tsx       # Text + attach file + voice toggle
│   │   │   └── StreamingCursor.tsx# Blinking cursor while streaming
│   │   ├── agents/
│   │   │   ├── AgentBadge.tsx     # Shows active agent type
│   │   │   ├── OCRResult.tsx      # Renders extracted text from OCR
│   │   │   ├── VisionResult.tsx   # Renders image analysis
│   │   │   └── FileDownload.tsx   # Download button for generated files
│   │   ├── artifact/
│   │   │   └── ArtifactPanel.tsx  # Desktop-only iframe panel
│   │   ├── auth/
│   │   │   └── GoogleSignIn.tsx   # Google OAuth button
│   │   └── shared/
│   │       └── SharedConversation.tsx  # Guest web view — read-only
│   └── pages/
│       ├── Login.tsx
│       ├── Chat.tsx               # Main chat page
│       └── Shared.tsx             # Public shared conversation view
├── index.html
├── vite.config.ts
└── tailwind.config.ts
```

### Desktop-Only Artifact Panel
```typescript
// components/artifact/ArtifactPanel.tsx
const ArtifactPanel: React.FC<{ content: string; type: 'html' | 'react' }> = ({ content, type }) => {
  const isDesktop = useMediaQuery('(min-width: 1024px)')
  if (!isDesktop) return null     // ← hidden on mobile

  const blob = new Blob([content], { type: 'text/html' })
  const url = URL.createObjectURL(blob)

  return (
    <div className="w-1/2 border-l border-zinc-800 h-full flex flex-col">
      <div className="flex items-center justify-between p-2 border-b border-zinc-800">
        <span className="text-sm text-zinc-400">Artifact Preview</span>
        <button onClick={() => downloadFile(content, 'artifact.html')}>
          ⬇ Download
        </button>
      </div>
      <iframe src={url} className="flex-1 bg-white" sandbox="allow-scripts" />
    </div>
  )
}
```

### Pattern B — Job Status Hook
```typescript
// hooks/useJob.ts
export const useJob = (jobId: string | null) => {
  const [job, setJob] = useState<Job | null>(null)

  useEffect(() => {
    if (!jobId) return
    const channel = supabase
      .channel(`job-${jobId}`)
      .on('postgres_changes', {
        event: 'UPDATE', schema: 'public', table: 'jobs',
        filter: `id=eq.${jobId}`
      }, (payload) => setJob(payload.new as Job))
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [jobId])

  return job
}
```

### Claude-Style Dictation Hook (`useVoice.ts`)

Implements a hybrid client-side silence-detection (VAD) and Groq-Whisper chunk transcription engine. 
* **Visual state**: text box blurs (connotes voice input mode, not typing) and overlays a subtle pulsating waveform.
* **VAD (Web Audio API)**: cuts recording buffer after 1.5s of silence, uploads the chunk to `/v1/audio/transcriptions`, and automatically restarts the recorder.
* **Stitching**: cleans, capitalizes, and appends chunks together into the input bar.

```typescript
// hooks/useVoice.ts
import { useState, useRef } from 'react';
import { api } from '../lib/api'; // axios instance

interface VoiceOptions {
  onTranscriptChange: (text: string) => void;
  silenceThresholdDb?: number; // e.g. -50 dB
  silenceDurationMs?: number;  // 1500ms default
}

export const useVoice = ({ onTranscriptChange, silenceThresholdDb = -50, silenceDurationMs = 1500 }: VoiceOptions) => {
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [currentVolume, setCurrentVolume] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isSilentRef = useRef(true);
  const fullTextRef = useRef('');

  // Starts recording audio and monitors voice activity
  const startListening = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setIsListening(true);
      audioChunksRef.current = [];
      
      // Setup Web Audio API for Silence Detection (VAD)
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      
      audioContextRef.current = audioCtx;
      analyserRef.current = analyser;

      // Setup MediaRecorder
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        // Upload the chunk if we have audio
        if (audioChunksRef.current.length > 0 && isListening) {
          const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
          audioChunksRef.current = [];
          await uploadChunk(audioBlob);
        }
      };

      // Start recording
      mediaRecorder.start(250); // timeslice of 250ms chunks

      // Start volume/silence polling loop
      monitorVolume();

    } catch (err) {
      console.error("Error accessing microphone:", err);
      stopListening();
    }
  };

  const stopListening = () => {
    setIsListening(false);
    setIsTranscribing(false);
    
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close();
    }

    // Stop all audio tracks from stream
    if (mediaRecorderRef.current && mediaRecorderRef.current.stream) {
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
    }
  };

  const monitorVolume = () => {
    if (!analyserRef.current || !isListening) return;

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    // Calculate average amplitude
    const average = dataArray.reduce((sum, val) => sum + val, 0) / dataArray.length;
    // Map average (0-255) to dB scale
    const db = average > 0 ? 20 * Math.log10(average / 255) : -Infinity;
    setCurrentVolume(average);

    const isSilent = db < silenceThresholdDb;

    if (isSilent) {
      if (!isSilentRef.current) {
        isSilentRef.current = true;
        // Start silence duration timer
        silenceTimerRef.current = setTimeout(() => {
          // Trigger VAD cut — stop recorder, which fires onstop & uploads, then restart
          triggerChunkCut();
        }, silenceDurationMs);
      }
    } else {
      isSilentRef.current = false;
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
    }

    if (isListening) {
      requestAnimationFrame(monitorVolume);
    }
  };

  const triggerChunkCut = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      // Trigger stop, which will upload the current chunk
      mediaRecorderRef.current.stop();
      
      // Immediately restart recording for the next chunk
      if (isListening) {
        audioChunksRef.current = [];
        mediaRecorderRef.current.start(250);
      }
    }
  };

  const uploadChunk = async (audioBlob: Blob) => {
    setIsTranscribing(true);
    const formData = new FormData();
    formData.append('file', audioBlob, 'chunk.webm');
    // Send existing text so the backend can stitch/correct it via lightweight LLM
    formData.append('existing_text', fullTextRef.current);
    
    try {
      const response = await api.post('/v1/audio/transcriptions', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      const newText = response.data.text || '';
      if (newText.trim()) {
        fullTextRef.current = newText;
        onTranscriptChange(newText);
      }
    } catch (err) {
      console.error("Transcription failed:", err);
    } finally {
      setIsTranscribing(false);
    }
  };

  // Stitching and auto-corrections are offloaded to FastAPI using NANO_MODEL_DEPLOYMENT,
  // returning unified and polished text blocks to prevent client-side inference lag.

  const clearTranscript = () => {
    fullTextRef.current = '';
    onTranscriptChange('');
  };

  return {
    isListening,
    isTranscribing,
    currentVolume,
    startListening,
    stopListening,
    clearTranscript
  };
};
```

---

## 10. Admin Dashboard

Deployed separately on Vercel. Uses `admin` or `superadmin` JWT to access `/v1/admin/*`.

### Pages & Features

```
admin/
├── src/
│   ├── pages/
│   │   ├── Users.tsx          # table: name, email, role, usage, status, actions
│   │   ├── Usage.tsx          # charts: tokens/day, agents/month, by user/model
│   │   ├── Budgets.tsx        # set per-user budget, global default
│   │   ├── Settings.tsx       # registration cap, maintenance mode, model override
│   │   └── AuditLog.tsx       # searchable audit trail
```

### Key UI Controls

| Control | Type | What it does |
|---|---|---|
| Registration Cap | Number input | Sets `admin_settings.registration_limit` |
| Registration Open | Toggle | Opens/closes signups globally |
| Maintenance Mode | Toggle | Returns 503 for all non-admin requests |
| Block User | Button | Writes to `blocked_identities` by google_sub |
| Suspend User | Toggle | Sets `profiles.is_active = false` (reversible) |
| Set Token Budget | Number input | Overrides `token_budgets.budget_limit` for user |
| Global Budget | Number input | Sets `admin_settings.global_daily_token_budget` |
| Active Model | Text input | Writes to Azure App Configuration (takes effect instantly) |

---

## 11. Azure Functions — All Workers & Crons

### Queue-Triggered Workers (Pattern B)

All workers follow this pattern:
```python
import azure.functions as func
import json

async def main(msg: func.QueueMessage) -> None:
    payload = json.loads(msg.get_body().decode())
    job_id  = payload["job_id"]

    # 1. Mark job as processing
    await supabase.table("jobs").update(
        {"status": "processing", "started_at": "now()"}
    ).eq("id", job_id).execute()

    try:
        # 2. Do the actual work (Azure SDK call)
        result = await process(payload)

        # 3. Mark job as done
        await supabase.table("jobs").update(
            {"status": "done", "result": result, "completed_at": "now()"}
        ).eq("id", job_id).execute()

    except Exception as e:
        # 4. Mark job as failed — Supabase Realtime pushes failure to frontend
        await supabase.table("jobs").update(
            {"status": "failed", "error": str(e)}
        ).eq("id", job_id).execute()
```

| Function | Trigger | What it does |
|---|---|---|
| `ocr_worker` | QueueTrigger: `agent-jobs` (type=ocr) | Azure Document Intelligence → extract text + tables |
| `vision_worker` | QueueTrigger: `agent-jobs` (type=vision) | Azure Computer Vision → image description |
| `speech_stt_worker` | QueueTrigger: `agent-jobs` (type=speech_stt) | Groq Whisper v3 Turbo → transcription |
| `speech_tts_worker` | QueueTrigger: `agent-jobs` (type=speech_tts) | Azure OpenAI TTS → audio blob |
| `image_gen_worker` | QueueTrigger: `agent-jobs` (type=image_gen) | Hugging Face Inference API (FLUX.1-dev) with Key Rotation → image → Azure Blob |
| `file_gen_worker` | QueueTrigger: `agent-jobs` (type=file_gen) | python-docx/reportlab/openpyxl → Azure Blob |
| `poison_handler` | QueueTrigger: `agent-jobs-poison` | Marks job as failed after 5 retries |

### Timer-Triggered Crons

| Function | Schedule | What it does |
|---|---|---|
| `token_quota_reset` | `0 0 * * *` (midnight UTC) | Resets daily token_budgets for all users |
| `agent_quota_reset` | `0 0 1 * *` (1st of month) | Resets agent_quotas for new month |
| `usage_aggregation` | `0 * * * *` (hourly) | Aggregates usage stats for admin dashboard |
| `conversation_archiver` | `0 2 * * *` (2am daily) | Sets is_archived=true on conversations older than 90 days |
| `model_expiry_monitor` | `0 9 * * *` (9am daily) | Checks MODEL_EXPIRY_DATE for all 4 deployments, alerts at 30 days, auto-swaps |
| `conversation_summarizer` | `0 3 * * *` (3am daily) | Finds conversations with message_count > COMPACTION_THRESHOLD → calls **GPT-o4-mini (o4-mini)** to summarize oldest 60% of messages → stores as `[SUMMARY]` message → archives originals |

---

## 12. Infrastructure & DevOps

### Full Resource List (Azure)

| Resource | Name | SKU/Tier |
|---|---|---|
| Resource Group | `rg-ochuko` | — |
| Azure AI Hub | `agent-ochuko-hub` | Standard |
| **Model: THINK** | `gpt-5.4` (GPT-5.4) | Standard — THINK mode |
| **Model: SOLVE** | `gpt-5.4-mini` (GPT-5.4 Mini) | Standard — SOLVE mode |
| **Model: NANO** | `gpt-5.4-nano` (GPT-5.4 Nano) | Standard — Greeting interceptor |
| **Model: Compaction** | `o4-mini` (GPT-o4-mini) | Standard — Background Cron Compaction |
| **Model: Image Gen** | `black-forest-labs/FLUX.1-dev` | Hugging Face Serverless Inference API (Free) |
| **Model: TTS** | `agent-ochuko-speech` (Azure Speech Neural TTS) | Free F0 (REST API) + Browser Fallback |
| Azure Document Intelligence | `agent-ochuko-docintelligence` | Free F0 |
| Azure Computer Vision | `agent-ochuko-vision` | Free F0 |
| Azure Storage Account | `agentochukostore` | Standard LRS |
| Azure Blob Containers | `uploads`, `generated`, `exports` | Private/Public |
| Azure Queue Storage | `agent-jobs`, `agent-jobs-poison` | — |
| Azure App Configuration | `agent-ochuko-appconfig` | Free |
| Azure Key Vault | `agent-ochuko-kv` | Standard |
| Azure Container Apps Env | `agent-ochuko-env` | Consumption |
| Azure Container App | `agent-ochuko-api` | 0.25 vCPU, 0.5 GB RAM |
| Azure Function App | `agent-ochuko-functions` | Consumption (Serverless) |
| Azure Static Web App (Frontend) | `agent-ochuko-frontend` | Free (Vite React PWA) |
| Azure Static Web App (Admin) | `agent-ochuko-admin` | Free (Vite React Admin) |
| Azure Application Insights | `agent-ochuko-insights` | — |

### Docker — Backend Container
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system deps for Azure SDKs
RUN apt-get update && apt-get install -y \
    libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Non-root user for security
RUN useradd -m ochuko && chown -R ochuko /app
USER ochuko

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--loop", "uvloop", "--http", "httptools"]
```

### Key Python Dependencies
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
openai>=1.35.0                        # Azure OpenAI Responses API
groq>=0.9.0                           # Groq API for Whisper STT
huggingface-hub>=0.23.0               # Hugging Face Inference API
pillow>=10.3.0                        # PIL for image handling
azure-storage-blob>=12.20.0
azure-storage-queue>=12.10.0
azure-ai-formrecognizer>=3.3.0        # Document Intelligence (OCR)
azure-cognitiveservices-vision-computervision>=0.9.0
azure-appconfiguration>=1.6.0
azure-keyvault-secrets>=4.8.0
azure-identity>=1.17.0                # Managed Identity auth
supabase>=2.4.0                       # Supabase client
python-jose[cryptography]>=3.3.0      # JWT validation
python-docx>=1.1.0                    # DOCX generation
reportlab>=4.2.0                      # PDF generation
openpyxl>=3.1.0                       # XLSX generation
python-multipart>=0.0.9               # File upload
httpx>=0.27.0
pydantic>=2.7.0
```

### CI/CD — GitHub Actions

```yaml
# .github/workflows/backend-deploy.yml
name: Deploy Backend
on:
  push:
    branches: [main]
    paths: ['backend/**']

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build & push Docker image
        uses: docker/build-push-action@v5
        with:
          context: ./backend
          push: true
          tags: ${{ secrets.ACR_LOGIN_SERVER }}/agent-ochuko-api:${{ github.sha }}
      - name: Deploy to Azure Container Apps
        uses: azure/container-apps-deploy-action@v1
        with:
          resourceGroup: rg-ochuko
          containerAppName: agent-ochuko-api
          imageToDeploy: ${{ secrets.ACR_LOGIN_SERVER }}/agent-ochuko-api:${{ github.sha }}
```

---

## 13. Security Model

### Secret Management (Zero Secrets in Code)

```
Developer machine  →  .env file (gitignored)
Azure Functions    →  Managed Identity → Key Vault
Azure Container App → Managed Identity → Key Vault
GitHub Actions     →  GitHub Secrets
Frontend           →  Only: SUPABASE_URL + SUPABASE_ANON_KEY (public, safe)
```

### Security Layers Summary

| Layer | Mechanism |
|---|---|
| Transport | HTTPS everywhere. HTTP redirects to HTTPS. |
| Authentication | Supabase JWT (RS256). Verified using JWKS endpoint. |
| Authorization | RLS (DB level) + ABAC (app level) + RBAC (role check) |
| Secrets | Azure Key Vault. Accessed via Managed Identity. No static keys. |
| File uploads | Presigned URL upload directly to Azure Blob. Files never pass through FastAPI. |
| CORS | Strict allow-list of origins. No wildcard. |
| Rate limiting | Per-user token budget. Per-IP request rate limit (100 req/min). |
| Audit | Every request logged. Audit log is append-only (no UPDATE/DELETE rule). |
| Blocking | By google_sub (permanent) + device fingerprint (secondary). |

---

## 14. Cost Analysis

### Monthly Cost Estimate (100 active users, student subscription)

| Service | Free Tier | Estimated Usage | Cost |
|---|---|---|---|
| Supabase | 500MB DB, 1GB storage, 50K MAU | ~200MB DB, ~20 users | **$0** |
| Azure OpenAI | Depends on TPM quota | Managed by token budgets | **~$0–$10** |
| Azure Document Intelligence | 500 pages/month | 50 users × 5 pages avg | **$0** |
| Azure Computer Vision | 5,000 calls/month | 50 users × 20 calls avg | **$0** |
| Azure Speech | 5 audio hours/month | ~3 hours total | **$0** |
| Azure Blob Storage | 5GB free | ~500MB files | **$0** |
| Azure Queue Storage | 1M transactions free | ~10K agent jobs/month | **$0** |
| Azure App Configuration | 10MB, 1M req free | Tiny | **$0** |
| Azure Container Apps | 180,000 vCPU-s free | Low traffic app | **$0–$2** |
| Azure Functions | 1M executions free | ~10K/month | **$0** |
| Azure Static Web Apps (Chat) | Free | — | **$0** |
| Azure Static Web Apps (Admin)| Free | — | **$0** |
| **TOTAL** | | | **~$0–$12/month** |

> The main cost driver is Azure OpenAI token usage. The token budget system keeps this controlled.

---

## 15. Phased Build Plan

### Phase 0 — Manual Setup (Azure Portal + Foundry Web UI)
*Estimated time: 1–2 days. No code written.*

- [ ] Azure AI Foundry: create Hub + Project + deploy GPT-5.4, GPT-5.4 Mini, GPT-5.4 Nano
- [ ] Azure Document Intelligence: create Free F0 resource
- [ ] Azure Computer Vision: create Free F0 resource
- [ ] Azure Speech Services: create Free F0 resource
- [ ] Azure Storage Account: create + Blob containers + Queue `agent-jobs` + `agent-jobs-poison`
- [ ] Azure App Configuration: create + add all keys (model name, expiry, budgets, flags)
- [ ] Azure Key Vault: create + add all secrets
- [ ] Azure Container Apps: create environment + enable Managed Identity
- [ ] Azure Function App: create + enable Managed Identity + grant Key Vault access
- [ ] Azure Static Web App: create (frontend deployment target)
- [ ] Azure Application Insights: create + link to Container App
- [ ] Supabase: create project (Cape Town region)
- [ ] Supabase: run all SQL migrations (schema + RLS + seed policies + seed admin_settings)
- [ ] Supabase: enable Google OAuth provider + set callback URL
- [ ] Supabase: enable Realtime on `messages`, `conversations`, `jobs`
- [ ] Supabase: create storage buckets (`uploads`, `generated`, `exports`)
- [ ] Google Cloud Console: create OAuth 2.0 client + add redirect URIs
- [ ] Local: create `backend/.env` from template in `04_local_dev_checklist.md`
- [ ] Smoke-test each service from Azure portal test UIs
- [ ] Your user promoted to `superadmin` in Supabase

---

### Phase 1 — Foundation
*Estimated time: 3–5 days.*

- [ ] Scaffold FastAPI backend (all async, lifespan, CORS)
- [ ] `jwt_validator.py` — verify Supabase JWT using JWKS
- [ ] `config.py` — load from Azure App Configuration at startup
- [ ] Scaffold React + Vite + Tailwind frontend
- [ ] Google OAuth login flow (`/login` page → Supabase Google provider)
- [ ] Protected route: redirect to `/login` if no session
- [ ] Basic `POST /v1/responses/stream` endpoint with SSE
- [ ] `useStream.ts` hook — reads SSE stream, appends to message state
- [ ] Store completed messages in Supabase (`conversations` + `messages`)
- [ ] Docker Compose for local dev (FastAPI + hot-reload)

**Milestone**: Can sign in with Google and have a streaming conversation saved to Supabase.

---

### Phase 2 — Core Chat Experience
*Estimated time: 5–7 days.*

- [ ] Full ChatGPT-quality UI (dark theme, sidebar, markdown, code highlighting)
- [ ] Sidebar: conversation list, new chat button, search
- [ ] Message bubbles: user/assistant distinction, copy button, timestamp
- [ ] Conversation CRUD: create, rename, delete, archive
- [ ] Model switching dropdown (reads available models from App Configuration)
- [ ] File upload: drag & drop → upload to Azure Blob via presigned URL → attach to message
- [ ] Artifact panel: detect HTML/React in response → render in iframe (desktop only)
- [ ] Download button for artifact panel content
- [ ] Shared conversation: `GET /v1/shared/{token}` → read-only public page + JSON export
- [ ] Guest web view (no auth required, export to JSON)
- [ ] Responsive layout: mobile-friendly (sidebar collapses, no artifact panel)

**Milestone**: Feature-parity with basic ChatGPT UI.

---

### Phase 3 — Beyond RBAC
*Estimated time: 4–6 days.*

- [ ] `maintenance_guard.py` middleware
- [ ] `block_guard.py` middleware (check `blocked_identities` by google_sub from JWT)
- [ ] `policy_engine.py` ABAC engine (load policies from DB, evaluate per request)
- [ ] `token_budget.py` middleware: atomic UPDATE with budget check
- [ ] `quota_guard.py` middleware: per-agent monthly quota checks
- [ ] `audit_logger.py` middleware: async background task, non-blocking
- [ ] Registration cap: DB trigger on `auth.users` INSERT checks `admin_settings`
- [ ] Full RBAC role enforcement on all routes

**Milestone**: Full security model active. Any request without valid auth + budget is rejected.

---

### Phase 4 — AI Agents + Queue Layer
*Estimated time: 5–7 days.*

- [ ] `queue_dispatcher.py`: enqueue message to Azure Queue Storage
- [ ] `/v1/agents/*` endpoints: validate → create job row → enqueue → return 202
- [ ] `useJob.ts` hook: subscribe to `jobs` Supabase Realtime channel
- [ ] `ocr_worker` Azure Function (QueueTrigger → Document Intelligence)
- [ ] `vision_worker` Azure Function (QueueTrigger → Computer Vision)
- [ ] `speech_stt_worker` + `speech_tts_worker` Azure Functions
- [x] `image_gen_worker` Azure Function (QueueTrigger → Hugging Face FLUX → Blob)
- [ ] `file_gen_worker` Azure Function (QueueTrigger → python-docx/reportlab/openpyxl → Blob)
- [ ] `poison_handler` Azure Function: marks failed jobs + notifies frontend
- [ ] Voice UI: record button → blob → enqueue STT job → transcript into input bar
- [ ] TTS: play button on assistant messages → enqueue TTS → stream audio

**Milestone**: Full agent pipeline working. User uploads PDF → sees OCR result in chat.

---

### Phase 5 — Admin Dashboard
*Estimated time: 3–4 days.*

- [ ] Admin React + Vite project scaffold → deploy to Azure SWA (Admin)
- [ ] Users page: list, search, role badge, usage columns, block/suspend/activate buttons
- [ ] Usage page: token chart per user/model/day, agent calls per type
- [ ] Budgets page: set per-user override, global default input
- [ ] Settings page: registration cap (number input), maintenance toggle, model name override
- [ ] Audit log page: searchable, filterable by action/user/date
- [ ] Real-time user count widget (shows current registered vs cap)

**Milestone**: Full admin control plane working on Azure SWA.

---

### Phase 6 — Azure Functions Crons
*Estimated time: 2–3 days.*

- [ ] `token_quota_reset`: midnight UTC daily, resets token_budgets
- [ ] `agent_quota_reset`: 1st of month, resets agent_quotas
- [ ] `usage_aggregation`: hourly, materializes usage stats for admin charts
- [ ] `conversation_archiver`: 2am daily, archives old conversations
- [ ] `model_expiry_monitor`: 9am daily, checks MODEL_EXPIRY_DATE, auto-swaps, sends alert email

**Milestone**: All background automation running. Model can be swapped without any code.

---

### Phase 7 — Production Hardening
*Estimated time: 3–5 days.*

- [ ] Azure Application Insights: traces, exceptions, custom events (token usage)
- [ ] Structured logging: every FastAPI request/error logged to App Insights
- [ ] CI/CD: GitHub Actions for backend (Docker Hub → Container App) + frontend/admin (Vite build → Storage Blob Static Sites)
- [ ] Container health check endpoint: `GET /health`
- [ ] Blue/green deployment strategy on Container Apps
- [ ] Load test: simulate 50 concurrent streaming users (k6 or locust)
- [ ] Security review: all RLS policies tested with role-specific JWTs
- [ ] CORS review: strict origin allow-list
- [ ] Final cost review: ensure within student subscription limits

---

## 16. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Student subscription quota exhaustion | Medium | High | Per-user token budgets + quota guards enforced before Azure is called |
| Model deployment expires (1 year) | Certain | High | Daily cron monitors expiry, auto-swaps to fallback, alerts 30 days early |
| Supabase Realtime message dropped | Low | Medium | Frontend polls job status every 10s as fallback if Realtime fails |
| Azure Function cold start delay | Low | Low | Consumption plan cold starts ~500ms — acceptable for async jobs |
| User bypasses block with new email | Low | Low | Block is by google_sub (permanent), not email. Secondary: device fingerprint |
| Cost overrun on student subscription | Low | High | Every agent call is quota-guarded. Alert at 80% usage. |

---

## 17. Verification & Testing Strategy

### Unit Tests (pytest + asyncio)
```
backend/tests/
├── test_jwt_validator.py      # valid token, expired token, wrong secret
├── test_policy_engine.py      # ALLOW/DENY for each policy condition
├── test_token_budget.py       # atomic deduction, budget exhausted, concurrent
├── test_quota_guard.py        # OCR pages exceeded, vision calls exceeded
├── test_dispatcher.py         # correct path selected for each request type
├── test_queue_dispatcher.py   # message enqueued with correct payload
└── test_admin_endpoints.py    # role-gated routes reject non-admins
```

### Integration Tests
- Real Supabase test project (separate from production)
- Test RLS with 5 different user JWTs (guest, user, power_user, admin, superadmin)
- Test block guard: login with google_sub that is in blocked_identities → 403

### E2E Tests (Playwright)
```
tests/e2e/
├── auth.spec.ts               # Google OAuth login → profile created
├── chat.spec.ts               # Send message → streaming → saved to DB
├── file_upload.spec.ts        # Upload PDF → OCR job → result in chat
├── share.spec.ts              # Share conversation → guest views it → exports JSON
├── registration_cap.spec.ts   # Attempt signup when cap reached → rejected
├── admin.spec.ts              # Admin blocks user → user gets 403
```

### Manual Verification Checklist
- [ ] Streaming chat: no buffering, tokens appear character by character
- [ ] Model switch: switch to fallback model → confirm different deployment used
- [ ] Artifact panel: shows on 1200px+ screen, absent on 600px screen
- [ ] Voice: speak → transcript appears in input bar
- [ ] OCR: upload 5-page PDF → all pages extracted, visible in chat
- [ ] Block: admin blocks user in dashboard → user's next request returns 403
- [ ] Registration cap: set cap to current user count → new signup shows "closed"
- [ ] Model rotation: change `ACTIVE_MODEL_DEPLOYMENT` in App Configuration → next request uses new model (no restart)
- [ ] Budget exhaustion: exhaust daily budget → next request returns 429 with clear message
- [ ] Maintenance mode: toggle ON in admin → non-admin users get 503 → toggle OFF → service resumes

---

## 18. Incremental Updates — Stateful Sandbox, Capability Registry, and UI/UX Polish

Since the original approval of the system plan, several core components have been upgraded to support advanced developer features, self-awareness capabilities, and dashboard UI/UX polishes.

### 18.1. Custom Sandboxed Execution Engine (Stateful Sandbox)
- **Architecture Shift**: Migrated from Azure Container App session-based interpreter to a custom, local/container-based sandboxed execution runner ([code_sandbox.py](file:///C:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/services/code_sandbox.py)).
- **Stateful Workspaces**: Subprocess execution is run in a persistent conversation directory (`/tmp/sandbox_{conversation_id}`) to maintain command context and generated file state across multiple chat turns.
- **Multi-Language Support & Normalization**: Default language execution is set to JavaScript/Node.js, with fallbacks for Python and arbitrary Shell/Bash scripts. Normalized bash paths and Unix-style environment configurations.
- **Differential Snapshotting**: Prior to execution, file metadata is indexed. Post-execution, only newly created or modified files are uploaded to R2, ignoring bulky version-control and dependency folders (`.git`, `node_modules`, `.venv`, `__pycache__`).
- **Dynamic Dependency Injection**: Added a 3-attempt package installation auto-retry. If execution fails due to a missing package, the system automatically runs `pip install --target` or `npm install --prefix` and retries.
- **File Link Interception**: Fixed backend download signature issues and wired a frontend interceptor to map raw local sandbox links generated by the execution engine to clean download actions in the UI.

### 18.2. Unified Capability Self-Awareness Registry
- **Dynamic System Prompt Construction**: Introduced [capability_registry.py](file:///C:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/core/capability_registry.py) as the single source of truth for agent capabilities, supported formats (Mermaid, SVG, LaTeX, Markdown), and sub-agent routing rules.
- **Formatting Skills**: Added custom project-scoped guidelines/instructions for generating beautiful Word reports (`.agents/skills/docx/SKILL.md`), formatting PDFs (`.agents/skills/pdf/SKILL.md`), and modern web interfaces (`.agents/skills/frontend-design/SKILL.md`).
- **Enforced File Generation Rule**: The agent is explicitly instructed to execute code and output downloadable files (DOCX, PDF, XLSX, CSV) whenever a user requests document creation, rather than outputting plain text in the chat bubble.
- **Proactive Web Grounding**: Enforced aggressive search queries in system prompts to ensure real-time Google search grounding is triggered prior to synthesizing responses for current events or documentation.
- **Native Frontend Rendering**: Integrated `ResponseRenderer.tsx` using `marked`, `DOMPurify` (to sanitize inline SVGs), and `mermaid.js` (to draw diagrams).

### 18.3. UI/UX Polish & Dashboard Enhancements
- **Dynamic Input Bar**: Redesigned the chat input section to render thumbnails/previews of uploaded documents or images *inside* the chat input area prior to sending, and upgraded the input element from a static text field to an auto-growing textarea.
- **Reasoning Loop Step Indicators**: Fixed an infinite spinning spinner bug on step loop execution, added visual checkmarks upon completing sub-steps in the OODA loop, and polished indicators by hiding the denominator (`/3` etc.) when steps are completely resolved.
- **Click-to-Copy Copyable Templates**: Wrapped copyable output templates in formatted `blockquote` and code blocks, and added a quick "Click-to-Copy" button directly on blockquote cards.
- **Binary File Previewing**: Enabled the right-side artifact panel to detect and render high-fidelity download widgets for binary formats (like `.docx` files) instead of displaying raw text or failing, preventing office viewer wrapping.
- **Rich Inline Previews**: Renders uploaded images and document thumbnails directly in the chat history alongside user prompts.
- **Robust Event Polling Fallback**: Replaced fragile real-time subscriptions with a hybrid WebSocket subscription + polling fallback and a 90-second stall guard for image generation jobs.
- **Download Proxy Endpoint**: Added a `GET /v1/agents/download-proxy` endpoint in [agents.py](file:///C:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/api/v1/endpoints/agents.py#L545-L585) to stream R2 files to clients directly as attachments, bypassing cross-origin browser download security policies.
- **Admin Budget Fix**: Adjusted `admin_service.py` to upsert budgets using a composite constraint on `(user_id, period)` to prevent DB key clashes.
- **Search Syntax Error Fix**: Resolved a 500 server error caused by database search syntax exceptions during conversational message lookup.
- **Branding**: Renamed references of "Claude" to "Agent Ochuko" inside instructions and skill sets.
