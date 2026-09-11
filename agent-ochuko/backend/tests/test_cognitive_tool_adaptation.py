# tests/test_cognitive_tool_adaptation.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from app.core.agent_task_models import AgentTask, TaskState, StepStatus, PlanStep, RiskLevel
from app.core.agent_task_manager import AgentTaskManager


@pytest.mark.asyncio
async def test_ai_resolve_feedback_and_adapt_direct():
    """Verify that _ai_resolve_feedback_and_adapt parses AI model decisions correctly."""
    task = AgentTask(
        conversation_id="conv-adapt-1",
        user_id="user-1",
        goal="Extract data from protected site",
    )
    step = PlanStep(
        index=1,
        description="Scrape target site https://example.com/protected",
        tool_name="scrape_web",
        risk_level=RiskLevel.LOW,
    )

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps({
                    "action": "retry_tool",
                    "tool_name": "search_web",
                    "description": "Search web for public mirrors or documentation of target site",
                    "reasoning": "Scraper was blocked by 403 Forbidden; searching web for public documentation.",
                })
            )
        )
    ]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    manager = AgentTaskManager(
        task=task,
        openai_client=mock_client,
        deployment="gpt-5.4",
        nano_deployment="gpt-5.4-nano",
    )

    decision = await manager._ai_resolve_feedback_and_adapt(
        step=step,
        error_feedback="403 Forbidden: Cloudflare anti-bot challenge encountered",
        attempt_num=1,
    )

    assert decision is not None
    assert decision["action"] == "retry_tool"
    assert decision["tool_name"] == "search_web"
    assert "403 Forbidden" in decision["reasoning"] or "Scraper" in decision["reasoning"]


@pytest.mark.asyncio
async def test_ai_cognitive_loop_emits_adaptation_event():
    """Verify that execute_plan_stream dynamically adapts a failing tool and emits agent_step_adapted."""
    task = AgentTask(
        conversation_id="conv-adapt-2",
        user_id="user-2",
        goal="Inspect financial statements",
    )
    task.plan = [
        PlanStep(
            index=1,
            description="Fetch filings from https://example.com/sec-filing",
            tool_name="scrape_web",
            risk_level=RiskLevel.LOW,
        )
    ]
    task.state = TaskState.EXECUTING

    mock_client = MagicMock()
    # 1. First completion call: AI feedback adaptation
    adapt_resp = MagicMock()
    adapt_resp.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps({
                    "action": "retry_tool",
                    "tool_name": "search_web",
                    "description": "Search web for 2026 financial statements SEC",
                    "reasoning": "Scraper failed, pivoting to search for public filings",
                })
            )
        )
    ]
    mock_client.chat.completions.create = AsyncMock(return_value=adapt_resp)

    # 2. Synthesis streaming
    mock_stream_ctx = MagicMock()
    class MockDelta:
        type = "response.output_text.delta"
        delta = "Final financial analysis completed."

    async def mock_gen():
        yield MockDelta()

    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_gen())
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_client.responses.stream.return_value = mock_stream_ctx

    async def mock_search_fn(query, **kwargs):
        return {
            "google_context": f"Found financial statements for query: {query}",
            "sources": [{"title": "Filings", "url": "https://sec.gov"}],
        }

    manager = AgentTaskManager(
        task=task,
        openai_client=mock_client,
        deployment="gpt-5.4",
        nano_deployment="gpt-5.4-nano",
    )

    events = []
    async for raw_sse in manager.execute_plan_stream(search_fn=mock_search_fn):
        if raw_sse.startswith("data: "):
            raw = raw_sse[6:].strip()
            if raw != "[DONE]":
                events.append(json.loads(raw))

    event_types = [e.get("type") for e in events]
    assert "agent_step_start" in event_types
    assert "agent_step_adapted" in event_types
    assert "agent_step_complete" in event_types
    assert "agent_task_complete" in event_types

    adapted_ev = next(e for e in events if e.get("type") == "agent_step_adapted")
    assert adapted_ev["previous_tool"] == "scrape_web"
    assert adapted_ev["tool_name"] == "search_web"
    assert "Scraper failed" in adapted_ev["reasoning"]

    assert task.state == TaskState.COMPLETED
    assert task.plan[0].status == StepStatus.COMPLETED
    assert task.plan[0].tool_name == "search_web"
