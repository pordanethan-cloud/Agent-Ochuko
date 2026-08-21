# tests/test_agent_execution_live.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from app.core.agent_task_models import AgentTask, TaskState, StepStatus
from app.core.agent_task_manager import AgentTaskManager


@pytest.mark.asyncio
async def test_agent_task_full_execution_stream():
    """Verify AgentTaskManager executes all steps and streams both stepper events and synthesis text."""
    task = AgentTask(
        conversation_id="conv-123",
        user_id="user-456",
        goal="Research market valuations and synthesize comparison",
        max_duration_seconds=300,
    )

    mock_client = MagicMock()
    mock_stream_ctx = MagicMock()

    class MockEvent:
        type = "response.output_text.delta"
        delta = "### Market Valuation Analysis\n\nNvidia and Apple combined market cap is $9.83T."

    async def mock_event_gen():
        yield MockEvent()

    mock_stream = mock_event_gen()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_client.responses.stream.return_value = mock_stream_ctx

    async def mock_search_fn(query, **kwargs):
        return {
            "google_context": (
                f"Search Query: {query}\n"
                "Search Synthesis: Nvidia market cap is $5.29T, Apple is $4.54T.\n\n"
                "Supporting Grounding Context:\nNvidia at $5.29T."
            ),
            "sources": [{"title": "Market Data", "url": "https://example.com"}],
        }

    config = {
        "enabled": True,
        "auto_approve_level": "medium",
        "max_steps": 5,
        "max_duration_seconds": 300,
        "step_timeout_seconds": 30,
    }

    manager = AgentTaskManager(
        task=task,
        openai_client=mock_client,
        deployment="gpt-5.4",
        nano_deployment="gpt-5.4-nano",
        config=config,
        supabase_client=None,
    )

    plan = await manager.init_plan()
    assert len(plan) >= 2

    events = []
    async for sse_event in manager.execute_plan_stream(search_fn=mock_search_fn):
        assert sse_event.startswith("data: ")
        payload = json.loads(sse_event[6:].strip())
        events.append(payload)

    event_types = [e.get("type") for e in events]

    assert "agent_plan" in event_types
    assert "agent_step_start" in event_types
    assert "agent_step_complete" in event_types
    assert "content_block_delta" in event_types
    assert "agent_task_complete" in event_types

    assert task.state == TaskState.COMPLETED
    for step in task.plan:
        assert step.status == StepStatus.COMPLETED
