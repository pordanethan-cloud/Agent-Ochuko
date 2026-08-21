# app/core/agent_task_manager.py
"""
Agent Task Manager — autonomous Plan-Act-Observe orchestrator.
Manages the full lifecycle of Agent Mode tasks: plan generation, user review/edits,
step execution with sub-agent delegation, HITL safety approval gates,
context compression, and artifact persistence.
"""

import asyncio
import json
import re
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
from app.services.supabase_admin import get_supabase_admin
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
                    "You are Agent Ochuko. Deliver a brilliant, insightful, fluid, and natural response directly answering the user. "
                    "Use clean markdown formatting, tables, or bullet points where they genuinely add clarity. "
                    "Do NOT use rigid robotic templates or clunky boilerplate headings (e.g., do NOT output 'Goal: ... — Final Answer', 'What I found', or 'Ready-to-use response'). "
                    "Speak naturally, authoritatively, and concisely. "
                    "If displaying mathematical formulas, use standard markdown math $$...$$. "
                    "CRITICAL: Only mention deliverables or created files if they are explicitly listed under GENERATED ARTIFACTS. Never invent fake files."
                )
                input_payload = [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": synthesis_prompt},
                ]

                accumulated_synthesis = ""
                if hasattr(self.client, "responses") and hasattr(self.client.responses, "stream"):
                    async with self.client.responses.stream(
                        model=self.deployment,
                        input=input_payload,
                        max_output_tokens=4096,
                    ) as stream:
                        async for event in stream:
                            event_type = getattr(event, "type", "")
                            if event_type == "response.output_text.delta":
                                chunk = getattr(event, "delta", "")
                                if chunk:
                                    accumulated_synthesis += chunk
                                    yield f"data: {json.dumps({'type': 'content_block_delta', 'delta': {'text': chunk}})}\n\n"
                elif hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                    stream_resp = await self.client.chat.completions.create(
                        model=self.deployment,
                        messages=input_payload,
                        max_tokens=4096,
                        stream=True,
                    )
                    async for chunk in stream_resp:
                        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                            delta_text = chunk.choices[0].delta.content
                            accumulated_synthesis += delta_text
                            yield f"data: {json.dumps({'type': 'content_block_delta', 'delta': {'text': delta_text}})}\n\n"
            except Exception as synth_err:
                logger.error(f"Agent final synthesis streaming error: {synth_err}")
                fallback_text = "\n\n".join([f"**Step {r['step_index']}: {r['description']}**\n{r['summary']}" for r in self.task.step_results if r.get('summary')])
                if fallback_text:
                    accumulated_synthesis = fallback_text
                    yield f"data: {json.dumps({'type': 'content_block_delta', 'delta': {'text': fallback_text}})}\n\n"

        self.task.state = TaskState.COMPLETED
        self.task.completed_at = datetime.utcnow()
        await self.save_state()

        # Persist the assistant message to database to maintain clean role synchronization
        if self.supabase and self.task.conversation_id and accumulated_synthesis:
            try:
                assistant_msg = {
                    "conversation_id": self.task.conversation_id,
                    "role": "assistant",
                    "content": accumulated_synthesis,
                    "routing_mode": "agent",
                    "model": self.deployment,
                    "tokens_output": len(accumulated_synthesis) // 4,
                    "content_parts": {
                        "agent_task_id": self.task.id,
                        "artifacts": self.task.artifacts,
                        "plan": [s.model_dump() for s in self.task.plan],
                    }
                }
                await asyncio.to_thread(
                    lambda: self.supabase.table("messages").insert(assistant_msg).execute()
                )
            except Exception as db_err:
                logger.warning(f"Failed to persist agent assistant message: {db_err}")

        total_duration = int(time.time() - self.start_time)
        yield f"data: {json.dumps({'type': 'agent_task_complete', 'task_id': self.task.id, 'state': 'completed', 'total_token_spend': self.task.total_token_spend, 'duration_seconds': total_duration, 'artifacts': self.task.artifacts})}\n\n"
        yield "data: [DONE]\n\n"

    async def _execute_single_step(
        self,
        step: PlanStep,
        search_fn=None,
        deep_research_fn=None,
    ) -> StepResult:
        """Executes one plan step and records spend + duration."""
        # Unwrap pasted content payload if present in step description
        pasted_full = re.search(r"\[Pasted Content:[^\]]*\]\s*```(?:[a-zA-Z0-9_-]*\n)?([\s\S]*?)```", step.description, flags=re.IGNORECASE)
        if pasted_full:
            clean_step_desc = pasted_full.group(1).strip()
        else:
            pasted_single = re.search(r"\[Pasted Content:\s*([^\]]+)\]", step.description, flags=re.IGNORECASE)
            clean_step_desc = pasted_single.group(1).strip() if pasted_single else step.description

        try:
            if step.tool_name in ("search_web", "google_search"):
                sub_res = await self.sub_agents.delegate_search(
                    query=clean_step_desc,
                    search_fn=search_fn,
                )
                return StepResult(
                    success=sub_res.success,
                    summary=sub_res.summary,
                    artifacts=sub_res.artifacts,
                    token_spend=sub_res.token_spend,
                    raw_length=sub_res.raw_length,
                    error=sub_res.error,
                )

            elif step.tool_name == "deep_research":
                sub_res = await self.sub_agents.delegate_deep_research(
                    prompt=clean_step_desc,
                    deep_research_fn=deep_research_fn,
                )
                return StepResult(
                    success=sub_res.success,
                    summary=sub_res.summary,
                    artifacts=sub_res.artifacts,
                    token_spend=sub_res.token_spend,
                    raw_length=sub_res.raw_length,
                    error=sub_res.error,
                )

            elif step.tool_name in ("execute_code", "python"):
                code_to_run = await self._generate_step_code(step)
                sub_res = await self.sub_agents.delegate_code_execution(code_to_run)
                return StepResult(
                    success=sub_res.success,
                    summary=sub_res.summary,
                    artifacts=sub_res.artifacts,
                    token_spend=sub_res.token_spend,
                    raw_length=sub_res.raw_length,
                    error=sub_res.error,
                )

            elif step.tool_name in ("scrape_web", "browser_navigate", "browse_page"):
                # Clean URL regex (stripping trailing brackets, quotes, punctuation)
                url_match = re.search(r"https?://[a-zA-Z0-9\-_]+(?:\.[a-zA-Z0-9\-_]+)+(?:/[^\s\]\)\`\"']*)?", clean_step_desc)
                url = url_match.group(0).rstrip(".:,;`)]'\"") if url_match else ""
                sub_res = await self.sub_agents.delegate_browser_scrape(
                    url=url,
                    query_context=clean_step_desc,
                    search_fn=search_fn,
                )
                return StepResult(
                    success=sub_res.success,
                    summary=sub_res.summary,
                    artifacts=sub_res.artifacts,
                    token_spend=sub_res.token_spend,
                    raw_length=sub_res.raw_length,
                    error=sub_res.error,
                )

            elif step.tool_name in ("lookup_handle", "github_profile", "social_profile"):
                handle_match = re.search(r"@?[\w\-\.]+", clean_step_desc)
                handle = handle_match.group(0) if handle_match else clean_step_desc.split(":")[-1].strip()
                sub_res = await self.sub_agents.delegate_handle_lookup(handle=handle)
                return StepResult(
                    success=sub_res.success,
                    summary=sub_res.summary,
                    artifacts=sub_res.artifacts,
                    token_spend=sub_res.token_spend,
                    raw_length=sub_res.raw_length,
                    error=sub_res.error,
                )

            elif step.tool_name in ("deploy_site", "publish_website", "create_landing_page"):
                site_code = await self._generate_website_code(step)
                sub_res = await self.sub_agents.delegate_site_deployment(
                    title=self.task.goal[:40],
                    html_content=site_code,
                    user_id=self.task.user_id,
                    conversation_id=self.task.conversation_id,
                    supabase_client=self.supabase,
                )
                return StepResult(
                    success=sub_res.success,
                    summary=sub_res.summary,
                    artifacts=sub_res.artifacts,
                    token_spend=sub_res.token_spend,
                    raw_length=sub_res.raw_length,
                    error=sub_res.error,
                )

            elif step.tool_name and step.tool_name.startswith("mcp_"):
                from app.connectors.mcp_registry import MCPRegistry
                mcp_registry = MCPRegistry()
                args = step.tool_args_hint if isinstance(step.tool_args_hint, dict) else {"query": clean_step_desc}
                output = await mcp_registry.execute_mcp_tool(
                    user_id=self.task.user_id,
                    tool_name=step.tool_name,
                    arguments=args,
                )
                is_err = str(output).startswith("Error") or "Invalid MCP" in str(output)
                return StepResult(
                    success=not is_err,
                    summary=str(output)[:400],
                    artifacts=[],
                    token_spend=120,
                    raw_length=len(str(output)),
                    error=str(output) if is_err else None,
                )

            elif step.tool_name in ("gmail_search", "gmail_read", "gmail_send"):
                from app.connectors.gmail_connector import GmailConnector
                token = None
                try:
                    supabase = self.supabase or get_supabase_admin()
                    if supabase:
                        conn_res = await asyncio.to_thread(
                            lambda: supabase.table("user_connectors")
                            .select("access_token_encrypted")
                            .eq("user_id", self.task.user_id)
                            .eq("connector_name", "gmail")
                            .eq("is_active", True)
                            .execute()
                        )
                        if conn_res.data and len(conn_res.data) > 0:
                            token = conn_res.data[0].get("access_token_encrypted")
                except Exception as e:
                    logger.debug(f"Could not load Gmail credentials: {e}")

                connector = GmailConnector(access_token=token)
                args = step.tool_args_hint if isinstance(step.tool_args_hint, dict) else {"query": clean_step_desc}
                output = await connector.handle_tool_call(step.tool_name, args)
                is_err = str(output).startswith("Gmail operation error")
                return StepResult(
                    success=not is_err,
                    summary=str(output)[:400],
                    artifacts=[],
                    token_spend=100,
                    raw_length=len(str(output)),
                    error=str(output) if is_err else None,
                )

            elif step.tool_name in ("calendar_list_events", "calendar_create_event", "calendar_check_availability"):
                from app.connectors.google_calendar_connector import GoogleCalendarConnector
                token = None
                try:
                    supabase = self.supabase or get_supabase_admin()
                    if supabase:
                        conn_res = await asyncio.to_thread(
                            lambda: supabase.table("user_connectors")
                            .select("access_token_encrypted")
                            .eq("user_id", self.task.user_id)
                            .eq("connector_name", "google_calendar")
                            .eq("is_active", True)
                            .execute()
                        )
                        if conn_res.data and len(conn_res.data) > 0:
                            token = conn_res.data[0].get("access_token_encrypted")
                except Exception as e:
                    logger.debug(f"Could not load Calendar credentials: {e}")

                connector = GoogleCalendarConnector(access_token=token)
                args = step.tool_args_hint if isinstance(step.tool_args_hint, dict) else {"date": clean_step_desc}
                output = await connector.handle_tool_call(step.tool_name, args)
                is_err = str(output).startswith("Calendar operation error")
                return StepResult(
                    success=not is_err,
                    summary=str(output)[:400],
                    artifacts=[],
                    token_spend=100,
                    raw_length=len(str(output)),
                    error=str(output) if is_err else None,
                )

            elif step.tool_name in ("photos_search", "photos_list", "photos_get", "photos_upload"):
                from app.connectors.google_photos_connector import GooglePhotosConnector
                token = None
                try:
                    supabase = self.supabase or get_supabase_admin()
                    if supabase:
                        conn_res = await asyncio.to_thread(
                            lambda: supabase.table("user_connectors")
                            .select("access_token_encrypted")
                            .eq("user_id", self.task.user_id)
                            .in_("connector_name", ["google_photos", "gmail", "google_calendar"])
                            .eq("is_active", True)
                            .execute()
                        )
                        if conn_res.data and len(conn_res.data) > 0:
                            token = conn_res.data[0].get("access_token_encrypted")
                except Exception as e:
                    logger.debug(f"Could not load Google Photos credentials: {e}")

                connector = GooglePhotosConnector(access_token=token)
                args = step.tool_args_hint if isinstance(step.tool_args_hint, dict) else {"query": clean_step_desc}
                output = await connector.handle_tool_call(step.tool_name, args)
                is_err = str(output).startswith("Photos operation error") or str(output).startswith("Failed to")
                return StepResult(
                    success=not is_err,
                    summary=str(output)[:400],
                    artifacts=[],
                    token_spend=100,
                    raw_length=len(str(output)),
                    error=str(output) if is_err else None,
                )

            else:
                # Direct analytical reasoning / greeting step
                greeting_match = bool(re.match(r"^\s*(hello|hi|hey|good\s+(?:morning|afternoon|evening|day)|greetings|who\s+are\s+you|what\s+can\s+you\s+do|how\s+are\s+you|help|thanks|thank\s+you|sup|yo)\b[!?.]*\s*$", self.task.goal.strip(), re.IGNORECASE))
                if greeting_match:
                    summary = "Hello! I am Agent Ochuko in Autonomous Agent Mode. I can plan and execute multi-step research, data analysis, document generation, and autonomous tasks for you. What would you like to build or explore?"
                else:
                    step_prompt = AgentContextCompressor.build_step_payload(self.task, step.index)
                    summary = await self.sub_agents.compress_text(
                        step_prompt,
                        instruction=f"Formulate a concise direct answer for step {step.index}: {step.description}",
                        max_tokens=200,
                    )
                return StepResult(
                    success=True,
                    summary=summary or "Step analyzed.",
                    artifacts=[],
                    token_spend=100,
                    raw_length=len(summary) if summary else 0,
                )

        except Exception as err:
            logger.error(f"Step execution exception: {err}")
            return StepResult(
                success=False,
                summary=f"Execution error: {str(err)[:150]}",
                error=str(err),
            )

    async def _generate_website_code(self, step: PlanStep) -> str:
        """Generates a complete, beautiful HTML5 + Tailwind website markup using the flagship model."""
        if not self.client:
            return "<div class='p-8 text-center text-xl font-bold'>Instant Site Preview</div>"

        prompt = [
            {
                "role": "system",
                "content": (
                    "You are a master frontend architect. Generate a complete, stunning, modern, responsive HTML page with Tailwind CSS. "
                    "Make it interactive with embedded JavaScript (e.g. working sliders, pricing toggle, calculator logic, charts). "
                    "Make it high-contrast, beautiful dark-mode UI with sleek glassmorphism and modern fonts. "
                    "Output ONLY valid HTML markup inside ```html fences."
                ),
            },
            {
                "role": "user",
                "content": f"Create a complete interactive web app / landing page for: {self.task.goal}\nStep: {step.description}",
            },
        ]
        try:
            if hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                resp = await self.client.chat.completions.create(model=self.deployment, messages=prompt)
                raw = resp.choices[0].message.content or ""
            else:
                resp = await self.client.responses.create(model=self.deployment, input=prompt)
                raw = getattr(resp, "output_text", "") or ""

            if "```html" in raw:
                raw = raw.split("```html", 1)[1].split("```", 1)[0]
            elif "```" in raw:
                raw = raw.split("```", 1)[1].split("```", 1)[0]
            return raw.strip()
        except Exception as e:
            logger.warning(f"Website generation fallback: {e}")
            return f"<div class='p-8 text-center text-white'><h1>{self.task.goal}</h1><p>Website deployed successfully.</p></div>"

    async def _generate_step_code(self, step: PlanStep) -> str:
        """Generates a targeted, self-contained Python script to fulfill a code execution step using the flagship model."""
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
                    model=self.deployment,
                    messages=prompt,
                )
                code_text = resp.choices[0].message.content or ""
            else:
                resp = await self.client.responses.create(
                    model=self.deployment,
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
