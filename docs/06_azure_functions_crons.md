# Phase 6 — Azure Functions Crons

> **Duration**: 2–3 days
> **Depends on**: Phase 4 (Function App deployed + Managed Identity granted Key Vault access), Phase 3 (`token_budgets` + `agent_quotas` tables with RLS), Phase 5 (admin dashboard for monitoring cron outputs)

All cron functions are deployed to `agent-ochuko-functions` (Azure Function App, Consumption plan). Each uses **Managed Identity** to fetch secrets from Key Vault — no hardcoded credentials.

---

## 6.1 — Daily Token Budget Reset (Day 1)

- [ ] Create `token_quota_reset` — **Timer Trigger**: `0 0 * * *` (midnight UTC daily)
- [ ] Logic:
  - For every active user (`profiles.is_active = true`), call `ensure_budget_row(user_id)` RPC
  - This inserts a new `token_budgets` row for `CURRENT_DATE` with `tokens_used = 0`
  - If a per-user `budget_limit` override was set by admin, preserve it — do NOT reset to the global default
  - Does NOT delete old rows — they are historical data for the Usage page charts
- [ ] Log to Application Insights: `{event: "token_reset", users_reset: N, timestamp: "..."}`
- [ ] Verification: after midnight UTC, query `SELECT * FROM token_budgets WHERE period = CURRENT_DATE` — every active user should have a fresh row with `tokens_used = 0`

---

## 6.2 — Monthly Agent Quota Reset (Day 1)

- [ ] Create `agent_quota_reset` — **Timer Trigger**: `0 0 1 * *` (1st of every month, midnight UTC)
- [ ] Logic:
  - For every active user, insert a new `agent_quotas` row: `period = 'YYYY-MM'`, all counters at 0
  - Old period rows are kept — historical reporting data
- [ ] Log: `{event: "agent_quota_reset", period: "2026-07", users_reset: N}`
- [ ] Verification: on the 1st, confirm `SELECT * FROM agent_quotas WHERE period = '2026-07'` exists for all active users with zeroed counters

---

## 6.3 — Hourly Usage Aggregation (Day 1–2)

- [ ] Create `usage_aggregation` — **Timer Trigger**: `0 * * * *` (top of every hour)
- [ ] Purpose: materializes pre-computed stats so the Admin Dashboard Usage page doesn't run expensive aggregate queries on every page load
- [ ] Create `usage_stats` table (run migration before deploying this function):

```sql
CREATE TABLE usage_stats (
  period_hour    TIMESTAMPTZ,
  user_id        UUID REFERENCES profiles(id) ON DELETE CASCADE,
  model          TEXT,
  tokens_in      BIGINT DEFAULT 0,
  tokens_out     BIGINT DEFAULT 0,
  request_count  INT DEFAULT 0,
  agent_type     TEXT,
  agent_calls    INT DEFAULT 0,
  PRIMARY KEY (period_hour, user_id, model, agent_type)
);

ALTER TABLE usage_stats ENABLE ROW LEVEL SECURITY;
CREATE POLICY "usage_admin" ON usage_stats FOR SELECT USING (is_admin());
```

- [ ] Query: aggregate from `messages` and `jobs` WHERE `created_at >= last_run AND created_at < now()`
- [ ] Upsert: `ON CONFLICT (period_hour, user_id, model, agent_type) DO UPDATE` — safe to re-run
- [ ] Log: `{event: "usage_aggregation", period_hour: "...", rows_written: N}`
- [ ] Verification: after 1 hour of usage, query `usage_stats` — should have rows matching chat and agent activity

---

## 6.4 — Conversation Archiver (Day 2)

- [ ] Create `conversation_archiver` — **Timer Trigger**: `0 2 * * *` (2am daily UTC)
- [ ] Logic:
  ```sql
  UPDATE conversations
  SET is_archived = TRUE
  WHERE updated_at < now() - INTERVAL '90 days'
    AND is_archived = FALSE;
  ```
- [ ] Archived conversations remain in DB — they are soft-archived only, never deleted
- [ ] Frontend already has a "Show archived" toggle that filters `is_archived = FALSE` by default
- [ ] Log: `{event: "conversations_archived", count: N, oldest_archived: "2026-03-27"}`
- [ ] Verification: create test conversation with `updated_at` set to 91 days ago → run archiver → confirm `is_archived = TRUE`

---

## 6.5 — Model Expiry Monitor (Day 2)

- [ ] Create `model_expiry_monitor` — **Timer Trigger**: `0 9 * * *` (9am daily UTC)
- [ ] Reads from Azure App Configuration:
  - `THINK_MODEL_DEPLOYMENT` + `THINK_MODEL_EXPIRY_DATE`
  - `SOLVE_MODEL_DEPLOYMENT` + `SOLVE_MODEL_EXPIRY_DATE`
  - `NANO_MODEL_DEPLOYMENT` + `NANO_MODEL_EXPIRY_DATE`
  - `COMPACTION_MODEL_DEPLOYMENT` + `COMPACTION_MODEL_EXPIRY_DATE`
- [ ] For each deployment:
  - **≤ 30 days to expiry** → log WARNING to Application Insights + send alert (email or webhook to admin)
  - **≤ 7 days to expiry** → log CRITICAL + send urgent alert
  - **Expired (past date)** → auto-swap to fallback deployment name stored in `{MODE}_FALLBACK_DEPLOYMENT` App Config key
    - Log: `{event: "model_auto_swap", from: "gpt-5.4", to: "gpt-5.4-fallback"}`
- [ ] After auto-swap: update the primary deployment key in Azure App Configuration so FastAPI reads it on next request — zero downtime, zero redeploy
- [ ] Verification: set test `THINK_MODEL_EXPIRY_DATE` to yesterday → run monitor → confirm auto-swap occurred and App Config updated

---

## 6.6 — Conversation Summarizer / Chat Compaction (Day 2–3)

- [ ] Create `conversation_summarizer` — **Timer Trigger**: `0 3 * * *` (3am daily UTC)
- [ ] Query qualifying conversations:
  ```sql
  SELECT id FROM conversations
  WHERE message_count > {COMPACTION_THRESHOLD}
    AND (last_compacted_at IS NULL OR last_compacted_at < now() - INTERVAL '7 days')
  LIMIT 20;
  ```
- [ ] For each qualifying conversation:
  1. Fetch all messages `WHERE is_archived_msg = FALSE ORDER BY created_at ASC`
  2. If count < `COMPACTION_THRESHOLD` (default 50) → skip (message_count may be stale)
  3. Take oldest 60% → format as structured text
  4. Call GPT-o4-mini (`COMPACTION_MODEL_DEPLOYMENT`) via Azure OpenAI Responses API:
     - System prompt: `"Summarize this conversation history concisely. Preserve: all decisions made, key facts, user preferences, ongoing tasks, and any code or data shared. Output as structured paragraphs. Be thorough but compact."`
  5. Insert `[SUMMARY]` message: `role = 'system'`, `is_summary = TRUE`, `is_archived_msg = FALSE`, `routing_mode = 'summary'`
  6. Mark old messages: `UPDATE messages SET is_archived_msg = TRUE WHERE id IN (...oldest 60%...)`
  7. Update conversation: `last_compacted_at = now()`
- [ ] Safeguards:
  - Max 20 conversations per run (prevent timeout — Consumption plan has 10-minute max execution)
  - If GPT-o4-mini call fails on one conversation → skip it, log error, move to next
  - Never delete messages — only set `is_archived_msg = TRUE`
- [ ] Log: `{event: "compaction", conversation_id: "...", messages_archived: 30, summary_tokens: 450}`
- [ ] Verification:
  - Seed conversation with 60+ messages
  - Run summarizer
  - Confirm summary message exists with `is_summary = TRUE`
  - Confirm old messages have `is_archived_msg = TRUE`
  - Confirm frontend LLM context query (`WHERE is_archived_msg = FALSE`) returns only summary + recent messages
  - Confirm frontend scroll still shows ALL messages (including archived)

---

## 6.7 — Deploy & Validate All Crons

- [ ] Deploy all 6 timer-triggered functions to `agent-ochuko-functions` Function App
- [ ] Verify each function appears in Azure Portal → Function App → Functions list
- [ ] Verify timer triggers registered in Azure Portal → Function App → App files → `host.json`
- [ ] Manually trigger each function from Azure Portal "Test/Run" — confirm end-to-end execution
- [ ] Check Application Insights for log entries from each cron
- [ ] Confirm Managed Identity can access Key Vault (no `403 Forbidden` errors in logs)

---

## Milestone

All background automation running. Token budgets reset daily, agent quotas reset monthly, usage stats materialized hourly, stale conversations archived, model deployments monitored for expiry and auto-swapped, and long conversations compacted by GPT-o4-mini — all without any manual intervention or code changes.

---

## Considerations

> Items from the implementation plan that require additional setup or decisions beyond the checklist above.

### `usage_stats` Table Is Not in Supabase Migrations

The `usage_stats` table (needed by `usage_aggregation` cron) is **not in any of the setup migration files** (`03_supabase_setup.md`). It is described only in `roadmap.txt` Phase 6.3. Run the SQL above as Migration 006 before deploying the `usage_aggregation` function.

### `COMPACTION_THRESHOLD` Key in App Configuration

The implementation plan (Section 2.5) defines this key as `50`. The `02_azure_services_setup.md` App Configuration table includes it (correctly). Confirm it is set before Phase 6.6 deploys — the summarizer reads it at runtime from App Config.

### Model Expiry Date Keys Must Be Manually Set

The App Configuration keys `THINK_MODEL_EXPIRY_DATE`, `SOLVE_MODEL_EXPIRY_DATE`, `NANO_MODEL_EXPIRY_DATE`, `COMPACTION_MODEL_EXPIRY_DATE`, and `{MODE}_FALLBACK_DEPLOYMENT` are referenced by the `model_expiry_monitor` cron but are **not listed** in the App Configuration setup in `02_azure_services_setup.md`. Add them manually in the Azure portal after deploying models. Use the deployment expiry date from Azure AI Foundry's Deployments tab.

### Poison Handler Is a Queue Worker, Not a Cron

The `poison_handler` Azure Function (`agent-jobs-poison` queue trigger) was listed in Phase 4 workers but is architecturally relevant here too — it updates `jobs.status = 'failed'` after 5 retries. Confirm it was deployed in Phase 4 before relying on the dead-letter queue behavior in production.

### `ensure_budget_row` RPC Must Exist Before Token Reset Runs

The `ensure_budget_row(p_user_id UUID)` Supabase RPC is defined in the full schema (implementation plan Section 6) but is **not present** in `03_supabase_setup.md` migrations. Add it as Migration 007:

```sql
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
```
