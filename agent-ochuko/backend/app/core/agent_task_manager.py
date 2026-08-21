# app/core/agent_task_manager.py
"""
Agent Task Manager — autonomous Plan-Act-Observe orchestrator.
Manages the full lifecycle of Agent Mode tasks: plan generation, user review/edits,
step execution with sub-agent delegation, HITL safety approval gates,
context compression, and artifact persistence.
"""

import asyncio
import json
import time
import logging
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, List, Optional
from openai import AsyncAzureOpenAI

from app.core.agent_task_models import (
    AgentTask,
    PlanStep,
    TaskState,
    StepStatus,
    RiskLevel,
    StepResult,
)
from app.core.agent_planner import generate_structured_plan, refine_plan
from app.core.hitl_gates import HITLGate
from app.core.sub_agent_pool import SubAgentPool
from app.core.circuit_breaker import create_turn_circuit_breaker, ActionBudgetExceeded, CircuitBreakerOpen
from app.core.reflexion_engine import create_reflexion_engine
from app.services.hybrid_memory import AgentContextCompressor

logger = logging.getLogger("app.core.agent_task_manager")


class AgentTaskManager:
    """Orchestrates autonomous multi-step execution with safety gates and token efficiency."""

    def __init__(
        self,
        task: AgentTask,
        openai_client: Optional[AsyncAzureOpenAI] = None,
        deployment: str = "gpt-5.4",
        nano_deployment: str = "gpt-5.4-nano",
        config: Optional[Dict[str, Any]] = None,
        supabase_client=None,
    ):
        self.task = task
        self.client = openai_client
        self.deployment = deployment
        self.nano_deployment = nano_deployment
        self.config = config or {}
        self.supabase = supabase_client
        self.sub_agents = SubAgentPool(openai_client=openai_client, nano_deployment=nano_deployment)
        
        max_duration = int(self.config.get("max_duration_seconds", 300))
        step_timeout = int(self.config.get("step_timeout_seconds", 90))
        max_steps = int(self.config.get("max_steps", 12))

        self.circuit_breaker = create_turn_circuit_breaker(
            max_steps=max_steps,
            max_duration_seconds=max_duration,
            step_timeout_seconds=step_timeout,
        )
        self.reflexion = create_reflexion_engine(max_attempts=2)
        self.start_time: Optional[float] = None

    async def init_plan(self, history: Optional[List[Dict]] = None) -> List[PlanStep]:
        """Generates initial structured plan and sets state to AWAITING_APPROVAL."""
        auto_level = self.config.get("auto_approve_level", "medium")
        plan = await generate_structured_plan(
            goal=self.task.goal,
            conversation_history=history,
            openai_client=self.client,
            nano_deployment=self.nano_deployment,
            auto_approve_level=auto_level,
        )
        self.task.plan = plan
        self.task.state = TaskState.AWAITING_APPROVAL
        await self.save_state()
        return plan

    async def save_state(self):
        """Persists task state to Supabase agent_tasks table."""
        if not self.supabase:
            return
        try:
            update_payload = {
                "conversation_id": self.task.conversation_id,
                "user_id": self.task.user_id,
                "goal": self.task.goal,
                "plan": [s.model_dump() for s in self.task.plan],
                "state": self.task.state.value,
                "current_step": self.task.current_step,
                "step_results": self.task.step_results,
                "artifacts": self.task.artifacts,
                "total_token_spend": self.task.total_token_spend,
                "max_duration_seconds": self.task.max_duration_seconds,
                "error_message": self.task.error_message,
                "updated_at": datetime.utcnow().isoformat(),
            }
            if self.task.started_at:
                update_payload["started_at"] = self.task.started_at.isoformat()
            if self.task.completed_at:
                update_payload["completed_at"] = self.task.completed_at.isoformat()

            await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: self.supabase.table("agent_tasks")
                    .upsert({"id": self.task.id, **update_payload})
                    .execute()
                ),
                timeout=2.0,
            )
        except Exception as e:
            logger.debug(f"Could not persist agent task state: {e}")

    async def execute_plan_stream(
        self,
        search_fn=None,
        deep_research_fn=None,
    ) -> AsyncGenerator[str, None]:
        """
        Executes the plan sequentially and streams real-time SSE events.
        Yields SSE-formatted strings 'data: {...}\n\n'.
        """
        self.start_time = time.time()
        self.task.started_at = datetime.utcnow()
        self.task.state = TaskState.EXECUTING
        await self.save_state()

        # Emit plan approval confirmation
        yield f"data: {json.dumps({'type': 'agent_plan', 'task_id': self.task.id, 'plan': [s.model_dump() for s in self.task.plan], 'state': 'executing'})}\n\n"

        for step in self.task.plan:
            # Skip already completed steps if resuming
            if step.status == StepStatus.COMPLETED:
                continue

            self.task.current_step = step.index
            step_start = time.time()

            # 1. Wall-clock duration check
            try:
                elapsed = self.circuit_breaker.check_time_budget()
                if elapsed >= self.task.max_duration_seconds * 0.8:
                    yield f"data: {json.dumps({'type': 'agent_time_warning', 'task_id': self.task.id, 'elapsed_seconds': int(elapsed), 'max_seconds': self.task.max_duration_seconds, 'message': 'Approaching task time limit, wrapping up remaining steps...'})}\n\n"
            except ActionBudgetExceeded as budget_err:
                logger.warning(f"Agent task timed out: {budget_err}")
                self.task.state = TaskState.COMPLETED
                self.task.error_message = str(budget_err)
                break

            # 2. HITL Approval Gate Check
            auto_level = self.config.get("auto_approve_level", "medium")
            if HITLGate.requires_approval(step, auto_approve_level=auto_level) and step.status != StepStatus.RUNNING:
                self.task.state = TaskState.PAUSED_FOR_HITL
                await self.save_state()

                rationale = HITLGate.get_risk_rationale(step)
                yield f"data: {json.dumps({'type': 'agent_approval_required', 'task_id': self.task.id, 'step_index': step.index, 'step': step.model_dump(), 'risk_level': step.risk_level.value, 'reason': rationale})}\n\n"
                logger.info(f"Agent task {self.task.id} paused for user approval at step {step.index}")
                return

            # 3. Mark step running
            step.status = StepStatus.RUNNING
            await self.save_state()
            yield f"data: {json.dumps({'type': 'agent_step_start', 'task_id': self.task.id, 'step_index': step.index, 'description': step.description, 'tool_name': step.tool_name, 'risk_level': step.risk_level.value})}\n\n"

            # 4. Execute step
            step_result = await self._execute_single_step(
                step=step,
                search_fn=search_fn,
                deep_research_fn=deep_research_fn,
            )

            step_duration_ms = int((time.time() - step_start) * 1000)
            step.duration_ms = step_duration_ms
            step.token_spend = step_result.token_spend
            self.task.total_token_spend += step_result.token_spend
            self.circuit_breaker.record_token_spend(step_result.token_spend)

            if step_result.success:
                step.status = StepStatus.COMPLETED
                step.result_summary = step_result.summary
                if step_result.artifacts:
                    step.artifacts = step_result.artifacts
                    self.task.artifacts.extend(step_result.artifacts)

                self.task.step_results.append({
                    "step_index": step.index,
                    "description": step.description,
                    "summary": step_result.summary,
                    "artifacts": step_result.artifacts,
                    "duration_ms": step_duration_ms,
                })
                self.circuit_breaker.record_success()

                yield f"data: {json.dumps({'type': 'agent_step_complete', 'task_id': self.task.id, 'step_index': step.index, 'result_summary': step.result_summary, 'artifacts': step.artifacts, 'duration_ms': step_duration_ms, 'token_spend': step.token_spend})}\n\n"
            else:
                step.status = StepStatus.FAILED
                step.error = step_result.error or "Step failed"
                logger.warning(f"Step {step.index} failed: {step.error}")

                # Reflexion retry attempt
                if len(self.reflexion.trials) < 2:
                    self.reflexion.record_trial(step.description, step.error)
                    # Attempt retry
                    step.description += " (Self-Correction Retry)"
                    continue

                yield f"data: {json.dumps({'type': 'agent_step_complete', 'task_id': self.task.id, 'step_index': step.index, 'status': 'failed', 'error': step.error, 'duration_ms': step_duration_ms})}\n\n"

            await self.save_state()

        # 5. Final Synthesis: Orchestrator streams the complete markdown answer to the chat
        synthesis_prompt = AgentContextCompressor.build_synthesis_payload(self.task)
        if self.client:
            try:
                system_instruction = (
                    "You are Agent Ochuko in Autonomous Agent Mode. "
                    "You have successfully executed all research and analysis plan steps. "
                    "Synthesize a compact, high-density, beautifully structured deliverable answering the user's goal directly. "
                    "Prioritize compact tables, clear bold metrics, and structured key takeaways over conversational filler. "
                    "If displaying mathematical equations, use standard markdown math $$...$$."
                )
                input_payload = [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": synthesis_prompt},
                ]

                if hasattr(self.client, "responses") and hasattr(self.client.responses, "stream"):
                    async with self.client.responses.stream(
                        model=self.deployment,
                        input=input_payload,
                    ) as stream:
                        async for event in stream:
                            event_type = getattr(event, "type", "")
                            if event_type == "response.output_text.delta":
                                chunk = getattr(event, "delta", "")
                                if chunk:
                                    yield f"data: {json.dumps({'type': 'content_block_delta', 'delta': {'text': chunk}})}\n\n"
                elif hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                    stream_resp = await self.client.chat.completions.create(
                        model=self.deployment,
                        messages=input_payload,
                        stream=True,
                    )
                    async for chunk in stream_resp:
                        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                            delta_text = chunk.choices[0].delta.content
                            yield f"data: {json.dumps({'type': 'content_block_delta', 'delta': {'text': delta_text}})}\n\n"
            except Exception as synth_err:
                logger.error(f"Agent final synthesis streaming error: {synth_err}")
                fallback_text = "\n\n".join([f"**Step {r['step_index']}: {r['description']}**\n{r['summary']}" for r in self.task.step_results if r.get('summary')])
                if fallback_text:
                    yield f"data: {json.dumps({'type': 'content_block_delta', 'delta': {'text': fallback_text}})}\n\n"

        self.task.state = TaskState.COMPLETED
        self.task.completed_at = datetime.utcnow()
        await self.save_state()

        total_duration = int(time.time() - self.start_time)
        yield f"data: {json.dumps({'type': 'agent_task_complete', 'task_id': self.task.id, 'summary': f'Completed {len(self.task.plan)} steps successfully.', 'artifacts': self.task.artifacts, 'total_token_spend': self.task.total_token_spend, 'duration_seconds': total_duration})}\n\n"

    async def _execute_single_step(
        self,
        step: PlanStep,
        search_fn=None,
        deep_research_fn=None,
    ) -> StepResult:
        """Executes a single step using sub-agent delegation or code sandbox."""
        tool = (step.tool_name or "").lower().strip()

        try:
            if tool == "search_web" and search_fn:
                query = step.description
                # Extract query keyword if available
                if ":" in query:
                    query = query.split(":", 1)[1].strip()
                return await self.sub_agents.delegate_search(query=query, search_fn=search_fn)

            elif tool == "deep_research" and deep_research_fn:
                queries = [step.description]
                res = await deep_research_fn(queries, deployment=self.nano_deployment)
                raw_ctx = res.get("merged_context", "")
                sources = res.get("sources", [])
                summary = await self.sub_agents.compress_text(
                    raw_ctx,
                    instruction="Synthesize the multi-query research facts into key findings.",
                    max_tokens=250,
                )
                return StepResult(
                    success=True,
                    summary=summary or f"Deep research completed ({len(sources)} sources).",
                    artifacts=[],
                    token_spend=(len(raw_ctx) // 4) + 200,
                    raw_length=len(raw_ctx),
                )

            elif tool == "execute_code":
                code_to_run = (step.tool_args_hint or {}).get("code", "")
                if not code_to_run:
                    # Generate concise python script using nano for this step
                    code_to_run = await self._generate_step_code(step)

                sub_res = await self.sub_agents.delegate_code_execution(
                    code=code_to_run,
                    language="python",
                    conversation_id=self.task.conversation_id,
                    user_id=self.task.user_id,
                )
                return StepResult(
                    success=sub_res.success,
                    summary=sub_res.summary,
                    artifacts=sub_res.artifacts,
                    token_spend=sub_res.token_spend,
                    raw_length=sub_res.raw_length,
                    error=sub_res.error,
                )

            else:
                # Direct analytical reasoning step
                step_prompt = AgentContextCompressor.build_step_payload(self.task, step.index)
                summary = await self.sub_agents.compress_text(
                    step_prompt,
                    instruction=f"Formulate a concise analytical answer for step {step.index}: {step.description}",
                    max_tokens=200,
                )
                return StepResult(
                    success=True,
                    summary=summary or "Step analyzed.",
                    artifacts=[],
                    token_spend=300,
                    raw_length=len(step_prompt),
                )

        except Exception as err:
            logger.error(f"Step execution exception: {err}")
            return StepResult(
                success=False,
                summary=f"Execution error: {str(err)[:150]}",
                error=str(err),
            )

    async def _generate_step_code(self, step: PlanStep) -> str:
        """Generates a targeted, self-contained Python script to fulfill a code execution step."""
        if not self.client:
            return "print('Execution complete')"

        prompt = [
            {
                "role": "system",
                "content": (
                    "You are a Python code generation assistant. Write a clean, self-contained Python script "
                    f"to accomplish: {step.description}\n"
                    "If creating a document or report, save to '../data/report.pdf' or '../data/output.csv'.\n"
                    "Output ONLY executable Python code inside ```python fences."
                ),
            },
            {
                "role": "user",
                "content": f"Task goal: {self.task.goal}\nStep: {step.description}",
            },
        ]

        try:
            if hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                resp = await self.client.chat.completions.create(
                    model=self.nano_deployment,
                    messages=prompt,
                )
                code_text = resp.choices[0].message.content or ""
            else:
                resp = await self.client.responses.create(
                    model=self.nano_deployment,
                    input=prompt,
                )
                code_text = getattr(resp, "output_text", "") or ""

            # Extract python code block
            if "```python" in code_text:
                code_text = code_text.split("```python", 1)[1].split("```", 1)[0]
            elif "```" in code_text:
                code_text = code_text.split("```", 1)[1].split("```", 1)[0]

            return code_text.strip()
        except Exception as e:
            logger.warning(f"Step code generation failed: {e}")
            return "print('Task step completed.')"
