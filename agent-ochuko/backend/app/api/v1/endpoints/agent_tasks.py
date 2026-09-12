# app/api/v1/endpoints/agent_tasks.py
"""
Agent Tasks REST API.
Exposes endpoints for creating, inspecting, approving, editing, and managing
autonomous Agent Mode tasks.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.jwt_validator import verify_jwt
from app.core.agent_task_models import AgentTask, TaskState, PlanStep, StepStatus
from app.core.agent_task_manager import AgentTaskManager
from app.core.agent_config import get_agent_mode_config
from app.core.agent_planner import refine_plan
from app.api.v1.endpoints.chat import (
    get_openai_client,
    get_supabase_admin,
    _perform_google_search,
    _perform_parallel_searches,
)

logger = logging.getLogger("app.api.v1.endpoints.agent_tasks")

router = APIRouter()


class CreateTaskRequest(BaseModel):
    conversation_id: str
    goal: str
    history: Optional[List[Dict[str, Any]]] = None


class ApproveStepRequest(BaseModel):
    action: str = Field("approve", description="'approve' | 'skip' | 'cancel' | 'respond'")
    step_index: Optional[int] = None
    user_response: Optional[str] = None



class EditPlanRequest(BaseModel):
    edits: Dict[int, str] = Field(..., description="Map of step_index to new description text")


@router.post("/", status_code=201)
async def create_agent_task(
    payload: CreateTaskRequest,
    user: Dict = Depends(verify_jwt),
):
    """
    Creates a new Agent Mode task, runs structured planning,
    and returns the plan in AWAITING_APPROVAL state.
    """
    user_id = user["sub"]
    config = await get_agent_mode_config()
    if not config.get("enabled", True):
        raise HTTPException(status_code=403, detail="Agent Mode is currently disabled.")

    supabase = get_supabase_admin()
    task = AgentTask(
        conversation_id=payload.conversation_id,
        user_id=user_id,
        goal=payload.goal,
        max_duration_seconds=config.get("max_duration_seconds", 300),
    )

    client = get_openai_client()
    manager = AgentTaskManager(
        task=task,
        openai_client=client,
        config=config,
        supabase_client=supabase,
    )

    plan = await manager.init_plan(history=payload.history)

    return {
        "task_id": task.id,
        "conversation_id": task.conversation_id,
        "goal": task.goal,
        "state": task.state.value,
        "plan": [s.model_dump() for s in plan],
        "max_duration_seconds": task.max_duration_seconds,
    }


@router.get("/{task_id}")
async def get_agent_task(
    task_id: str,
    user: Dict = Depends(verify_jwt),
):
    """Retrieves full task state, plan, step results, and artifacts."""
    user_id = user["sub"]
    supabase = get_supabase_admin()

    result = await asyncio.to_thread(
        lambda: supabase.table("agent_tasks")
        .select("*")
        .eq("id", task_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Agent task not found.")

    return result.data


@router.post("/{task_id}/approve")
async def approve_agent_task(
    task_id: str,
    payload: ApproveStepRequest,
    user: Dict = Depends(verify_jwt),
):
    """
    Handles user approval actions:
    - 'approve': Approves plan to start executing, or approves a paused HITL step
    - 'skip': Skips a paused high-risk step
    - 'cancel': Cancels task execution

    approve/skip return an SSE stream: execution is RESUMED in-process by
    re-running execute_plan_stream (completed/skipped steps are skipped, the
    approved step runs, later risky steps still pause). This closes the old
    stall where approve only patched the DB and nothing continued.
    """
    user_id = user["sub"]
    supabase = get_supabase_admin()

    result = await asyncio.to_thread(
        lambda: supabase.table("agent_tasks")
        .select("*")
        .eq("id", task_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Agent task not found.")

    task_data = result.data
    task = AgentTask(**task_data)

    action = (payload.action or "approve").lower()

    if action == "cancel":
        task.state = TaskState.CANCELLED
        task.completed_at = datetime.utcnow()
        await asyncio.to_thread(
            lambda: supabase.table("agent_tasks")
            .update({
                "state": task.state.value,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "updated_at": datetime.utcnow().isoformat(),
            })
            .eq("id", task_id)
            .execute()
        )
        return {
            "task_id": task.id,
            "state": task.state.value,
            "action": action,
            "plan": [s.model_dump() for s in task.plan],
        }

    if task.state not in (TaskState.AWAITING_APPROVAL, TaskState.PAUSED_FOR_HITL, TaskState.EXECUTING):
        raise HTTPException(
            status_code=400,
            detail=f"Task is not awaiting approval (state={task.state.value}).",
        )

    if action == "skip" and task.state == TaskState.PAUSED_FOR_HITL:
        # Mark current step skipped
        step_idx = payload.step_index or task.current_step
        for s in task.plan:
            if s.index == step_idx:
                s.status = StepStatus.SKIPPED
                s.result_summary = "Skipped by user."
        task.state = TaskState.EXECUTING
    elif action in ("approve", "respond"):
        if task.state == TaskState.AWAITING_APPROVAL:
            task.state = TaskState.EXECUTING
            task.started_at = task.started_at or datetime.utcnow()
            # Resume-critical: mark the first pending step RUNNING so the HITL
            # gate does not instantly re-pause on the plan the user just approved.
            for s in task.plan:
                if s.status == StepStatus.PENDING:
                    s.status = StepStatus.RUNNING
                    break
        elif task.state == TaskState.PAUSED_FOR_HITL:
            step_idx = payload.step_index or task.current_step
            for s in task.plan:
                if s.index == step_idx:
                    if payload.user_response:
                        s.status = StepStatus.COMPLETED
                        s.result_summary = f"User responded: {payload.user_response}"
                        task.step_results.append({
                            "step_index": s.index,
                            "description": s.description,
                            "summary": f"User responded: {payload.user_response}",
                            "artifacts": [],
                            "duration_ms": 0,
                        })
                    else:
                        s.status = StepStatus.RUNNING
            task.state = TaskState.EXECUTING
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action '{action}'.")

    # Save update
    await asyncio.to_thread(
        lambda: supabase.table("agent_tasks")
        .update({
            "state": task.state.value,
            "plan": [s.model_dump() for s in task.plan],
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "updated_at": datetime.utcnow().isoformat(),
        })
        .eq("id", task_id)
        .execute()
    )

    # Resume execution and stream the remainder of the plan back to the client.
    config = await get_agent_mode_config()
    manager = AgentTaskManager(
        task=task,
        openai_client=get_openai_client(),
        config=config,
        supabase_client=supabase,
    )
    return StreamingResponse(
        manager.execute_plan_stream(
            search_fn=_perform_google_search,
            deep_research_fn=_perform_parallel_searches,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{task_id}/edit-plan")
async def edit_agent_plan(
    task_id: str,
    payload: EditPlanRequest,
    user: Dict = Depends(verify_jwt),
):
    """Applies user edits to pending plan steps before execution."""
    user_id = user["sub"]
    supabase = get_supabase_admin()

    result = await asyncio.to_thread(
        lambda: supabase.table("agent_tasks")
        .select("*")
        .eq("id", task_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Agent task not found.")

    task = AgentTask(**result.data)
    if task.state not in (TaskState.AWAITING_APPROVAL, TaskState.PLANNING):
        raise HTTPException(status_code=400, detail="Plan can only be edited before execution starts.")

    updated_plan = await refine_plan(task.plan, payload.edits)
    task.plan = updated_plan

    await asyncio.to_thread(
        lambda: supabase.table("agent_tasks")
        .update({
            "plan": [s.model_dump() for s in task.plan],
            "updated_at": datetime.utcnow().isoformat(),
        })
        .eq("id", task_id)
        .execute()
    )

    return {
        "task_id": task.id,
        "plan": [s.model_dump() for s in task.plan],
    }


@router.get("/{task_id}/artifacts")
async def get_task_artifacts(
    task_id: str,
    user: Dict = Depends(verify_jwt),
):
    """Lists deliverables produced by this agent task."""
    user_id = user["sub"]
    supabase = get_supabase_admin()

    result = await asyncio.to_thread(
        lambda: supabase.table("agent_tasks")
        .select("artifacts, goal, state, completed_at")
        .eq("id", task_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Agent task not found.")

    return {
        "task_id": task_id,
        "artifacts": result.data.get("artifacts", []),
        "state": result.data.get("state"),
        "completed_at": result.data.get("completed_at"),
    }


@router.get("/")
async def list_agent_tasks(
    limit: int = Query(20, ge=1, le=100),
    user: Dict = Depends(verify_jwt),
):
    """Lists recent agent tasks for the authenticated user."""
    user_id = user["sub"]
    supabase = get_supabase_admin()

    result = await asyncio.to_thread(
        lambda: supabase.table("agent_tasks")
        .select("id, conversation_id, goal, state, current_step, total_token_spend, created_at, completed_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return {"tasks": result.data or []}
