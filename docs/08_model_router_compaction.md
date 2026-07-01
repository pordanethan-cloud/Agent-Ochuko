# Phase 8 — Model Router Intelligence + Chat Compaction Integration

> **Duration**: 2–3 days
> **Depends on**: Phase 6.6 (conversation summarizer cron), Phase 1 (`model_router.py` scaffolded), Phase 2 (frontend mode toggle)

---

## 8.1 — ModelRouter in the Hot Path (Day 1)

- [x] Verify `model_router.py` is invoked on every `POST /v1/responses/stream` request — **after** the full middleware stack, **before** the Azure OpenAI call
- [x] Wire routing decision into the persisted message record:
  - `messages.routing_mode` — populated from `RoutingDecision.mode` on every assistant response
  - `messages.routing_reason` — populated from `RoutingDecision.reasoning` (debug trail)
- [x] Confirm Nano interceptor fires correctly:
  - Send "hi" → routed to `gpt-5.4-nano`, `routing_mode = 'nano'`
  - Send "hi" 3 times → 4th message falls through to user's selected mode
  - Send "hi" while in DISCUSS mode → bypasses interceptor, uses DISCUSS prompt directly
- [x] Confirm mode switching works: user changes mode from DISCUSS → THINK mid-conversation → next message uses `gpt-5.4` with THINK prompt
- [x] Log every routing decision to `audit_log`: `action = 'model_route'`, `metadata = {mode, deployment, reasoning}`

---

## 8.2 — Compaction Context Integration (Day 1–2)

- [x] Backend `build_llm_context()` function must:
  1. Query: `SELECT * FROM messages WHERE conversation_id = :id AND is_archived_msg = FALSE ORDER BY created_at ASC`
  2. This naturally includes: the `[SUMMARY]` message (`is_summary = TRUE`, `is_archived_msg = FALSE`) + all post-compaction messages
  3. Prepend the routing-selected system prompt from `ModelRouter`
  4. Send this context to Azure OpenAI Responses API
- [x] Frontend must NOT change — it queries ALL messages (including archived) for scrollable display:
  ```sql
  SELECT * FROM messages WHERE conversation_id = :id ORDER BY created_at ASC
  ```
  The LLM only sees the compacted context; the user sees the full history.
- [x] Test: conversation with 60 messages → compaction runs → send new message → verify LLM response references facts from the summary, not hallucinated content

---

## 8.3 — Runtime Prompt Override (Day 2)

- [x] Verify Azure App Configuration prompt keys override in-code constants at runtime:
  - `THINK_PROMPT`, `SOLVE_PROMPT`, `DISCUSS_PROMPT`, `NANO_PROMPT`
- [x] Test: change `THINK_PROMPT` value in Azure App Configuration portal → send a THINK-mode message → verify new prompt behavior in the response — no redeploy required
- [x] Implement `config.py` cache refresh strategy (choose one):
  - **Option A (Polling)**: background task refreshes App Config cache every 5 minutes
  - **Option B (Sentinel key)**: use Azure App Configuration's push-based refresh — watch a `config_version` sentinel key; when it changes, reload all config

---

## 8.4 — Mode Toggle UI (Day 2–3)

- [x] Frontend: 3-mode toggle pill (THINK / SOLVE / DISCUSS) visible in the chat input area
- [x] Default mode on new conversation: **DISCUSS** (cheapest — GPT-5.4 Nano)
- [x] Mode persisted per-conversation in `conversations.mode` column
- [x] Switching mode mid-conversation: `PATCH /v1/conversations/{id}` with `{mode: "think"}` → next message uses new mode
- [x] Visual indicator on each assistant message bubble — small badge showing:
  - `"THINK · GPT-5.4"`, `"SOLVE · GPT-5.4 Mini"`, `"DISCUSS · GPT-5.4 Nano"`, `"NANO · intercepted"`
  - Badge uses `messages.routing_mode` from the DB

---

## Milestone

Intelligent model routing fully operational. Users consciously choose their cost tier, greetings are silently deflected to Nano, long conversations are compacted without losing context, and prompts can be tuned live from the Azure portal — no redeploy needed.

---

## Considerations

> Items from the implementation plan relevant to this phase that require additional context or setup.

### Conversations Table Mode Column Mismatch

In `03_supabase_setup.md` Migration 001, `conversations.mode` has the constraint:
```sql
mode TEXT DEFAULT 'discuss' CHECK (mode IN ('think','solve','discuss'))
```
This correctly includes `discuss`. However, the initial implementation plan Section 6 schema shows `CHECK (mode IN ('think','solve'))` — missing `discuss`. The correct version is the one in `03_supabase_setup.md`. Ensure the production table has all three values: `think`, `solve`, `discuss`.

### `messages.routing_mode` Missing `discuss` Value

The `messages.routing_mode` column in both the full schema (Section 6) and Migration 001 has:
```sql
routing_mode TEXT CHECK (routing_mode IN ('think','solve','nano','summary'))
```
But `discuss` mode responses are also stored. Add `discuss` to the constraint:
```sql
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_routing_mode_check;
ALTER TABLE messages ADD CONSTRAINT messages_routing_mode_check
  CHECK (routing_mode IN ('think','solve','nano','discuss','summary'));
```

### Config Cache Refresh Timing

The implementation plan (Section 8.3) mentions either polling or a sentinel key for config refresh. The current `config.py` implementation only refreshes on miss (`if key not in _config_cache`). This means a prompt updated in App Configuration won't take effect until the cache is cleared. For Phase 8 to work correctly (live prompt updates), implement at minimum Option A (5-minute background polling task).

### `increment_nano_turns` RPC Must Be Present

The `model_router.py` calls `supabase.rpc("increment_nano_turns", ...)` for atomic Nano turn counting. This RPC is defined in the full schema (Section 2.5) and in `03_supabase_setup.md` Migration 001. Confirm it exists in the production Supabase project before testing the Nano interceptor end-to-end.

### `routing_reason` Column Not in Migration 001

The `messages.routing_reason` column (populated by `ModelRouter.reasoning`) is present in the full schema (Section 6) but **may be absent** in `03_supabase_setup.md` Migration 001 (the column list there is abbreviated). Confirm it exists; if not, add:
```sql
ALTER TABLE messages ADD COLUMN IF NOT EXISTS routing_reason TEXT;
```
