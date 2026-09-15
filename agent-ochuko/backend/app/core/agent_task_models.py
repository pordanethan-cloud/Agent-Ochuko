# app/core/agent_task_models.py
"""
Agent Task Data Models & Enums.
Provides type-safe models for Agent Mode plan decomposition, step tracking,
HITL gates, sub-agent delegation, and artifact provenance.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

# Phase 9 — Blackboard working memory caps. The scratchpad exists to close
# the distillation gap: step_results keep only ~500-char summaries, so later
# steps (and the final synthesis) lose the WHY behind earlier outcomes.
# Entries are capped hard to protect prompt budgets.
SCRATCHPAD_MAX_ENTRIES = 30
SCRATCHPAD_MAX_CONTENT = 500

class TaskState(str, Enum):
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    PAUSED_FOR_HITL = "paused_for_hitl"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(str, Enum):
    LOW = "low"        # Auto-execute (search_web, deep_research, visualize__read_me)
    MEDIUM = "medium"  # Safe compute (read-only code execution, widget preview)
    HIGH = "high"      # Human-in-the-loop required (file generation, external mutations, uploads)


class PlanStep(BaseModel):
    index: int
    description: str
    tool_name: Optional[str] = None
    tool_args_hint: Optional[Dict[str, Any]] = None
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    status: StepStatus = StepStatus.PENDING
    result_summary: Optional[str] = None
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    duration_ms: Optional[int] = None
    token_spend: int = 0
    error: Optional[str] = None


class StepResult(BaseModel):
    success: bool
    summary: str
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    token_spend: int = 0
    raw_length: int = 0
    error: Optional[str] = None


class SubAgentResult(BaseModel):
    success: bool
    summary: str
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    token_spend: int = 0
    raw_length: int = 0
    error: Optional[str] = None


class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    user_id: str
    goal: str
    plan: List[PlanStep] = Field(default_factory=list)
    state: TaskState = TaskState.PLANNING
    current_step: int = 0
    step_results: List[Dict[str, Any]] = Field(default_factory=list)
    # Phase 9: blackboard working memory — {"entries": [{id, kind, content,
    # step_index, created_at}]}, appended via append_scratchpad_entry().
    scratchpad: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    total_token_spend: int = 0
    max_duration_seconds: int = 300
    replan_count: int = 0
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


def append_scratchpad_entry(
    scratchpad: Dict[str, Any],
    kind: str,
    content: str,
    step_index: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Phase 9: append a capped entry to the blackboard scratchpad (pure function).

    Kinds: fact | decision | discovery | artifact_ref | open_question |
    constraint. Empty content is a no-op. Content is truncated to
    SCRATCHPAD_MAX_CONTENT chars; when the board exceeds
    SCRATCHPAD_MAX_ENTRIES entries the oldest are evicted.
    """
    content = (content or "").strip()
    if not content:
        return scratchpad
    entries = scratchpad.setdefault("entries", [])
    entries.append({
        "id": f"{kind}-{len(entries)}-{uuid.uuid4().hex[:8]}",
        "kind": kind,
        "content": content[:SCRATCHPAD_MAX_CONTENT],
        "step_index": step_index,
        "created_at": datetime.utcnow().isoformat(),
    })
    if len(entries) > SCRATCHPAD_MAX_ENTRIES:
        scratchpad["entries"] = entries[-SCRATCHPAD_MAX_ENTRIES:]
    return scratchpad


def scratchpad_digest(scratchpad: Optional[Dict[str, Any]]) -> str:
    """
    Phase 9: compact one-line-per-entry digest for prompt injection.
    Returns '' when the board is empty or malformed (never raises).
    """
    entries = (scratchpad or {}).get("entries") or []
    if not entries:
        return ""
    lines = ["WORKING MEMORY (facts and decisions from earlier steps):"]
    for e in entries:
        if isinstance(e, dict):
            kind = e.get("kind", "fact")
            content = e.get("content", "")
        else:
            kind, content = "fact", str(e)
        lines.append(f"- [{kind}] {content}")
    lines.append("Use these findings and decisions; do not contradict or rediscover them.")
    return "\n".join(lines)
