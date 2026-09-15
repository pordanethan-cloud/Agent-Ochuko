# app/core/agent_ooda.py
"""
OODA loop dynamics — Phase 2/3 support primitives.

Soft-cap state machine (Claude-parity): the conversational OODA loop keeps
iterating while the model makes tool-call progress. Forced closure
(tool_choice="none") is demoted to a BACKSTOP that fires only when:
  - the stall circuit breaker trips (consecutive failed-tool iterations), or
  - the hard ceiling (nominal cap × multiplier) is exhausted.
While progress continues, the iteration budget self-extends in small grace
grants (runtime-tunable via App Config; see agent_config.get_ooda_dynamics).

Also hosts the update_todo (TodoWrite analog) normalizer for Phase 3 —
pure logic, no I/O, fully unit-testable.
"""

from typing import Any, Dict, List, Optional


# ── Tool-output failure detection ────────────────────────────────────────────

# Tool executors in chat.py signal failure by emitting a marker-prefixed
# descriptor near the head of the output ("search_web error: ...",
# "memory_save blocked: ...", "memory_save conflict: ..."). Success outputs
# are prose / result payloads.
_FAILURE_MARKERS = ("error:", "conflict:", "blocked:", "failed:", "exception:")


def tool_output_failed(out: Any) -> bool:
    """
    Heuristically classifies a tool output string as failed. Never raises.
    None counts as failed (a missing output is never progress).
    """
    if out is None:
        return True
    head = str(out)[:80].lower()
    return any(marker in head for marker in _FAILURE_MARKERS)


# ── Phase 2: soft-cap state machine ─────────────────────────────────────────

class OODASoftCap:
    """
    Tracks per-iteration tool progress and decides budget extension vs
    forced closure for the conversational OODA loop.

    Contract with the chat.py loop:
      - after each tool-execution iteration, call note_iteration(outputs)
      - if note_iteration tripped the stall breaker (forced_close), the loop
        pins effective_max_iterations to iteration + 1 so the next pass is a
        forced tool_choice="none" synthesis turn (the backstop)
      - otherwise call propose_extension(iteration, effective_cap); a
        non-None return is the new effective cap (grace granted because the
        loop is still making progress)
    """

    def __init__(
        self,
        nominal_cap: int,
        hard_ceiling: Optional[int] = None,
        grace_iters: int = 3,
        stall_limit: int = 2,
    ):
        self.nominal_cap = max(1, int(nominal_cap))
        # Default hard ceiling mirrors shipped dynamics (hard_ceil_mult = 2):
        # nominal budget may self-extend ×2 while tool-call progress continues.
        self.hard_ceiling = max(self.nominal_cap, int(hard_ceiling or self.nominal_cap * 2))
        self.grace_iters = max(1, int(grace_iters))
        self.stall_limit = max(1, int(stall_limit))
        self.stall_count = 0
        self.progress_count = 0
        self.extensions_granted = 0
        self.forced_close = False

    def note_iteration(self, outputs: List[Any]) -> bool:
        """
        Records the outcome of one tool-execution iteration.
        Returns True when at least one output represents progress.
        An iteration with no tool outputs is not progress (the loop would
        have broken anyway; recorded defensively).
        """
        if outputs and any(not tool_output_failed(o) for o in outputs):
            self.progress_count += 1
            self.stall_count = 0
            return True
        self.stall_count += 1
        if self.stall_count >= self.stall_limit:
            self.forced_close = True
        return False

    def propose_extension(self, iteration_done: int, effective_cap: int) -> Optional[int]:
        """
        Called after iteration_done completes. Returns the new effective cap
        when a grace extension is granted, else None. Extension happens only
        when the loop just exhausted its effective cap while still making
        progress and the hard ceiling has not been reached.
        """
        next_iter = iteration_done + 1  # the iteration about to run
        if next_iter < effective_cap:
            return None                      # budget remains — nothing to extend
        if self.forced_close or self.stall_count > 0:
            return None                      # stalling — no grace for thrash
        if effective_cap >= self.hard_ceiling:
            return None                      # hard backstop reached — close now
        new_cap = min(effective_cap + self.grace_iters, self.hard_ceiling)
        self.extensions_granted += 1
        return new_cap


# ── Phase 4: shared loop-engine primitives ───────────────────────────────────
# Extracted from chat.py's conversational OODA loop so both tiers (the
# per-turn tool loop and Agent Mode's per-step mini-OODA) distill
# observations and phase telemetry through the same pure logic.


def build_observations(
    tool_calls: List[Any],
    tool_outputs: List[Any],
) -> List[Dict[str, Any]]:
    """
    Distills one iteration's tool executions into orient records.

    Zips the issued tool calls with their outputs and classifies each as
    ok/error via tool_output_failed. Summaries are truncated to 160 chars.
    Tolerates length mismatches (zips short) and junk outputs (never raises).
    """
    observations: List[Dict[str, Any]] = []
    for tc, t_out in zip(tool_calls, tool_outputs):
        name = "tool"
        if isinstance(tc, dict):
            name = tc.get("name") or "tool"
        else:
            name = getattr(tc, "name", None) or "tool"
        ok = not tool_output_failed(t_out)
        observations.append({
            "name": name,
            "status": "ok" if ok else "error",
            "summary": str(t_out)[:160],
        })
    return observations


class OODATurnTelemetry:
    """
    Phase recorder for one OODA turn (either tier).

    Wraps the phases list chat.py appends to inline; summary() renders the
    agent_telemetry SSE payload exactly as shipped (last 20 phase records).
    """

    def __init__(self) -> None:
        self.phases: List[Dict[str, Any]] = []

    def record_observe(
        self,
        iteration: int,
        progressed: bool,
        observations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        record = {
            "phase": "observe",
            "iteration": iteration,
            "progressed": progressed,
            "observations": observations,
        }
        self.phases.append(record)
        return record

    def record_orient(
        self,
        iteration: int,
        decision: str,
        reasoning: str = "",
        **extra: Any,
    ) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "phase": "orient",
            "iteration": iteration,
            "decision": decision,
            "reasoning": reasoning,
        }
        record.update(extra)
        self.phases.append(record)
        return record

    def summary(
        self,
        mode: str,
        iterations: int,
        cap: "OODASoftCap",
    ) -> Dict[str, Any]:
        """Renders the agent_telemetry payload (matches the shipped shape)."""
        tool_iterations = sum(
            1 for p in self.phases if p.get("phase") == "observe"
        )
        return {
            "mode": mode,
            "iterations": iterations,
            "tool_iterations": tool_iterations,
            "cap_extensions": cap.extensions_granted,
            "stall_breaker": bool(cap.forced_close),
            "phases": self.phases[-20:],
        }


# ── Phase 3: update_todo (TodoWrite analog) ─────────────────────────────────

_VALID_TODO_STATUS = ("pending", "in_progress", "completed")
_MAX_TODO_ITEMS = 50


def normalize_todo_list(raw: Any) -> List[Dict[str, Any]]:
    """
    Normalizes an update_todo payload into [{"content", "status"}] items.
    Tolerates junk input (never raises): string items become pending; dict
    items accept content/task/text keys; unknown statuses coerce to pending.
    Mirrors Claude Code's TodoWrite shape.
    """
    if isinstance(raw, dict):
        raw = raw.get("todos")
    if not isinstance(raw, list):
        return []
    todos: List[Dict[str, Any]] = []
    for item in raw[:_MAX_TODO_ITEMS]:
        if isinstance(item, str):
            entry = {"content": item.strip(), "status": "pending"}
        elif isinstance(item, dict):
            content = str(
                item.get("content") or item.get("task") or item.get("text") or ""
            ).strip()
            status = str(item.get("status") or "pending").strip().lower()
            if status not in _VALID_TODO_STATUS:
                status = "pending"
            entry = {"content": content, "status": status}
        else:
            continue
        if entry["content"]:
            todos.append(entry)
    return todos


def todo_summary(todos: List[Dict[str, Any]]) -> str:
    """Renders the normalized todo list as the model-facing tool output."""
    done = sum(1 for t in todos if t["status"] == "completed")
    active = [t["content"] for t in todos if t["status"] == "in_progress"]
    rendered = "; ".join(f"[{t['status']}] {t['content']}" for t in todos)
    summary = f"Todo list updated ({len(todos)} items, {done} completed): {rendered}"
    if active:
        summary += f" | Currently active: {active[0]}"
    return summary