# tests/test_agent_mode_phase1.py
"""
Unit tests for Agent Mode Phase 1 Foundation.
Tests data models, structured planning, HITL gates, sub-agent delegation,
context compression, and duration budgeting.
"""

import pytest
import asyncio
from app.core.agent_task_models import (
    AgentTask,
    PlanStep,
    TaskState,
    StepStatus,
    RiskLevel,
    SubAgentResult,
)
from app.core.hitl_gates import HITLGate
from app.core.sub_agent_pool import SubAgentPool
from app.core.circuit_breaker import create_turn_circuit_breaker, ActionBudgetExceeded
from app.services.hybrid_memory import AgentContextCompressor
from app.core.agent_planner import generate_structured_plan, refine_plan


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
    edits = {1: "New updated step 1 description"}
    refined = await refine_plan(plan, edits)
    assert refined[0].description == "New updated step 1 description"
    assert refined[1].description == "Old step 2"
