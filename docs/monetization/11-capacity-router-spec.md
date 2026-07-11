# Capacity Router — Spec

Phase 5 build sheet.

---

## What & how

### What exists today

All chat inference uses one global `AsyncAzureOpenAI` client from
`get_openai_client()` in `chat.py`. It reads `AZURE_OPENAI_ENDPOINT` and
`AZURE_OPENAI_API_KEY` from env. Called from:

| Location | Purpose |
|---|---|
| `chat.py` ~1057 | Compaction |
| `chat.py` ~1138 | Stream path |
| `chat.py` ~1891 | Auto title generation |
| `chat.py` ~2080 | Agent loop |
| `main.py` ~48 | Startup warmup |

`model_router.py` selects deployment *names* (nano, standard, etc.) from App
Configuration. It does not select *which Azure account* to bill.

`reconcile_token_budget` runs post-stream (~line 1847). `usage_stats` aggregates
hourly for admin charts — separate from per-provider cost tracking.

### What the router must accomplish

One function decides which Azure credential handles a request. Platform deployment
and renter donations are the same kind of row in `capacity_providers`. Subscribers
prefer platform capacity; renters draw from the pool. Every inference logs cost
against the provider that served it.

### How (directives)

1. **v1 scope: chat completions in `chat.py` stream path only.** `audio.py`, code
   executor (`get_code_executor_client`), and Azure Functions keep platform env creds.
2. **No silent fallback.** If no provider has quota, return 503. Do not fall back to
   env vars silently — that hides pool exhaustion.
3. **Client cache per provider.** `Dict[UUID, AsyncAzureOpenAI]` — invalidate on
   deactivate or key rotation.
4. **Deployment mapping is per provider.** Renters may name deployments differently.
   `capacity_providers.deployment_mapping` maps logical keys (`nano`) to their
   actual deployment name.
5. **Subscriber overflow to renter pool is behind a flag** until Phase 9 legal
   clearance: `RENTER_POOL_OVERFLOW_ENABLED`.
6. **Access gate runs before router.** No point selecting a provider for a user
   who shouldn't be chatting.

### Routing rules (locked for v1)

```
admin        → platform rows only, ignore quota (or high cap)
subscriber   → platform rows (priority DESC, quota room)
               → if none && OVERFLOW_ENABLED → renter pool
               → else 503
renter       → any active row with quota (own row included)
               → prefer own row if active (optional, not required)
NULL tier    → 403 before router (access_gate)
```

### Decisions you own

| Decision | Options |
|---|---|
| Own-row preference for renters | Always prefer own key / round-robin all pool rows |
| Quota exhaustion mid-stream | Fail request / complete stream then mark provider degraded |
| Cost estimation | Token counts × price table / Azure billing API later |
| `reset_quotas` cadence | 1st of month / rolling 30d from provider creation |

---

## What must be implemented

### `capacity_router.py` API

```python
@dataclass
class RoutedClient:
    client: AsyncAzureOpenAI
    capacity_provider_id: UUID
    deployment_mapping: dict[str, str]

async def get_client_for_request(
    user_id: str,
    access_tier: str | None,
    logical_model: str,  # e.g. "nano" from model_router
) -> RoutedClient:
    ...

async def log_usage(
    capacity_provider_id: UUID,
    user_id: str,
    conversation_id: UUID | None,
    tokens_input: int,
    tokens_output: int,
    model: str,
    cost_usd: Decimal,
) -> None:
    # INSERT usage_log; UPDATE capacity_providers.quota_used_usd

async def reset_quotas() -> int:
    # WHERE quota_reset_date <= today: quota_used_usd = 0, bump reset_date
```

### Provider selection query (pseudocode)

```sql
SELECT * FROM capacity_providers
WHERE is_active = true
  AND type = :type_filter
  AND quota_used_usd < quota_limit_usd
ORDER BY priority DESC, quota_used_usd ASC
LIMIT 1
```

- Subscriber platform pass: `type_filter = 'platform'`
- Subscriber overflow: `type_filter = 'renter'`, only if flag enabled
- Renter: no type filter, all active rows with room

### Integration in `chat.py`

Replace in stream generator (and compaction/title/agent if same request context):

```python
# Before
client = get_openai_client()

# After
routed = await get_client_for_request(user_id, profile.access_tier, logical_model)
client = routed.client
deployment = routed.deployment_mapping.get(logical_model, logical_model)
```

Post-stream (existing block ~1847):

```python
await log_usage(
    capacity_provider_id=routed.capacity_provider_id,
    user_id=user_id,
    conversation_id=conversation_id,
    tokens_input=input_tokens,
    tokens_output=output_tokens,
    model=deployment,
    cost_usd=estimate_cost(...),
)
# existing reconcile_token_budget stays — complementary, not replaced
```

### `access_gate.py`

Called at start of `/v1/responses/stream` handler and in middleware:

```python
async def assert_chat_access(user_id: str, profile: dict, subscription: dict | None) -> None:
    ...
```

Maps to HTTP codes in `01-implementation-plan.md`.

### Middleware order

Current: `Maintenance → Block → TokenBudget → Quota → Audit`

Insert **AccessGate** before TokenBudget:

```
Maintenance → Block → AccessGate → TokenBudget → Quota → Audit
```

AccessGate needs profile + subscription — cache per user_id TTL 60s to avoid DB
on every request.

### Anomaly check (v1 simple)

Inside TokenBudgetMiddleware or post-stream: if today's `usage_log` sum for user
> 3× trailing 7-day daily average → log warning + optional admin alert. Not a
separate service.

### `reset_quotas`

Wire into existing `functions/` cron pattern (same as usage aggregation). Daily
check: `UPDATE capacity_providers SET quota_used_usd = 0, quota_reset_date = ...`
where `quota_reset_date <= CURRENT_DATE`.

### Feature flag

```python
RENTER_POOL_OVERFLOW_ENABLED = os.getenv("RENTER_POOL_OVERFLOW_ENABLED", "false").lower() == "true"
```

Default `false` until Phase 9.

### Files

| File | Action |
|---|---|
| `backend/app/services/capacity_router.py` | New |
| `backend/app/services/access_gate.py` | New |
| `backend/app/api/v1/endpoints/chat.py` | Replace client calls in stream path |
| `backend/app/middleware/access_gate.py` | New, or extend token_budget |
| `functions/function_app.py` | Add `reset_quotas` timer trigger |

### Out of scope v1 (document, don't build)

| Call site | Stays on env creds |
|---|---|
| `audio.py` | Platform TTS |
| Code executor | Azure AI Projects |
| `function_app.py` background jobs | Platform |
| Compaction/title if you choose | Document decision — can stay platform to reduce scope |

### Checkpoint

- [ ] Subscriber request hits platform row in `usage_log`
- [ ] Renter request hits a pool row
- [ ] All providers at quota → 503 with `{"error": "capacity_exhausted"}`
- [ ] Deactivated provider not selected
- [ ] `deployment_mapping` respected for renter with non-standard deployment name
- [ ] Overflow flag off → subscriber never hits renter row
