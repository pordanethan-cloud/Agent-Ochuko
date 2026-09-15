"""
Workstation Notice contract tests.

The "Workstation Notice:" marker is a cross-module contract:
  1. WorkstationMCP returns it when a host path cannot be reached AND the
     local Companion Bridge (127.0.0.1:3920) is down — with actionable
     guidance (bridge daemon, toggle, backend co-location).
  2. AgentTaskManager._execute_single_step classifies it as a step FAILURE
     (never a success) and records a scratchpad decision note, so the
     mini-OODA stall detector and Phase 8 replan logic can react.
     (Regression guard: the notice used to return success=True — soft
     fake-success, Think-vs-Agent root cause #5 in doc 09.)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.connectors.workstation_mcp import WorkstationMCP
from app.core.agent_task_manager import AgentTaskManager
from app.core.agent_task_models import AgentTask, PlanStep


@pytest.mark.asyncio
async def test_mcp_notice_is_actionable_not_generic():
    """Host path that cannot exist + bridge down -> actionable notice, both sites."""
    with tempfile_dir() as temp_dir:
        mcp = WorkstationMCP(workspace_root=temp_dir)

        read_res = await mcp.read_file("Q:\\Missing\\books\\list.txt")
        assert read_res.startswith("Workstation Notice:")
        assert "Companion Bridge" in read_res
        assert "workstation_bridge.py" in read_res
        # The old misleading copy must be gone.
        assert "please ensure Workstation Access is toggled ON in Settings." not in read_res

        list_res = await mcp.list_directory("Q:\\Missing\\books")
        assert list_res.startswith("Workstation Notice:")
        assert "Companion Bridge" in list_res


def _patched_registry(notice: str):
    """
    Patches the MCPRegistry CLASS (not just execute_mcp_tool) so manager tests
    never instantiate the process-wide singleton: MCPRegistry.__new__ caches
    one instance and __init__ ignores later workspace_root args, so a real
    instantiation here would poison workspace_root for every other test.
    """
    mock_cls = MagicMock()
    mock_cls.return_value.execute_mcp_tool = AsyncMock(return_value=notice)
    return patch("app.connectors.mcp_registry.MCPRegistry", mock_cls)


@pytest.mark.asyncio
async def test_mcp_dispatch_marks_workstation_notice_as_failure():
    """Generic mcp_* dispatch: notice -> success=False + scratchpad decision note."""
    task = AgentTask(goal="Look up my books folder", conversation_id="conv-ws-1", user_id="user-ws")
    manager = AgentTaskManager(
        task=task,
        openai_client=MagicMock(),
        deployment="test",
        nano_deployment="test",
        config={"workstation_access_enabled": True},
    )
    step = PlanStep(
        index=1,
        description="List the books folder in Documents",
        tool_name="mcp_workstation_list",
        tool_args_hint={"path": "documents/books"},
    )
    notice = "Workstation Notice: 'documents/books' is on your physical computer, but the local Companion Bridge is unreachable."
    with _patched_registry(notice):
        res = await manager._execute_single_step(step)

    assert res.success is False
    assert res.error is not None
    assert "Companion Bridge" in res.summary

    entries = task.scratchpad.get("entries", [])
    assert any(
        isinstance(e, dict)
        and e.get("kind") == "decision"
        and "Companion Bridge" in str(e.get("content", ""))
        and e.get("step_index") == 1
        for e in entries
    )


@pytest.mark.asyncio
async def test_bare_alias_workstation_read_also_classified_as_failure():
    """Bare alias 'workstation_read' routes through the SAME generic
    mcp_*/workstation_* dispatch branch (startswith checks at the top of the
    chain) — the notice classification must hold there too."""
    task = AgentTask(goal="Read my books list", conversation_id="conv-ws-2", user_id="user-ws")
    manager = AgentTaskManager(
        task=task,
        openai_client=MagicMock(),
        deployment="test",
        nano_deployment="test",
        config={"workstation_access_enabled": True},
    )
    step = PlanStep(
        index=1,
        description="Read C:\\Users\\books\\list.txt",
        tool_name="workstation_read",
        tool_args_hint={"path": "C:\\Users\\books\\list.txt"},
    )
    notice = "Workstation Notice: 'C:\\Users\\books\\list.txt' is on your physical computer, but the local Companion Bridge is unreachable."
    with _patched_registry(notice):
        res = await manager._execute_single_step(step)

    assert res.success is False
    assert "Companion Bridge" in res.summary
    entries = task.scratchpad.get("entries", [])
    assert any(
        isinstance(e, dict) and e.get("kind") == "decision" for e in entries
    )


@pytest.mark.asyncio
async def test_notice_toggle_off_changes_blocker_copy():
    """When Workstation Access is OFF the blocker copy says so."""
    task = AgentTask(goal="Look up my books folder", conversation_id="conv-ws-3", user_id="user-ws")
    manager = AgentTaskManager(
        task=task,
        openai_client=MagicMock(),
        deployment="test",
        nano_deployment="test",
        config={},  # toggle OFF
    )
    step = PlanStep(
        index=2,
        description="List the books folder in Documents",
        tool_name="mcp_workstation_list",
        tool_args_hint={"path": "documents"},
    )
    notice = "Workstation Notice: 'documents' is on your physical computer, but the local Companion Bridge is unreachable."
    with _patched_registry(notice):
        res = await manager._execute_single_step(step)

    assert res.success is False
    assert "toggle is OFF" in res.summary


def tempfile_dir():
    import tempfile

    return tempfile.TemporaryDirectory()

