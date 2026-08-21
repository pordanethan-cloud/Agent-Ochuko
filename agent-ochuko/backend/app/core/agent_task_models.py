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
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    total_token_spend: int = 0
    max_duration_seconds: int = 300
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
