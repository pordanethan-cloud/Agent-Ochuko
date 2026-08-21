# Phase 1: Agent Mode Foundation

> **Parent**: [Master Plan](./00_master_plan.md)
> **Timeline**: Weeks 1–3
> **Status**: Draft

---

## Phase 1 Overview

Phase 1 builds the core agent mode infrastructure on top of what Agent Ochuko already has. By the end, users can toggle agent mode, see an editable execution plan, watch step-by-step progress, and the system aggressively manages tokens via context compression and sub-agent delegation.

### Deliverables

1. Agent Task State Machine (`AgentTaskManager`)
2. Structured Plan Generator (upgrade to `agent_planner.py`)
3. HITL Approval Gates (chat-thread pause/resume)
4. Sub-Agent Delegation Pool (nano workers for isolated tool calls)
5. Context Compression Engine (sliding window + step-result summarization)
6. Time Limit Enforcement (per-step 90s + per-task 5 min)
7. Frontend: Agent Mode toggle, plan review panel, execution progress bar, approval UI
8. Database: `agent_tasks` table with RLS

---

## 1.1 Agent Task State Machine

### File: [NEW] `app/core/agent_task_manager.py`

The central orchestrator that replaces the inline `while iteration < max_iterations` loop in `chat.py` for agent-mode requests.

#### State Diagram

```
                    ┌───────────┐
          ┌────────>│ CANCELLED │
          │         └───────────┘
          │
┌─────────┴───┐     ┌──────────────────┐     ┌───────────┐
│  PLANNING   │────>│ AWAITING_APPROVAL│────>│ EXECUTING │
└─────────────┘     └──────────────────┘     └─────┬─────┘
                            ^                       │
                            │                       │
                    ┌───────┴──────────┐     ┌──────v─────────┐
                    │ PAUSED_FOR_HITL  │<────│ (high-risk step)│
                    └──────────────────┘     └────────────────┘
                                                    │
                                              ┌─────v──────┐
                                              │ COMPLETED  │
                                              └────────────┘
                                              ┌────────────┐
                                              │  FAILED    │
                                              └────────────┘
```

#### Data Models

```python
# app/core/agent_task_manager.py

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class TaskState(str, Enum):
    PLANNING           = "planning"
    AWAITING_APPROVAL  = "awaiting_approval"
    EXECUTING          = "executing"
    PAUSED_FOR_HITL    = "paused_for_hitl"
    COMPLETED          = "completed"
    FAILED             = "failed"
    CANCELLED          = "cancelled"

class StepStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"

class RiskLevel(str, Enum):
    LOW    = "low"     # auto-execute (search, read_me)
    MEDIUM = "medium"  # execute but log (read-only code, widget)
    HIGH   = "high"    # pause for HITL (file writes, email, API calls)

class PlanStep(BaseModel):
    index: int
    description: str
    tool_name: Optional[str] = None        # Expected tool
    tool_args_hint: Optional[Dict] = None  # Pre-filled args (optional)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False        # Derived from risk_level + config
    status: StepStatus = StepStatus.PENDING
    result_summary: Optional[str] = None   # Compressed result (< 200 tokens)
    artifacts: List[str] = []              # File URLs produced
    duration_ms: Optional[int] = None
    token_spend: int = 0
    error: Optional[str] = None

class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    user_id: str
    goal: str                              # Original user goal
    plan: List[PlanStep] = []
    state: TaskState = TaskState.PLANNING
    current_step: int = 0
    artifacts: List[Dict[str, Any]] = []   # {filename, url, size, produced_by_step}
    total_token_spend: int = 0
    max_duration_seconds: int = 300        # 5 minutes
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
```

#### Core Methods

```python
class AgentTaskManager:
    """Orchestrates the Plan-Act-Observe loop for agent mode tasks."""

    def __init__(self, task: AgentTask, openai_client, config):
        self.task = task
        self.client = openai_client
        self.config = config
        self.circuit_breaker = create_turn_circuit_breaker(max_steps=len(task.plan))
        self.reflexion = create_reflexion_engine(max_attempts=3)
        self.start_time = None

    async def generate_plan(self) -> List[PlanStep]:
        """
        Calls nano model to decompose goal into structured PlanSteps.
        Uses JSON-mode output for reliable parsing.
        Returns structured plan with risk classifications.
        """
        ...

    async def execute_plan(self) -> AsyncGenerator[SSEEvent, None]:
        """
        Main execution loop. Yields SSE events for frontend.
        For each step:
          1. Check time budget (wall-clock)
          2. Check token budget
          3. If step.requires_approval → yield HITL event, pause
          4. Build compressed context (task state + aim + prev result)
          5. Delegate to sub-agent if applicable
          6. Execute step tool
          7. Compress result into summary
          8. Update task state in DB
          9. Yield progress SSE event
        """
        ...

    async def execute_single_step(self, step: PlanStep) -> StepResult:
        """
        Executes one plan step. Builds a MINIMAL context payload:
        - System prompt (~500 tok)
        - Task goal (~50 tok)
        - Plan overview with step statuses (~200 tok)
        - Previous step result summary (~200 tok)
        - Reflexion context if errors (~100 tok)
        Total: ~1,050 tokens input per step
        """
        ...

    def build_step_context(self, step_index: int) -> List[Dict]:
        """
        Builds the compressed context for a single step.
        This is WHERE token savings happen.
        """
        context = [
            {"role": "system", "content": self._build_agent_system_prompt()},
            {"role": "user", "content": self._build_step_payload(step_index)},
        ]
        return context

    def _build_step_payload(self, step_index: int) -> str:
        """
        Builds the user message for a step execution.
        Contains ONLY:
        - Goal (1 line)
        - Plan summary (numbered list with checkmarks for completed steps)
        - Current step instruction
        - Previous step result (compressed)
        - Reflexion hints (if any failures)
        """
        step = self.task.plan[step_index]
        plan_summary = "\n".join(
            f"{'[x]' if s.status == 'completed' else '[ ]'} {s.index}. {s.description}"
            for s in self.task.plan
        )
        prev_result = ""
        if step_index > 0:
            prev = self.task.plan[step_index - 1]
            prev_result = f"\nPrevious step result: {prev.result_summary or 'completed'}"

        return (
            f"GOAL: {self.task.goal}\n\n"
            f"PLAN:\n{plan_summary}\n\n"
            f"CURRENT STEP {step.index}: {step.description}\n"
            f"{prev_result}\n\n"
            f"Execute this step now. Use the appropriate tool."
        )

    def check_time_budget(self) -> bool:
        """Returns False if wall-clock time exceeds max_duration_seconds."""
        if self.start_time is None:
            return True
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        return elapsed < self.task.max_duration_seconds

    def check_token_budget(self, estimated_cost: int) -> bool:
        """Returns False if adding estimated_cost would exceed user's remaining budget."""
        # Reads from the SHARED daily token budget (same as chat mode)
        ...
```

---

## 1.2 Structured Plan Generator

### File: [MODIFY] `app/core/agent_planner.py`

Upgrade from raw text output to structured `List[PlanStep]` with risk classification.

#### Changes

1. **New function**: `generate_structured_plan()` — uses JSON-mode output from nano

```python
_STRUCTURED_PLANNER_SYSTEM = (
    "You are a task planning assistant. Decompose the user's goal into 2-8 actionable steps.\n"
    "Output ONLY valid JSON — an array of objects with these fields:\n"
    "- description: string (what to do)\n"
    "- tool_name: string or null (search_web | execute_code | deep_research | "
    "  generate_image | browse_web | null)\n"
    "- risk_level: 'low' | 'medium' | 'high'\n\n"
    "Risk classification:\n"
    "- low: reading/searching (search_web, deep_research)\n"
    "- medium: code execution that only reads/computes (execute_code with no file writes)\n"
    "- high: code that writes files, sends emails, modifies external systems, browse_web\n\n"
    "If the goal is trivially simple (one step), return: [{\"description\": \"...\", "
    "\"tool_name\": null, \"risk_level\": \"low\"}]"
)

async def generate_structured_plan(
    user_message: str,
    conversation_history: Optional[List[Dict]] = None,
    openai_client: Optional[AsyncAzureOpenAI] = None,
    nano_deployment: str = "gpt-5.4-nano",
) -> Optional[List[PlanStep]]:
    """
    Returns structured plan steps or None if message is simple.
    Uses JSON-mode for reliable parsing.
    """
    if not _is_complex(user_message) and not _RESEARCH_INTENSIVE_RE.search(user_message):
        return None

    # ... call nano with response_format={"type": "json_object"} ...
    # Parse response into List[PlanStep]
    # Auto-set requires_approval based on risk_level vs AGENT_MODE_AUTO_APPROVE config
```

2. **Keep existing** `generate_plan()` for non-agent-mode chat (backward compatible)

3. **New function**: `refine_plan()` — accepts user edits and regenerates downstream steps

```python
async def refine_plan(
    original_plan: List[PlanStep],
    user_edits: Dict[int, str],  # {step_index: new_description}
    openai_client: Optional[AsyncAzureOpenAI] = None,
) -> List[PlanStep]:
    """Re-plans steps after user edits, keeping completed steps intact."""
```

---

## 1.3 Sub-Agent Delegation Pool

### File: [NEW] `app/core/sub_agent_pool.py`

Lightweight nano workers that execute isolated tool calls and return compressed results to the orchestrator.

#### Design

```python
class SubAgentResult(BaseModel):
    """What the orchestrator receives from a sub-agent."""
    success: bool
    summary: str           # Compressed result (< 200 tokens)
    artifacts: List[str]   # File URLs if any
    token_spend: int       # Tokens consumed by this sub-agent call
    raw_length: int        # Original output length before compression

class SubAgentPool:
    """Manages isolated sub-agent executions for token-efficient delegation."""

    def __init__(self, openai_client, nano_deployment="gpt-5.4-nano"):
        self.client = openai_client
        self.nano = nano_deployment

    async def delegate_search(self, query: str) -> SubAgentResult:
        """
        Executes a web search in an isolated context.
        The raw search results (often 2,000-5,000 tokens) are processed
        by nano into a compressed summary (< 200 tokens).
        The orchestrator NEVER sees the raw results.
        """
        # 1. Call search tool
        raw_result = await _perform_google_search(query, ...)
        # 2. Compress with nano
        summary = await self._compress_result(
            f"Search results for '{query}':\n{raw_result}",
            instruction="Extract the key facts in 2-3 sentences. Include specific numbers, dates, and names."
        )
        return SubAgentResult(
            success=True,
            summary=summary,
            artifacts=[],
            token_spend=estimated_tokens,
            raw_length=len(raw_result),
        )

    async def delegate_code_execution(
        self, code: str, language: str, conversation_id: str, user_id: str
    ) -> SubAgentResult:
        """
        Executes code in sandbox. Returns compressed output + any file artifacts.
        Full stdout/stderr stays in the sub-agent; only the summary is returned.
        """
        exec_output, exec_files = await execute_code_in_sandbox(
            code=code, language=language,
            conversation_id=conversation_id, user_id=user_id,
            timeout_seconds=60,
        )
        # Compress stdout/stderr
        if len(exec_output) > 500:
            summary = await self._compress_result(
                exec_output,
                instruction="Summarize the code execution output. Include key results, errors, and file paths."
            )
        else:
            summary = exec_output

        return SubAgentResult(
            success="error" not in exec_output.lower(),
            summary=summary,
            artifacts=[f["download_url"] for f in exec_files] if exec_files else [],
            token_spend=estimated_tokens,
            raw_length=len(exec_output),
        )

    async def _compress_result(self, raw_text: str, instruction: str) -> str:
        """
        Uses nano to compress raw tool output into a concise summary.
        This is the core token-saving mechanism.
        Target: < 200 tokens output.
        """
        response = await self.client.responses.create(
            model=self.nano,
            input=[
                {"role": "system", "content": (
                    "You are a result compressor. Read the raw output below and "
                    f"{instruction}\n"
                    "Be concise. Maximum 3 sentences. Include specific data points."
                )},
                {"role": "user", "content": raw_text[:4000]},  # Cap input
            ],
        )
        return (getattr(response, "output_text", "") or "").strip()
```

---

## 1.4 Context Compression Engine

### File: [MODIFY] `app/services/hybrid_memory.py`

Upgrade to support agent-mode context compression.

#### Changes

```python
class AgentContextCompressor:
    """
    Builds minimal context payloads for agent mode steps.
    
    Strategy:
    - Each step gets ONLY: system + task state + prev result + reflexion
    - No conversation history is carried
    - Sub-agent outputs are pre-compressed before reaching the orchestrator
    - Browser state uses accessibility tree (200 tok) not screenshots (5000 tok)
    """

    @staticmethod
    def build_task_state_prompt(task: AgentTask) -> str:
        """
        Serializes current task state into ~300 tokens.
        This replaces the full conversation history in agent mode.
        """
        completed = [s for s in task.plan if s.status == StepStatus.COMPLETED]
        completed_summary = "; ".join(
            f"Step {s.index}: {s.result_summary or 'done'}"
            for s in completed[-3:]  # Only last 3 completed steps
        ) if completed else "No steps completed yet"

        return (
            f"TASK GOAL: {task.goal}\n"
            f"PROGRESS: {len(completed)}/{len(task.plan)} steps completed\n"
            f"RECENT RESULTS: {completed_summary}\n"
            f"CURRENT STEP: {task.current_step}/{len(task.plan)}"
        )

    @staticmethod
    def compress_step_result(raw_output: str, max_tokens: int = 200) -> str:
        """
        Truncates/summarizes step output to fit within token budget.
        For short outputs: return as-is.
        For long outputs: truncate to key lines + ellipsis.
        For very long outputs: delegate to nano for summarization.
        """
        if len(raw_output) < max_tokens * 4:  # ~4 chars per token
            return raw_output
        # Simple truncation with boundary detection
        truncated = raw_output[:max_tokens * 4]
        last_newline = truncated.rfind("\n")
        if last_newline > 200:
            truncated = truncated[:last_newline]
        return truncated + "\n[...truncated]"
```

---

## 1.5 HITL Approval Gates

### File: [NEW] `app/core/hitl_gates.py`

```python
class HITLGate:
    """
    Manages human-in-the-loop approval for high-risk agent steps.
    
    When a step requires approval:
    1. Task state transitions to PAUSED_FOR_HITL
    2. SSE event `agent_approval_required` is emitted to frontend
    3. Frontend shows approval UI in the chat thread
    4. User clicks Approve / Skip / Cancel
    5. API endpoint /v1/agent-tasks/{id}/approve resumes execution
    """

    @staticmethod
    def classify_risk(step: PlanStep) -> RiskLevel:
        """Determines risk level based on tool and arguments."""
        LOW_RISK_TOOLS = {"search_web", "deep_research", "visualize__read_me"}
        MEDIUM_RISK_TOOLS = {"visualize__show_widget"}
        HIGH_RISK_TOOLS = {"generate_image", "browse_web"}

        if step.tool_name in LOW_RISK_TOOLS:
            return RiskLevel.LOW
        if step.tool_name in MEDIUM_RISK_TOOLS:
            return RiskLevel.MEDIUM
        if step.tool_name in HIGH_RISK_TOOLS:
            return RiskLevel.HIGH
        if step.tool_name == "execute_code":
            # Check if code writes files
            code = (step.tool_args_hint or {}).get("code", "")
            write_indicators = ["open(", "write(", "save(", "to_csv", "to_excel",
                              "savefig", "to_pdf", "shutil", "os.rename"]
            if any(ind in code for ind in write_indicators):
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM
        return RiskLevel.MEDIUM

    @staticmethod
    def requires_approval(step: PlanStep, auto_approve_level: str = "low") -> bool:
        """
        Returns True if the step should pause for human approval.
        auto_approve_level from config: "low" | "medium" | "high" | "none"
        """
        risk = HITLGate.classify_risk(step)
        level_order = {"none": -1, "low": 0, "medium": 1, "high": 2}
        return level_order.get(risk.value, 1) > level_order.get(auto_approve_level, 0)
```

---

## 1.6 Time Limit Enforcement

### File: [MODIFY] `app/core/circuit_breaker.py`

Add wall-clock timer and token budget tracking for agent mode.

```python
# New additions to CircuitBreaker class:

class CircuitBreaker:
    def __init__(self, max_steps=10, max_consecutive_errors=3,
                 max_duration_seconds=300, max_tokens=None):
        self.max_duration_seconds = max_duration_seconds
        self.max_tokens = max_tokens  # None = use shared budget
        self.total_tokens_used = 0
        # ... existing fields ...

    def check_time_budget(self) -> bool:
        """Returns False if wall-clock time exceeds max_duration_seconds."""
        elapsed = time.time() - self.start_time
        if elapsed >= self.max_duration_seconds:
            raise ActionBudgetExceeded(
                f"Task time limit exceeded ({int(elapsed)}s / {self.max_duration_seconds}s). "
                "Synthesizing final answer from completed steps."
            )
        return True

    def record_token_spend(self, tokens: int):
        """Track cumulative token spend across all steps."""
        self.total_tokens_used += tokens
        logger.info(f"Token spend: {self.total_tokens_used} total")

    def check_step_timeout(self, step_start: float, step_timeout: int = 90):
        """Raises if a single step exceeds its timeout."""
        elapsed = time.time() - step_start
        if elapsed >= step_timeout:
            raise ActionBudgetExceeded(
                f"Step timeout exceeded ({int(elapsed)}s / {step_timeout}s)"
            )
```

---

## 1.7 Agent Config Updates

### File: [MODIFY] `app/core/agent_config.py`

```python
# New config keys for agent mode:

async def get_agent_mode_config() -> Dict[str, Any]:
    return {
        "enabled": (await get_config("AGENT_MODE_ENABLED", "true")).lower() != "false",
        "max_steps": int(await get_config("AGENT_MODE_MAX_STEPS", "15")),
        "max_duration_seconds": int(await get_config("AGENT_MODE_MAX_DURATION", "300")),
        "step_timeout_seconds": int(await get_config("AGENT_MODE_STEP_TIMEOUT", "90")),
        "auto_approve_level": await get_config("AGENT_MODE_AUTO_APPROVE", "low"),
        # "low" = auto-approve low-risk, pause for medium+high
        # "medium" = auto-approve low+medium, pause for high only
        # "none" = pause for everything
    }
```

---

## 1.8 API Endpoints

### File: [NEW] `app/api/v1/endpoints/agent_tasks.py`

```python
router = APIRouter()

class CreateTaskRequest(BaseModel):
    conversation_id: str
    goal: str

class ApproveRequest(BaseModel):
    action: str = "approve"  # "approve" | "skip" | "cancel"
    step_index: Optional[int] = None

class EditPlanRequest(BaseModel):
    edits: Dict[int, str]  # {step_index: new_description}

@router.post("/", status_code=202)
async def create_agent_task(payload: CreateTaskRequest, user=Depends(verify_jwt)):
    """
    1. Create AgentTask with state=PLANNING
    2. Generate structured plan via nano
    3. Persist to agent_tasks table
    4. Return task_id + plan for frontend review
    """
    ...

@router.get("/{task_id}")
async def get_task_status(task_id: str, user=Depends(verify_jwt)):
    """Returns current task state, plan, step results, artifacts."""
    ...

@router.post("/{task_id}/approve")
async def approve_task(task_id: str, payload: ApproveRequest, user=Depends(verify_jwt)):
    """
    If task is AWAITING_APPROVAL: approve plan and start execution (SSE stream)
    If task is PAUSED_FOR_HITL: approve/skip the current step, resume execution
    If action is "cancel": set state to CANCELLED
    """
    ...

@router.post("/{task_id}/edit-plan")
async def edit_plan(task_id: str, payload: EditPlanRequest, user=Depends(verify_jwt)):
    """User edits plan steps before approval. Re-generates downstream steps."""
    ...

@router.get("/{task_id}/artifacts")
async def list_artifacts(task_id: str, user=Depends(verify_jwt)):
    """Lists all files produced by this task with provenance."""
    ...

@router.get("/")
async def list_tasks(user=Depends(verify_jwt)):
    """Lists user's recent agent tasks (last 30 days)."""
    ...
```

### File: [MODIFY] `app/main.py`

```python
from app.api.v1.endpoints.agent_tasks import router as agent_tasks_router
# ...
app.include_router(agent_tasks_router, prefix="/v1/agent-tasks", tags=["agent-tasks"])
```

### File: [MODIFY] `app/api/v1/endpoints/chat.py`

Add agent mode detection in `stream_chat()`:

```python
# In stream_chat(), after routing decision:
if request_mode == "agent" or (plan and len(plan) > 3):
    # Route to agent task manager instead of inline OODA loop
    task = AgentTask(conversation_id=conversation_id, user_id=user_id, goal=user_message)
    manager = AgentTaskManager(task, client, config)
    plan_steps = await manager.generate_plan()
    # ... persist, yield agent_plan SSE event, await approval ...
else:
    # Existing OODA loop for standard chat mode (no changes)
    ...
```

---

## 1.9 SSE Event Specifications

New SSE events for agent mode (in addition to existing events):

```json
// Plan ready for user review
{"type": "agent_plan", "task_id": "uuid", "plan": [
  {"index": 1, "description": "Search for...", "tool_name": "search_web", "risk_level": "low"},
  {"index": 2, "description": "Run code to...", "tool_name": "execute_code", "risk_level": "medium"},
  {"index": 3, "description": "Generate report...", "tool_name": "execute_code", "risk_level": "high"}
]}

// Step started
{"type": "agent_step_start", "task_id": "uuid", "step_index": 1,
 "description": "Searching for cloud provider pricing...", "tool_name": "search_web"}

// Step completed
{"type": "agent_step_complete", "task_id": "uuid", "step_index": 1,
 "result_summary": "Found pricing for AWS, Azure, GCP...",
 "duration_ms": 3200, "token_spend": 450}

// HITL approval needed
{"type": "agent_approval_required", "task_id": "uuid", "step_index": 3,
 "description": "Generate PDF report with comparison data",
 "risk_level": "high", "reason": "This step will create and save a file"}

// Task completed
{"type": "agent_task_complete", "task_id": "uuid",
 "summary": "Completed 3/3 steps. Generated comparison report.",
 "artifacts": [{"filename": "report.pdf", "url": "https://...", "size_bytes": 45200}],
 "total_token_spend": 3800, "duration_seconds": 42}

// Task failed
{"type": "agent_task_failed", "task_id": "uuid",
 "error": "Step 2 failed after 3 retries: API rate limit",
 "completed_steps": 1, "recovery_suggestion": "Try again in 5 minutes"}

// Time limit warning (at 80% of budget)
{"type": "agent_time_warning", "task_id": "uuid",
 "elapsed_seconds": 240, "max_seconds": 300,
 "message": "4 minutes elapsed. Completing remaining steps..."}
```

---

## 1.10 Database Migration

### Supabase SQL: `agent_tasks` table

```sql
-- Create agent_tasks table
CREATE TABLE IF NOT EXISTS agent_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    goal TEXT NOT NULL,
    plan JSONB DEFAULT '[]'::jsonb,
    state TEXT NOT NULL DEFAULT 'planning'
        CHECK (state IN ('planning', 'awaiting_approval', 'executing',
                         'paused_for_hitl', 'completed', 'failed', 'cancelled')),
    current_step INT DEFAULT 0,
    step_results JSONB DEFAULT '[]'::jsonb,
    artifacts JSONB DEFAULT '[]'::jsonb,
    total_token_spend INT DEFAULT 0,
    max_duration_seconds INT DEFAULT 300,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Row Level Security
ALTER TABLE agent_tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own tasks"
    ON agent_tasks FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own tasks"
    ON agent_tasks FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own tasks"
    ON agent_tasks FOR UPDATE
    USING (auth.uid() = user_id);

-- Service role bypass for backend
CREATE POLICY "Service role full access"
    ON agent_tasks FOR ALL
    USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX idx_agent_tasks_user_state ON agent_tasks(user_id, state);
CREATE INDEX idx_agent_tasks_conversation ON agent_tasks(conversation_id);
CREATE INDEX idx_agent_tasks_created ON agent_tasks(created_at DESC);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_agent_task_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agent_tasks_updated_at
    BEFORE UPDATE ON agent_tasks
    FOR EACH ROW EXECUTE FUNCTION update_agent_task_timestamp();
```

---

## 1.11 Frontend Changes

### File: [MODIFY] `Dashboard.tsx`

#### A. Agent Mode Toggle

Add to the chat composer area:

```tsx
// New state
const [isAgentMode, setIsAgentMode] = useState(false);
const [agentTask, setAgentTask] = useState<AgentTask | null>(null);

// Toggle button next to the send button
<button
  onClick={() => setIsAgentMode(!isAgentMode)}
  className={`agent-mode-toggle ${isAgentMode ? 'active' : ''}`}
  title="Toggle Agent Mode"
>
  <AgentIcon /> {/* Rocket or agent icon */}
</button>

// Dynamic placeholder
<textarea
  placeholder={isAgentMode
    ? "Describe your goal — Agent Ochuko will plan and execute it..."
    : "Ask anything..."}
/>
```

#### B. Plan Review Panel

When `agent_plan` SSE event arrives:

```tsx
// Renders inside the chat thread as a special message bubble
<AgentPlanReview
  plan={agentTask.plan}
  onApprove={() => approvePlan(agentTask.id)}
  onEdit={(stepIndex, newDesc) => editPlanStep(agentTask.id, stepIndex, newDesc)}
  onCancel={() => cancelTask(agentTask.id)}
/>

// AgentPlanReview component shows:
// - Numbered step list with risk badges (green/yellow/red)
// - Editable description fields
// - Reorder drag handles
// - "Approve & Execute" / "Cancel" buttons
```

#### C. Execution Progress

During execution, render a progress component in the chat:

```tsx
<AgentProgress
  task={agentTask}
  steps={agentTask.plan}
  currentStep={agentTask.current_step}
  elapsedSeconds={elapsed}
  maxSeconds={agentTask.max_duration_seconds}
  onPause={() => pauseTask(agentTask.id)}
  onCancel={() => cancelTask(agentTask.id)}
/>

// Shows:
// - Progress bar: step X/N
// - Time elapsed / time remaining
// - Each step: pending (gray) → running (spinner) → done (green check) → failed (red X)
// - Expandable step results
// - Pause / Cancel buttons
```

#### D. HITL Approval in Chat Thread

When `agent_approval_required` SSE event arrives:

```tsx
<AgentApprovalCard
  step={pendingStep}
  riskLevel={pendingStep.risk_level}
  reason="This step will create and save a file to your storage"
  onApprove={() => approveStep(agentTask.id, pendingStep.index)}
  onSkip={() => skipStep(agentTask.id, pendingStep.index)}
  onCancel={() => cancelTask(agentTask.id)}
/>
```

#### E. SSE Event Handling Extension

```typescript
// Add to existing SSE parser in Dashboard.tsx:
case "agent_plan":
  setAgentTask(prev => ({ ...prev, plan: data.plan, state: "awaiting_approval" }));
  break;
case "agent_step_start":
  updateStepStatus(data.step_index, "running", data.description);
  break;
case "agent_step_complete":
  updateStepStatus(data.step_index, "completed", data.result_summary);
  break;
case "agent_approval_required":
  setAgentTask(prev => ({ ...prev, state: "paused_for_hitl" }));
  setPendingApproval(data);
  break;
case "agent_task_complete":
  setAgentTask(prev => ({ ...prev, state: "completed", artifacts: data.artifacts }));
  break;
case "agent_task_failed":
  setAgentTask(prev => ({ ...prev, state: "failed", error: data.error }));
  break;
case "agent_time_warning":
  showTimeWarning(data.message);
  break;
```

---

## 1.12 Capability Registry Update

### File: [MODIFY] `app/core/capability_registry.py`

```python
# Add to CAPABILITY_REGISTRY:
"agent_mode": {
    "description": "Autonomous multi-step task execution with planning, approval, and artifact production",
    "activation": "User toggles Agent Mode or sends a complex goal",
    "capabilities": [
        "Goal decomposition into executable plan steps",
        "Autonomous tool orchestration (search, code, image, widgets)",
        "Human-in-the-loop approval for high-risk actions",
        "Sub-agent delegation for token-efficient execution",
        "Context compression — each turn carries only task state + aim",
        "Time-limited execution (5 min max)",
        "Artifact production with provenance tracking",
    ],
    "limits": {
        "max_steps": 15,
        "max_duration_seconds": 300,
        "step_timeout_seconds": 90,
    },
}
```

---

## 1.13 File Change Summary

| Action | File | Description |
|---|---|---|
| **NEW** | `app/core/agent_task_manager.py` | Task state machine + Plan-Act-Observe loop |
| **NEW** | `app/core/sub_agent_pool.py` | Nano sub-agents with compressed returns |
| **NEW** | `app/core/hitl_gates.py` | Risk classification + approval logic |
| **NEW** | `app/api/v1/endpoints/agent_tasks.py` | REST API for task lifecycle |
| **MODIFY** | `app/core/agent_planner.py` | Structured JSON plan output |
| **MODIFY** | `app/core/agent_config.py` | Agent mode config keys |
| **MODIFY** | `app/core/circuit_breaker.py` | Wall-clock timer + token budget |
| **MODIFY** | `app/core/capability_registry.py` | Agent mode capability entry |
| **MODIFY** | `app/services/hybrid_memory.py` | Context compression for agent mode |
| **MODIFY** | `app/api/v1/endpoints/chat.py` | Agent mode routing (5-10 lines) |
| **MODIFY** | `app/main.py` | Register agent_tasks router |
| **MODIFY** | `frontend/src/pages/Dashboard.tsx` | Agent mode toggle, plan review, progress, HITL |
| **NEW** | Supabase migration | `agent_tasks` table + RLS + indexes |

---

## 1.14 Verification Plan

### Automated Tests

```bash
# New tests
python -m pytest tests/test_agent_task_manager.py -v
python -m pytest tests/test_structured_planner.py -v
python -m pytest tests/test_sub_agent_pool.py -v
python -m pytest tests/test_hitl_gates.py -v
python -m pytest tests/test_context_compression.py -v

# Regression — existing tests must pass unchanged
python -m pytest tests/test_agent_architecture.py tests/test_model_router.py tests/test_document_pipeline.py -v

# Frontend
cd agent-ochuko/frontend && npx tsc --noEmit && npm run build
```

### Manual Test Scenarios

1. **Plan Review**: Toggle agent mode → submit "Compare AWS, Azure, GCP pricing for a startup and generate a report" → verify structured plan appears → edit a step → approve → watch execution
2. **HITL Pause**: Submit goal with file generation → verify pause at high-risk step → approve → verify file produced
3. **Token Efficiency**: Monitor token spend per step — should average ~1,200 tokens/step vs ~6,000 for current chat mode
4. **Time Limit**: Set `AGENT_MODE_MAX_DURATION=30` (30 seconds) → submit complex goal → verify graceful timeout with partial results
5. **Cancel**: Start task → cancel mid-execution → verify state = cancelled, no further steps
6. **Regression**: Run 10 standard chat queries with agent mode OFF → verify identical behavior to current production
