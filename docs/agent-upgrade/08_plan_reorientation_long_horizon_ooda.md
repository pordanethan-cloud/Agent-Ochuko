# Phase 8: Plan Re-Orientation for Long-Horizon OODA

> Status: **DESIGNED, NOT IMPLEMENTED** — this document is the approved implementation
> plan. Execution is deferred until a subsequent work cycle.
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
