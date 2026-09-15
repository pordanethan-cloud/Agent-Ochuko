# Phase 8: Plan Re-Orientation for Long-Horizon OODA

> Status: **IMPLEMENTED** (2026-09). All sections below describe the design as
> shipped. Implementation deltas vs. this document: `replan_remaining()` gained
> `failed_step`, `openai_client`, and `nano_deployment` parameters (§3.1); the
> re-orientation chip shows `Plan re-oriented ×N` (replan budget counter) rather
> than per-plan `reasoning`, which the re-plan call does not emit (§3.6).
> Migration: `migrations/029_agent_task_replan_count.sql` must be applied before deploy.
>
> Related: `06_tools_architecture_claude_parity_and_ooda_loop.md` (per-turn tool loop),
> `01_phase1_foundation.md` (structured planner, refine_plan, HITL gates).

## 1. Ground-Truth Audit (verified against code, 2026-09)

Agent Mode's autonomy is asymmetric across two tiers:

| Tier | Location | Structure | OODA fidelity |
|---|---|---|---|
| Per-turn tool loop | `chat.py` `chat_stream_generator` (~L1470–3157) | Model-driven, `tool_choice="auto"` | Adaptive (real OODA) |
| Task / plan tier | `agent_planner.py` + `agent_task_manager.py` | Frozen 2–6 step plan | Rigid (plan-then-execute) |

### Verified rigidity constraints (task tier)

1. **Plan frozen at t=0.** `_STRUCTURED_PLANNER_SYSTEM` (`agent_planner.py:53`) caps plans
   at 2–6 steps. `refine_plan()` (`agent_planner.py:465`) is reachable only via the human
   `edit-plan` endpoint, which refuses edits after execution starts
   (`agent_tasks.py:273`: "Plan can only be edited before execution starts."). There is
   **no automatic re-planning** when observations contradict the plan.
2. **Linear iterator binds once.** `agent_task_manager.py:171`:
   `for step in self.task.plan:` — the iterator snapshots the list at loop start.
   Any mid-loop splice that reassigns `self.task.plan` would be **silently ignored**
   by the live iteration.
3. **Recovery is local and whitelisted.** `_ai_resolve_feedback_and_adapt`
   (`agent_task_manager.py:829`) can only react to step *failure*, max 2 attempts, and
   may only pivot within a hard whitelist of 9 web/execution tools
   (`agent_task_manager.py:899–902`: search_web, google_search, deep_research, scrape_web,
   execute_code, python, deploy_site, lookup_handle, synthesize_answer). It cannot touch
   sandbox_* / gmail / calendar / photos tools, and its only two actions are
   `retry_tool` and `proceed`.
4. **Information loss between steps.** `task.step_results.append({...})`
   (`agent_task_manager.py:284–290`) keeps only `summary` + artifacts; raw observations
   are distilled before downstream steps see them.
5. **Forced closure at the cap.** At `max_steps - 1` the per-turn loop forces
   `tool_choice="none"` so the model must narrate completion even if work is unfinished.

### Non-goals / anti-goals

- No unconstrained ReAct: pre-computed plans remain the anchor against drift
  (this is deliberate — see `01_phase1_foundation.md` design rationale).
- No DAG parallelism. The former `rewoo_planner.py` module was **deleted** in the
  dead-code cleanup that preceded this phase: it was test-only, never imported by
  production code, and its `PlanStep` model was incompatible with
  `agent_task_models.PlanStep`. README claims of ReWOO DAG execution were corrected.

## 2. Phase Goal

Allow the orchestrator to **re-orient the remaining plan** when a step's outcome
invalidates the premise of upcoming steps — without abandoning the plan-as-anchor
guarantees (bounded plans, HITL gates, circuit breakers, deterministic termination).

Concretely: when a step fails both AI adaptation retries, or its summary contradicts
the premise of the next step, the orchestrator may invoke a bounded, LLM-driven
**re-plan of the remaining steps only**, preserving completed state.

## 3. Design

### 3.1 `replan_remaining()` in `agent_planner.py`

Sibling of `refine_plan()`, but model-driven rather than human-driven:

```python
async def replan_remaining(
    original_plan: List[PlanStep],
    completed_results: List[Dict[str, Any]],   # task.step_results
    remaining_steps: List[PlanStep],           # plan[i:]
    goal: str,
    failed_step: Optional[PlanStep] = None,    # supplies the obstacle context
    auto_approve_level: str = "high",
    openai_client: Optional[AsyncAzureOpenAI] = None,
    nano_deployment: str = "gpt-5.6-luna",
) -> Optional[List[PlanStep]]:
```

Contract:

- Returns a fresh `List[PlanStep]` (re-indexed to continue the original numbering) or
  `None` on any parse/validation failure (caller keeps the original remaining steps).
- Every returned step passes `HITLGate.requires_approval(step, auto_approve_level)`
  (same pattern as `generate_structured_plan`, `agent_planner.py:452–453`).
- Tool names validated against the same roster as `_STRUCTURED_PLANNER_SYSTEM`.
- Completed steps are **never** re-planned or re-executed (caller splices only `plan[i:]`).
- JSON-only output, same defensive parsing as `generate_structured_plan`
  (markdown-fence stripping at `agent_planner.py:411–417`).
- Runs on the nano deployment (`gpt-5.6-luna`), mirroring `refine_plan`'s economy.

### 3.2 Executor loop conversion in `agent_task_manager.py`

Replace `agent_task_manager.py:171`:

```python
for step in self.task.plan:
```

with an index-based loop so splices take effect:

```python
i = 0
while i < len(self.task.plan):
    step = self.task.plan[i]
    ...
    i += 1
```

> **Why this matters:** `for` binds a snapshot iterator; `self.task.plan = old[:i] + new`
> inside a `for` loop is a silent no-op for the running iteration. This is the classic
> Python mutation pitfall flagged in the pre-implementation review.

### 3.3 Trigger point and guardrails

- **Trigger:** immediately after a step is marked `FAILED` following both
  `_ai_resolve_feedback_and_adapt` retries (after `agent_task_manager.py:307`),
  i.e. one attempted re-orientation per exhausted step.
- **Budget:** new App Config key `max_replans_per_task` (default `2`, `0` disables).
  Enforced with a per-task counter persisted on `AgentTask` (new field
  `replan_count: int = 0`) so it survives `save_state()`/resume.
- **Circuit breaker:** a re-plan does **not** reset `record_success/record_failure`
  history; if the breaker is already open, re-planning is skipped.
- **HITL:** any HIGH-risk step produced by a re-plan still pauses via the existing
  `PAUSED_FOR_HITL` path — no bypass.

### 3.4 SSE contract

New event, emitted in the existing raw-f-string style (there is no `emit_event`
helper in this codebase):

```python
yield f"data: {json.dumps({'type': 'agent_plan_reoriented', 'task_id': self.task.id, 'replan_count': self.task.replan_count, 'plan': [s.model_dump() for s in self.task.plan]})}\n\n"
```

### 3.5 State persistence & resume

- `save_state()` already serializes the whole `AgentTask`, so a spliced plan persists
  across pause/resume with no schema migration beyond `replan_count`.
- After a splice, `current_step` is recomputed from the first `PENDING` step.
- The resume skip at `agent_task_manager.py:172–173`
  (`if step.status in (COMPLETED, SKIPPED)`) continues to work unchanged because
  completed steps are preserved by construction.

### 3.6 Frontend (`frontend/src/pages/AgentModeWidgets.tsx` + SSE handler)

- Accept a second `agent_plan`-shaped event (`agent_plan_reoriented`) mid-execution.
- Render rule: replace only steps whose status is `pending`; keep `completed` /
  `failed` steps rendered in place with their original index labels.
- Show a subtle "Plan re-oriented" chip with `reasoning` from the re-plan response.

## 4. Test Plan

1. **Unit (test_agent_mode_phase1.py):** `replan_remaining` — valid JSON path
   (re-indexing, HITL re-classification, completed-step exclusion), invalid JSON →
   `None`, tool-name validation, `0` remaining steps → `None`.
2. **Manager loop:** simulate a step that fails both retries with
   `max_replans_per_task=1`; assert (a) splice applied, (b) second failure does not
   re-plan, (c) `replan_count` persisted by `save_state()`.
3. **Iteration-safety test:** construct a plan whose re-plan inserts 2 extra steps;
   assert the `while` executor visits them (would have silently no-op'd under `for`).
4. **SSE contract:** `agent_plan_reoriented` event well-formed; frontend handler test.
5. **Regression:** full matrix stays green
   (`tests/test_document_pipeline.py tests/test_agent_architecture.py tests/test_model_router.py` — 34/34 at Phase 8 design time).

## 5. Explicitly Out of Scope (future phases)

- DAG / parallel step execution (deleted with `rewoo_planner.py`; would require a
  fresh dependency-aware `PlanStep` model designed against the live task model).
- Hierarchical milestones with per-milestone micro-OODA loops.
- Persistent scratchpad / blackboard working memory to reduce summary distillation
  loss (`agent_task_manager.py:284–290`).
- Autonomous checkpoint-and-resume across sessions (currently HITL-pause only).

## 6. Reference: failure-mode walkthrough (the motivating example)

Goal: "Audit our Stripe webhook integration, fix signature bugs, write tests."
Step 1 observes the repo actually uses Paystack.

- **Today:** Step 2 ("patch Stripe validation") fails, `proceed` after 2 retries,
  Step 3 runs tests against nothing, synthesis invents a plausible story.
- **After Phase 8:** Step 2's failure exhausts retries → `replan_remaining()` is
  invoked → remaining steps are regenerated around Paystack → `agent_plan_reoriented`
  event updates the UI → execution continues with a plan that matches reality.
