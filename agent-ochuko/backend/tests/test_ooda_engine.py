"""
Phase 4 (shared OODA engine + Agent Mode mini-OODA) — unit tests.

Covers:
- build_observations / OODATurnTelemetry: the loop-engine primitives
  extracted from chat.py into app.core.agent_ooda (one engine, two tiers).
- agent_task_manager mini-OODA wiring: OODASoftCap import/tuning, the
  effective_attempts retry loop, agent_step_ooda SSE payload contract,
  and the `ooda` block on agent_step_complete.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.agent_ooda import (  # noqa: E402
    OODASoftCap,
    OODATurnTelemetry,
    build_observations,
)

_TASK_MANAGER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "core", "agent_task_manager.py",
)


class TestBuildObservations:
    """Pure-function contract: zip tool calls with outputs, classify, truncate."""

    def test_basic_distillation(self):
        calls = [{"name": "search_web"}, {"name": "fetch_url"}]
        outputs = ["results about oidc", "markdown page body"]
        obs = build_observations(calls, outputs)
        assert obs == [
            {"name": "search_web", "status": "ok", "summary": "results about oidc"},
            {"name": "fetch_url", "status": "ok", "summary": "markdown page body"},
        ]

    def test_error_classification(self):
        calls = [{"name": "search_web"}, {"name": "fetch_url"}]
        outputs = ["good results", "Error: quota exceeded"]
        obs = build_observations(calls, outputs)
        assert obs[0]["status"] == "ok"
        assert obs[1]["status"] == "error"
        assert "quota exceeded" in obs[1]["summary"]

    def test_length_mismatch_zips_short(self):
        calls = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        outputs = ["only one"]
        obs = build_observations(calls, outputs)
        assert len(obs) == 1
        assert obs[0]["name"] == "a"

    def test_empty_inputs(self):
        assert build_observations([], []) == []

    def test_object_shaped_tool_calls(self):
        class TC:
            name = "update_todo"

        obs = build_observations([TC()], ["ok"])
        assert obs[0]["name"] == "update_todo"
        assert obs[0]["status"] == "ok"

    def test_dict_tool_call_missing_name(self):
        obs = build_observations([{}], ["out"])
        assert obs[0]["name"] == "tool"

    def test_summary_truncated_to_160(self):
        obs = build_observations([{"name": "t"}], ["x" * 500])
        assert len(obs[0]["summary"]) == 160

    def test_never_raises_on_junk(self):
        # tool_output_failed(None) is True by contract: a missing output is
        # never progress, so build_observations must classify it as error.
        obs = build_observations([{"name": "t"}], [None])
        assert obs[0]["status"] == "error"
        assert obs[0]["summary"] == "None"


class TestOODATurnTelemetry:
    """summary() must reproduce the shipped agent_telemetry payload shape."""

    def _sample(self) -> OODATurnTelemetry:
        t = OODATurnTelemetry()
        t.record_observe(1, True, [{"name": "search_web", "status": "ok", "summary": "r"}])
        t.record_observe(2, False, [{"name": "fetch_url", "status": "error", "summary": "Error"}])
        t.record_orient(3, "synthesize", reasoning="done")
        return t

    def test_record_observe_shape(self):
        t = self._sample()
        assert t.phases[0] == {
            "phase": "observe",
            "iteration": 1,
            "progressed": True,
            "observations": [{"name": "search_web", "status": "ok", "summary": "r"}],
        }

    def test_record_orient_extra_fields(self):
        rec = self._sample().phases[2]
        assert rec["phase"] == "orient"
        assert rec["decision"] == "synthesize"
        assert rec["reasoning"] == "done"

    def test_summary_counts_tool_iterations(self):
        s = self._sample().summary("agent", 3, OODASoftCap(nominal_cap=10))
        assert s["tool_iterations"] == 2  # observe records only
        assert s["iterations"] == 3
        assert s["mode"] == "agent"

    def test_summary_cap_metrics(self):
        cap = OODASoftCap(nominal_cap=10)
        cap.note_iteration([None])  # stall
        s = self._sample().summary("agent", 3, cap)
        assert s["cap_extensions"] == 0
        assert s["stall_breaker"] is False

    def test_summary_truncates_phases_to_last_20(self):
        t = OODATurnTelemetry()
        for i in range(30):
            t.record_observe(i, True, [])
        s = t.summary("agent", 30, OODASoftCap(nominal_cap=50))
        assert len(s["phases"]) == 20
        assert s["phases"][-1]["iteration"] == 29

    def test_summary_serializable(self):
        import json

        s = self._sample().summary("chat", 3, OODASoftCap(nominal_cap=10))
        assert json.loads(json.dumps(s)) == s


class TestTaskManagerMiniOoda:
    """
    Structural contract for the Agent Mode per-step mini-OODA wiring.
    The full manager requires Azure + Supabase; these assertions pin the
    wiring that must not regress: imports, cap tuning, loop bound, and
    SSE payload shapes.
    """

    def _source(self) -> str:
        with open(_TASK_MANAGER_PATH, "r", encoding="utf-8") as f:
            return f.read()

    def test_imports_ooda_soft_cap(self):
        assert "from app.core.agent_ooda import OODASoftCap" in self._source()

    def test_mini_cap_tuning(self):
        # nominal 2, grace 1, hard ceiling 4, stall 2 — pinned contract.
        tree = ast.parse(self._source())
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "OODASoftCap":
                found.append({kw.arg: ast.literal_eval(kw.value) for kw in node.keywords})
        mini = [f for f in found if f.get("nominal_cap") == 2]
        assert mini, "mini-OODA OODASoftCap(nominal_cap=2) instantiation missing"
        assert mini[0] == {
            "nominal_cap": 2, "grace_iters": 1, "hard_ceiling": 4, "stall_limit": 3,
        }

    def test_retry_loop_uses_effective_attempts(self):
        src = self._source()
        assert "attempt < effective_attempts" in src
        assert "effective_attempts = 2" in src
        # Legacy fixed bound must be gone.
        assert "attempt < max_ai_retries" not in src

    def test_pivot_drives_cap_progress(self):
        src = self._source()
        assert "_pivot = new_tool != step.tool_name" in src
        assert "mini_cap.note_iteration(" in src
        assert "mini_cap.propose_extension(" in src

    def test_stall_breaker_forces_closure(self):
        src = self._source()
        assert "if mini_cap.forced_close:" in src
        assert "Mini-OODA stall breaker" in src

    def test_agent_step_ooda_payload_keys(self):
        src = self._source()
        assert '"type": "agent_step_ooda"' in src
        for key in (
            '"task_id"', '"step_index"', '"attempt"', '"decision"',
            '"progressed"', '"stall_breaker"', '"effective_attempts"',
        ):
            assert key in src, f"agent_step_ooda payload missing {key}"
        assert '"status": "cap_extended"' in src

    def test_step_complete_carries_ooda_block(self):
        src = self._source()
        complete_events = [
            ln for ln in src.splitlines()
            if "'agent_step_complete'" in ln
        ]
        assert len(complete_events) >= 2, "expected success + failed complete events"
        for ln in complete_events:
            assert "'ooda':" in ln, f"agent_step_complete missing ooda block: {ln.strip()[:80]}"
            assert "'attempts': attempt" in ln
            assert "'stall_breaker': mini_cap.forced_close" in ln

    def test_minimal_cap_behavior_matches_tuning(self):
        # The tuned cap's real behavior, exercised directly.
        cap = OODASoftCap(nominal_cap=2, grace_iters=1, hard_ceiling=4, stall_limit=3)
        assert cap.note_iteration(["search_web: ok"]) is True   # pivot → progress
        assert cap.propose_extension(2, 2) == 3                 # 2 → 3
        stall_cap = OODASoftCap(nominal_cap=2, grace_iters=1, hard_ceiling=4, stall_limit=3)
        assert stall_cap.note_iteration([None]) is False        # same-tool retry = stall
        assert stall_cap.note_iteration([None]) is False
        assert stall_cap.forced_close is False                  # transient retry survives
        assert stall_cap.note_iteration([None]) is False
        assert stall_cap.forced_close is True                   # 3rd non-pivot trips it


class TestChatLoopUsesExtractedPrimitives:
    """chat.py must delegate to the shared engine, not duplicate it."""

    _CHAT_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "api", "v1", "endpoints", "chat.py",
    )

    def _source(self) -> str:
        with open(self._CHAT_PATH, "r", encoding="utf-8") as f:
            return f.read()

    def test_imports_new_primitives(self):
        src = self._source()
        assert "OODATurnTelemetry," in src
        assert "build_observations," in src

    def test_no_inline_observation_distillation_left(self):
        # The extracted block must be replaced by the shared helper call.
        assert "build_observations(current_tool_calls, tool_outputs)" in self._source()
        assert '"summary": str(t_out)[:160]' not in self._source()

    def test_ooda_telemetry_record_present(self):
        src = self._source()
        assert "ooda_telemetry = OODATurnTelemetry()" in src
        assert "ooda_telemetry.record_observe(iteration, _progressed, _observations)" in src

    def test_no_phases_list_residual(self):
        assert "ooda_phases" not in self._source(), (
            "chat.py still references the removed phases list"
        )

    def test_telemetry_emit_uses_summary(self):
        assert "ooda_telemetry.summary(routing_mode, iteration, ooda_cap)" in self._source()
