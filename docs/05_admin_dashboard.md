# Phase 5 — Admin Dashboard

> **Duration**: 3–4 days
> **Depends on**: Phase 3 (RBAC roles in `profiles.role`), Phase 1 (FastAPI `/v1/admin/*` routes scaffolded)
> **Prerequisite**: Phases 0–4 complete. You have: Azure infra, FastAPI backend with full middleware, React chat UI, Google OAuth, RBAC/ABAC/ReBAC security model, all agent workers, Supabase Realtime.

---

## 5.1 — Scaffold & Auth Gate (Day 1)

- [ ] Init separate React + Vite project in `admin/`
- [ ] Configure Vite for Azure Static Web App deployment target (`agent-ochuko-admin`)
- [ ] Implement admin login — reuse Supabase Google OAuth, but enforce `role IN ('admin', 'superadmin')` after session loads
- [ ] Redirect non-admin JWTs to a `NotAuthorized` page — no silent fail, clear error message
- [ ] Create `api.ts` client that automatically injects the admin JWT into all `/v1/admin/*` calls
- [ ] Wire up base layout: sidebar nav with links: **Users | Usage | Budgets | Settings | Audit Log**

---

## 5.2 — Users Page (Day 1–2)

- [ ] Call `GET /v1/admin/users` — render paginated table with columns:
  - Name, Email, Role, Tokens Used Today, Agent Calls This Month, Status (active/suspended/blocked), Last Seen
- [ ] Search bar — client-side filter by name or email
- [ ] Role badge (color-coded): `guest` / `user` / `power_user` / `admin` / `superadmin`
- [ ] Action buttons per row:
  - **Block** → `PATCH /v1/admin/users/{id}/block` — writes to `blocked_identities` by `google_sub` (permanent, unbypassable)
  - **Suspend** → sets `profiles.is_active = false` (reversible)
  - **Activate** → sets `profiles.is_active = true`
  - **Change Role** → dropdown, writes to `profiles.role`
- [ ] Confirmation modal before block/suspend actions (show user name + action summary)
- [ ] Real-time user count widget: `{current_registered} / {registration_limit}` pulled from `admin_settings`

---

## 5.3 — Usage Page (Day 2)

- [ ] Token consumption chart — per user, per model, per day (line chart, last 30 days)
- [ ] Agent calls chart — per type (`ocr`, `vision`, `speech`, `image_gen`, `file_gen`), per month (bar chart)
- [ ] Top 5 users by token consumption table (sortable)
- [ ] Data source:
  - **Before Phase 6 cron is live**: query `messages` and `agent_quotas` directly
  - **After Phase 6.3**: pull from the `usage_stats` materialized table (much faster)

---

## 5.4 — Budgets Page (Day 2–3)

- [ ] **Global default daily token budget** — number input → writes to `admin_settings.global_daily_token_budget`
- [ ] **Per-user budget override table** — select user → set custom `token_budgets.budget_limit` for that user
- [ ] Show current `tokens_used` vs `budget_limit` as a progress bar per user
- [ ] **Agent quota limits display** (OCR pages, vision calls, speech seconds, image gen) — read from `admin_settings`
- [ ] All writes use `PATCH /v1/admin/users/{id}/budget` or `PATCH /v1/admin/settings`

---

## 5.5 — Settings Page (Day 3)

- [ ] **Registration Cap** — number input → `admin_settings.registration_limit` via `PATCH /v1/admin/settings`
- [ ] **Registration Open** — toggle → `admin_settings.registration_open`
- [ ] **Maintenance Mode** — toggle → `admin_settings.maintenance_mode`
  - Show warning banner: "All non-admin requests will return 503"
- [ ] **Active Model Override** — text inputs for:
  - `THINK_MODEL_DEPLOYMENT`, `SOLVE_MODEL_DEPLOYMENT`, `NANO_MODEL_DEPLOYMENT`, `COMPACTION_MODEL_DEPLOYMENT`
  - All write to **Azure App Configuration** via admin endpoint → take effect instantly (no redeploy)
- [ ] **Max File Size** — number input → `admin_settings.max_file_size_mb`
- [ ] All changes require a confirmation click → show success/error toast

---

## 5.6 — Audit Log Page (Day 3–4)

- [ ] Call `GET /v1/admin/audit` — paginated, sortable table
- [ ] Columns: Timestamp, User, Action, Resource Type, Policy Decision (`ALLOW`/`DENY`), IP Address, User Agent
- [ ] Filters: by action type, by user, by date range, by policy decision
- [ ] Expandable row → shows full `metadata` JSONB (model used, `response_id`, tokens, `job_id`)
- [ ] **Export to CSV** button — downloads current filtered view

---

## 5.7 — Deploy Admin Dashboard

- [ ] Build: `npm run build` → produces `dist/`
- [ ] Deploy to Azure Static Web App (`agent-ochuko-admin`)
- [ ] Verify CORS: admin SWA origin (`https://agent-ochuko-admin.azurestaticapps.net`) added to FastAPI `ALLOWED_ORIGINS`
- [ ] Smoke test every page with a `superadmin` JWT
- [ ] Verify non-admin JWT gets redirected to `NotAuthorized` page

---

## Milestone

Full admin control plane live. Owner can manage users, set token budgets, block/suspend users, toggle maintenance mode, override active model deployments, and view the complete audit trail — all from a web UI without touching code or redeploying.

---

## Considerations

> Items from the implementation plan that are architecturally defined but require additional decision or setup beyond the task checklist above.

### Admin Dashboard Deployment Target

The implementation plan (Section 10) says "Deployed separately on Vercel" but Section 12 (Infrastructure) lists `agent-ochuko-admin` as an **Azure Static Web App (Free tier)**. The correct target is Azure Static Web App — consistent with the CI/CD pipeline in Phase 7.3. Disregard the Vercel mention; it is an artifact from an earlier draft.

### Usage Page Data Before Phase 6

Until the `usage_aggregation` cron (Phase 6.3) is live, the Usage page will run live aggregate queries against `messages` and `jobs`. On a small user base this is acceptable, but add a note in the UI: "Usage data updates hourly once background aggregation is active."

### System Prompt Live Editing

The Settings page should also expose `THINK_PROMPT`, `SOLVE_PROMPT`, `DISCUSS_PROMPT`, and `NANO_PROMPT` as multi-line text areas that write to Azure App Configuration. This is specified in the implementation plan (Section 2.5, Azure App Configuration Keys) but not explicitly called out in the Phase 5 settings checklist. Add them as an advanced collapsible section under Settings.

### Audit Log Schema Gap

In Migration 001 (`03_supabase_setup.md`), the `audit_log` table is missing the `resource_id`, `user_agent`, and `policy_reason` columns present in the full schema (implementation plan Section 6). Ensure a follow-up migration adds those columns before the Audit Log page queries them.

### Agent Quota Limits Missing from Seed Data

The quota limit keys (`max_ocr_pages_per_user`, `max_file_size_mb`, etc.) are seeded in the full schema (Section 6) but are **not present** in the `03_supabase_setup.md` seed data. Add a Migration 005 before Phase 5:

```sql
INSERT INTO admin_settings (key, value, description) VALUES
  ('max_file_size_mb',       '10',   'Max file upload size in MB'),
  ('max_ocr_pages_per_user', '50',   'Max OCR pages per user per month'),
  ('max_vision_calls',       '5000', 'Max vision calls per user per month'),
  ('max_speech_seconds',     '3600', 'Max speech seconds per user per month'),
  ('max_image_gen',          '100',  'Max image generations per user per month')
ON CONFLICT (key) DO NOTHING;
```
