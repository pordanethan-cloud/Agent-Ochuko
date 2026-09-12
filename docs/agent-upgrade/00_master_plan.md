# Agent Mode Upgrade — Master Implementation Plan

> **Document**: `docs/agent-upgrade/00_master_plan.md`
> **Status**: Draft — Awaiting Approval
> **Created**: 2026-08-21

---

## What Is Agent Mode?

Agent Mode transforms Agent Ochuko from a conversational AI into an **autonomous task executor** that can:

1. **Plan** — decompose a user goal into numbered steps, show the plan to the user for review/edit
2. **Act** — execute each step autonomously using tools (code sandbox, web search, browser actions, image generation, MCP connectors)
3. **Observe** — evaluate each step's output, self-correct on failure via reflexion
4. **Delegate** — spin up lightweight sub-agents for isolated tasks to save tokens
5. **Browse** — take actions in a headless browser (click, type, scroll, fill forms, scrape) via Playwright
6. **Connect** — call external services (Gmail, Google Calendar, GitHub, Notion) via MCP servers and Google APIs
7. **Deliver** — produce finished artifacts (PDFs, spreadsheets, reports, datasets) with provenance tracking
8. **Gate** — pause before high-risk actions and ask the user for approval in the chat thread

---

## Design Decisions (From User Feedback)

| Decision | Resolution |
|---|---|
| **Task duration** | Phase 1: 5 min max. Phase 2: 15 min max |
| **HITL UX** | Pause in chat thread + "Resume" button (no push notifications) |
| **Connectors** | MCPs + Google APIs (Gmail, Calendar). Sub-plan in Phase 3 doc |
| **Token budget** | **Shared** with existing daily budget — one budget, one slider. No separate "agent quota" |
| **Token optimization** | Context compression — each turn carries only: current task state + aim + step result. Not the full conversation history. Sub-agents return only final results. Sliding window for browser interactions |
| **Browser actions** | Playwright-based headless browser with accessibility tree for token efficiency (~200 tokens vs ~5000 for screenshots) |
| **Sub-agents** | Isolated execution contexts that return only compressed results to the orchestrator — prevents token bloat |
| **Time limits** | Enforced at both per-step level (90s) and per-task level (5 min / 15 min) with wall-clock timer |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                    AGENT MODE SYSTEM                                      │
│                                                                                          │
│  ┌──────────────────┐    ┌────────────────────────┐    ┌──────────────────────────────┐  │
│  │  Orchestrator     │───>│  Plan-Act-Observe Loop │───>│  Artifact Manager            │  │
│  │  (agent_task_mgr) │    │  (state machine)       │    │  (provenance + R2 upload)    │  │
│  └────────┬─────────┘    └───────────┬────────────┘    └──────────────────────────────┘  │
│           │                          │                                                    │
│           │              ┌───────────┼───────────────────────────┐                        │
│           │              │           │                           │                        │
│           v              v           v                           v                        │
│  ┌────────────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────────────────┐                │
│  │  Sub-Agent Pool │ │ Browser │ │  Code    │ │  MCP Connector Gateway   │                │
│  │  (nano workers) │ │ Agent   │ │  Sandbox │ │  (Gmail, Calendar, etc.) │                │
│  │  - search       │ │ (PW)   │ │          │ │                          │                │
│  │  - summarize    │ │         │ │          │ │                          │                │
│  │  - classify     │ └─────────┘ └──────────┘ └──────────────────────────┘                │
│  └────────────────┘                                                                      │
│                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐ │
│  │  Token Budget & Context Compression Layer                                            │ │
│  │  - Shared daily budget (same slider)                                                 │ │
│  │  - Sliding window: last 2 turns verbatim + compressed summary for older context     │ │
│  │  - Sub-agent isolation: raw tool output stays in sub-agent, only result returned    │ │
│  │  - Browser context: accessibility tree (~200 tok) preferred over screenshots (~5k)  │ │
│  └──────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐ │
│  │  Safety & Guardrails                                                                 │ │
│  │  - Circuit breaker (step budget + token budget + wall-clock timer)                   │ │
│  │  - HITL gates: pause in chat thread for high-risk steps                              │ │
│  │  - Per-step time limit: 90s    |    Per-task time limit: 5 min (Ph1) / 15 min (Ph2) │ │
│  │  - Reflexion engine: self-correction on step failure                                │ │
│  │  - Prompt defense: injection scanning on all tool outputs                           │ │
│  └──────────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase Breakdown

| Phase | Name | Weeks | Key Deliverables |
|---|---|---|---|
| **1** | [Agent Mode Foundation](./01_phase1_foundation.md) | 1-3 | Task state machine, structured plans, HITL gates, sub-agent delegation, context compression, frontend plan review + execution progress UX |
| **2** | [Browser Agent & Background Execution](./02_phase2_browser_and_background.md) | 4-6 | Playwright browser-use agent, background task worker via Azure Queue, durable state in Supabase, Realtime push updates, 15-min task support |
| **3** | [MCP Connectors & Google APIs](./03_phase3_mcp_connectors.md) | 7-10 | MCP server framework, Gmail connector, Google Calendar connector, GitHub connector, connector permission UI, dynamic tool injection |
| **4** | [Workspace Agents & Team Collaboration](./04_phase4_workspace_agents.md) | 11-14 | Shared team agents, custom system prompts, scoped tool/connector access, usage analytics |

---

## What Already Exists (Gap Analysis)

| Capability | Current State | Gap |
|---|---|---|
| OODA agent loop | `chat.py` L931-1599 — synchronous within SSE request | Need to extract into reusable state machine |
| Planning | `agent_planner.py` — nano call, returns raw text | Need structured steps + user-visible plan |
| Tool execution | `execute_code`, `search_web`, `deep_research`, `generate_image`, `show_widget` | Strong |
| Multi-model routing | `model_router.py` — think/solve/discuss/nano | Strong |
| Circuit breaker | `circuit_breaker.py` — step + error tracking | Need wall-clock timer + token budget |
| Reflexion | `reflexion_engine.py` — self-correction feedback | Strong |
| Sandbox | `code_sandbox.py` — subprocess isolation | Strong |
| Durable state | `durable_state.py` — file-based /tmp | Need DB-backed for cross-container |
| Sub-agents | `supervisor_router.py` — basic routing | Need isolated execution + compressed returns |
| Memory | `hybrid_memory.py` — in-memory blocks | Need context compression for agent mode |
| Skill store | `skill_store.py` — JSON skills on disk | Available |
| Browser actions | None | New — Playwright integration |
| MCP connectors | None | New — MCP server framework |
| App connectors (Google) | Google Drive OAuth sync only | Extend to Gmail + Calendar |
| HITL approval | None | New — chat-thread pause/resume |
| Task lifecycle | No task entity | New — DB-backed task with states |
| Background execution | Azure Functions (OCR, image-gen only) | Extend to general agent tasks |
| Workspace agents | Single-user only | New — Phase 4 |

---

## Token Cost Management Strategy

**Core Principle**: Same budget, managed aggressively. Every agent turn carries only what's necessary.

### What Each Agent Turn Carries (Context Payload)

```
AGENT TURN CONTEXT PAYLOAD (what the LLM sees each step)

  1. System prompt (base identity + active skill)    ~500 tok
  2. Task state snapshot:
     - Goal (original user request)                  ~50 tok
     - Current plan (step list with statuses)        ~200 tok
     - Current step index + description              ~30 tok
  3. Previous step result (compressed)               ~300 tok
  4. Reflexion context (if errors occurred)          ~100 tok
  5. Browser state (accessibility tree, if active)   ~200 tok

  TOTAL PER TURN: ~1,200-1,500 tokens
  vs current chat mode: ~4,000-12,000 tokens
```

### What Is NOT Carried

- Full conversation history (summarized into task state)
- Raw tool outputs from previous steps (compressed into result summaries)
- Raw browser screenshots (use accessibility tree instead)
- Sub-agent internal context (only final result returned)
- Previous step code/search results in full (only key findings carried forward)

### Sub-Agent Token Isolation

```
Orchestrator                          Sub-Agent (nano)
────────────                          ────────────────
Delegates: "Search for X pricing"  ->  Gets: system + query (200 tok)
                                      Executes: search_web
                                      Raw results: 3,000 tokens
                                      Compresses to: 150 tok summary
Receives: "X costs $99/mo..." (150t) <-  Returns only summary
```

The orchestrator **never** sees the 3,000-token raw search results. The sub-agent absorbs them, extracts the answer, and returns a compressed result. This is the primary token-saving mechanism.

---

## Sub-Plan Documents

Each phase has its own detailed sub-plan document with file-by-file change breakdowns, data models, schemas, code architecture, SSE event specifications, database migrations, test plans, and estimated effort.

| Document | Contents |
|---|---|
| [01_phase1_foundation.md](./01_phase1_foundation.md) | Task state machine, structured planner, HITL gates, sub-agent pool, context compression, frontend UX |
| [02_phase2_browser_and_background.md](./02_phase2_browser_and_background.md) | Playwright browser agent, background worker, durable state upgrade, Realtime push, 15-min tasks |
| [03_phase3_mcp_connectors.md](./03_phase3_mcp_connectors.md) | MCP server framework, Gmail/Calendar/GitHub connectors, OAuth flow, permission UI, dynamic tools |
| [04_phase4_workspace_agents.md](./04_phase4_workspace_agents.md) | Shared team agents, custom prompts, scoped access, analytics |
| [05_phase5_webdesign_conduct_and_website_engine.md](./05_phase5_webdesign_conduct_and_website_engine.md) | Web design engine, sandbox rendering, visual widgets, conduct gates |
| [06_tools_architecture_claude_parity_and_ooda_loop.md](./06_tools_architecture_claude_parity_and_ooda_loop.md) | 18-tool roster, OODA iteration engine, prompt contracts, conduct perimeter |
| [07_workstation_access_and_cowork_engine_under_the_hood.md](./07_workstation_access_and_cowork_engine_under_the_hood.md) | Workstation computer access & collaboration engine ("cowork"), dual-tier bridge, reverse-mtime file discovery, HitL safety, mobile-first toggle architecture |
