# Phase 12 — End-to-End Testing & Pre-Launch QA

> **Duration**: 3–4 days
> **Depends on**: All phases complete. Run against a dedicated staging environment — never against production.

---

## 12.1 — Unit Test Suite (Day 1)

All tests in `backend/tests/`:

- [ ] `test_jwt_validator.py`:
  - Valid token → `200 OK`
  - Expired token → `401`
  - Wrong secret → `401`
  - `alg=none` attack (unsigned JWT) → `401`
- [ ] `test_policy_engine.py`:
  - ALLOW/DENY for each seeded access policy
  - Custom policy with multiple conditions
  - Priority ordering: higher-priority DENY overrides lower-priority ALLOW
- [ ] `test_model_router.py`:
  - THINK/SOLVE/DISCUSS routing correctness
  - Nano interceptor fires on greeting messages
  - Nano turn counter increments correctly
  - Nano budget exhaustion → falls through to selected mode
  - DISCUSS mode bypasses Nano interceptor entirely
- [ ] `test_token_budget.py`:
  - Atomic deduction: `tokens_used += N` where N < remaining budget → `200 OK`
  - Budget exhausted: `tokens_used + N > budget_limit` → `429`
  - Concurrent deductions do not double-spend (run 10 concurrent requests)
- [ ] `test_quota_guard.py`:
  - OCR pages exceeded → `429`
  - Vision calls exceeded → `429`
  - Speech seconds exceeded → `429`
- [ ] `test_dispatcher.py`:
  - Chat request → Pattern A (StreamingResponse)
  - Agent request → Pattern B (job created, `202` returned)
  - Correct job type created for each agent endpoint
- [ ] `test_queue_dispatcher.py`:
  - Message enqueued with correct payload shape
  - Correct queue name (`agent-jobs`) used
- [ ] `test_admin_endpoints.py`:
  - Non-admin JWT → `403`
  - `admin` JWT → `200`
  - `superadmin` JWT → can modify App Configuration via admin endpoint
- [ ] `test_registration_cap.py`:
  - Signup when at cap → exception / `400`
  - Signup when `registration_open = false` → exception / `400`

- [ ] Run: `pytest --cov=app --cov-report=html` — target **80%+ line coverage** on core modules
- [ ] All tests pass in the CI pipeline before any deployment

---

## 12.2 — Integration Tests (Day 1–2)

- [ ] Use a **separate Supabase test project** (not production)
- [ ] Seed test data: 5 users (one per role: guest, user, power_user, admin, superadmin), 10 conversations, 100 messages, 5 jobs
- [ ] **RLS tests** — for each of the 5 role JWTs, attempt:
  - Read own data → ✅ returns data
  - Read another user's data → ❌ returns empty result (not an error)
  - Write to another user's conversation → ❌ blocked
  - Admin reads all data → ✅
  - Guest reads shared conversation → ✅, reads non-shared conversation → ❌
- [ ] **Block guard integration**: insert `google_sub` into `blocked_identities` → attempt login → `403`
- [ ] **Budget integration**: set budget to 100 tokens → send message using > 100 tokens → `429`
- [ ] **Compaction integration**: insert 60 messages → trigger `conversation_summarizer` manually → verify:
  - Summary message inserted with `is_summary = TRUE`
  - Old messages have `is_archived_msg = TRUE`
  - LLM context builder returns only summary + recent messages
  - All messages still visible in frontend scroll

---

## 12.3 — E2E Tests with Playwright (Day 2–3)

All tests in `tests/e2e/`:

- [ ] `auth.spec.ts` — Google OAuth login → profile created in `profiles` table → redirected to `/chat`
- [ ] `chat.spec.ts` — send message → streaming renders token-by-token → message saved in DB → appears on page reload
- [ ] `mode_switch.spec.ts` — switch to THINK mode → send message → verify routing badge shows "THINK · GPT-5.4"
- [ ] `file_upload.spec.ts` — drag PDF into input → upload progress → OCR job created → `202` returned → result appears in chat via Realtime
- [ ] `image_gen.spec.ts` — send image generation request → image appears in chat (may take 10–30s)
- [ ] `voice.spec.ts` — click mic → speak (or use mock `MediaRecorder`) → transcript appears in input bar
- [ ] `share.spec.ts` — share conversation → open link in incognito window → guest view renders → JSON export downloads correctly
- [ ] `registration_cap.spec.ts` — set cap to current count via admin → attempt signup in incognito → rejected with clear message
- [ ] `admin.spec.ts` — login as admin → navigate all admin pages → block a user → verify blocked user's next request returns `403`
- [ ] `maintenance.spec.ts` — enable maintenance mode via admin → non-admin user gets `503` → disable → service resumes
- [ ] `budget_exhaustion.spec.ts` — exhaust budget → next request shows `429` error message in UI

- [ ] Run against **staging environment** (not production)
- [ ] All tests pass in CI pipeline (Playwright in GitHub Actions with browser install step)

---

## 12.4 — Manual Verification Checklist (Day 3–4)

- [ ] **Streaming chat**: tokens appear one by one, not buffered — no delay between first and second token
- [ ] **Model switch**: change `THINK_MODEL_DEPLOYMENT` in App Configuration → next request uses new model — confirmed via routing badge, no restart needed
- [ ] **Artifact panel**: shows on 1200px+ screen width, absent on 600px width
- [ ] **Voice input**: speak → transcript appears in input bar, grammar corrected, editable
- [ ] **Voice output**: click play on assistant message → audio plays → stop button works
- [ ] **OCR**: upload 5-page PDF → all pages extracted → result rendered in chat with table formatting
- [ ] **Vision**: upload image → description appears in chat
- [ ] **Image gen**: request image → generated image appears in chat (may take 10–30s)
- [ ] **File gen**: request DOCX file → download button appears → file downloads correctly
- [ ] **Block**: admin blocks user via dashboard → user's next request returns `403` with clear message
- [ ] **Suspend**: admin suspends user → `403` → admin activates → user resumes normally
- [ ] **Registration cap**: set cap to current user count → new signup shows "Registration is currently closed"
- [ ] **Budget exhaustion**: exhaust budget → `429` with "Resets at midnight UTC" message → midnight reset → resumes
- [ ] **Maintenance mode**: toggle ON → non-admin users get `503` → toggle OFF → service resumes
- [ ] **Shared conversation**: share → open link in incognito → read-only renders correctly → JSON export downloads
- [ ] **Conversation search**: type keyword → matching conversations highlighted in sidebar
- [ ] **Conversation archive**: old conversation archived by cron → not shown by default → "Show archived" reveals it
- [ ] **Chat compaction**: 60+ message conversation → after cron runs → new messages reference compacted context correctly
- [ ] **Mobile**: full chat flow works on Chrome Android and Safari iOS (voice may have reduced functionality on Safari)

---

## Milestone

Every feature tested at unit, integration, and E2E level. Manual QA confirms real-world behavior across all platforms. System is ready for production launch.

---

## Considerations

> Items from the implementation plan relevant to this phase that require additional context.

### `test_model_router.py` Requires DISCUSS Mode Test

The implementation plan's test list (Section 12.1) covers THINK/SOLVE/DISCUSS/Nano routing. Make sure `test_model_router.py` explicitly tests DISCUSS mode:
- DISCUSS mode with a greeting → bypasses Nano interceptor, routes to GPT-5.4 Nano with DISCUSS prompt
- DISCUSS mode with a complex question → still routes to GPT-5.4 Nano (not escalated)

### Playwright Google OAuth Mocking

Real Google OAuth requires a real browser session, which is difficult to automate in CI without service accounts. For `auth.spec.ts`, use Playwright's `storageState` to inject a pre-authenticated Supabase session, or mock the OAuth flow entirely. See [Playwright Auth Docs](https://playwright.dev/docs/auth) for session state strategies.

### Staging Environment Setup

The E2E tests require a fully-functional staging environment (separate Supabase project + separate Azure resources). This is not defined in the implementation plan's setup guides. Before Phase 12, provision:
- A second Supabase project: `agent-ochuko-staging`
- All seed data and migrations applied identically
- A staging Container App revision or a separate staging slot
- E2E tests pointed at the staging URLs via a `.env.test` file

### Compaction Integration Test Timing

The compaction integration test (12.2) requires triggering the `conversation_summarizer` manually (since the cron runs at 3am). Azure Functions support manual trigger via the Azure Portal "Test/Run" button or via the Azure Functions Core Tools CLI:
```
func azure functionapp logstream agent-ochuko-functions
```
Or call the HTTP trigger endpoint if the function is exposed with an HTTP trigger for testing.
