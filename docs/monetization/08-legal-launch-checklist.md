# Legal & Launch Gate

**This phase blocks Phase 5 (capacity router) from going live with real
subscriber traffic, even if the code is fully built and tested.** Routing a
paying subscriber's request through a renter's personal Azure resource is,
functionally, reselling access to someone else's Azure capacity — that has
real consequences if not checked first.

## Checklist

- [ ] **Azure OpenAI Product Terms / Acceptable Use Policy reviewed.** Confirm
      multi-tenant routing through a renter's personal Azure OpenAI resource
      doesn't violate Microsoft's terms for that resource type. A flagged or
      suspended renter account breaks the pool without warning.
- [ ] **Renter agreement drafted** (can be informal, but written) covering:
  - what traffic is allowed to route through their key
  - that you're not liable for Microsoft-side quota/ToS actions against
    their account
  - how they exit / deactivate
- [ ] **Privacy disclosure decided.** A subscriber's prompts routed through a
      renter's Azure resource are visible in that renter's Azure tenant logs
      (Content Safety logs, resource diagnostics) — the renter can technically
      see paying customers' conversation content. Either:
  - disclose this to subscribers explicitly, or
  - restrict renter-routed traffic to non-sensitive request types and keep
    anything sensitive on the platform's own deployment only.
- [ ] **Minimum quota threshold enforced in code**, not just documented — the
      $5/month floor in `register-capacity` (already specified in
      `07-api-endpoints.md`) is the fairness mechanism preventing a
      near-empty Azure account from getting full free access.
- [ ] **Renter quota exhaustion behavior decided and implemented.** When a
      renter's own Azure account runs out of credit or gets disabled, decide:
      grace period + notice, or immediate downgrade
      (`renter_onboarding_status = 'suspended'`). Right now this would
      otherwise fail silently.
- [ ] **Renter transparency shipped**, not deferred — the aggregate usage
      self-view (`GET /v1/renter/usage`) exists precisely so a renter can see
      what's being used against their donated quota. Ship it in Phase 4/5,
      not as a "nice to have" later.

## Not blocking, but worth deciding before scale

- Whether to formalize Key Vault for credential storage once there's a real
  security audit requirement — v1 app-level AES-256-GCM encryption is a
  reasonable stopgap, not a permanent answer.
- Whether renter capacity ever extends beyond chat completions (TTS, code
  executor) — currently explicitly out of scope for v1.
