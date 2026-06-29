# Phase 7 — Production Hardening

> **Duration**: 3–5 days
> **Depends on**: All previous phases complete and functional

---

## 7.1 — Observability & Structured Logging (Day 1)

- [ ] Integrate `azure-monitor-opentelemetry` (or `opencensus-ext-azure`) into FastAPI
- [ ] Every request logs a structured trace:
  ```json
  {
    "request_id": "...", "user_id": "...", "method": "POST",
    "path": "/v1/responses/stream", "status_code": 200,
    "latency_ms": 340, "model_used": "gpt-5.4", "tokens_in": 120, "tokens_out": 450
  }
  ```
- [ ] Every unhandled exception logs full stack trace + request context to Application Insights `exceptions` table
- [ ] Custom metrics to Application Insights:
  - `chat.stream.ttft_ms` — time to first token (P50, P95, P99)
  - `chat.stream.total_ms` — total stream duration
  - `agent.job.duration_ms` — by agent type
  - `agent.job.failure_rate` — by agent type
  - `budget.utilization_pct` — per user, per day
  - `model_router.decision` — count by routing mode (think/solve/discuss/nano)
- [ ] Azure Function workers: same structured logging pattern — each job logs `{job_id, type, status, duration_ms, error}`
- [ ] Set up Application Insights Alerts:
  - **Error rate > 5% over 5 minutes** → email admin
  - **P95 TTFT > 3 seconds** → email admin
  - **Any cron function fails** → email admin
  - **Budget utilization > 80% globally** → email admin

---

## 7.2 — Health Check & Readiness Endpoints (Day 1)

- [ ] Implement `GET /health` — returns `200 OK` with:
  ```json
  {
    "status": "healthy",
    "version": "1.0.0",
    "commit": "abc1234",
    "checks": {
      "supabase": "ok",
      "azure_openai": "ok",
      "azure_queue": "ok",
      "azure_app_config": "ok",
      "azure_blob": "ok"
    }
  }
  ```
- [ ] Each check: lightweight ping/HEAD — timeout 2 seconds per service, mark `"degraded"` if any fail
- [ ] If Supabase OR Azure OpenAI is down → return `503` with degraded status
- [ ] Configure Azure Container Apps **liveness probe**: `GET /health`, restart if unhealthy for 3 consecutive checks
- [ ] Implement `GET /ready` — returns `200` only if `load_config()` has completed AND Supabase client is initialized
- [ ] Configure Azure Container Apps **readiness probe**: `GET /ready` — Container Apps won't route traffic until ready

---

## 7.3 — CI/CD Pipelines (Day 1–2)

- [ ] **Backend pipeline** (`.github/workflows/backend-deploy.yml`):
  1. Trigger: push to `main` with changes in `backend/**`
  2. Run `pytest` (unit tests) — fail pipeline if any test fails
  3. Run `ruff check` + `ruff format --check` (linting)
  4. Build Docker image, tag with `git SHA`
  5. Push to private Docker Hub registry (`agent-ochuko-api`)
  6. Deploy to Azure Container Apps
  7. Wait for `/health` to pass on new revision

- [ ] **Frontend pipeline** (`.github/workflows/frontend-deploy.yml`):
  1. Trigger: push to `main` with changes in `frontend/**`
  2. `npm ci` → `npm run build` → `npm run lint`
  3. Deploy `dist/` to Azure Storage Blob static website container (`$web` on `agentochukostore`)

- [ ] **Admin pipeline** (`.github/workflows/admin-deploy.yml`):
  1. Same as frontend but deploys to Azure Storage Blob static website container (`$web` on `agentochukoadmin`)

- [ ] **Functions pipeline** (`.github/workflows/functions-deploy.yml`):
  1. Trigger: push to `main` with changes in `functions/**`
  2. Run function-specific unit tests
  3. Deploy: `func azure functionapp publish agent-ochuko-functions`

- [ ] All pipelines use GitHub Secrets for:
  - `AZURE_CREDENTIALS`, `DOCKER_USERNAME`, `DOCKER_PASSWORD`

---

## 7.4 — Container Deployment Strategy (Day 2)

- [ ] **Blue/green (revision-based)** on Azure Container Apps:
  - New revision deployed with 0% traffic initially
  - Health check passes → shift 100% traffic to new revision
  - Old revision kept for 1 hour as instant rollback target
  - Health check fails → new revision deactivated, old revision keeps serving
- [ ] Set Container App scaling rules:
  - **Min replicas**: 1 (always warm — no cold start for users)
  - **Max replicas**: 3 (handle burst concurrent traffic)
  - **Scale rule**: HTTP concurrent requests > 20 per replica → scale out
- [ ] Resource limits: 0.5 vCPU, 1 GB RAM per replica (upgrade from Phase 0's 0.25 vCPU if load tests demand it)

---

## 7.5 — Security Hardening Review (Day 2–3)

- [ ] **RLS policy audit** — for every table, test with 5 role-specific JWTs (guest, user, power_user, admin, superadmin):
  - `guest`: can ONLY read shared conversations and their messages — nothing else
  - `user`: can ONLY read/write their own conversations, messages, jobs
  - `user`: CANNOT read another user's data even with a hand-crafted query
  - `admin`: can read all data, manage users, but CANNOT modify `audit_log`
  - `superadmin`: full admin access + can modify App Configuration via admin endpoints

- [ ] **JWT validation hardening**:
  - Verify `iss` (issuer) matches Supabase project URL
  - Verify `aud` (audience) is correct
  - Verify `exp` is not in the past
  - Reject tokens signed with `none` algorithm (JWT alg confusion attack)
  - Cache JWKS keys for 1 hour, refresh on miss

- [ ] **CORS strict audit**:
  - `ALLOWED_ORIGINS` contains ONLY:
    - `https://agentochukostore.z1.web.core.windows.net` (chat)
    - `https://agentochukoadmin.z1.web.core.windows.net` (admin)
    - `http://localhost:5173` (dev)
  - No wildcard `*` — ever
  - `allow_credentials = True` — required for JWT cookie flow

- [ ] **Rate limiting**:
  - Per-IP: 100 requests/minute (prevent scraping/abuse)
  - Per-user: 30 streaming requests/minute (prevent token burning)
  - Implementation: `slowapi` middleware with in-memory storage (`memory://`), relying on Azure Container Apps sticky sessions (session affinity) for replica consistency.

- [ ] **File upload security**:
  - Validate MIME type server-side before generating presigned URL
  - Max file size enforced: `admin_settings.max_file_size_mb` (default 10MB)
  - Blob container access: `uploads` = private, `generated` = private, `exports` = private
  - Blocked file extensions: `.exe`, `.sh`, `.bat`, `.cmd`, `.ps1`, `.js`

- [ ] **Security headers** on FastAPI:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - `Content-Security-Policy: default-src 'self'` (via SWA `staticwebapp.config.json`)

- [ ] **Dependency audit**: run `pip audit` on `requirements.txt` — resolve any CVEs before production

---

## 7.6 — Load Testing (Day 3–4)

- [ ] Tool: `locust` or `k6` — script simulates realistic user behavior
- [ ] **Scenario 1 — Concurrent streaming** (primary):
  - 50 virtual users, each sends 1 chat message every 30 seconds
  - Measure: TTFT (P50, P95, P99), total stream time, error rate
  - Pass criteria: P95 TTFT < 2 seconds, error rate < 1%
- [ ] **Scenario 2 — Agent burst**:
  - 20 virtual users, each submits 1 OCR job simultaneously
  - Measure: time from `202 Accepted` to `status = 'done'`
  - Pass criteria: 95% of jobs complete within 30 seconds
- [ ] **Scenario 3 — Budget exhaustion under load**:
  - 10 users hit their daily token budget simultaneously mid-stream
  - Verify: stream terminates gracefully with `429`, no partial writes, no double-deduction
- [ ] **Scenario 4 — Mixed load**:
  - 30 chat users + 10 agent users + 5 admin dashboard users concurrently
  - Verify: no cross-contamination (user A never sees user B's data), no RLS bypass under load
- [ ] Document results in `docs/10_load_test_results.md`
- [ ] If bottlenecks found: tune Container App replica count, adjust vCPU/RAM, optimize slow Supabase queries via `pg_stat_statements`

---

## 7.7 — Final Cost Validation (Day 4)

- [ ] Run the full system for 48 hours with simulated usage (10–20 active test accounts)
- [ ] Check Azure Cost Management:
  - Azure OpenAI: total token spend — project monthly at 100 users
  - Container Apps: vCPU-seconds and memory-seconds consumed
  - Functions: total executions
  - Storage: blob size + queue transactions
  - All other services: confirm free tier not exceeded
- [ ] Compare against the cost analysis table in Section 14 of the implementation plan
- [ ] If monthly projection exceeds $12: identify the cost driver, adjust token budgets or agent quotas accordingly
- [ ] Document results in `docs/11_cost_validation.md`

---

## 7.8 — Error Handling & Graceful Degradation (Day 4–5)

- [ ] **Azure OpenAI down**: FastAPI returns `503` with `Retry-After: 30` header — frontend shows "AI service temporarily unavailable, please try again shortly"
- [ ] **Supabase down**: health check marks degraded — in-flight streams can complete, new requests get `503`
- [ ] **Azure Queue down**: agent endpoints return `503` instead of silently failing — frontend shows clear error
- [ ] **Hugging Face all keys exhausted**: `image_gen_worker` writes `status = 'failed'` with error "Image generation temporarily unavailable" — frontend shows human-readable message, not stack trace
- [ ] **Groq Whisper down**: `speech_stt_worker` falls back to Azure Speech STT (if configured) or fails gracefully with error message
- [ ] **Frontend SSE stream breaks mid-response**: `useStream.ts` implements auto-reconnect — if stream drops, show partial response with "(Response interrupted — click to retry)" button
- [ ] **Supabase Realtime drops**: `useJob.ts` fallback polling — if no Realtime update received within 15 seconds for a pending job, poll `GET /v1/jobs/{id}` every 10 seconds
- [ ] All error responses follow a consistent JSON shape:
  ```json
  {
    "error": {
      "code": "BUDGET_EXHAUSTED",
      "message": "Daily token budget exhausted. Resets at midnight UTC.",
      "retry_after": 3600
    }
  }
  ```

---

## Milestone

System is production-grade. Observable, tested under load, secured at every layer, cost-validated, CI/CD automated, and graceful under failure. Ready for real users.

---

## Considerations

> Items from the implementation plan relevant to this phase that require additional decision or setup.

### Docker Hub Private Registry Usage

The CI/CD pipeline pushes Docker images to private Docker Hub repositories instead of Azure Container Registry (ACR). Ensure the credentials `DOCKER_USERNAME` and `DOCKER_PASSWORD` are maintained in GitHub secrets.

### Rate Limiting via Sticky Sessions

We use `slowapi` with in-memory storage (`memory://`). Consistency across multiple Container App replicas is guaranteed by enabling **Session Affinity (sticky sessions)** on the Container App, ensuring a user's requests route back to the same replica where their rate limits are tracked in-memory.

### `pg_stat_statements` Extension

The implementation plan mentions using `pg_stat_statements` for query monitoring (Section 6). This is a Supabase-native extension but must be **explicitly enabled** in the Supabase SQL editor:
```sql
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
```
It is listed in the full schema migrations but not in `03_supabase_setup.md`.

### Load Test Results and Cost Validation File Names

The roadmap references `docs/05_load_test_results.md` and `docs/06_cost_validation.md` as output files. Since `05_` and `06_` are taken by admin dashboard and functions crons in this doc series, use `10_load_test_results.md` and `11_cost_validation.md` to avoid filename conflicts.

### `Azure Application Insights` Must Be Linked Before Logging

Application Insights (`agent-ochuko-insights`) is created in Phase 0 setup but needs to be **linked to the Container App** via the `APPLICATIONINSIGHTS_CONNECTION_STRING` environment variable. Set this in the Container App's environment variables using the Key Vault reference pattern before deploying the observability changes in 7.1.
