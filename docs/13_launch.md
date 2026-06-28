# Phase 13 — Launch

> **Duration**: 1 day
> **Depends on**: All phases complete. All CI checks green. All E2E tests passing against staging.

---

## Pre-Launch Checklist

### Code & Branch

- [ ] Final `main` branch merged — all feature branches merged, no pending PRs
- [ ] All CI pipeline checks green (backend tests, frontend build, lint, Playwright)
- [ ] No open `TODO`/`FIXME` comments in hot-path files (`model_router.py`, `jwt_validator.py`, `token_budget.py`)

---

### Supabase (Production)

- [ ] All SQL migrations applied in order (001 through 007, plus any considerations patches)
- [ ] Seed data confirmed: `admin_settings` has all required keys including quota limits
- [ ] RLS verified on all tables (run the RLS audit from Phase 7.5 against production)
- [ ] `is_admin()` function exists and works correctly
- [ ] `ensure_budget_row()` RPC exists
- [ ] `increment_nano_turns()` RPC exists
- [ ] Realtime enabled for `messages`, `conversations`, `jobs`
- [ ] Supabase Storage buckets created: `uploads` (private), `generated` (private), `exports` (private)
- [ ] Google OAuth provider configured and working in Supabase Auth dashboard
- [ ] Redirect URLs in Supabase Auth URL Configuration match production domains

---

### Azure (Production)

- [ ] All resources provisioned in `rg-ochuko`:
  - Azure AI Foundry Hub + Project
  - All 5 model deployments active: `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `o4-mini`, `tts-1-ochuko`
  - Azure Document Intelligence (`agent-ochuko-docintelligence`)
  - Azure Computer Vision (`agent-ochuko-vision`)
  - Azure Speech Services (`agent-ochuko-speech`)
  - Azure Blob Storage (`agentochukostore`) with `uploads`, `generated`, `exports` containers
  - Azure Queue Storage: `agent-jobs` + `agent-jobs-poison` queues
  - Azure App Configuration (`agent-ochuko-appconfig`) with all keys populated
  - Azure Key Vault (`agent-ochuko-kv`) with ALL secrets added
  - Azure Container Registry (`agent-ochuko-acr`) with backend image pushed
  - Azure Container Apps Environment + App (`agent-ochuko-api`)
  - Azure Function App (`agent-ochuko-functions`)
  - Azure Static Web App — Chat frontend
  - Azure Static Web App — Admin dashboard
  - Azure Application Insights (`agent-ochuko-insights`)
- [ ] All secrets in Key Vault (no secrets in code, no secrets in Container App env vars directly — use Key Vault references)
- [ ] Managed Identities granted Key Vault access: Container App + Function App
- [ ] App Configuration connection string in Container App environment variables
- [ ] Application Insights connection string in Container App environment variables

---

### Deploy

- [ ] Deploy backend Docker image to Container Apps (production revision) → health check passes
- [ ] Deploy frontend to Azure Static Web App (Chat)
- [ ] Deploy admin dashboard to Azure Static Web App (Admin)
- [ ] Deploy all Azure Functions (all 6 workers + 6 crons)
- [ ] Verify all Function triggers visible in Azure Portal → Function App → Functions list

---

### Post-Deploy Verification

- [ ] Promote your account to `superadmin` in production Supabase (run `UPDATE profiles SET role = 'superadmin' WHERE id = '<YOUR_ID>'`)
- [ ] Set in `admin_settings`:
  - `registration_open = true`
  - `registration_limit = 20` (start small)
  - `maintenance_mode = false`
- [ ] DNS: point custom domain (if applicable) to Azure Static Web App
- [ ] CORS: confirm FastAPI `ALLOWED_ORIGINS` includes both production SWA domains
- [ ] Send first message — verify streaming works end-to-end in production
- [ ] Upload a PDF — verify OCR job completes and result appears in chat
- [ ] Check Application Insights for 10 minutes — watch for errors, failed function executions
- [ ] Open admin dashboard — verify user appears, usage charts load

---

### Invite First Users

- [ ] Invite first batch (5–10 trusted users)
- [ ] Monitor Application Insights for 24 hours:
  - Watch for error spikes
  - Watch for P95 TTFT > 2 seconds
  - Watch for unexpected Azure OpenAI costs
- [ ] After 24 hours: review `usage_stats` in admin dashboard — confirm cost trajectory is within student subscription

---

## Milestone

Agent Ochuko is live. Users are chatting. Admin is monitoring. The system is self-healing (crons reset budgets, monitor model expiry, compact conversations), cost-controlled (token budgets enforced before Azure is called), and observable (every request logged to Application Insights).

---

## Considerations

> Post-launch items from the implementation plan that are worth tracking but are not blocking launch.

### Capacitor Native App Wrapping

The implementation plan (ADR-005) notes long-term compatibility with **Capacitor** for wrapping the Vite React build into native iOS/Android apps. This enables over-the-air updates via Capgo or Ionic Appflow. This is explicitly out of scope for launch but is a low-effort post-launch enhancement given the pure SPA architecture.

### Custom Domain Setup

If a custom domain is used (e.g., `agent.ochuko.dev`), configure it in Azure Static Web App settings and add the custom domain's TXT/CNAME records to your DNS provider. Azure will automatically provision an SSL certificate. Update Supabase Auth redirect URLs and FastAPI `ALLOWED_ORIGINS` accordingly.

### Model Expiry Date Population

After launch, go to Azure AI Foundry → your project → Deployments tab → note the expiry date for each model deployment. Add these dates to Azure App Configuration as:
- `THINK_MODEL_EXPIRY_DATE` (format: `YYYY-MM-DD`)
- `SOLVE_MODEL_EXPIRY_DATE`
- `NANO_MODEL_EXPIRY_DATE`
- `COMPACTION_MODEL_EXPIRY_DATE`

The `model_expiry_monitor` cron (Phase 6.5) will begin alerting 30 days before expiry once these keys are populated.

### Registration Limit Scaling

Starting with `registration_limit = 20` is conservative and correct. As you gain confidence in cost and stability, increment via the admin dashboard Settings page — no code change or redeploy required.
