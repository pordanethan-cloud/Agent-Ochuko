# Agent Ochuko — Architecture Improvement Proposal
### From 18 Tools to Claude-Grade Parity: Structured Output Layer, Router Efficiency & Memory Integrity

> Companion to `06_tools_architecture_claude_parity_and_ooda_loop.md`. This doc identifies the concrete gap between Ochuko's current 18-tool roster and full Claude-grade parity, then specifies exactly what to build, in what order.

---

## 1. Where Ochuko Already Wins

Worth stating plainly before the gap analysis — Ochuko's current architecture beats a lot of production agents on:
- **Surgical edits** (`sandbox_edit`) — exact parity with Claude's `str_replace_editor`.
- **Entity-novelty forced grounding** — this is *ahead* of documented Claude behavior; Claude decides to search from prompt instructions, Ochuko mechanically intercepts it.
- **Read-only perimeter + network allowlist** — stronger sandboxing than most agent frameworks bother with.
- **Deadlock breaker** (`tool_choice="none"` on final iteration) — solves a real failure mode (infinite tool loops) that plenty of agentic systems still hit in production.
- **Post-loop conduct guards as deterministic code, not model instructions** — cheaper and more reliable than prompting for tone.

The gap isn't reasoning architecture. It's **output surface area** — what the user actually sees rendered — and **routing efficiency** at scale.

---

## 2. Gap Analysis: 18 Tools vs 42

| Domain | Ochuko has | Claude has that Ochuko doesn't | Verdict |
|---|---|---|---|
| Research | `search_web`, `deep_research`, `fetch_url` | — | **Parity, arguably ahead** (deep_research auto-parallelizes) |
| Memory | `memory_save`, `memory_recall` | Versioned edits (`memory_str_replace`, `memory_append`), file listing with previews, explicit delete-only-on-request | **Gap: no optimistic concurrency, no partial edits** |
| File System | `sandbox_ls/read/write/edit` | — | **Parity** |
| Execution | `execute_code`, `terminal` | — | **Parity, arguably ahead** (terminal build-grade timeout) |
| Visual Media | `generate_image`, `fetch_stock_image` | `image_search` | **Parity** (Ochuko's is actually more capable — generation + stock) |
| Widgets | `visualize__read_me/show_widget` | Same pattern | **Parity** |
| **Structured Display** | **none** | 15 purpose-built display cards (comparison, carousel, itinerary, quiz, recipe, steps, translation, chart, map, places, options, message-compose, link-preview, featured-product) | **Major gap — this is the whole missing category** |
| Elicitation | `ask_user_input` | `ask_user_input_v0` | **Parity** |
| Realtime | `weather_fetch` | Same + `fetch_sports_data` | **Minor gap** |
| Meta/Extensibility | none | Skill/plugin/connector discovery-and-suggest tools | **Gap, but lowest priority — v2 concern** |
| Safety | `end_conversation` | Same | **Parity** |

**The headline finding:** Ochuko's *reasoning* and *execution* layers are Claude-grade or better. Its *presentation* layer is not — everything currently comes back as markdown prose or a single generic widget call. That's the highest-leverage gap to close, because it's the difference the user actually sees on every single turn, not just coding tasks.

---

## 3. Proposed Addition: The Structured Display Layer

Rather than porting all 15 display tools 1:1, consolidate into **6 new tool contracts** that cover the same ground with less schema surface area to route between — this matches Ochuko's existing philosophy of tight, purposeful tools rather than tool sprawl.

### Domain: **UI & Widgets** (extend existing domain)

| Tool Name | Operational Mechanism | Replaces / Covers |
|---|---|---|
| `render_options_card` | Structured N-option comparison/pick UI | Claude's comparison_card, featured_card, product_carousel, options_card — unified via an `options` array + `mode: "compare"\|"single_pick"\|"carousel"` |
| `render_step_flow` | Ordered stepper or checklist UI | step_card_display_v0, recipe_display_v0 (recipe becomes `mode: "recipe"` with ingredient scaling) |
| `render_itinerary` | Day-tabbed schedule with stops | itinerary_display_v0 |
| `render_map` | Location pins + optional route, backed by a places search | places_map_display_v0 + places_search combined into one contract (search, then auto-render) |
| `render_quiz` | Multiple-choice quiz / flashcard flip UI | quiz_display_v0 |
| `render_translation` | Side-by-side source/target text card | translation_display_v0 |

**Why consolidate instead of porting all 15:** Ochuko already fights token budget via `_COMPACT_TOOLS`. Adding 15 new schemas raw would roughly double roster size. Consolidating to 6 parametrized tools keeps the roster at **24 tools total** — a 33% increase for near-total feature parity, instead of a 133% increase.

### Tool Contract — `render_options_card` (flagship example, full Claude-grade contract)

```
WHEN to call:
  - User is choosing between 2+ named things (products, approaches, plans) that share comparable attributes
  - A single best recommendation is being made and deserves a rich visual treatment, not just a text answer

WHEN NOT to call:
  - Fewer than 2 attributes worth comparing (just answer in prose)
  - The options aren't purchasable/selectable things — abstract tradeoffs go in prose, not this card
  - You already rendered one this turn — don't stack cards without prose between them

QUALITY BAR:
  - Every option must use the SAME attribute label set, in the SAME order, so rows align
  - mode="single_pick" requires exactly 1 option with a full justification blurb
  - mode="compare" requires 2-3 options; mode="carousel" allows up to 6
  - Never re-list attribute values in prose after the card renders — the card IS the answer

DUTY:
  - If any option has a real product URL, include it — never fabricate a link
  - Write the one-sentence summary field LAST, after the options are finalized
```

```json
{
  "name": "render_options_card",
  "parameters": {
    "mode": "single_pick | compare | carousel",
    "summary": "string, <15 words, for surfaces that can't render the card",
    "options": [
      {
        "name": "string",
        "price": "string (optional)",
        "url": "string (optional, real link only)",
        "blurb": "string (mode=single_pick/carousel — up to a paragraph)",
        "attributes": [
          { "label": "string", "value": "string" }
        ]
      }
    ]
  }
}
```

Apply the same contract discipline (WHEN / WHEN NOT / QUALITY BAR / DUTY) to the other 5 — don't skip this step. This is the actual mechanism that made your `sandbox_edit` and `sandbox_write` contracts good; reuse it here rather than writing thin descriptions.

---

## 4. Router-Level Fix: The Category Gate

Right now, Ochuko's invocation intelligence (Section 4 of the architecture doc) handles **whether to search** (entity novelty) and **which model tier** to route to (complexity classifier). It does not yet answer **which tool category is even relevant** before the model sees the full schema list.

### Proposed addition: pre-model Category Gate

Insert this as a cheap, deterministic (or nano-model) pre-classification step, *before* `Router: Complexity Classifier` in the existing flowchart:

```
Prompt[User Input Message] --> CategoryGate[Category Gate: keyword + intent classifier]
CategoryGate -- "no external need detected" --> DirectAnswer[Skip tool schemas entirely]
CategoryGate -- "category detected" --> LoadSchemas[Load ONLY matching domain schemas into _COMPACT_TOOLS]
LoadSchemas --> Novelty[Entity Novelty Detection]
```

**Categories to classify into** (mirrors Section 1 of the earlier Tool Intelligence doc):
- `none` — conversational, no tool needed at all → skip tool-loading overhead entirely, not just skip calling one
- `research` — web_search / deep_research / fetch_url
- `file_ops` — sandbox_ls/read/write/edit, execute_code, terminal
- `display` — the new render_* tools
- `memory` — memory_save/recall
- `media` — generate_image/fetch_stock_image
- `realtime` — weather_fetch

**Why this matters for Ochuko specifically:** your `_COMPACT_TOOLS` optimization already proves you care about this — this is the same idea applied one layer earlier. Right now (per the architecture doc) the per-conversation tool registry likely still exposes the full roster to the model's function-calling context every turn. A category gate means a "what's the weather" message never even sees the `sandbox_write` or `execute_code` schemas in its context window. At 24 tools post-expansion, this stops being optional — it's the difference between linear and near-flat token cost as the roster grows.

---

## 5. Memory Layer Fix: Optimistic Concurrency

Current state: `memory_save` / `memory_recall` — a flat key-value store, no versioning mentioned.

**Gap:** if two agent runs (or a retried request) write to the same memory key concurrently, last-write-wins silently. No conflict detection.

**Proposed fix — minimal, matches your Supabase setup:**
1. Add a `version` column (integer or updated_at timestamp) to the memory table.
2. `memory_save` accepts an optional `if_version` parameter. On mismatch, return the current row + version instead of failing silently — the agent can merge and retry in the same turn (no round-trip to the user needed).
3. Add `memory_edit` (surgical, `old_str`/`new_str` on a stored text blob) for correcting one fact without resending the whole record — same surgical philosophy as `sandbox_edit`, applied to memory. This also cuts token cost on every memory correction.

This is a small schema change with outsized reliability payoff — it's the one place in the current architecture where silent data loss is possible.

---

## 6. Revised Domain Table (Post-Improvement, 24 Tools)

| Domain | Tool Name | Status |
|---|---|---|
| UI & Widgets | `visualize__read_me` | existing |
| UI & Widgets | `visualize__show_widget` | existing |
| **UI & Widgets** | **`render_options_card`** | **new** |
| **UI & Widgets** | **`render_step_flow`** | **new** |
| **UI & Widgets** | **`render_itinerary`** | **new** |
| **UI & Widgets** | **`render_map`** | **new** |
| **UI & Widgets** | **`render_quiz`** | **new** |
| **UI & Widgets** | **`render_translation`** | **new** |
| Research | `search_web` | existing |
| Research | `deep_research` | existing |
| Research | `fetch_url` | existing |
| Memory | `memory_save` | existing, **+ versioning** |
| Memory | `memory_recall` | existing |
| **Memory** | **`memory_edit`** | **new** |
| File System | `sandbox_ls` | existing |
| File System | `sandbox_read` | existing |
| File System | `sandbox_write` | existing |
| File System | `sandbox_edit` | existing |
| Execution | `execute_code` | existing |
| Execution | `terminal` | existing |
| Visual Media | `generate_image` | existing |
| Visual Media | `fetch_stock_image` | existing |
| User Agency | `ask_user_input` | existing |
| Realtime | `weather_fetch` | existing |
| Safety | `end_conversation` | existing |

**18 → 25 tools.** (24 planned + memory_edit)

---

## 7. Phased Rollout

**Phase 1 — Router efficiency (do this first, it's free money):**
Implement the Category Gate ahead of the existing Complexity Classifier. Zero new user-facing surface, pure cost/latency win. Should be measurable in your existing test suite (`test_phase5_upgrade.py`) as a token-per-conversation reduction on non-tool-needing turns.

**Phase 2 — Memory versioning:**
Add the version column + `if_version` param + `memory_edit`. Low risk, backward compatible (old calls without `if_version` just skip the conflict check).

**Phase 3 — Display layer, ship in this order by expected usage frequency for a chat platform:**
1. `render_options_card` (covers the most ground — comparisons, recommendations, single picks)
2. `render_step_flow` (how-tos are extremely common in a general chat product)
3. `render_map` (high value if any location-adjacent user base)
4. `render_quiz`, `render_itinerary`, `render_translation` (more niche — ship based on actual usage logs, not assumption)

**Phase 4 — Verification gates for new tools:**
Extend `verification_gates.py` to cover the new render_* tools — e.g. reject `render_options_card` calls where attribute label sets don't match across options (the same class of mechanical check you already do for responsive HTML).

---

## 8. What NOT to Port

Deliberately excluding from this proposal, with reasons:
- **`suggest_connectors` / `search_mcp_registry` / plugin-catalog tools** — these exist in Claude because Claude.ai has a connector marketplace. Ochuko doesn't have that ecosystem yet; building the tools before the ecosystem is premature.
- **`fetch_sports_data`** — narrow vertical, low value-per-engineering-hour versus `weather_fetch`'s existing keyless API pattern. Add only if usage data shows demand.
- **`show_recommendation_cards`** (Claude's own cross-sell tool) — not applicable; Ochuko is a single surface, not a multi-app suite.

Keeping the roster tight is itself the point — this proposal aims for parity in *capability*, not roster size.

---

*Companion to [[agent-ochuko]] architecture. Pairs with `agent_ochuko_tool_intelligence.md` and `claude_tools_reference_v2.md`.*
