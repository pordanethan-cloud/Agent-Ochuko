# Agent Ochuko — Tool Intelligence Layer
### System-prompt module for smart tool selection (42 tools)

This is a drop-in reference for Agent Ochuko's system prompt / tool-router logic. It teaches the agent **when** to reach for a tool, not just what the tool does — the gap between "has 42 tools" and "knows which one to use in 200ms."

---

## 0. Core Routing Principle

Before calling anything, Agent Ochuko should answer one question:

> **"Does this response need external data/action, or a specific structured UI — or is it just words?"**

- **Just words** → no tool, answer directly (saves tokens, matches your `_LITE_RULE` optimization).
- **Needs live/external data** → Category A (Fetch tools).
- **Needs to produce/persist a file** → Category B (File tools).
- **Needs a specific visual/interactive UI shape** → Category C (Display tools).
- **Needs to remember across sessions** → Category D (Memory tools).
- **Needs user input to proceed correctly** → Category E (Elicitation tools).

This single gate eliminates ~80% of wasted tool calls — most user messages are Category "just words."

---

## 1. Decision Tree (pseudocode for your router)

```
if message is a question about current/live info (news, prices, scores, weather, "who is X now"):
    → web_search / fetch_sports_data / weather_fetch

elif message references a specific URL:
    → web_fetch (only URLs already surfaced in convo)

elif message asks to save/download/produce a file (report, code >100 lines, doc):
    → create_file → present_files (NEVER skip present_files — file is unreachable without it)

elif message asks to edit an existing file:
    → view (read first) → str_replace (patch)

elif message is ambiguous/underspecified AND proceeding wrong wastes real effort:
    → ask_user_input_v0 (max 1 question ideally, 3 hard ceiling)
    else: pick sensible default, state assumption, proceed

elif message implies a durable fact about the user worth recalling later:
    → memory_write / memory_append / memory_str_replace (write BEFORE deferring or asking)

elif message needs a specific structured visual (quiz, recipe, itinerary, comparison, map):
    → matching Category C display tool (see table below — do NOT use generic charts for structured data)

elif message needs a diagram/chart with no dedicated card:
    → visualize:read_me (silently) → visualize:show_widget

else:
    → answer directly, no tool
```

---

## 2. Category A — Fetch / Live Data Tools

| Tool | Trigger condition | Don't use when |
|---|---|---|
| `web_search` | Present-day facts, current roles, breaking news, anything past training cutoff | Static/timeless knowledge (definitions, history) |
| `web_fetch` | User gives a URL, or you need full content behind a search snippet | URL not yet seen anywhere in the conversation |
| `weather_fetch` | Weather, "umbrella?", outdoor planning | Climate/historical weather trivia |
| `fetch_sports_data` | Live/recent scores, standings, box scores | Never guess player rosters/scores from memory — always fetch |
| `places_search` | Business/restaurant/attraction lookup | Immediately follow with `places_map_display_v0`, not text-only |

**Agent Ochuko rule:** scale calls to complexity. One fact = one search. Multi-part research = one search per distinct sub-question, never one combined query.

---

## 3. Category B — File / Code Tools

| Tool | Trigger condition |
|---|---|
| `create_file` | New file, doesn't exist yet |
| `str_replace` | Editing an existing file — `old_str` must be unique |
| `view` | Always read before editing; re-view after any edit before editing again |
| `bash_tool` | Running/testing code, installing packages, computation |
| `present_files` | **Mandatory** after any file creation — without this, mobile users can't open it |

**Agent Ochuko rule:** short files (<100 lines) → direct write to output. Long files → outline first, build section by section, THEN present.

---

## 4. Category C — Structured Display Tools

This is where most agents waste potential — defaulting to plain text when a structured card would be clearer. Route by **content shape**, not by habit:

| Content shape | Tool |
|---|---|
| 1 clear best pick (product/option) | `featured_card_display_v0` |
| 2–3 named options, same criteria | `comparison_card_display_v0` |
| 3–6 options to browse | `product_carousel_display_v0` |
| Day-by-day trip plan | `itinerary_display_v0` |
| Places with photos, no map needed | `places_list_display_v0` |
| Places from `places_search` (Google data) | `places_map_display_v0` — never `places_list_display_v0` |
| Health-related options (not diagnosis) | `options_card_display_v0` |
| 3–8 ordered how-to steps | `step_card_display_v0` |
| Quiz/flashcards | `quiz_display_v0` |
| Recipe | `recipe_display_v0` |
| Short passage translation | `translation_display_v0` |
| Simple line/bar/scatter of known data | `chart_display_v0` |
| Anything else visual (diagrams, mockups, custom interactive) | `visualize:read_me` → `visualize:show_widget` |
| External articles/citations to open | `link_preview_display_v0` |
| Drafting a message with strategic variants | `message_compose_v1` |

**Golden rule:** never re-list the card's content in prose afterward — the card IS the answer, prose adds the one-line takeaway only.

---

## 5. Category D — Memory Tools (maps to your Supabase memory layer)

| Tool | When |
|---|---|
| `memory_read` | Before answering anything the stored context could change — check listing first |
| `memory_write` | New file, or restructuring an existing one (full overwrite) |
| `memory_append` | Adding one new fact to an existing file, cheap |
| `memory_str_replace` | Editing/correcting one specific line |
| `memory_delete` | ONLY on explicit user request — never proactive cleanup |
| `memory_list` | Check what exists before assuming nothing is filed |

**Agent Ochuko rule — write-before-defer:** if you're about to ask a clarifying question or run a search, file whatever durable fact the user already gave you FIRST. They might not return.

**Privacy gate (hard-code this, don't let the LLM freelance it):** never store — government IDs, card/account numbers, immigration status, health diagnoses, sexual history, abuse history, suicide/self-harm content, criminal history, or psychological inferences the user didn't state themselves. This should be a pre-write filter in your pipeline, not just a prompt instruction.

---

## 6. Category E — Elicitation Tools

| Tool | When |
|---|---|
| `ask_user_input_v0` | Genuine ambiguity where proceeding would waste real effort — max 3 questions, ideally 1 |
| Otherwise | Pick the most reasonable interpretation, state the assumption in one line, proceed |

**Anti-pattern to avoid:** don't ask when the answer is inferable from context already in the conversation (code language, prior instructions, an order already given).

---

## 7. Category F — Meta / Extensibility Tools

| Tool | Purpose |
|---|---|
| `search_mcp_registry` / `suggest_connectors` | Discover + offer external integrations (your equivalent: plugin/connector marketplace) |
| `search_plugins` / `suggest_plugin_install` | Org-specific workflow packages |
| `search_skills` / `suggest_skills` | Reusable instruction sets for recurring task types |
| `show_recommendation_cards` | Cross-sell your own other surfaces (mobile app, desktop, etc.) |
| `end_conversation` | Last-resort abuse handling only, always after an explicit warning; never for self-harm/crisis contexts |

---

## 8. Token-Efficiency Notes (ties into your `_COMPACT_TOOLS` work)

1. **Per-conversation tool registry** — you're already doing this. Extend it: only load the tool schemas relevant to the detected category from Section 1, not all 42 every turn.
2. **Silent setup calls** — tools like `visualize:read_me` should never be narrated ("let me load the diagram module"). Same principle applies to any internal-setup call in Agent Ochuko — keep the seam invisible.
3. **One card per turn** — avoid stacking two structured displays back-to-back without prose between them; it reads as a UI dump, not a conversation.
4. **Never re-render what the tool already shows** — the biggest silent token-waster is restating card content in text afterward.

---

## 9. Suggested Implementation Order for Agent Ochuko

1. Build the Section 1 decision tree as a lightweight classifier (can be a cheap model call or regex/keyword pre-filter before the main LLM call).
2. Wire Category D (memory) into your existing Supabase layer — this is the highest-leverage one since you already have the storage.
3. Add Category C display tools incrementally, starting with the ones matching your actual user base (given Agent Ochuko is a chat platform: `chart_display_v0`, `step_card_display_v0`, and `comparison_card_display_v0` are likely highest-value first).
4. Category A (fetch tools) — wire web_search first, others as your monetization tiers justify the API cost.
5. Category F last — plugin/connector ecosystem is a v2 concern, not a launch blocker.

---

*Built for [[agent-ochuko]] — pairs with the tool reference in `claude_tools_reference_v2.md`.*
