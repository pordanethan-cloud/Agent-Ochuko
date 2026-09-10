# tests/test_agent_resume.py
"""
Regression tests for the approve-then-stall bug:
POST /agent-tasks/{id}/approve used to only patch the DB row — nothing ever
re-ran execute_plan_stream, so approved tasks sat in "executing" forever.
Approve now resumes execution as an SSE stream.
"""
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.core.agent_task_models import AgentTask, PlanStep, TaskState, StepStatus
from app.core.agent_task_manager import AgentTaskManager
from app.api.v1.endpoints import agent_tasks as at


def _make_client():
    """MagicMock AzureOpenAI whose responses.stream yields one text delta."""
    mock_client = MagicMock()
    mock_stream_ctx = MagicMock()

    class MockEvent:
        type = "response.output_text.delta"
        delta = "Final synthesized answer."

    async def mock_event_gen():
        yield MockEvent()

    mock_stream = mock_event_gen()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_client.responses.stream.return_value = mock_stream_ctx
    return mock_client


def _make_config():
    return {
        "enabled": True,
        "auto_approve_level": "medium",
        "max_steps": 5,
        "max_duration_seconds": 300,
        "step_timeout_seconds": 30,
    }


def _make_task() -> AgentTask:
    task = AgentTask(
        conversation_id="conv-resume",
        user_id="user-resume",
        goal="Research then email the summary",
        max_duration_seconds=300,
    )
    task.plan = [
        PlanStep(index=1, description="Search for market data", tool_name="search_web"),
        # High-risk: pauses at medium auto-approve level
        PlanStep(index=2, description="Send client confirmation email", tool_name="gmail_send"),
        PlanStep(index=3, description="Draft the follow-up note", tool_name="memory_save"),
    ]
    return task


async def _collect(manager: AgentTaskManager):
    events = []
    async for sse in manager.execute_plan_stream(search_fn=_mock_search):
        raw = sse[6:].strip()
        if raw == "[DONE]":
            continue
        events.append(json.loads(raw))
    return events


async def _mock_search(query, **kwargs):
    return {
        "google_context": f"Search Query: {query}\nSearch Synthesis: data.\n\nSupporting Grounding Context:\ndata.",
        "sources": [{"title": "Reuters", "url": "https://reuters.com"}],
    }


@pytest.mark.asyncio
async def test_hitl_pause_then_resume_completes_task():
    """Run 1 pauses for approval; after approve-simulation, run 2 finishes without re-pausing."""
    task = _make_task()
    manager = AgentTaskManager(
        task=task, openai_client=_make_client(), config=_make_config(), supabase_client=None,
    )

    # Run 1: should pause at the high-risk gmail_send step
    events1 = await _collect(manager)
    types1 = [e.get("type") for e in events1]
    assert "agent_approval_required" in types1
    assert task.state == TaskState.PAUSED_FOR_HITL
    assert task.plan[0].status == StepStatus.COMPLETED
    assert task.plan[1].status == StepStatus.PENDING

    # Simulate the approve endpoint logic (HITL branch)
    task.plan[1].status = StepStatus.RUNNING
    task.state = TaskState.EXECUTING

    # Run 2: NEW manager re-instantiated from saved task (as the endpoint does)
    manager2 = AgentTaskManager(
        task=task, openai_client=_make_client(), config=_make_config(), supabase_client=None,
    )
    events2 = await _collect(manager2)
    types2 = [e.get("type") for e in events2]

    assert "agent_approval_required" not in types2, "approved step must not re-pause"
    assert "agent_step_start" in types2
    assert "agent_task_complete" in types2
    assert task.state == TaskState.COMPLETED
    assert task.plan[0].status == StepStatus.COMPLETED  # not re-executed
    assert task.plan[1].status in (StepStatus.COMPLETED, StepStatus.FAILED)
    assert task.plan[2].status in (StepStatus.COMPLETED, StepStatus.FAILED)


@pytest.mark.asyncio
async def test_skipped_step_not_reexecuted_on_resume():
    task = _make_task()
    task.plan[0].status = StepStatus.COMPLETED
    task.plan[1].status = StepStatus.SKIPPED
    task.plan[1].result_summary = "Skipped by user."
    task.state = TaskState.EXECUTING

    manager = AgentTaskManager(
        task=task, openai_client=_make_client(), config=_make_config(), supabase_client=None,
    )
    events = await _collect(manager)
    starts = [e for e in events if e.get("type") == "agent_step_start"]
    started_idx = [e.get("step_index") for e in starts]

    assert 2 not in started_idx, "skipped step must not re-execute on resume"
    assert 3 in started_idx
    assert task.state == TaskState.COMPLETED


# ── Endpoint-level: approve returns an SSE StreamingResponse ─────────────────


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, rows: dict):
        self._rows = rows

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def single(self):
        return self

    def update(self, vals):
        self._pending_update = vals
        return self

    def upsert(self, vals):
        self._pending_update = vals
        return self

    def execute(self):
        if hasattr(self, "_pending_update"):
            payload = self._pending_update
            if "id" in payload:
                # upsert semantics
                existing = self._rows.get("t1") or {}
                existing.update({k: v for k, v in payload.items() if k != "id"})
            elif isinstance(payload, dict):
                for row in self._rows.values():
                    row.update(payload)
            del self._pending_update
            return _FakeResponse(None)
        return _FakeResponse(self._rows.get("t1"))


class _FakeSupabase:
    def __init__(self, row: dict):
        self._table = _FakeTable({"t1": row})

    def table(self, name):
        return self._table


@pytest.mark.asyncio
async def test_approve_endpoint_returns_streaming_response(monkeypatch):
    task = _make_task()
    task.state = TaskState.PAUSED_FOR_HITL
    task.current_step = 2
    task.plan[0].status = StepStatus.COMPLETED
    task.plan[1].status = StepStatus.PENDING
    task.started_at = datetime.utcnow()

    row = task.model_dump(mode="json")
    row["id"] = task.id
    fake_supabase = _FakeSupabase(row)

    monkeypatch.setattr(at, "get_supabase_admin", lambda: fake_supabase)
    monkeypatch.setattr(at, "get_openai_client", lambda: _make_client())
    monkeypatch.setattr(at, "_perform_google_search", _mock_search)
    monkeypatch.setattr(at, "_perform_parallel_searches", AsyncMock())
    monkeypatch.setattr(at, "get_agent_mode_config", AsyncMock(return_value=_make_config()))

    resp = await at.approve_agent_task(
        task.id,
        at.ApproveStepRequest(action="approve", step_index=2),
        user={"sub": task.user_id},
    )

    from fastapi.responses import StreamingResponse
    assert isinstance(resp, StreamingResponse), "approve must return an SSE stream, not JSON"
    assert resp.media_type == "text/event-stream"

    # Consume the stream: the approved step runs, no re-pause, task completes.
    events = []
    async for chunk in resp.body_iterator:
        raw = str(chunk)[6:].strip()
        if raw == "[DONE]":
            continue
        if raw:
            events.append(json.loads(raw))

    types = [e.get("type") for e in events]
    assert "agent_approval_required" not in types
    assert "agent_task_complete" in types

    # The endpoint operates on its own re-hydrated task — assert on the
    # persisted row state the fake Supabase captured.
    persisted = fake_supabase._table._rows["t1"]
    assert persisted["state"] == "completed"
    assert persisted["plan"][1]["status"] in ("completed", "failed")
