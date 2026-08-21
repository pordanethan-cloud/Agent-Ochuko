# Phase 2: Browser Agent & Background Execution

> **Parent**: [Master Plan](./00_master_plan.md)
> **Depends on**: [Phase 1](./01_phase1_foundation.md)
> **Timeline**: Weeks 4–6
> **Status**: Draft

---

## Phase 2 Overview

Phase 2 adds two major capabilities:
1. **Browser Agent** — Playwright-based headless browser that lets Agent Ochuko take actions on web pages (click, type, scroll, fill forms, scrape data, navigate) on behalf of the user
2. **Background Execution** — moves long-running agent tasks off the SSE request thread into Azure Queue workers with durable DB-backed state, enabling 15-minute task execution and resilience to page refreshes

### Deliverables

1. Browser Agent (Playwright + accessibility tree for token efficiency)
2. Background Agent Worker (Azure Functions queue-triggered)
3. Durable State upgrade (Supabase-backed, cross-container resume)
4. Realtime Push Updates (Supabase Realtime for live progress)
5. Extended time limits (15 minutes per task)
6. Browser tool registration in agent mode tool set

---

## 2.1 Browser Agent Architecture

### File: [NEW] `app/services/browser_agent.py`

The browser agent uses **Playwright** to control a headless Chromium browser. It reads page state via the **accessibility tree** (not screenshots) to minimize token consumption.

#### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser Agent                                                      │
│                                                                     │
│  ┌──────────────┐     ┌────────────────────┐     ┌──────────────┐  │
│  │  Orchestrator │────>│  Observation Layer │────>│ LLM (nano)   │  │
│  │  (AgentTask)  │     │  - A11y tree       │     │ Decide next  │  │
│  │              │     │  - URL + title     │     │ action       │  │
│  │              │<────│  - Page text       │<────│              │  │
│  │              │     └────────────────────┘     └──────────────┘  │
│  │              │                                                   │
│  │              │     ┌────────────────────┐                       │
│  │              │────>│  Action Layer       │                       │
│  │              │     │  - click(selector)  │                       │
│  │              │     │  - type(selector,t) │                       │
│  │              │     │  - scroll(dir)      │                       │
│  │              │     │  - navigate(url)    │                       │
│  │              │     │  - extract(selector)│                       │
│  │              │     │  - screenshot()     │                       │
│  │              │     └────────────────────┘                       │
│  └──────────────┘                                                   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Token Efficiency Layer                                      │  │
│  │  - Accessibility tree snapshot: ~200-400 tokens              │  │
│  │  - Only take screenshot on LLM request (fallback for canvas)│  │
│  │  - Sliding window: carry only current page state per turn    │  │
│  │  - Max 10 browser actions per step before forcing completion │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

#### Data Models

```python
from enum import Enum
from pydantic import BaseModel
from typing import Optional, List

class BrowserAction(str, Enum):
    NAVIGATE  = "navigate"
    CLICK     = "click"
    TYPE      = "type"
    SCROLL    = "scroll"
    EXTRACT   = "extract"
    SCREENSHOT = "screenshot"
    WAIT      = "wait"
    DONE      = "done"

class BrowserCommand(BaseModel):
    action: BrowserAction
    selector: Optional[str] = None   # CSS selector or accessibility ref
    value: Optional[str] = None      # Text to type, URL to navigate to
    direction: Optional[str] = None  # "up" | "down" for scroll

class BrowserObservation(BaseModel):
    url: str
    title: str
    accessibility_tree: str          # YAML-like a11y snapshot (~200-400 tokens)
    extracted_text: Optional[str] = None
    screenshot_base64: Optional[str] = None  # Only on explicit request
    error: Optional[str] = None
```

#### Implementation

```python
import asyncio
import logging
from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger("app.services.browser_agent")

class BrowserAgent:
    """
    Playwright-based browser for agent mode.
    Uses accessibility tree for token-efficient page state representation.
    """

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.action_count = 0
        self.max_actions_per_step = 10

    async def start(self):
        """Launch headless Chromium browser."""
        pw = await async_playwright().start()
        self.browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = await self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="AgentOchuko/1.0 (Browser Agent)"
        )
        self.page = await context.new_page()

    async def stop(self):
        """Close browser and release resources."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None

    async def observe(self) -> BrowserObservation:
        """
        Capture current page state using accessibility tree.
        This is the TOKEN-EFFICIENT alternative to screenshots.
        
        Accessibility tree: ~200-400 tokens (structured YAML)
        Screenshot:         ~3,000-5,000 tokens (base64 image)
        
        We ALWAYS use a11y tree. Screenshots only on explicit model request.
        """
        if not self.page:
            return BrowserObservation(url="", title="", accessibility_tree="No page loaded")

        url = self.page.url
        title = await self.page.title()

        # Get accessibility snapshot (Playwright built-in)
        a11y_snapshot = await self.page.accessibility.snapshot()
        a11y_text = self._format_accessibility_tree(a11y_snapshot)

        return BrowserObservation(
            url=url,
            title=title,
            accessibility_tree=a11y_text,
        )

    def _format_accessibility_tree(self, node: dict, depth: int = 0) -> str:
        """
        Formats a11y tree into compact YAML-like text for LLM consumption.
        Keeps it under 400 tokens by truncating deep nesting and long text.
        """
        if not node:
            return ""

        indent = "  " * depth
        role = node.get("role", "")
        name = (node.get("name") or "")[:80]  # Truncate long names
        value = (node.get("value") or "")[:50]

        line = f"{indent}- {role}"
        if name:
            line += f": \"{name}\""
        if value:
            line += f" [value=\"{value}\"]"

        lines = [line]

        # Limit depth to 4 levels to control token count
        if depth < 4:
            for child in (node.get("children") or [])[:15]:  # Max 15 children
                lines.append(self._format_accessibility_tree(child, depth + 1))

        return "\n".join(lines)

    async def execute(self, command: BrowserCommand) -> BrowserObservation:
        """Execute a browser action and return new observation."""
        if not self.page:
            return BrowserObservation(url="", title="", accessibility_tree="", error="No page loaded")

        self.action_count += 1
        if self.action_count > self.max_actions_per_step:
            return BrowserObservation(
                url=self.page.url,
                title=await self.page.title(),
                accessibility_tree="",
                error=f"Max actions per step reached ({self.max_actions_per_step})"
            )

        try:
            if command.action == BrowserAction.NAVIGATE:
                await self.page.goto(command.value or "", wait_until="domcontentloaded", timeout=15000)

            elif command.action == BrowserAction.CLICK:
                await self.page.click(command.selector or "", timeout=5000)

            elif command.action == BrowserAction.TYPE:
                await self.page.fill(command.selector or "", command.value or "", timeout=5000)

            elif command.action == BrowserAction.SCROLL:
                direction = command.direction or "down"
                delta = 500 if direction == "down" else -500
                await self.page.mouse.wheel(0, delta)
                await asyncio.sleep(0.5)  # Wait for scroll to settle

            elif command.action == BrowserAction.EXTRACT:
                text = await self.page.inner_text(command.selector or "body", timeout=5000)
                obs = await self.observe()
                obs.extracted_text = text[:2000]  # Cap extracted text
                return obs

            elif command.action == BrowserAction.SCREENSHOT:
                screenshot_bytes = await self.page.screenshot(type="jpeg", quality=60)
                import base64
                obs = await self.observe()
                obs.screenshot_base64 = base64.b64encode(screenshot_bytes).decode()
                return obs

            elif command.action == BrowserAction.WAIT:
                await asyncio.sleep(min(int(command.value or "1"), 5))

        except Exception as e:
            logger.warning(f"Browser action {command.action} failed: {e}")
            obs = await self.observe()
            obs.error = str(e)[:200]
            return obs

        return await self.observe()
```

#### Browser Tool Definition (for agent mode)

```python
# Added to the agent mode tool set:
BROWSER_TOOL = {
    "type": "function",
    "name": "browse_web",
    "description": (
        "Control a web browser to navigate pages, click buttons, fill forms, "
        "scroll, and extract data. Use for tasks that require interacting with "
        "web interfaces — booking, form submission, data extraction from dynamic pages, "
        "price comparison across sites. "
        "Actions: navigate(url), click(selector), type(selector, text), "
        "scroll(up/down), extract(selector), screenshot(). "
        "The browser returns an accessibility tree of the page (not a screenshot) "
        "to save tokens. Request a screenshot only for visual elements."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["navigate", "click", "type", "scroll", "extract", "screenshot", "wait", "done"],
            },
            "selector": {"type": "string", "description": "CSS selector or element reference"},
            "value": {"type": "string", "description": "URL for navigate, text for type"},
            "direction": {"type": "string", "enum": ["up", "down"], "description": "Scroll direction"},
        },
        "required": ["action"],
    },
}
```

#### Token-Efficient Browser Context Per Turn

Each browser turn carries ONLY:

```
System: "You are controlling a web browser. Current state:" (~50 tok)
Page URL + title: (~20 tok)
Accessibility tree: (~200-400 tok)
Task goal + current step: (~100 tok)
Previous action result: (~50 tok)
─────────────────────────────
TOTAL: ~420-620 tokens per browser turn
```

No conversation history. No previous page states. Just current state + goal + last action.

---

## 2.2 Background Agent Worker

### File: [NEW] `app/services/agent_worker.py`

Processes agent tasks from Azure Queue Storage, running in Azure Functions.

```python
class AgentWorker:
    """
    Background worker for long-running agent tasks.
    Dequeues task IDs from Azure Queue, loads state from Supabase,
    executes steps, writes progress to DB after each step.
    """

    async def execute_task(self, task_id: str):
        """
        Main entry point. Called by Azure Function queue trigger.
        
        1. Load task from Supabase
        2. Verify state is EXECUTING
        3. Resume from current_step (handles container restart)
        4. Execute remaining steps
        5. Write progress to DB after EVERY step
        6. Handle time limits and token budgets
        7. Set final state (completed/failed)
        """
        supabase = get_supabase_admin()
        task_data = await self._load_task(supabase, task_id)
        task = AgentTask(**task_data)

        if task.state not in (TaskState.EXECUTING, TaskState.PAUSED_FOR_HITL):
            logger.warning(f"Task {task_id} in unexpected state: {task.state}")
            return

        manager = AgentTaskManager(task, get_openai_client(), await get_agent_mode_config())
        manager.start_time = task.started_at or datetime.utcnow()

        for step_idx in range(task.current_step, len(task.plan)):
            step = task.plan[step_idx]

            # Time check
            if not manager.check_time_budget():
                await self._complete_task(supabase, task, "Time limit reached. Partial results available.")
                return

            # HITL check
            if step.requires_approval and step.status != StepStatus.COMPLETED:
                task.state = TaskState.PAUSED_FOR_HITL
                await self._update_task(supabase, task)
                logger.info(f"Task {task_id} paused for HITL at step {step_idx}")
                return  # Will be re-triggered when user approves

            # Execute step
            try:
                result = await manager.execute_single_step(step)
                step.status = StepStatus.COMPLETED
                step.result_summary = result.summary
                step.artifacts = result.artifacts
                step.token_spend = result.token_spend
                task.current_step = step_idx + 1
                task.total_token_spend += result.token_spend
            except Exception as e:
                step.status = StepStatus.FAILED
                step.error = str(e)[:500]
                # Try reflexion (max 2 retries per step)
                if manager.reflexion.trials and len(manager.reflexion.trials) < 2:
                    manager.reflexion.record_trial(step.description, str(e))
                    # Retry will happen on next loop iteration
                    continue
                else:
                    task.state = TaskState.FAILED
                    task.error_message = f"Step {step_idx} failed: {str(e)[:200]}"
                    await self._update_task(supabase, task)
                    return

            # Persist progress after EVERY step
            await self._update_task(supabase, task)

        # All steps completed
        task.state = TaskState.COMPLETED
        task.completed_at = datetime.utcnow()
        await self._update_task(supabase, task)

    async def _update_task(self, supabase, task: AgentTask):
        """Writes current task state to Supabase."""
        await asyncio.to_thread(
            lambda: supabase.table("agent_tasks").update({
                "state": task.state.value,
                "current_step": task.current_step,
                "plan": [s.model_dump() for s in task.plan],
                "step_results": [s.model_dump() for s in task.plan if s.status == StepStatus.COMPLETED],
                "artifacts": task.artifacts,
                "total_token_spend": task.total_token_spend,
                "error_message": task.error_message,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }).eq("id", task.id).execute()
        )
```

### File: [MODIFY] `functions/function_app.py`

Add Azure Function queue trigger:

```python
@app.queue_trigger(
    arg_name="msg",
    queue_name="agent-tasks-queue",
    connection="AzureWebJobsStorage"
)
async def process_agent_task(msg: func.QueueMessage):
    """
    Queue-triggered function for background agent task execution.
    Receives task_id, loads from DB, executes, writes progress.
    """
    task_id = msg.get_body().decode("utf-8").strip()
    logger.info(f"Processing agent task: {task_id}")

    try:
        worker = AgentWorker()
        await worker.execute_task(task_id)
        logger.info(f"Agent task {task_id} completed")
    except Exception as e:
        logger.error(f"Agent task {task_id} failed: {e}")
        # Update task state to FAILED
        supabase = get_supabase()
        supabase.table("agent_tasks").update({
            "state": "failed",
            "error_message": str(e)[:500],
        }).eq("id", task_id).execute()
```

### File: [MODIFY] `app/services/queue_dispatcher.py`

```python
async def enqueue_agent_task(task_id: str) -> bool:
    """Dispatches an agent task to the background worker queue."""
    return await enqueue_job("agent-tasks-queue", task_id)
```

---

## 2.3 Durable State Upgrade

### File: [MODIFY] `app/services/durable_state.py`

Replace file-based checkpointing with Supabase-backed persistence.

```python
class DurableStateStore:
    """
    Upgraded from file-based to Supabase-backed state persistence.
    Enables cross-container task resumption after restarts.
    """

    @staticmethod
    async def save_checkpoint(task_id: str, step_index: int, state_data: Dict) -> bool:
        """Saves task checkpoint to Supabase agent_tasks table."""
        supabase = get_supabase_admin()
        try:
            await asyncio.to_thread(
                lambda: supabase.table("agent_tasks").update({
                    "current_step": step_index,
                    "step_results": state_data.get("step_results", []),
                    "total_token_spend": state_data.get("total_token_spend", 0),
                }).eq("id", task_id).execute()
            )
            return True
        except Exception as e:
            logger.error(f"Checkpoint save failed for task {task_id}: {e}")
            return False

    @staticmethod
    async def load_checkpoint(task_id: str) -> Optional[Dict]:
        """Loads latest task state from Supabase."""
        supabase = get_supabase_admin()
        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("agent_tasks")
                    .select("*")
                    .eq("id", task_id)
                    .single()
                    .execute()
            )
            return result.data if result else None
        except Exception as e:
            logger.error(f"Checkpoint load failed for task {task_id}: {e}")
            return None
```

---

## 2.4 Realtime Push Updates

### Frontend Integration: Supabase Realtime

Instead of keeping an SSE connection alive for 15 minutes, the frontend subscribes to the `agent_tasks` table via Supabase Realtime.

```typescript
// In Dashboard.tsx — when an agent task is created:
useEffect(() => {
  if (!agentTask?.id) return;

  const channel = supabase
    .channel(`agent-task-${agentTask.id}`)
    .on(
      "postgres_changes",
      {
        event: "UPDATE",
        schema: "public",
        table: "agent_tasks",
        filter: `id=eq.${agentTask.id}`,
      },
      (payload) => {
        const updated = payload.new;
        setAgentTask({
          ...agentTask,
          state: updated.state,
          current_step: updated.current_step,
          plan: updated.plan,
          artifacts: updated.artifacts,
          total_token_spend: updated.total_token_spend,
          error_message: updated.error_message,
        });
      }
    )
    .subscribe();

  return () => { supabase.removeChannel(channel); };
}, [agentTask?.id]);
```

This gives us:
- **Live progress**: frontend auto-updates as each step completes
- **Resilience**: page refresh reconnects and shows current state
- **No long SSE**: the HTTP request completes immediately after queuing the task

---

## 2.5 Extended Time Limits

### Config Changes

```python
# Phase 2 defaults (agent_config.py):
AGENT_MODE_MAX_DURATION = "900"   # 15 minutes (up from 5)
AGENT_MODE_STEP_TIMEOUT = "120"   # 2 minutes per step (up from 90s)
```

### Time Budget Warning Events

The worker writes time-warning metadata to the task record when approaching limits:

```python
# At 80% of time budget:
if elapsed >= max_duration * 0.8:
    task.plan[current_step].description += " [TIME WARNING: completing remaining steps quickly]"
    await self._update_task(supabase, task)
```

---

## 2.6 Requirements

### Backend Dependencies

```
# requirements.txt additions:
playwright>=1.40.0
```

### Playwright Setup

```bash
# Container/deployment setup:
pip install playwright
playwright install chromium --with-deps
```

### Azure Queue

```powershell
# Create the agent tasks queue:
az storage queue create --name agent-tasks-queue --account-name <storage-account>
```

---

## 2.7 File Change Summary

| Action | File | Description |
|---|---|---|
| **NEW** | `app/services/browser_agent.py` | Playwright browser control + a11y tree |
| **NEW** | `app/services/agent_worker.py` | Background worker for queue-triggered tasks |
| **MODIFY** | `functions/function_app.py` | Add `process_agent_task` queue trigger |
| **MODIFY** | `app/services/queue_dispatcher.py` | Add `enqueue_agent_task()` |
| **MODIFY** | `app/services/durable_state.py` | Supabase-backed checkpoints |
| **MODIFY** | `app/core/agent_config.py` | Extended time limits (15 min) |
| **MODIFY** | `frontend/src/pages/Dashboard.tsx` | Supabase Realtime subscription |
| **MODIFY** | `backend/requirements.txt` | Add `playwright` |
| **MODIFY** | `backend/Dockerfile` | Add `playwright install chromium` |

---

## 2.8 Verification Plan

### Automated Tests

```bash
python -m pytest tests/test_browser_agent.py -v
python -m pytest tests/test_agent_worker.py -v
python -m pytest tests/test_durable_state_supabase.py -v
```

### Manual Test Scenarios

1. **Browser navigation**: Agent mode goal "Go to weather.com and get today's forecast for Lagos" → verify browser navigates, extracts data, returns result
2. **Form filling**: "Fill out the contact form at example.com with name X, email Y" → verify browser fills and submits
3. **Background execution**: Submit a 10-step task → close browser tab → reopen → verify progress continues and UI shows current state via Realtime
4. **Container restart resilience**: Kill the container mid-task → restart → verify task resumes from last checkpoint
5. **15-minute task**: Submit a large research + report task → verify it runs for up to 15 minutes without timeout (with Phase 2 config)
6. **Token efficiency**: Browser interactions should use ~400-600 tokens per action (a11y tree), not ~5,000 (screenshots)
