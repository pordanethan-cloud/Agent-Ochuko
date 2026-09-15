# 09 — Phase 4 Mini-OODA Engine, Phase 9 Working Memory, and the Think-vs-Agent Gap

**Status:** Shipped (backend) · **Scope:** `agent_ooda.py`, `agent_task_manager.py`, `agent_task_models.py`, `hybrid_memory.py`, `scripts/030_agent_task_scratchpad.sql`

---

## 1. Phase 4 recap — the shared OODA engine

Phase 4 extracted the conversational loop's primitives into `app/core/agent_ooda.py` so **one engine drives two tiers**:

- `build_observations(calls, outputs)` — zips tool calls with outputs, classifies each as `ok`/`error` (`tool_output_failed(None)` is **True** by contract: a missing output is never progress), truncates summaries to 160 chars.
- `OODATurnTelemetry` — records `observe`/`orient` phases; `summary()` reproduces the shipped `agent_telemetry` SSE payload shape.
- `OODASoftCap(nominal_cap=2, grace_iters=1, hard_ceiling=4, stall_limit=3)` — the shared cap dynamics. `hard_ceiling` defaults to `nominal_cap × 2`.

### Agent Mode mini-OODA (`execute_plan_stream`)

The old fixed retry loop was replaced with a per-step mini-OODA governed by `OODASoftCap`:

| Dynamic | Value | Meaning |
|---|---|---|
| Nominal budget | 2 attempts | Unchanged default path |
| Pivot (orient to a NEW tool) | +1 grace attempt, up to hard ceiling 4 | Progress grants extension via `propose_extension` |
| Stall (same failing tool again) | counted; 3 consecutive non-pivot decisions trip the breaker | `stall_limit=3` — a transient failure still gets its second identical retry (raised from 2 by user approval) |
| Stall breaker | forced closure | Hands off to the Phase 8 replan path instead of thrashing |

SSE contract (pinned by `TestTaskManagerMiniOoda`): `agent_step_ooda` (orient decisions with `attempt/decision/progressed/pivot/reasoning`, plus `status: cap_extended` events), and `agent_step_complete` carrying an `ooda` block `{attempts, extensions, stall_breaker, phases[-10:]}`. Frontend (Batch C + Phase 4 UI): the `agent_step_ooda` handler in `Dashboard.tsx`, the `OODA ×N +ext · stalled` chip and expandable orient reasoning in `AgentModeWidgets.tsx` (`hasDetail` includes `ooda_reasoning`).

`_ai_resolve_feedback_and_adapt` now receives `attempt_budget` (fixes the hardcoded "of 2" prompt bug — budget grows with soft-cap extensions).

## 2. Why Think Mode beat Agent Mode on basic tasks (gap analysis)

User-observed: basic tasks finished better/faster in Think Mode. Four compounding root causes, found by auditing `_execute_single_step`:

1. **Unknown tools fake-succeed (executor roster gap).** The dispatch has dedicated branches for `search_web, deep_research, execute_code, lookup_handle, youtube_transcript, deploy_site, ask_user_input, gmail_*, calendar_*, photos_*, mcp_*/workstation_*, sandbox_ls/read/write/edit, present_deliverable` — but **no branches for `fetch_url, memory_save/recall/edit, terminal, generate_image, fetch_stock_image`**. The planner's prompt *recommends* some of these (`fetch_url`, `memory_save`), so the step falls into the final `else`, which calls `sub_agents.compress_text` to *write a plausible answer about the step description* and returns `success=True`. Think Mode is immune: its native tool loop exposes the full 18-tool roster (`agent_tools.py`), so a missing tool degrades at choose-time, not as a fake success at execute-time.
   **→ Named follow-up:** add the missing dispatch branches (or a generic route-into-full-roster fallback).
2. **Frozen plan vs. per-iteration choice.** Agent Mode commits to a plan before seeing tool output; basic tasks needing one detour get stuck in retry/pivot loops instead of just doing the detour. Think Mode re-decides every turn (up to ~20 iterations).
3. **Distillation loss.** Later steps only saw the immediately preceding step's summary (`build_step_payload` includes just the LAST completed step) — `step_results` keep ~400–500-char summaries and raw outputs were dropped. **→ Fixed by Phase 9 (below).**
4. **Cap asymmetry.** Mini-OODA's 2–4 attempts vs. Think Mode's ~20-iteration loop with full OODA discipline.

**Not** a sandbox permissions problem: `sandbox_*` tools are fully wired (including R2 upload + artifact generation on `sandbox_write`).

## 3. Phase 9 — blackboard scratchpad working memory

### Why

The rigidity constraint: *information loss between steps*. `step_results` keeps only distilled summaries; later steps couldn't see earlier findings, and the WHY behind pivots/failures was discarded entirely.

### Design

`AgentTask.scratchpad: Dict[str, Any]` — a capped blackboard persisted alongside the task in `agent_tasks.scratchpad` (jsonb, migration **030**):

```json
{"entries": [{"id": "fact-3-a1b2c3d4", "kind": "fact", "content": "Step 2 (search_web): repo uses bun",
              "step_index": 2, "created_at": "2026-09-15T..."}]}
```

- **Kinds:** `fact | decision | discovery | artifact_ref | open_question | constraint`
- **Caps:** `SCRATCHPAD_MAX_ENTRIES = 30` (oldest evicted), `SCRATCHPAD_MAX_CONTENT = 500` chars — protects prompt budgets.
- **Pure helpers (unit-tested, no manager instantiation needed):** `append_scratchpad_entry()` and `scratchpad_digest()` live in `agent_task_models.py`.

### Capture points (`AgentTaskManager._write_note`, all exception-safe)

| Site | Kind | Content |
|---|---|---|
| Step success | `fact` | `Step N (tool): <summary[:300]>` |
| Step produced artifacts | `artifact_ref` | `Step N produced artifact: <filename>` |
| Mini-OODA retry decision | `decision` | `Step N retry #k: pivot|stall to <tool> — <reasoning[:200]>` |
| Stall breaker trip | `decision` | `stall breaker tripped after N non-pivot decisions` |
| Step final failure | `decision` | `Step N failed after mini-OODA (k attempt(s))` |
| Discovery replan (Phase 8.1) | `discovery` | `Premise divergence at step N: <reason>` |
| Failure replan (Phase 8) | `discovery` | `Plan re-oriented after step N failure: <error[:300]>` |

### Injection points (`AgentContextCompressor`, `hybrid_memory.py`)

- `build_step_payload` — inserts a `WORKING MEMORY (facts and decisions from earlier steps):` section between the previous-step result and the current target, giving **every** step visibility into ALL earlier facts/decisions (not just the immediately preceding summary).
- `build_synthesis_payload` — the final answer is grounded in the same working memory (e.g. "do not invent files" pairs with actual `artifact_ref` entries).

### Persistence

`save_state()` now writes `"scratchpad": self.task.scratchpad` (explicit column mapping — matching migration 030). Empty-board tasks write `{}`; the column defaults to `'{}'` for rows created before the migration.

## 4. Validation

- `tests/test_scratchpad.py` — 4 classes: append shape/caps/eviction/no-op, digest formatting/malformed-safety, model round-trip, compressor injection, manager wiring (AST + source contract, mirroring `test_ooda_engine.py` style).
- Structural contracts from Phase 4 remain pinned in `tests/test_ooda_engine.py` (mini-OODA tuning incl. `stall_limit=3`, SSE shapes, `TestChatLoopUsesExtractedPrimitives`).

## 5. Deliberate behavior changes (audit trail)

1. **Stall limit 2 → 3** (user-approved): restores the transient-failure second retry; only genuine thrash trips the breaker.
2. **Pivot-based extension**: orienting to a NEW tool grants +1 attempt up to ceiling 4 (previously impossible).
3. **Stall breaker skips hopeless re-execution**: forced closure feeds the replan path instead of burning the final attempt on the same failing tool.
4. **Scratchpad notes**: new prompt sections (`WORKING MEMORY`) appear in step + synthesis payloads when the board is non-empty — additive; empty boards produce byte-identical prompts.

## 6. Addendum — live validation finding: workstation notice soft fake-success (root cause #5)

The planned live validation ("Look up my books folder") failed in the field. Diagnosis pinned down by direct code audit + live probes:

1. **Companion Bridge daemon was not running** (`http://127.0.0.1:3920/health` refused). The browser pre-fetch relay (`Dashboard.tsx` → bridge → `workstation_dirs`/`workstation_folder_inventory.txt` cached into the backend workspace, `chat.py`) therefore contributed **zero** cache files.
2. The executing backend **could not see `C:\Users` on its own filesystem** (the "Workstation Notice" fires only when the resolved path doesn't exist locally) → the backend was the **remote deployment**. Architectural fact: `WorkstationMCP._query_bridge` targets `127.0.0.1:3920` **of the backend server**; a loopback-bound bridge on the user's PC is unreachable from a cloud backend even when running.
3. **Soft fake-success**: `agent_task_manager.py` generic `mcp_*` dispatch classified errors via `str(output).startswith("Error")` — the output starts with `"Workstation Notice:"`, so the blocked step returned **`success=True`**. Mini-OODA stall detection, replan, and the Phase 9 scratchpad never saw the failure (validating the audit-trail design: nothing to capture, because the step *looked* successful).
4. **Misleading copy**: the notice said "ensure Workstation Access is toggled ON in Settings" while the toggle was on — three distinct failure modes (toggle off / bridge daemon down / bridge unreachable from remote backend) collapsed into one wrong instruction.

**Fixes shipped (this batch):**

- `workstation_mcp.py`: `_workstation_unreachable_notice(path)` — distinct, actionable copy at both sites (`read_file`, `list_directory`); names the Companion Bridge, the daemon start command, and the backend co-location constraint. The `"Workstation Notice:"` prefix is now a **documented cross-module contract**.
- `agent_task_manager.py`: both workstation dispatch paths (generic `mcp_*` branch and dedicated `mcp_workstation_read` branch) classify the notice as a step **failure**, surface blocker copy (`Companion Bridge daemon not reachable` vs `toggle is OFF and …`), and write a scratchpad `decision` note (new 8th/9th capture points).
- `tests/test_workstation_notice.py`: 4 tests pinning notice copy, failure classification, scratchpad capture, and toggle-state blocker copy.

**Recorded follow-ups (Phase C, architecture):** browser-relayed reads or a bridge dial-out/tunnel so a cloud backend can serve Workstation Access; plus the pre-existing executor-roster gap (§2 root cause #1 — missing dispatch branches for `fetch_url`, `memory_save/recall/edit`, `terminal`, `generate_image`, `fetch_stock_image`).

**Additional latent bugs found during this batch (recorded, not fixed):**

- `MCPRegistry` is a process-wide **singleton** (`__new__` + `_initialized` guard) whose `__init__` silently ignores `workspace_root` on every construction after the first — any caller passing a different workspace root gets the first caller's root. Manager tests now patch the whole class to avoid instantiating it.
- The dedicated `mcp_workstation_read`/`workstation_read` dispatch branch in `_execute_single_step` is **unreachable**: the earlier generic `mcp_*`/`workstation_*` `startswith` branch catches every such name first. The branch's new notice handling is defense-in-depth only; the classification fix lives in the generic branch.

**Live validation runbook (Phase B, user actions):** run migration `030` in Supabase; start the Companion Bridge daemon on the PC; run the **backend locally** (co-located); re-run "Look up my books folder" in Agent Mode and confirm: steps dispatch through the bridge, scratchpad entries accumulate (incl. any `decision` notes), persist via `save_state`, and appear in step prompts + synthesis.

