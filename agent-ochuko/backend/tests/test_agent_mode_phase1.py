# tests/test_agent_mode_phase1.py
"""
Unit tests for Agent Mode Phase 1 Foundation.
Tests data models, structured planning, HITL gates, sub-agent delegation,
context compression, and duration budgeting.
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from app.core.agent_task_models import (
    AgentTask,
    PlanStep,
    TaskState,
    StepStatus,
    StepResult,
    RiskLevel,
    SubAgentResult,
)
from app.core.hitl_gates import HITLGate
from app.core.sub_agent_pool import SubAgentPool
from app.core.circuit_breaker import create_turn_circuit_breaker, ActionBudgetExceeded
from app.services.hybrid_memory import AgentContextCompressor
from app.core.agent_planner import generate_structured_plan, refine_plan, replan_remaining, check_premise_divergence
from app.core import agent_task_manager as agent_task_manager_module
from app.core.agent_task_manager import AgentTaskManager


def test_agent_task_models():
    task = AgentTask(
        conversation_id="11111111-1111-1111-1111-111111111111",
        user_id="22222222-2222-2222-2222-222222222222",
        goal="Compare cloud providers and generate comparison PDF",
    )
    assert task.state == TaskState.PLANNING
    assert task.current_step == 0
    assert task.max_duration_seconds == 300
    assert len(task.plan) == 0


def test_hitl_risk_classification():
    # Low risk
    search_step = PlanStep(
        index=1,
        description="Search for Azure pricing",
        tool_name="search_web",
    )
    assert HITLGate.classify_risk(search_step) == RiskLevel.LOW
    assert not HITLGate.requires_approval(search_step, auto_approve_level="low")

    # Medium risk
    calc_step = PlanStep(
        index=2,
        description="Compute ROI table numbers",
        tool_name="execute_code",
        tool_args_hint={"code": "res = 100 * 1.5\nprint(res)"},
    )
    assert HITLGate.classify_risk(calc_step) == RiskLevel.MEDIUM
    assert HITLGate.requires_approval(calc_step, auto_approve_level="low")
    assert not HITLGate.requires_approval(calc_step, auto_approve_level="medium")

    # High risk (file write)
    pdf_step = PlanStep(
        index=3,
        description="Generate executive comparison PDF report",
        tool_name="execute_code",
        tool_args_hint={"code": "with open('report.pdf', 'wb') as f: f.write(b'pdf')"},
    )
    assert HITLGate.classify_risk(pdf_step) == RiskLevel.HIGH
    assert HITLGate.requires_approval(pdf_step, auto_approve_level="medium")
    assert HITLGate.requires_approval(pdf_step, auto_approve_level="low")

    # Image gen (high risk)
    img_step = PlanStep(
        index=4,
        description="Generate diagram illustration",
        tool_name="generate_image",
    )
    assert HITLGate.classify_risk(img_step) == RiskLevel.HIGH


@pytest.mark.asyncio
async def test_sub_agent_compression_fallback():
    pool = SubAgentPool(openai_client=None)
    long_text = "Data point 1: Azure costs $50.\n" * 50
    compressed = await pool.compress_text(long_text, max_tokens=100)
    assert len(compressed) <= 100 * 4 + 50
    assert "truncated" in compressed


def test_agent_context_compressor():
    task = AgentTask(
        conversation_id="conv-1",
        user_id="user-1",
        goal="Build multi-cloud comparison chart",
        plan=[
            PlanStep(index=1, description="Search pricing", status=StepStatus.COMPLETED, result_summary="AWS $100, Azure $80"),
            PlanStep(index=2, description="Plot comparison", status=StepStatus.PENDING),
        ],
    )
    payload = AgentContextCompressor.build_step_payload(task, step_index=2)
    assert "OVERALL GOAL: Build multi-cloud comparison chart" in payload
    assert "[x] Step 1: Search pricing" in payload
    assert "[>] Step 2: Plot comparison" in payload
    assert "AWS $100, Azure $80" in payload


def test_circuit_breaker_duration():
    cb = create_turn_circuit_breaker(max_steps=5, max_duration_seconds=1)
    cb.record_step("Step 1")
    # Simulate time passing
    cb.start_time -= 2.0
    with pytest.raises(ActionBudgetExceeded):
        cb.record_step("Step 2")


@pytest.mark.asyncio
async def test_structured_planner_programmatic_fallback():
    plan = await generate_structured_plan(
        goal="Analyze recent Nigeria tax legislation",
        conversation_history=None,
        openai_client=None,
    )
    assert len(plan) == 2
    assert plan[0].tool_name == "search_web"
    assert plan[0].risk_level == RiskLevel.LOW
    assert plan[1].index == 2


@pytest.mark.asyncio
async def test_refine_plan():
    plan = [
        PlanStep(index=1, description="Old step 1"),
        PlanStep(index=2, description="Old step 2"),
    ]
    edits = {2: "Updated step 2 with specific data"}
    new_plan = await refine_plan(plan, edits)
    assert new_plan[1].description == "Updated step 2 with specific data"


@pytest.mark.asyncio
async def test_greeting_single_step_planning():
    """Verify greetings and simple queries return a 1-step direct response plan without search or code execution."""
    for greeting in ["hello", "Hi!", "good morning", "who are you?", "help"]:
        plan = await generate_structured_plan(
            goal=greeting,
            conversation_history=None,
            openai_client=None,
        )
        assert len(plan) == 1
        assert plan[0].tool_name is None
        assert plan[0].risk_level == RiskLevel.LOW


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8: Dynamic Plan Re-Orientation (long-horizon OODA)
# ─────────────────────────────────────────────────────────────────────────────

def _replan_client(payload: str) -> MagicMock:
    """Mock OpenAI client answering on the Responses API path with raw JSON text."""
    client = MagicMock()
    resp = MagicMock()
    resp.output_text = payload
    client.responses.create = AsyncMock(return_value=resp)
    return client


def _make_synthesis_stream_mock(client: MagicMock) -> None:
    """Mirrors the synthesis streaming contract (see test_cognitive_tool_adaptation)."""
    class MockDelta:
        type = "response.output_text.delta"
        delta = "Final synthesis text."

    async def mock_gen():
        yield MockDelta()

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_gen())
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
    client.responses.stream.return_value = mock_stream_ctx


@pytest.mark.asyncio
async def test_replan_remaining_reindexes_and_reapplies_hitl():
    """Valid JSON path: re-indexing continues original numbering; HITL re-applied."""
    plan = [
        PlanStep(index=1, description="Inspect repo payment flow", tool_name="sandbox_read", status=StepStatus.COMPLETED),
        PlanStep(index=2, description="Patch Stripe validation", tool_name="execute_code"),
        PlanStep(index=3, description="Run payment tests", tool_name="execute_code"),
    ]
    completed = [{"step_index": 1, "summary": "Repo uses Paystack, not Stripe", "artifacts": []}]
    client = _replan_client(json.dumps([
        {"description": "Inspect Paystack webhook signature handling", "tool_name": "sandbox_read", "risk_level": "low"},
        {"description": "Patch Paystack signature verification", "tool_name": "execute_code", "risk_level": "medium"},
        {"description": "Send test webhook", "tool_name": "gmail_send", "risk_level": "high"},
    ]))
    new_steps = await replan_remaining(
        original_plan=plan,
        completed_results=completed,
        remaining_steps=plan[1:],
        goal="Audit and fix payment webhook integration",
        failed_step=plan[1],
        auto_approve_level="medium",
        openai_client=client,
        nano_deployment="gpt-5.6-luna",
    )
    assert new_steps is not None
    assert [s.index for s in new_steps] == [2, 3, 4]
    assert all(s.status == StepStatus.PENDING for s in new_steps)
    assert new_steps[0].tool_name == "sandbox_read"
    # Token economy: summaries (never artifacts) and the failure context reach the prompt
    call_kwargs = client.responses.create.call_args.kwargs
    prompt_blob = json.dumps(call_kwargs.get("input") or call_kwargs.get("messages"))
    assert "Paystack, not Stripe" in prompt_blob
    assert "FAILED STEP #2" in prompt_blob
    # HITL re-applied: high-risk re-planned step requires approval, low-risk does not
    assert new_steps[2].requires_approval is True
    assert new_steps[0].requires_approval is False


@pytest.mark.asyncio
async def test_replan_remaining_failsafe_returns_none():
    """Invalid JSON, unknown tools, empty descriptions, no remaining steps, or no
    client all return None so the caller keeps the original remaining steps."""
    plan = [PlanStep(index=1, description="Do the thing", tool_name="search_web")]

    # Empty remaining steps / no client short-circuit
    ok_client = _replan_client(json.dumps([{"description": "Adapted step", "tool_name": "search_web"}]))
    assert await replan_remaining(plan, [], [], "goal", openai_client=ok_client) is None
    assert await replan_remaining(plan, [], plan, "goal", openai_client=None) is None

    # Happy path with the same client (re-indexed from 1, single step)
    ok = await replan_remaining(plan, [], plan, "goal", openai_client=ok_client)
    assert ok is not None and len(ok) == 1 and ok[0].index == 1

    # Malformed JSON
    bad_json = _replan_client("this is not json {")
    assert await replan_remaining(plan, [], plan, "goal", openai_client=bad_json) is None

    # Tool outside the planner roster
    bad_tool = _replan_client(json.dumps([{"description": "Hack it", "tool_name": "npm_publish"}]))
    assert await replan_remaining(plan, [], plan, "goal", openai_client=bad_tool) is None

    # Empty description
    empty_desc = _replan_client(json.dumps([{"description": "   ", "tool_name": None}]))
    assert await replan_remaining(plan, [], plan, "goal", openai_client=empty_desc) is None


@pytest.mark.asyncio
async def test_executor_loop_reorients_plan_after_exhausted_failure(monkeypatch):
    """A step that exhausts both AI retries triggers one re-orientation; the splice
    takes effect (spliced steps ARE visited — a `for` loop would skip them) and the
    budget caps further re-plans."""
    task = AgentTask(conversation_id="conv-replan-1", user_id="user-1", goal="Fix payment webhooks")
    task.plan = [
        PlanStep(index=1, description="Patch Stripe validation", tool_name="scrape_web"),
        PlanStep(index=2, description="Run Stripe tests", tool_name="execute_code"),
    ]
    task.state = TaskState.EXECUTING

    client = MagicMock()
    adapt_resp = MagicMock()
    adapt_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({"action": "proceed"})))]
    client.chat.completions.create = AsyncMock(return_value=adapt_resp)
    _make_synthesis_stream_mock(client)

    new_tail = [
        PlanStep(index=2, description="Inspect Paystack signature handling", tool_name="search_web"),
        PlanStep(index=3, description="Verify webhook fix", tool_name="sandbox_ls"),
    ]
    replan_mock = AsyncMock(return_value=new_tail)
    monkeypatch.setattr(agent_task_manager_module, "replan_remaining", replan_mock)

    manager = AgentTaskManager(
        task=task,
        openai_client=client,
        deployment="gpt-5.6-terra",
        nano_deployment="gpt-5.6-luna",
        config={"max_replans_per_task": 1},
    )

    async def fail_step(step, search_fn=None, deep_research_fn=None):
        return StepResult(success=False, summary="", error="403 blocked", token_spend=0)

    monkeypatch.setattr(manager, "_execute_single_step", fail_step)

    events = []
    async for raw_sse in manager.execute_plan_stream():
        if raw_sse.startswith("data: "):
            raw = raw_sse[6:].strip()
            if raw != "[DONE]":
                events.append(json.loads(raw))

    types = [e.get("type") for e in events]
    assert "agent_plan_reoriented" in types
    reoriented = next(e for e in events if e["type"] == "agent_plan_reoriented")
    assert reoriented["replan_count"] == 1
    assert [s["index"] for s in reoriented["plan"]] == [1, 2, 3]

    # Iteration safety: spliced steps were actually visited by the while loop
    started = {e["step_index"] for e in events if e["type"] == "agent_step_start"}
    assert started == {1, 2, 3}

    # Budget: exactly one re-plan despite three exhausted failures
    assert replan_mock.await_count == 1
    assert task.replan_count == 1


@pytest.mark.asyncio
async def test_replan_budget_zero_disables_reorientation(monkeypatch):
    """max_replans_per_task=0 fully disables dynamic re-orientation."""
    task = AgentTask(conversation_id="conv-replan-2", user_id="user-2", goal="Fix webhooks")
    task.plan = [
        PlanStep(index=1, description="Patch validation", tool_name="scrape_web"),
        PlanStep(index=2, description="Run tests", tool_name="execute_code"),
    ]
    task.state = TaskState.EXECUTING

    client = MagicMock()
    adapt_resp = MagicMock()
    adapt_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({"action": "proceed"})))]
    client.chat.completions.create = AsyncMock(return_value=adapt_resp)
    _make_synthesis_stream_mock(client)

    replan_mock = AsyncMock(return_value=[PlanStep(index=2, description="Alt path", tool_name="search_web")])
    monkeypatch.setattr(agent_task_manager_module, "replan_remaining", replan_mock)

    manager = AgentTaskManager(
        task=task,
        openai_client=client,
        deployment="gpt-5.6-terra",
        nano_deployment="gpt-5.6-luna",
        config={"max_replans_per_task": 0},
    )

    async def fail_step(step, search_fn=None, deep_research_fn=None):
        return StepResult(success=False, summary="", error="blocked", token_spend=0)

    monkeypatch.setattr(manager, "_execute_single_step", fail_step)

    events = []
    async for raw_sse in manager.execute_plan_stream():
        if raw_sse.startswith("data: "):
            raw = raw_sse[6:].strip()
            if raw != "[DONE]":
                events.append(json.loads(raw))

    assert replan_mock.await_count == 0
    assert "agent_plan_reoriented" not in [e.get("type") for e in events]
    assert task.replan_count == 0


@pytest.mark.asyncio
async def test_replan_count_persisted_by_save_state():
    """replan_count survives save_state() so the budget holds across pause/resume."""
    task = AgentTask(conversation_id="conv-replan-3", user_id="user-3", goal="G")
    task.replan_count = 2
    fake_sb = MagicMock()
    manager = AgentTaskManager(task=task, supabase_client=fake_sb)
    await manager.save_state()
    upsert_payload = fake_sb.table.return_value.upsert.call_args.args[0]
    assert upsert_payload["replan_count"] == 2


@pytest.mark.asyncio
async def test_check_premise_divergence_true_returns_reason():
    """check_premise_divergence returns the reason string when the nano call
    reports diverged=true with a non-empty reason."""
    completed = PlanStep(
        index=1, description="Inspect repo payment flow", tool_name="search_web",
        status=StepStatus.COMPLETED, result_summary="Repo uses bun, not npm",
    )
    next_step = PlanStep(index=2, description="Run npm build", tool_name="terminal")

    class _Part:
        text = '{"diverged": true, "reason": "Repo uses bun instead of npm"}'

    class _Item:
        content = [_Part()]

    resp = MagicMock()
    resp.output = [_Item()]
    client = MagicMock()
    client.responses.create = AsyncMock(return_value=resp)

    reason = await check_premise_divergence(
        completed_step=completed,
        result_summary="Repo uses bun, not npm",
        next_steps=[next_step],
        openai_client=client,
        nano_deployment="gpt-5.6-luna",
    )
    assert reason == "Repo uses bun instead of npm"
    assert client.responses.create.await_count == 1


@pytest.mark.asyncio
async def test_check_premise_divergence_false_and_errors_return_none():
    """check_premise_divergence returns None on diverged=false, malformed JSON,
    empty reason, timeout, and missing client - never raises."""
    completed = PlanStep(
        index=1, description="Inspect repo", tool_name="search_web",
        status=StepStatus.COMPLETED, result_summary="all good",
    )
    next_step = PlanStep(index=2, description="Build", tool_name="terminal")

    # Case 1: diverged=false
    class _PartFalse:
        text = '{"diverged": false}'

    class _ItemFalse:
        content = [_PartFalse()]

    resp_false = MagicMock()
    resp_false.output = [_ItemFalse()]
    client_false = MagicMock()
    client_false.responses.create = AsyncMock(return_value=resp_false)
    assert await check_premise_divergence(completed, "all good", [next_step], client_false) is None

    # Case 2: diverged=true but empty reason -> None
    class _PartEmpty:
        text = '{"diverged": true, "reason": "   "}'

    class _ItemEmpty:
        content = [_PartEmpty()]

    resp_empty = MagicMock()
    resp_empty.output = [_ItemEmpty()]
    client_empty = MagicMock()
    client_empty.responses.create = AsyncMock(return_value=resp_empty)
    assert await check_premise_divergence(completed, "all good", [next_step], client_empty) is None

    # Case 3: malformed JSON -> None
    class _PartBad:
        text = "not json at all"

    class _ItemBad:
        content = [_PartBad()]

    resp_bad = MagicMock()
    resp_bad.output = [_ItemBad()]
    client_bad = MagicMock()
    client_bad.responses.create = AsyncMock(return_value=resp_bad)
    assert await check_premise_divergence(completed, "all good", [next_step], client_bad) is None

    # Case 4: timeout (asyncio.TimeoutError) -> None
    client_timeout = MagicMock()
    client_timeout.responses.create = AsyncMock(side_effect=asyncio.TimeoutError())
    assert await check_premise_divergence(completed, "all good", [next_step], client_timeout) is None

    # Case 5: no client -> None
    assert await check_premise_divergence(completed, "all good", [next_step], None) is None

    # Case 6: no next_steps -> None
    assert await check_premise_divergence(completed, "all good", [], client_false) is None


@pytest.mark.asyncio
async def test_replan_remaining_with_discovery_context():
    """Phase 8.1: when triggered by a premise shift (discovery_context) rather than
    a hard failure, the obstacle block shows OBSERVATION / PREMISE SHIFT and the
    failed-step block is absent."""
    plan = [
        PlanStep(index=1, description="Inspect repo stack", tool_name="search_web", status=StepStatus.COMPLETED),
        PlanStep(index=2, description="Run npm build", tool_name="terminal"),
        PlanStep(index=3, description="Deploy", tool_name="terminal"),
    ]
    completed = [{"step_index": 1, "summary": "Repo uses bun, not npm", "artifacts": [
        {"filename": "bun.lockb"}, {"filename": "package.json"},
    ]}]
    discovery = "Repo uses bun instead of npm (bun.lockb present, no package-lock.json)"
    client = _replan_client(json.dumps([
        {"description": "Run bun install", "tool_name": "terminal", "risk_level": "low"},
        {"description": "Run bun build", "tool_name": "terminal", "risk_level": "low"},
    ]))
    new_steps = await replan_remaining(
        original_plan=plan,
        completed_results=completed,
        remaining_steps=plan[1:],
        goal="Build and deploy the app",
        discovery_context=discovery,
        auto_approve_level="medium",
        openai_client=client,
        nano_deployment="gpt-5.6-luna",
    )
    assert new_steps is not None
    assert [s.index for s in new_steps] == [2, 3]
    call_kwargs = client.responses.create.call_args.kwargs
    prompt_blob = json.dumps(call_kwargs.get("input") or call_kwargs.get("messages"))
    assert "OBSERVATION / PREMISE SHIFT" in prompt_blob
    assert "bun instead of npm" in prompt_blob
    assert "FAILED STEP" not in prompt_blob
    # Dynamic horizon: 2 remaining -> max(2, 2+1)=3, min(6,3) = 3
    assert "3 steps max" in prompt_blob


@pytest.mark.asyncio
async def test_dynamic_step_horizon_bounds():
    """The dynamic step horizon floors at 2 (near finish) and caps at 6 (early pivot)."""
    base_completed = [{"step_index": 1, "summary": "done", "artifacts": []}]

    # Near finish: 1 remaining step -> horizon = max(2, 1+1) = 2
    plan_near = [
        PlanStep(index=1, description="done", status=StepStatus.COMPLETED),
        PlanStep(index=2, description="Final step", tool_name="search_web"),
    ]
    client_near = _replan_client(json.dumps([
        {"description": "Adapted final step", "tool_name": "search_web", "risk_level": "low"},
        {"description": "Cleanup", "tool_name": "search_web", "risk_level": "low"},
    ]))
    await replan_remaining(
        original_plan=plan_near, completed_results=base_completed,
        remaining_steps=plan_near[1:], goal="g", openai_client=client_near,
    )
    prompt_near = json.dumps(client_near.responses.create.call_args.kwargs.get("input"))
    assert "2 steps max" in prompt_near

    # Early pivot: 5 remaining steps -> horizon = min(6, 5+1) = 6
    plan_far = [PlanStep(index=1, description="done", status=StepStatus.COMPLETED)]
    for idx in range(2, 7):
        plan_far.append(PlanStep(index=idx, description=f"Step {idx}", tool_name="search_web"))
    client_far = _replan_client(json.dumps([
        {"description": f"Adapted step {i}", "tool_name": "search_web", "risk_level": "low"}
        for i in range(6)
    ]))
    await replan_remaining(
        original_plan=plan_far, completed_results=base_completed,
        remaining_steps=plan_far[1:], goal="g", openai_client=client_far,
    )
    prompt_far = json.dumps(client_far.responses.create.call_args.kwargs.get("input"))
    assert "6 steps max" in prompt_far


@pytest.mark.asyncio
async def test_premise_divergence_check_triggers_reorientation(monkeypatch):
    """A successful investigative step whose results contradict the next step premise
    triggers a discovery re-orientation BEFORE the doomed step runs."""
    task = AgentTask(conversation_id="conv-diverge-1", user_id="user-1", goal="Fix deployment")
    task.plan = [
        PlanStep(index=1, description="Inspect the deployment stack", tool_name="search_web"),
        PlanStep(index=2, description="Run npm build and deploy", tool_name="terminal"),
    ]
    task.state = TaskState.EXECUTING

    client = MagicMock()
    adapt_resp = MagicMock()
    adapt_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({"action": "proceed"})))]
    client.chat.completions.create = AsyncMock(return_value=adapt_resp)
    _make_synthesis_stream_mock(client)

    new_tail = [
        PlanStep(index=2, description="Run bun build and deploy via bun", tool_name="terminal"),
    ]
    replan_mock = AsyncMock(return_value=new_tail)
    monkeypatch.setattr(agent_task_manager_module, "replan_remaining", replan_mock)

    # Force the nano divergence probe to report a premise shift.
    monkeypatch.setattr(
        agent_task_manager_module, "check_premise_divergence",
        AsyncMock(return_value="Repo uses bun instead of npm"),
    )

    manager = AgentTaskManager(
        task=task, openai_client=client, deployment="gpt-5.6-terra",
        nano_deployment="gpt-5.6-luna", config={"max_replans_per_task": 2},
    )

    async def succeed_step(step, search_fn=None, deep_research_fn=None):
        return StepResult(
            success=True,
            summary="Inspected repo: uses bun instead of npm",
            artifacts=[], token_spend=0,
        )
    monkeypatch.setattr(manager, "_execute_single_step", succeed_step)

    events = []
    async for raw_sse in manager.execute_plan_stream():
        if raw_sse.startswith("data: "):
            raw = raw_sse[6:].strip()
            if raw != "[DONE]":
                events.append(json.loads(raw))

    types = [e.get("type") for e in events]
    assert "agent_plan_reoriented" in types
    reoriented = next(e for e in events if e["type"] == "agent_plan_reoriented")
    assert reoriented["replan_count"] == 1
    assert reoriented["trigger"] == "discovery"
    assert reoriented["reason"] == "Repo uses bun instead of npm"
    assert any("bun" in s["description"] for s in reoriented["plan"])
