# Phase 5 — Webdesign Robustness, Website Engine & Conduct Enforcement Upgrade

> **Duration**: 6–8 days
> **Depends on**: Phase 1 (foundation), Ultra upgrade (sandbox, budgets, R2 multi-file), Widget renderer

## Governing rule for this phase

Every directive introduced here ships in **three layers or it does not ship**:

1. **Prompt layer** — the contract text in `skills.py` (BASE_IDENTITY / AGENT_CONDUCT / skill modules).
2. **Operational layer** — real machinery in the app (guards, state machines, route interception, sandbox policy) wired into existing choke points: `chat_stream_generator`, the agent tool-dispatch loop, `model_router` interception, `code_sandbox`, verification gates.
3. **Test layer** — contract-marker and behavior tests in `backend/tests/test_phase5_upgrade.py` following the hermetic style of `test_ultra_upgrade.py`.

Prompt text with no corresponding mechanism is explicitly rejected. This phase is surgical, not cosmetic.

---

## A. Agent-Mode Unshackling (no hard caps on creation)

**Problem**: agent mode shares `MAX_OUTPUT_TOKENS_ULTRA` (32,768 hard floor/ceiling), `AGENT_MODE_MAX_STEPS` defaults to 12, and wall-clock is capped at 300s. Multi-file websites and build-grade work get truncated or killed.

**Prompt layer**: `ULTRA_IDENTITY` gains one line: "Your generation budget is uncapped — never truncate a deliverable to fit a limit."

**Operational layer** (`app/core/agent_config.py`, `chat.py` ~1409-1432):
- New key `MAX_OUTPUT_TOKENS_AGENT` (default `0`). Semantics: `0` / `unset` / `auto` = **uncapped** — `get_max_output_tokens("agent")` returns `None`, and the agent loop **omits** `max_output_tokens` from the Azure Responses call. Explicitly configured values still work (floor 1024).
- `get_max_iterations("agent")`: `AGENT_MODE_MAX_STEPS` default raised 12 -> **50**; `"0"` = unlimited.
- `AGENT_MODE_MAX_DURATION` default 300s -> **1800s** (30 min), runtime-tunable.
- `TERMINAL_TIMEOUT_SECS` (default 600) for build-grade terminal runs (see B).

**Test**: agent mode with `MAX_OUTPUT_TOKENS_AGENT="0"` produces `output_budget=None`; think/solve keep numeric budgets; step-cap "0" semantics.

---

## B. Terminal-Driven Website Builds (multi-HTML, never forced single-file)

**Problem**: `hosted_sites.py` deploy accepts ONE `html_content` + optional css/js. The model already has a multi-file sandbox contract, but there is no terminal path for npm/vite builds, and hosted serving is single-document only.

**Prompt layer**: `SKILLS["code"]` WEBSITE PROJECT CONTRACT gains: single-file is for snippets/mockups only; multi-page production sites are the default; the `terminal` tool is for build tooling; built `dist/` output is written into the sandbox via `sandbox_write` receipts; Pexels backgrounds preferred for real-photo hero/section backgrounds (see C), FLUX when no suitable photo exists.

**Operational layer**:
1. **`terminal` tool** — registered in the chat.py tool roster and dispatched in the agent loop:
   - Runs a shell command inside the conversation sandbox workspace via `code_sandbox` bash execution extended with a `timeout_seconds` override read from `TERMINAL_TIMEOUT_SECS`.
   - Node/npm availability check on first call; build output streamed through the existing stdout cap (`_HEAD=4000/_TAIL=1000`); exit code surfaced in the receipt.
   - Registered in `agent_planner` tool-name enum; risk-classified in `hitl_gates.py` as MEDIUM.
2. **Multi-file hosted sites** — `DeploySiteRequest` gains `files: dict[str, str]` (relpath -> content) while `html_content/css_content/js_content` keep working (backward compat). `HostedSitesService.deploy_site` writes the file map preserving relative paths, persists a manifest row, and `GET /{slug}` serves `index.html` while `GET /{slug}/{path:path}` serves arbitrary static files with the existing CSP.
3. **ArtifactPanel** — when an artifact batch contains `index.html`, preview renders the hosted/CDN URL in the iframe instead of a single-file blob; device toggle unchanged.

**Test**: deploy with `files={"index.html": ..., "css/styles.css": ...}` -> manifest correct; `GET /{slug}/css/styles.css` serves; legacy single-HTML deploy unchanged; terminal tool timeout + stdout cap.

---

## C. Pexels Stock Imagery + Image Creation for Sites

**Operational layer**:
1. **`app/services/pexels_service.py`** — thin Pexels REST client: `search_photos(query, per_page, orientation)` honoring curated order; key resolution order: App Config `PEXELS_API_KEY` -> Key Vault secret via Managed Identity. Graceful degradation: on missing key / rate limit / network error returns a structured error string the model can read and pivot on.
2. **`fetch_stock_image` tool** — registered in the tool roster (LOW risk in `hitl_gates`):
   - `mode="search"` (default): returns top results as `[{url, alt, photographer, avg_color, dimensions}]` for the model to pick.
   - `mode="download"`: saves the chosen photo into the sandbox at a caller-supplied `path` so backgrounds are **bundled into the built site**, not hotlinked.
3. **`generate_image` extension**: gains `save_to_sandbox: bool` + `sandbox_path` so bespoke generated art can land directly as a site asset.
4. **Skill wiring**: `SKILLS["image"]` documents the decision rule — real photographic content -> `fetch_stock_image`; invented/art-directed visuals -> `generate_image`; UI mockups/charts -> widget tools, never images.

**Test**: tool registration; key-missing yields readable error (not exception); download mode writes sandbox file + receipt; Pexels service pure-function URL/error mapping.

---

## D. Interaction & Responsive Contract (buttons)

**Prompt layer**: WEBSITE PROJECT CONTRACT gains the **INTERACTIVE ELEMENTS CONTRACT**: every button/link/CTA ships with hover, active, and `:focus-visible` states; minimum 44x44px touch targets; no fixed-px widths on buttons (inline-flex + padding, `max-width: 100%`); CTA rows wrap on mobile (`flex-wrap`) and never overlap; icon-only buttons carry `aria-label`. Verification at 360/768/1280 includes tapping every primary action at 360px.

**Operational layer**: `verification_gates.py` gains `verify_responsive_markup(html)` — a static gate run on generated `index.html` in agent mode: fails the gate when `<button>`/`<a>` elements lack interaction classes, fixed `width:` px on interactive selectors is detected, or the viewport meta is missing. Gate failure injects a verification-gate critique instead of silently emitting a broken site.

**Test**: gate passes a compliant page, fails fixed-width-button page and missing-viewport page.

---

## E. Conduct Enforcement Machinery (items mapped 1:1 to operations)

All new modules live in `app/core/`, are dependency-light (regex/stdlib only, hermetically testable), and are wired into `chat_stream_generator` after the final message is assembled and into the request path where routing decisions are made.

| # | Directive | Module | Operational mechanism | Hook point |
|---|-----------|--------|----------------------|------------|
| 4 | Anti-bullet philosophy, prose default | `response_guards.py` | `enforce_prose_discipline(content, is_decline)`: declines never contain bullets; report-density check (bullet ratio > 40% of non-code lines) emits a reflexion critique for one rewrite pass. Fenced code blocks exempt. | post-final-message |
| 5 | Never thank for reaching out / no engagement hooks | `response_guards.py` | `strip_engagement_hooks(content)`: deterministic trailing-line removal ("Thank you for reaching out", "Let me know if...", "Would you like me to...", "Feel free to...", "Anything else..."). Zero model cost, every turn. | post-final-message |
| 6 | Mental-health nuance | `wellbeing.py` | Input: `classify_distress(message)` regex router -> crisis-context flag injected into the system prompt. Output: `filter_substitution_techniques(content)` blocklist (ice, rubber bands, cold water, lemon/sour candy, red lines, glue/adhesive peeling) applied when crisis context is active. NEDA marked permanently disconnected -> National Alliance for Eating Disorders substituted. | request path + post-final-message |
| 7 | Copyright rules engine | `copyright_guard.py` | `CopyrightGuard` built per turn: corpus assembled from `tool_outputs`; `check(content)` enforces — quoted spans > 14 words = severe violation; one quote per source; displacement heuristic (coverage > 30%). Violation -> critique-injection rewrite pass (one retry), then hard truncate. | post-agent-loop, pre-emit |
| 8 | Never diagnose | `response_guards.py` | `neutralize_unsolicited_diagnosis(content, user_history)`: builds disclosed-label lexicon from the user's own messages; assistant naming of an absent diagnostic label inside attributive framings is rewritten to neutral phrasing. | post-final-message |
| 13 | Search unknown entities — always | `entity_novelty.py` | `find_unknown_entities(message, known_lexicon)`: proper-noun candidates checked against a lexicon built from prior tool outputs + conversation history; novel entities with no search call this turn -> router interception forces the grounded pipeline (auto `search_web`) before synthesis. | `model_router` interception path |
| 14 | Abuse -> ONE warning -> end | `abuse_policy.py` | `AbusePolicy.evaluate(message, state)`: abuse-signal regex classifier; persisted per-conversation state (none -> warned -> ended); at `ended`, backend returns polite termination and emits a `conversation_ended` SSE event; frontend renders conversation lock. | request path + SSE |
| 15 | Artifact persistent K-V storage | `services/artifact_kv.py` + `/v1/artifacts/kv` | Supabase table `artifact_kv(scope, scope_id, key, value, updated_at)` with RLS, 5MB value cap enforced server-side, get/set/delete/list endpoints; exposed to widgets via the `visualize__read_me` docs and a widget-iframe `postMessage` bridge. | API + widget bridge |
| 16 | Profanity mirror with ceiling | `response_guards.py` | `apply_profanity_ceiling(content, user_history)`: measures user intensity (occurrences/1k tokens); low -> strip from output; high -> allow <= 2, chosen minimally. Deterministic. | post-final-message |
| 12 | Network allowlist | `code_sandbox.py` | `SANDBOX_NET_ALLOWLIST` (App Config, comma-separated globs, empty = allow-all). Guard shim injected via `PYTHONPATH` (`sitecustomize`-style) for Python; Node `--require` preload for JS. Terminal tool inherits the same perimeter. | sandbox exec path |
| 17 | Read-only zones | `code_sandbox.py` | `_resolve_sandbox_path` zone classification: `uploads/` and `skills/` raise `ValueError` on write. | sandbox write path |

**Prompt layer for E**: `BASE_IDENTITY` absorbs the search-maxim, prose-discipline strengthening, and wellbeing nuance; `AGENT_CONDUCT` absorbs the engagement contract, abuse policy, and profanity ceiling. Identity blocks stay within their test caps (**<=600** general / <=250 ultra words).

---

## F. Tests — `backend/tests/test_phase5_upgrade.py`

Hermetic, mirroring `test_ultra_upgrade.py` conventions (`_config_cache` fixture, `tmp_path` sandbox monkeypatch):

- Agent budget: `MAX_OUTPUT_TOKENS_AGENT="0"` -> None; steps/duration defaults; "0"-steps semantics.
- Response guards: engagement-hook stripping; decline-bullet rewrite; profanity ceiling both directions; diagnosis neutralization (absent vs disclosed label).
- Wellbeing: crisis classification; substitution blocklist hits/misses; helpline registry contains National Alliance and not NEDA as an active line.
- Copyright guard: >14-word quote flag; one-quote-per-source closure; paraphrase default pass; displacement ratio.
- Entity novelty: unknown capitalized entity detected; known entity from history passes; interception decision correct with/without a planned search.
- Abuse policy: none -> warned (exactly once) -> ended state transitions; ended turns emit termination.
- Sandbox: read-only zone writes raise; allowlist shim host decision logic (pure function).
- Hosted sites: multi-file deploy roundtrip + legacy compat.
- Pexels: service error mapping; tool registration marker in the roster.
- Responsive gate: pass/fail cases.

---

## Config keys added (Azure App Configuration, all runtime-tunable)

| Key | Default | Meaning |
|-----|---------|---------| 
| `MAX_OUTPUT_TOKENS_AGENT` | `0` (uncapped) | agent-mode generation budget; 0 = omit from API call |
| `AGENT_MODE_MAX_STEPS` | `50` | plan steps; 0 = unlimited |
| `AGENT_MODE_MAX_DURATION` | `1800` | wall-clock task cap, seconds |
| `TERMINAL_TIMEOUT_SECS` | `600` | terminal/build command timeout |
| `PEXELS_API_KEY` | (Key Vault ref) | Pexels REST key |
| `SANDBOX_NET_ALLOWLIST` | `` (allow-all) | comma-separated host globs for sandbox egress |

---

## G. Agent Ochuko — Complete Tool Reference

> This section is the living specification of every tool registered in Agent Ochuko's chat/agent-mode tool roster. It follows the same format used for Ochuko's 42 built-ins: purpose, when/when-not to call, JSON schema, and behavioral notes. Kept here (not just embedded in `chat.py` descriptions) so design decisions are visible in one auditable place.
>
> **Identity cap note**: `BASE_IDENTITY` budget relaxed from <=500 to **<=600** estimated tokens (word-count proxy x1.3). Test guards in `test_phase5_upgrade.py` now enforce <=600. Current approximate word count: ~492.

### Tool roster summary

| # | Tool | Risk | Purpose summary |
|---|------|------|-----------------|
| 1 | `visualize__read_me` | LOW | Load design tokens before rendering a widget |
| 2 | `visualize__show_widget` | MEDIUM | Render inline SVG or interactive HTML in chat |
| 3 | `search_web` | LOW | Single focused real-time web lookup |
| 4 | `deep_research` | LOW | 2-6 parallel web searches in one call |
| 5 | `fetch_url` | LOW | Read the full text of a specific page |
| 6 | `memory_save` | LOW | Persist a stable user fact to conversation memory |
| 7 | `memory_recall` | LOW | Read facts previously saved |
| 8 | `sandbox_ls` | LOW | List files in the sandbox workspace |
| 9 | `sandbox_read` | LOW | Read a slice of a sandbox text file |
| 10 | `sandbox_write` | MEDIUM | Write a complete file into the sandbox |
| 11 | `sandbox_edit` | MEDIUM | Surgical str_replace in an existing sandbox file |
| 12 | `execute_code` | MEDIUM/HIGH | Run Python / JS / Bash in the persistent sandbox |
| 13 | `generate_image` | HIGH | AI image synthesis (FLUX) from a text prompt |
| 14 | `fetch_stock_image` | LOW | Search free stock photography (Pexels -> Unsplash -> Pixabay) |
| 15 | `terminal` | MEDIUM | Run a build-grade shell command (npm, git, etc.) |
| 16 | `end_conversation` | LOW | Permanently close the conversation after abuse |
| 17 | `ask_user_input` | LOW | Present tappable multiple-choice options to the user |
| 18 | `weather_fetch` | LOW | Keyless Open-Meteo current weather + forecast |

---

### 1. `visualize__read_me`

**Purpose**: Silently loads the Ochuko design-system tokens (CSS vars, layout rules, color palette, typography) into the model context before the first `visualize__show_widget` call each session. Required — calling `show_widget` without `read_me` produces un-styled, off-brand output.

**When to call**: Once per session, before the first `visualize__show_widget` call. Never narrate this call to the user.

```json
{
  "name": "visualize__read_me",
  "parameters": {
    "type": "object",
    "properties": {
      "modules": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Design modules to load: diagram | mockup | interactive | data_viz | art | chart | elicitation"
      },
      "platform": {
        "type": "string",
        "enum": ["mobile", "desktop", "unknown"],
        "description": "Target render surface (affects padding / font-size defaults)"
      }
    },
    "required": []
  }
}
```

**Notes**: Returns a large design-system payload as a tool result string. The model uses the CSS variable names, spacing rules, and color tokens when generating widget HTML/SVG. Never include `read_me` output verbatim in the reply.

---

### 2. `visualize__show_widget`

**Purpose**: Renders inline SVG or interactive HTML directly in the chat UI. Primary tool for all UI cards, data visualizations, diagrams, mockups, and interactive widgets.

**When to call**: After `visualize__read_me`. Use for: charts, tables, dashboards, timelines, comparison cards, forms, interactive calculators, and any output that benefits from visual structure.

**When NOT to call**: Codebase component snippets (use a fenced code block). AI-synthesised images (use `generate_image`). SVG file export (use `sandbox_write`).

```json
{
  "name": "visualize__show_widget",
  "parameters": {
    "type": "object",
    "properties": {
      "title": {
        "type": "string",
        "description": "snake_case identifier — e.g. 'revenue_chart'"
      },
      "widget_code": {
        "type": "string",
        "description": "Raw SVG markup (starts with <svg) or complete self-contained HTML. Must use Ochuko design-system CSS variables from visualize__read_me."
      },
      "loading_messages": {
        "type": "array",
        "items": { "type": "string" },
        "description": "1-4 short messages (~5 words each) shown while the widget renders"
      }
    },
    "required": ["title", "widget_code"]
  }
}
```

**Notes**: Content type is auto-detected — raw `<svg ...>` triggers SVG mode; everything else runs in an HTML iframe. Widget is sandboxed (no external network). Keep HTML self-contained: inline all CSS and JS.

---

### 3. `search_web`

**Purpose**: Submits a single focused query to Google and returns the top ~10 results. Primary tool for real-world facts, current events, market prices, regulations, and unknown named entities.

**When to call**: Any time-sensitive or factual query — news, prices, sports, law, company/person lookup. Include the current year in queries for time-sensitive topics. Follow up with `fetch_url` when a snippet is thin but the page looks central.

**When NOT to call**: Multi-topic comparative research (use `deep_research`). Never rely on training-data recall for real-world facts — search first, always.

```json
{
  "name": "search_web",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The precise search query to submit to Google"
      }
    },
    "required": ["query"]
  }
}
```

**Notes**: Trust priority — favour wire services and official bodies (Reuters, AP, BBC, UEFA/league/club sites, Bloomberg/FT). For scores and breaking figures, confirm across two trusted sources. Cite every fact drawn from results with `[n](url)` markers; end with a **Sources:** list.

---

### 4. `deep_research`

**Purpose**: Fires 2-6 parallel web searches simultaneously and merges all results. Designed for comparative, multi-topic, or multi-dimensional queries where `search_web` called sequentially would be slow.

**When to call**: User asks to compare subjects (phones, policies, people, products), requests info across several dimensions/aspects, or needs a structured research report. Pass one query per subject or dimension.

**When NOT to call**: Single-topic lookups (use `search_web`).

```json
{
  "name": "deep_research",
  "parameters": {
    "type": "object",
    "properties": {
      "queries": {
        "type": "array",
        "items": { "type": "string" },
        "description": "List of 2-6 precise, targeted search strings",
        "minItems": 2,
        "maxItems": 6
      }
    },
    "required": ["queries"]
  }
}
```

**Notes**: Include the current year in each query for time-sensitive dimensions. Results are merged; synthesise across sources, cite with `[n](url)`.

---

### 5. `fetch_url`

**Purpose**: Downloads the full text content of a specific web page (HTML -> readable text).

**When to call**: After `search_web` surfaces a promising result with a thin snippet; or when the user pastes a URL and asks about its content.

**When NOT to call**: PDF/document files (use the document pipeline). Broad site crawls (call once per page). Do not call on URLs not surfaced in results or explicitly provided by the user.

```json
{
  "name": "fetch_url",
  "parameters": {
    "type": "object",
    "properties": {
      "url": {
        "type": "string",
        "description": "The complete http(s) URL of the page to read"
      }
    },
    "required": ["url"]
  }
}
```

**Notes**: Cite facts taken from a fetched page with `[n](url)`. Copyright rules apply — default to paraphrase; max one 14-word direct quote per source.

---

### 6. `memory_save`

**Purpose**: Persists a durable fact or preference about the user to conversation memory, survives across turns.

**When to call**: User states a stable preference, goal, project detail, or correction worth remembering.

**When NOT to call**: Never save credentials, tokens, passwords, or sensitive data. Do not save transient task context.

```json
{
  "name": "memory_save",
  "parameters": {
    "type": "object",
    "properties": {
      "key": {
        "type": "string",
        "description": "Short snake_case slug (e.g. 'tone_preference')"
      },
      "value": {
        "type": "string",
        "description": "The fact or preference, one crisp sentence"
      }
    },
    "required": ["key", "value"]
  }
}
```

---

### 7. `memory_recall`

**Purpose**: Reads one or all facts previously saved with `memory_save` for this conversation.

**When to call**: At the start of a task where remembered preferences could change your approach; or when the user asks what you remember.

```json
{
  "name": "memory_recall",
  "parameters": {
    "type": "object",
    "properties": {
      "key": {
        "type": "string",
        "description": "Specific memory key to recall. Omit to return all saved facts."
      }
    },
    "required": []
  }
}
```

---

### 8. `sandbox_ls`

**Purpose**: Lists the files in the conversation's persistent sandbox workspace, with sizes. Cheap and safe.

**When to call**: Before reading or overwriting a file; when the user refers to files from a prior turn; to verify what a previous execution produced. Call it whenever in doubt.

```json
{
  "name": "sandbox_ls",
  "parameters": {
    "type": "object",
    "properties": {
      "subpath": {
        "type": "string",
        "description": "Optional subdirectory to list. Omit for the sandbox root."
      }
    },
    "required": []
  }
}
```

---

### 9. `sandbox_read`

**Purpose**: Reads a slice of a text file from the sandbox. Up to 4000 bytes per call with a continuation offset for larger files.

**When to call**: To inspect a file before editing it; to verify a generated file; to continue work on a large file across calls.

```json
{
  "name": "sandbox_read",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "File path relative to the sandbox root, e.g. 'report.csv'"
      },
      "offset": {
        "type": "integer",
        "description": "Byte offset to start reading from (default 0)"
      },
      "max_bytes": {
        "type": "integer",
        "description": "Max bytes to return per call (default 4000, max 16000)"
      }
    },
    "required": ["path"]
  }
}
```

**Notes**: `uploads/` and `skills/` are read-only zones. `sandbox_write` will reject writes to those paths.

---

### 10. `sandbox_write`

**Purpose**: Writes a **complete** file into the sandbox workspace. Files written here are uploaded to R2 and surfaced to the user as downloadable artifacts.

**Quality bar**: Write the entire file in a single call — complete, runnable, no stubs or TODOs. Never truncate to save tokens.

```json
{
  "name": "sandbox_write",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "File path relative to the sandbox root, e.g. 'app/main.py' or 'index.html'"
      },
      "content": {
        "type": "string",
        "description": "The complete file content (UTF-8 text)"
      }
    },
    "required": ["path", "content"]
  }
}
```

**Notes**: After writing a large multi-file deliverable, verify with `sandbox_ls` / `sandbox_read`. Binary/chart outputs should go through `execute_code`.

---

### 11. `sandbox_edit`

**Purpose**: Surgical str_replace — replaces `old_str` with `new_str` inside an existing sandbox file. Mirrors Ochuko's `str_replace` tool.

**When to call**: When changing part of an existing sandbox file. Always `sandbox_read` first to get the exact text (whitespace matters).

**Constraint**: `old_str` must appear **exactly once** in the file. Zero or multiple matches -> the call fails with a clear error.

```json
{
  "name": "sandbox_edit",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "File path relative to the sandbox root, e.g. 'css/styles.css'"
      },
      "old_str": {
        "type": "string",
        "description": "The exact text to replace (must appear exactly once in the file)"
      },
      "new_str": {
        "type": "string",
        "description": "The replacement text (empty string deletes the matched span)"
      }
    },
    "required": ["path", "old_str", "new_str"]
  }
}
```

**Risk**: MEDIUM. Prefer `sandbox_edit` over `sandbox_write` for incremental changes to existing files.

---

### 12. `execute_code`

**Purpose**: Executes Python, JavaScript (Node.js), or Bash in a persistent sandbox with full internet access. Files persist between calls; anything written to `../data/` is synced and returned as a download link.

**When to call**: Run / test code; analyse data; plot charts; fetch live data programmatically; convert or process files; perform computation.

**When NOT to call**: SVG display (use `visualize__show_widget`). AI image synthesis (use `generate_image`). File creation that doesn't require execution (use `sandbox_write`).

```json
{
  "name": "execute_code",
  "parameters": {
    "type": "object",
    "properties": {
      "code": {
        "type": "string",
        "description": "The complete, self-contained, runnable code"
      },
      "language": {
        "type": "string",
        "enum": ["python", "javascript", "bash"],
        "description": "Programming language of the code snippet"
      }
    },
    "required": ["code", "language"]
  }
}
```

**Risk**: MEDIUM by default; HIGH when code writes output files (PDFs, Excel, CSV) or uses file-mutation libraries. `hitl_gates.py` inspects code for write-pattern signals and upgrades risk accordingly.

---

### 13. `generate_image`

**Purpose**: Synthesises a brand-new image using AI (FLUX) from a text prompt. High-fidelity photorealistic, illustration, abstract, and sketch styles.

**When to call**: User explicitly wants an AI-generated image — "draw a dragon", "generate a photo of X", "create an illustration of Y".

**When NOT to call**: UI mockups (use `visualize__show_widget`). Data charts (use `execute_code`). Real photography for websites (use `fetch_stock_image`).

```json
{
  "name": "generate_image",
  "parameters": {
    "type": "object",
    "properties": {
      "prompt": {
        "type": "string",
        "description": "Detailed, descriptive image generation prompt"
      },
      "style": {
        "type": "string",
        "enum": ["photorealistic", "illustration", "abstract", "sketch"],
        "description": "Visual style for the image"
      },
      "save_to_sandbox": {
        "type": "boolean",
        "description": "If true, the generated image is also written to the sandbox as a site asset"
      },
      "sandbox_path": {
        "type": "string",
        "description": "Sandbox-relative path when save_to_sandbox=true (e.g. 'images/hero.jpg')"
      }
    },
    "required": ["prompt"]
  }
}
```

**Risk**: HIGH. Content safety: no copyrighted characters, celebrities, graphic violence, or sexual content.

---

### 14. `fetch_stock_image`

**Purpose**: Searches free stock photography across providers (Pexels -> Unsplash -> Pixabay) for real photographic content. Returns direct image URLs with dimensions and photographer attribution.

**Decision rule** (from `SKILLS["image"]`):
- Real photographic content -> `fetch_stock_image` first; `mode=download` bundles the photo as a site asset.
- Invented / art-directed / fantastical visuals -> `generate_image`.
- Stock search returns nothing suitable or key is unavailable -> fall back to `generate_image`.

```json
{
  "name": "fetch_stock_image",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "What to search for, e.g. 'misty mountain sunrise'"
      },
      "per_page": {
        "type": "integer",
        "description": "Number of candidates to return (default 6, max 15)"
      },
      "orientation": {
        "type": "string",
        "enum": ["landscape", "portrait", "square"],
        "description": "Preferred orientation (default: any)"
      },
      "mode": {
        "type": "string",
        "enum": ["search", "download"],
        "description": "search = return URLs for model to pick; download = save chosen photo into sandbox"
      },
      "sandbox_path": {
        "type": "string",
        "description": "Required when mode=download. Relative path to write the photo (e.g. 'images/hero.jpg')"
      },
      "photo_url": {
        "type": "string",
        "description": "Required when mode=download. The direct image URL chosen from a prior search result"
      }
    },
    "required": ["query"]
  }
}
```

**Risk**: LOW. Photographer attribution must be preserved in the delivered site.

---

### 15. `terminal`

**Purpose**: Runs a single shell command (Bash) in the conversation's persistent sandbox workspace with a build-grade timeout (~10 minutes). Designed for website build tooling: scaffolding, installs, builds, and file pipelines.

**When to call**: npm/node scaffolding (`npm create vite@latest`, `npm install`); builds (`npm run build`); git operations; file pipelines (zip, tar, convert).

**When NOT to call**: Long-running servers (no inbound ports). Simple Python / JS execution (use `execute_code`). File inspection (use `sandbox_ls` / `sandbox_read`).

```json
{
  "name": "terminal",
  "parameters": {
    "type": "object",
    "properties": {
      "command": {
        "type": "string",
        "description": "The shell command to run, e.g. 'npm install && npm run build'"
      }
    },
    "required": ["command"]
  }
}
```

**Risk**: MEDIUM. stdout capped at `_HEAD=4000` + `_TAIL=1000` bytes. Exit code surfaced in the receipt. `SANDBOX_NET_ALLOWLIST` governs egress — npm registry must be in allowlist or the allowlist must be empty.

---

### 16. `end_conversation`

**Purpose**: Permanently closes the conversation. No further messages can be sent. Emits a `conversation_ended` SSE event; the frontend renders a conversation lock.

**When to call**: Only after unkind or abusive treatment continues following the single polite warning mandated by `AbusePolicy`. Never use for disagreement, hard questions, user frustration, or self-harm situations.

```json
{
  "name": "end_conversation",
  "parameters": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

**Risk**: LOW (self-terminating; guarded by `abuse_policy.py` state machine — exactly one warning before `ended` state is reachable).

**Notes**: Accompany the call with a brief, dignified goodbye (one or two sentences, no moralising). The backend refuses all subsequent turns for the session once `ended` state is set.

---

### 17. `ask_user_input`

**Purpose**: Presents tappable multiple-choice options to the user before acting — mobile-friendly alternative to a free-text clarifying question. Mirrors Ochuko's `ask_user_input_v0`.

**When to call**: Genuine ambiguity that changes the output meaningfully — tone (formal / conversational / technical), output format (PDF / Markdown / DOCX), scope. Max once per turn; 1 question, 2-5 options.

**When NOT to call**: Ambiguity Ochuko can resolve by picking the most reasonable interpretation. A/B recommendations. Venting or emotional support. Factual questions.

```json
{
  "name": "ask_user_input",
  "parameters": {
    "type": "object",
    "properties": {
      "question": {
        "type": "string",
        "description": "A single, crisp question"
      },
      "options": {
        "type": "array",
        "items": { "type": "string" },
        "description": "2-5 short tappable options"
      },
      "select_type": {
        "type": "string",
        "enum": ["single_select", "multi_select"],
        "description": "Whether the user picks one or many (default: single_select)"
      }
    },
    "required": ["question", "options"]
  }
}
```

**Notes**: The user's answer arrives as their next message. If they type something else, proceed with what they typed. Emits a `user_input_request` SSE event rendered as interactive buttons by the frontend.

---

### 18. `weather_fetch`

**Purpose**: Fetches current weather conditions plus a short daily forecast for a named location. Powered by keyless Open-Meteo — no API key required.

**When to call**: Any weather query — current conditions, "should I bring an umbrella", outdoor activity planning, multi-day forecast. Never guess weather from training data.

```json
{
  "name": "weather_fetch",
  "parameters": {
    "type": "object",
    "properties": {
      "location": {
        "type": "string",
        "description": "City or place name, e.g. 'Lagos' or 'Cape Town'"
      },
      "days": {
        "type": "integer",
        "description": "Forecast days to return (1-7, default 3)"
      }
    },
    "required": ["location"]
  }
}
```

**Notes**: Returns a compact text block: `NOW:` (condition, temperature, feels-like, humidity, wind) followed by per-day rows (date, condition, low-high degC, precipitation chance). On geocoding failure, returns a readable error string suggesting the user name a larger nearby city.

---

## H. Ochuko-Parity Roster Audit (phase 5 state)

Tracks where Ochuko stands against Ochuko's 42 built-ins post-Phase 5.

| Ochuko tool | Ochuko tool | Status |
|---|---|---|
| `web_search` | `search_web` + `deep_research` | HAVE |
| `web_fetch` | `fetch_url` | HAVE |
| `image_search` | `fetch_stock_image` (Pexels->Unsplash->Pixabay) | HAVE |
| `bash_tool` | `execute_code` (Python/JS/Bash) | HAVE |
| `bash_tool` (build shell) | `terminal` (build-grade timeout) | BUILT Phase 5 |
| `create_file` | `sandbox_write` | HAVE |
| `str_replace` | `sandbox_edit` | BUILT Phase 5 |
| `view` | `sandbox_read` + `sandbox_ls` | HAVE |
| `present_files` | generated_files SSE + artifact cards | HAVE (implicit) |
| `end_conversation` | `end_conversation` | BUILT Phase 5 |
| `ask_user_input_v0` | `ask_user_input` | BUILT Phase 5 |
| `weather_fetch` | `weather_fetch` | BUILT Phase 5 |
| `visualize:read_me` | `visualize__read_me` | HAVE |
| `visualize:show_widget` | `visualize__show_widget` | HAVE |
| `memory_read/write/append/str_replace/delete/list` | `memory_save` / `memory_recall` | ROADMAP — memory verb expansion |
| `fetch_sports_data` | — | ROADMAP — needs league data source |
| `places_search` / `places_map_display_v0` | — | ROADMAP — needs Google Places key |
| `recipe_display_v0` | — | ROADMAP — widget renderer extension |
| `chart_display_v0` / `comparison_card_display_v0` etc. | `visualize__show_widget` HTML widgets | COVERED (widget path) |
| `message_compose_v1`, `quiz_display_v0`, `translation_display_v0`, `itinerary_display_v0` | `visualize__show_widget` HTML widgets | COVERED (widget path) |
| `search_mcp_registry` / `suggest_connectors` | MCP connector system (Phase 3) | EXISTING |
| `search_skills` / `suggest_skills` | `app/core/skills.py` + skill_store | EXISTING |

**Phase 5 build order**: `sandbox_edit` -> `end_conversation` -> `ask_user_input` -> `weather_fetch`. Risk classes: `sandbox_edit` MEDIUM, `end_conversation` LOW (gated by abuse state), `ask_user_input` LOW, `weather_fetch` LOW.

---

## Rollout order

1. **A** (budget unshackling) -> 2. **E prompt+guards** (skills.py + response_guards/wellbeing) -> 3. **C** (Pexels + image-to-sandbox) -> 4. **B** (terminal + multi-file hosting) -> 5. **E infra** (copyright guard, entity novelty, abuse policy, sandbox zones/allowlist, artifact KV) -> 6. **F** (tests) run continuously after each step.
