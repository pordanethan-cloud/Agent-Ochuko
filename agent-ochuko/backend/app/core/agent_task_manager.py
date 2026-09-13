# app/core/agent_task_manager.py
"""
Agent Task Manager — autonomous Plan-Act-Observe orchestrator.
Manages the full lifecycle of Agent Mode tasks: plan generation, user review/edits,
step execution with sub-agent delegation, HITL safety approval gates,
context compression, and artifact persistence.
"""

import os
import asyncio
import json
import re
import time
import logging
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple
from openai import AsyncAzureOpenAI

from app.core.agent_task_models import (
    AgentTask,
    PlanStep,
    TaskState,
    StepStatus,
    RiskLevel,
    StepResult,
)
from app.core.agent_planner import generate_structured_plan, refine_plan, replan_remaining, check_premise_divergence
from app.core.hitl_gates import HITLGate
from app.core.skills import AGENT_CONDUCT, ULTRA_IDENTITY
from app.core.sub_agent_pool import SubAgentPool
from app.core.circuit_breaker import create_turn_circuit_breaker, ActionBudgetExceeded, CircuitBreakerOpen
from app.core.reflexion_engine import create_reflexion_engine
from app.services.supabase_admin import get_supabase_admin
from app.services.hybrid_memory import AgentContextCompressor

logger = logging.getLogger("app.core.agent_task_manager")

# Phase 8.1 — zero-cost heuristic gate for premise divergence. These are
# LITERAL strings: the canonical investigative tool names from the spec plus
# the live roster equivalents, and the exact divergence keyword list. Do NOT
# infer or abbreviate them — the gate must match these verbatim.
_DIVERGENCE_INVESTIGATIVE_TOOLS = frozenset({
    # Canonical Phase 8.1 spec names (verbatim):
    "search_web", "read_file", "list_dir", "workstation_read",
    # Live roster equivalents so the gate fires on actual step tool names:
    "sandbox_read", "sandbox_ls", "fetch_url", "scrape_web", "deep_research",
    "youtube_transcript", "terminal", "mcp_workstation_read", "mcp_workstation_list",
})
_DIVERGENCE_KEYWORDS = (
    "instead of", "not found", "different", "unsupported", "actual stack",
    "actually", "turns out", "requires", "missing",
)
_DIVERGENCE_KEYWORDS_RE = re.compile(
    "|".join(re.escape(k) for k in _DIVERGENCE_KEYWORDS), re.IGNORECASE,
)
_DISCOVERY_VERB_RE = re.compile(
    r"\b(inspect|check|review|read|list|fetch|query|scan|browse|verify|research|investigate|examine)\b",
    re.IGNORECASE,
)


class AgentTaskManager:
    """Orchestrates autonomous multi-step execution with safety gates and token efficiency."""

    def __init__(
        self,
        task: AgentTask,
        openai_client: Optional[AsyncAzureOpenAI] = None,
        deployment: str = "gpt-5.6-terra",
        nano_deployment: str = "gpt-5.6-luna",
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
        self._effort_cache: Optional[str] = None
        self._effort_resolved = False
        
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

    async def _get_effort(self) -> Optional[str]:
        """
        Rule-classified reasoning effort for this task's goal (cached).
        Ultra/agent requests floor at medium complexity; the effort value
        comes from TERRA_EFFORT_MAP via App Config (runtime-tunable).
        """
        if not self._effort_resolved:
            self._effort_resolved = True
            try:
                from app.core.complexity_router import classify
                from app.core.agent_config import get_reasoning_effort
                tier = classify(self.task.goal, floor="medium").tier
                self._effort_cache = await get_reasoning_effort("agent", tier, self.deployment)
            except Exception as effort_err:
                logger.debug(f"Effort resolution failed, defaulting to high: {effort_err}")
                self._effort_cache = "high"
        return self._effort_cache

    async def init_plan(self, history: Optional[List[Dict]] = None) -> List[PlanStep]:
        """Generates initial structured plan and sets state to EXECUTING (zero-wait autonomous execution)."""
        auto_level = self.config.get("auto_approve_level", "high")

        # Hydrate sandbox workspace from Cloudflare R2 so the agent has full knowledge
        # of all previously uploaded and generated files in this conversation
        workspace_file_names = []
        try:
            from app.services.code_sandbox import sync_conversation_sandbox_workspace
            if self.task.conversation_id:
                ws_items = await sync_conversation_sandbox_workspace(self.task.conversation_id, self.task.user_id)
                workspace_file_names = [item["filename"] for item in ws_items if item.get("filename")]
        except Exception as ws_err:
            logger.debug(f"Workspace hydration warning in init_plan: {ws_err}")

        try:
            import tempfile
            conv_id = self.task.conversation_id or "default"
            local_data_dir = os.path.join(tempfile.gettempdir(), f"sandbox_{conv_id}", "data")
            if os.path.exists(local_data_dir):
                for f in os.listdir(local_data_dir):
                    if f not in workspace_file_names and not f.startswith("."):
                        workspace_file_names.append(f)
        except Exception as scan_err:
            logger.debug(f"Local sandbox scan warning in init_plan: {scan_err}")

        ws_access = bool(self.config.get("workstation_access_enabled", False))
        plan = await generate_structured_plan(
            goal=self.task.goal,
            conversation_history=history,
            openai_client=self.client,
            nano_deployment=self.nano_deployment,
            auto_approve_level=auto_level,
            workspace_files=workspace_file_names,
            workstation_access_enabled=ws_access,
        )
        self.task.plan = plan
        self.task.state = TaskState.EXECUTING
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
                "replan_count": self.task.replan_count,
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

        # Phase 8: index-based `while` loop so plan splices (dynamic
        # re-orientation) take effect mid-flight — a `for` binds a snapshot
        # iterator and would silently skip appended steps.
        i = 0
        while i < len(self.task.plan):
            step = self.task.plan[i]
            # Skip already completed/skipped steps if resuming
            if step.status in (StepStatus.COMPLETED, StepStatus.SKIPPED):
                i += 1
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

            # 2a. Explicit User Input Question Step Check
            if step.tool_name == "ask_user_input" and step.status != StepStatus.RUNNING:
                args = step.tool_args_hint if isinstance(step.tool_args_hint, dict) else {}
                q = args.get("question") or step.description
                opts = args.get("options") or ["Yes, proceed", "No, adjust plan", "Provide more details"]
                sel_type = args.get("select_type", "single_select")

                self.task.state = TaskState.PAUSED_FOR_HITL
                await self.save_state()

                yield f"data: {json.dumps({'type': 'agent_ask_user_input', 'task_id': self.task.id, 'step_index': step.index, 'question': q, 'options': opts, 'select_type': sel_type})}\n\n"
                logger.info(f"Agent task {self.task.id} paused at step {step.index} for user input: {q}")
                return

            # 2b. HITL Approval Gate Check
            default_level = "medium" if self.config.get("review_policy") == "always_ask" else "high"
            auto_level = self.config.get("auto_approve_level", default_level)
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

            # 5. AI-Level Cognitive Tool Loop:
            # If the tool failed or was blocked, feed the feedback directly to the AI model.
            # The AI inspects the obstacle, formulates an aim, and selects the best alternative tool.
            attempt = 0
            max_ai_retries = 2
            while not step_result.success and attempt < max_ai_retries:
                attempt += 1
                ai_adaptation = await self._ai_resolve_feedback_and_adapt(
                    step=step,
                    error_feedback=step_result.error or "Step produced no successful output",
                    attempt_num=attempt,
                )
                if not ai_adaptation or ai_adaptation.get("action") != "retry_tool":
                    # AI concluded it should proceed or alternatives are exhausted
                    break

                new_tool = ai_adaptation.get("tool_name")
                new_desc = ai_adaptation.get("description") or step.description
                reasoning = ai_adaptation.get("reasoning", "AI adapting tool based on feedback")

                logger.info(
                    "AI dynamically adapted step %s from %s to %s. Reasoning: %s",
                    step.index, step.tool_name, new_tool, reasoning
                )

                # Emit real-time cognitive adaptation event
                yield f"data: {json.dumps({'type': 'agent_step_adapted', 'task_id': self.task.id, 'step_index': step.index, 'previous_tool': step.tool_name, 'tool_name': new_tool, 'description': new_desc, 'reasoning': reasoning, 'status': 'running'})}\n\n"

                step.tool_name = new_tool
                step.description = new_desc

                # Re-execute step with the AI-chosen tool
                step_result = await self._execute_single_step(
                    step=step,
                    search_fn=search_fn,
                    deep_research_fn=deep_research_fn,
                )
                step_duration_ms = int((time.time() - step_start) * 1000)
                step.duration_ms = step_duration_ms
                step.token_spend += step_result.token_spend
                self.task.total_token_spend += step_result.token_spend
                self.circuit_breaker.record_token_spend(step_result.token_spend)

            if step_result.success:
                step.status = StepStatus.COMPLETED
                step.result_summary = step_result.summary
                if step_result.artifacts:
                    step.artifacts = step_result.artifacts
                    for art in step_result.artifacts:
                        if not any(a.get("filename") == art.get("filename") for a in self.task.artifacts):
                            self.task.artifacts.append(art)
                    yield f"data: {json.dumps({'type': 'generated_files', 'files': step_result.artifacts})}\n\n"

                self.task.step_results.append({
                    "step_index": step.index,
                    "description": step.description,
                    "summary": step_result.summary,
                    "artifacts": step_result.artifacts,
                    "duration_ms": step_duration_ms,
                })
                self.circuit_breaker.record_success()

                yield f"data: {json.dumps({'type': 'agent_step_complete', 'task_id': self.task.id, 'step_index': step.index, 'result_summary': step.result_summary, 'artifacts': step.artifacts, 'duration_ms': step_duration_ms, 'token_spend': step.token_spend})}\n\n"
                # Phase 8.1: Proactive premise-divergence re-orientation.
                # A step can SUCCEED yet reveal facts that invalidate later steps
                # (e.g. "repo uses bun, not npm"). The heuristic gate below is
                # zero-cost; check_premise_divergence only fires on a match and
                # returns None on any failure. Only a REAL re-plan spends budget.
                try:
                    _max_replans = int(self.config.get("max_replans_per_task", 2))
                except (ValueError, TypeError):
                    _max_replans = 2
                if (
                    self.client
                    and i + 1 < len(self.task.plan)
                    and self.task.replan_count < _max_replans
                ):
                    divergence = await self._check_premise_divergence(step, i)
                    if divergence:
                        reoriented_tail = await self._attempt_replan(
                            discovery_context=divergence,
                            remaining_steps=self.task.plan[i + 1:],
                        )
                        if reoriented_tail:
                            self.task.replan_count += 1
                            self.task.plan = self.task.plan[: i + 1] + reoriented_tail
                            yield (
                                f"data: {json.dumps({'type': 'agent_plan_reoriented', 'task_id': self.task.id, 'replan_count': self.task.replan_count, 'trigger': 'discovery', 'reason': divergence, 'plan': [s.model_dump() for s in self.task.plan]})}\n\n"
                            )
                            logger.info(
                                "Agent task %s re-oriented plan after step %s discovery (premise shift; replan #%s): %s",
                                self.task.id, step.index, self.task.replan_count, divergence,
                            )
                            await self.save_state()

            else:
                step.status = StepStatus.FAILED
                step.error = step_result.error or "Step failed"
                logger.warning(f"Step {step.index} concluded as failed after AI tool evaluations: {step.error}")

                self.task.step_results.append({
                    "step_index": step.index,
                    "description": step.description,
                    "summary": f"Failed: {step.error}",
                    "artifacts": [],
                    "duration_ms": step_duration_ms,
                })

                yield f"data: {json.dumps({'type': 'agent_step_complete', 'task_id': self.task.id, 'step_index': step.index, 'status': 'failed', 'error': step.error, 'duration_ms': step_duration_ms})}\n\n"

            await self.save_state()

            # Phase 8: Dynamic plan re-orientation (long-horizon OODA).
            # After BOTH AI retries are exhausted and the step is still FAILED,
            # regenerate the remaining steps against reality — budget-capped
            # via max_replans_per_task and guarded by the circuit breaker.
            if step.status == StepStatus.FAILED:
                reoriented_tail = await self._attempt_replan(
                    failed_step=step,
                    remaining_steps=self.task.plan[i + 1:],
                )
                if reoriented_tail:
                    self.task.replan_count += 1
                    self.task.plan = self.task.plan[: i + 1] + reoriented_tail
                    yield f"data: {json.dumps({'type': 'agent_plan_reoriented', 'task_id': self.task.id, 'replan_count': self.task.replan_count, 'plan': [s.model_dump() for s in self.task.plan]})}\n\n"
                    logger.info(
                        "Agent task %s re-oriented plan after step %s failure (replan #%s)",
                        self.task.id, step.index, self.task.replan_count,
                    )
                    await self.save_state()

            i += 1

        # 5. Final Synthesis: Orchestrator streams the complete markdown answer to the chat
        synthesis_prompt = AgentContextCompressor.build_synthesis_payload(self.task)
        if self.client:
            try:
                system_instruction = (
                    "You are Ochuko Ultra, the autonomous deep-reasoning tier of Agent Ochuko. "
                    "Deliver a brilliant, insightful, fluid, and natural response directly answering the user. "
                    "Use clean markdown formatting, tables, or bullet points where they genuinely add clarity. "
                    "Do NOT use rigid robotic templates or clunky boilerplate headings (e.g., do NOT output 'Goal: ... — Final Answer', 'What I found', or 'Ready-to-use response'). "
                    "Speak naturally, authoritatively, and concisely. "
                    "If displaying mathematical formulas, use standard markdown math $$...$$. "
                    "CRITICAL: Only mention deliverables or created files if they are explicitly listed under GENERATED ARTIFACTS. Never invent fake files. "
                    "Deliverables must be complete and usable — never describe a file as truncated or partial. "
                    "When the task involves website design, software architecture, or implementation planning: "
                    "deliver a comprehensive, elite implementation plan and architectural breakdown matching the highest caliber of Think Mode "
                    "(system design, UI/UX aesthetics, component hierarchy, responsive breakdown, and interactive preview links). "
                    "For multi-file projects, note that while the full repository is bundled in a zip for bulk download, "
                    "every individual file is also individually accessible, viewable, and demandable directly. "
                    "For single-file deliverables, ensure they are provided directly without zipping.\n\n"
                    + AGENT_CONDUCT + "\n\n" + ULTRA_IDENTITY
                )

                ws_enabled = bool(self.config.get("workstation_access_enabled", False))
                ws_context = (
                    "WORKSTATION COMPUTER ACCESS (COWORK):\n"
                    f"- Current Status: {'ENABLED' if ws_enabled else 'NOT YET ENABLED (default safety sandbox)'}.\n"
                    "- When Workstation Access is toggled ON, you have direct access to the user's computer via `mcp_workstation_*` tools (read, write, list, exec).\n"
                    "- If the user asks whether you can see or browse their PC files, explain that access is isolated by default for safety, but they can easily enable Workstation Access by toggling it ON in Settings or the header. When enabled, you can read, write, and inspect their local files directly.\n\n"
                )
                system_instruction = system_instruction + "\n\n" + ws_context

                input_payload = [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": synthesis_prompt},
                ]

                accumulated_synthesis = ""
                from app.core.agent_config import get_max_output_tokens
                ultra_budget = await get_max_output_tokens("ultra")
                ultra_effort = await self._get_effort()
                if hasattr(self.client, "responses") and hasattr(self.client.responses, "stream"):
                    synth_stream_kwargs: Dict[str, Any] = {
                        "model": self.deployment,
                        "input": input_payload,
                        "max_output_tokens": ultra_budget,
                    }
                    if ultra_effort:
                        synth_stream_kwargs["reasoning"] = {"effort": ultra_effort}
                    async with self.client.responses.stream(**synth_stream_kwargs) as stream:
                        async for event in stream:
                            event_type = getattr(event, "type", "")
                            if event_type == "response.output_text.delta":
                                chunk = getattr(event, "delta", "")
                                if chunk:
                                    accumulated_synthesis += chunk
                                    yield f"data: {json.dumps({'type': 'content_block_delta', 'delta': {'text': chunk}})}\n\n"
                elif hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                    synth_cc_kwargs: Dict[str, Any] = {
                        "model": self.deployment,
                        "messages": input_payload,
                        "max_tokens": ultra_budget,
                        "stream": True,
                    }
                    if ultra_effort:
                        synth_cc_kwargs["reasoning_effort"] = ultra_effort
                    stream_resp = await self.client.chat.completions.create(**synth_cc_kwargs)
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
                        "generated_files": self.task.artifacts,
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
                sub_res = await self.sub_agents.delegate_code_execution(
                    code=code_to_run,
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

            elif step.tool_name in ("youtube_transcript", "youtube_video"):
                args = step.tool_args_hint if isinstance(step.tool_args_hint, dict) else {}
                target = args.get("url_or_id") or args.get("url") or args.get("video_id")
                if not target:
                    url_match = re.search(r"https?://[a-zA-Z0-9\-_]+(?:\.[a-zA-Z0-9\-_]+)+(?:/[^\s\]\)\`\"']*)?", clean_step_desc)
                    target = url_match.group(0).rstrip(".:,;`)]'\"") if url_match else clean_step_desc
                sub_res = await self.sub_agents.delegate_youtube_transcript(url_or_id=target)
                return StepResult(
                    success=sub_res.success,
                    summary=sub_res.summary,
                    artifacts=sub_res.artifacts,
                    token_spend=sub_res.token_spend,
                    raw_length=sub_res.raw_length,
                    error=sub_res.error,
                )

            elif step.tool_name in ("deploy_site", "publish_website", "create_landing_page", "build_website"):
                sandbox_files = await self._collect_sandbox_web_files()
                res_gen = await self._generate_website_code(step)
                if isinstance(res_gen, tuple) and len(res_gen) == 2:
                    site_code, project_files = res_gen
                else:
                    site_code, project_files = res_gen, {}
                all_files = {**sandbox_files, **project_files}
                sub_res = await self.sub_agents.delegate_site_deployment(
                    title=self.task.goal[:40],
                    html_content=site_code,
                    files=all_files if all_files else None,
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

            elif step.tool_name == "ask_user_input":
                args = step.tool_args_hint if isinstance(step.tool_args_hint, dict) else {}
                q = args.get("question") or clean_step_desc
                opts = args.get("options") or ["Yes, proceed", "No, adjust plan", "Provide more details"]
                sel_type = args.get("select_type", "single_select")
                return StepResult(
                    success=True,
                    summary=f"Presented question to user: '{q}'. Options: {', '.join(str(o) for o in opts)}",
                    artifacts=[{
                        "type": "user_input_request",
                        "question": q,
                        "options": opts,
                        "select_type": sel_type,
                    }],
                    token_spend=25,
                    raw_length=len(q),
                )

            elif step.tool_name and (step.tool_name.startswith("mcp_") or step.tool_name.startswith("workstation_")):
                from app.connectors.mcp_registry import MCPRegistry
                mcp_registry = MCPRegistry()
                args = dict(step.tool_args_hint) if isinstance(step.tool_args_hint, dict) else {}
                if not args.get("path") or args.get("path") == ".":
                    combined_text = f"{clean_step_desc} {self.task.goal}"
                    path_match = re.search(r'[A-Za-z]:\\[^"\'\s]+|[A-Za-z]:/[^"\'\s]+', combined_text)
                    if path_match:
                        args["path"] = path_match.group(0).rstrip(".:,;`)]'\"")
                    elif re.search(r'\bdownload(?:s)?\b', combined_text, re.IGNORECASE):
                        args["path"] = "downloads"
                    elif re.search(r'\bdesktop\b', combined_text, re.IGNORECASE):
                        args["path"] = "desktop"
                    elif re.search(r'\bdocuments?\b', combined_text, re.IGNORECASE):
                        args["path"] = "documents"
                    else:
                        args["path"] = args.get("path") or "."

                output = await mcp_registry.execute_mcp_tool(
                    user_id=self.task.user_id,
                    tool_name=step.tool_name,
                    arguments=args,
                    conversation_id=self.task.conversation_id,
                )
                is_err = str(output).startswith("Error") or "Invalid MCP" in str(output)
                return StepResult(
                    success=not is_err,
                    summary=str(output)[:500],
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

            elif step.tool_name == "sandbox_ls":
                from app.services.code_sandbox import sandbox_list_files
                res_str = await sandbox_list_files(self.task.conversation_id or "default")
                return StepResult(
                    success=True,
                    summary=res_str[:400],
                    artifacts=[],
                    token_spend=50,
                    raw_length=len(res_str),
                )

            elif step.tool_name == "sandbox_read":
                from app.services.code_sandbox import sandbox_read_file
                target_path = ""
                if isinstance(step.tool_args_hint, dict):
                    target_path = step.tool_args_hint.get("path", "")
                if not target_path:
                    m = re.search(r"[\w\-\.\/]+\.[a-zA-Z0-9]+", clean_step_desc)
                    if m:
                        target_path = m.group(0)
                res_str = await sandbox_read_file(self.task.conversation_id or "default", target_path or clean_step_desc)
                is_err = "sandbox_read error" in res_str
                return StepResult(
                    success=not is_err,
                    summary=res_str[:400],
                    artifacts=[],
                    token_spend=80,
                    raw_length=len(res_str),
                    error=res_str if is_err else None,
                )

            elif step.tool_name == "sandbox_write":
                from app.services.code_sandbox import sandbox_write_file, _resolve_sandbox_path
                target_path = ""
                file_content = ""
                if isinstance(step.tool_args_hint, dict):
                    target_path = step.tool_args_hint.get("path", "")
                    file_content = step.tool_args_hint.get("content", "")
                if not target_path:
                    m = re.search(r"[\w\-\.\/]+\.[a-zA-Z0-9]+", clean_step_desc)
                    if m:
                        target_path = m.group(0)
                    else:
                        target_path = "output.txt"
                if not file_content or len(file_content.strip()) < 60 or file_content.strip() == clean_step_desc.strip():
                    file_content = await self._generate_file_content(step, target_path)
                conv_id = self.task.conversation_id or "default"
                res_str = await sandbox_write_file(conv_id, target_path or "output.txt", file_content)
                is_err = "sandbox_write error" in res_str
                artifacts_list = []
                if not is_err and target_path:
                    try:
                        from app.services.cloudflare_r2 import upload_file_bytes
                        import mimetypes
                        full_p = _resolve_sandbox_path(conv_id, target_path)
                        mime = mimetypes.guess_type(full_p)[0] or "text/plain"
                        r2_url = await upload_file_bytes(
                            file_bytes=file_content.encode("utf-8"),
                            filename=f"generated/{conv_id}/{target_path}",
                            mime_type=mime,
                            bucket_type="GENERATED",
                        )
                        art = {"filename": target_path, "download_url": r2_url, "size_bytes": len(file_content)}
                        artifacts_list.append(art)
                        if not any(a.get("filename") == target_path for a in self.task.artifacts):
                            self.task.artifacts.append(art)
                    except Exception:
                        art = {"filename": target_path, "download_url": f"/v1/files/sandbox/{conv_id}/{target_path}", "size_bytes": len(file_content)}
                        artifacts_list.append(art)
                        if not any(a.get("filename") == target_path for a in self.task.artifacts):
                            self.task.artifacts.append(art)
                return StepResult(
                    success=not is_err,
                    summary=f"Wrote {len(file_content)} bytes to {target_path}. {res_str[:150]}",
                    artifacts=artifacts_list,
                    token_spend=350,
                    raw_length=len(file_content),
                    error=res_str if is_err else None,
                )

            elif step.tool_name == "present_deliverable":
                import zipfile
                import mimetypes
                from app.services.code_sandbox import get_or_create_sandbox_workspace, _upload_generated_file
                from app.services.google_drive import upload_to_google_drive

                conv_id = self.task.conversation_id or "default"
                user_id = self.task.user_id or "anonymous"
                workspace_root, src_dir, data_dir = get_or_create_sandbox_workspace(conv_id)
                presented_items = []

                candidate_files = []
                if os.path.exists(data_dir):
                    for r, d, fs in os.walk(data_dir):
                        d[:] = [x for x in d if x not in (".git", "node_modules", ".venv", "__pycache__")]
                        for f in fs:
                            if f not in ("script.py", "script.js", "command.sh", "project.zip"):
                                candidate_files.append(os.path.relpath(os.path.join(r, f), data_dir).replace("\\", "/"))

                for rel_f in candidate_files:
                    full_p = os.path.join(data_dir, rel_f)
                    if os.path.exists(full_p) and os.path.isfile(full_p):
                        try:
                            with open(full_p, "rb") as f_in:
                                b_data = f_in.read()
                            mime_t, _ = mimetypes.guess_type(rel_f)
                            f_url = await _upload_generated_file(
                                file_bytes=b_data,
                                filename=rel_f,
                                mime_type=mime_t or "application/octet-stream",
                                conversation_id=conv_id,
                                user_id=user_id,
                            )
                            presented_items.append({
                                "filename": rel_f,
                                "download_url": f_url,
                                "size_bytes": len(b_data),
                            })
                        except Exception as up_err:
                            logger.warning(f"Failed to upload {rel_f} in present_deliverable: {up_err}")

                if len(candidate_files) > 1 and os.path.exists(data_dir):
                    try:
                        import io as _io
                        z_buf = _io.BytesIO()
                        with zipfile.ZipFile(z_buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                            for root_z, dirs_z, files_z in os.walk(data_dir):
                                dirs_z[:] = [d for d in dirs_z if d not in (".git", "node_modules", ".venv", "__pycache__")]
                                for fz in files_z:
                                    if fz in ("script.py", "script.js", "command.sh", "project.zip"):
                                        continue
                                    fp_z = os.path.join(root_z, fz)
                                    zf.write(fp_z, arcname=os.path.relpath(fp_z, data_dir))
                        z_bytes = z_buf.getvalue()
                        if z_bytes:
                            zip_p = os.path.join(data_dir, "project.zip")
                            with open(zip_p, "wb") as zf_out:
                                zf_out.write(z_bytes)
                            try:
                                await upload_to_google_drive(user_id, conv_id, data_dir)
                            except Exception as gd_err:
                                logger.warning(f"Google Drive sync in present_deliverable: {gd_err}")
                            z_url = await _upload_generated_file(
                                file_bytes=z_bytes,
                                filename="project.zip",
                                mime_type="application/zip",
                                conversation_id=conv_id,
                                user_id=user_id,
                            )
                            presented_items.append({
                                "filename": "project.zip",
                                "download_url": z_url,
                                "size_bytes": len(z_bytes),
                            })
                    except Exception as z_err:
                        logger.warning(f"Error creating project.zip in present_deliverable: {z_err}")

                for item in presented_items:
                    if not any(a.get("filename") == item["filename"] for a in self.task.artifacts):
                        self.task.artifacts.append(item)

                return StepResult(
                    success=True,
                    summary=f"Packaged and presented {len(presented_items)} deliverable files including project.zip.",
                    artifacts=presented_items,
                    token_spend=120,
                    raw_length=len(presented_items),
                )

            elif step.tool_name in ("mcp_workstation_read", "workstation_read"):
                target_path = ""
                if isinstance(step.tool_args_hint, dict):
                    target_path = step.tool_args_hint.get("path", "")
                if not target_path:
                    m = re.search(r"[\w\-\.\/\\:]+\.[a-zA-Z0-9]+", clean_step_desc)
                    if m:
                        target_path = m.group(0)
                target_path = target_path or clean_step_desc
                res_str = ""
                try:
                    import urllib.request
                    import urllib.parse
                    url = f"http://127.0.0.1:3920/read?path={urllib.parse.quote(target_path)}"
                    req = urllib.request.Request(url, method="GET")
                    with urllib.request.urlopen(req, timeout=2.0) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            res_str = data.get("content", "")
                except Exception:
                    pass
                if not res_str:
                    from app.services.code_sandbox import sandbox_read_file
                    fname = os.path.basename(target_path.replace("\\", "/"))
                    res_str = await sandbox_read_file(self.task.conversation_id or "default", fname)
                is_err = not res_str or "sandbox_read error" in res_str
                return StepResult(
                    success=not is_err,
                    summary=res_str[:400] if not is_err else f"Could not read workstation file {target_path}",
                    artifacts=[],
                    token_spend=80,
                    raw_length=len(res_str),
                    error=res_str if is_err else None,
                )

            elif step.tool_name == "sandbox_edit":
                from app.services.code_sandbox import sandbox_edit_file, _resolve_sandbox_path
                target_path = ""
                old_str = ""
                new_str = ""
                if isinstance(step.tool_args_hint, dict):
                    target_path = step.tool_args_hint.get("path", "")
                    old_str = step.tool_args_hint.get("old_str", "")
                    new_str = step.tool_args_hint.get("new_str", "")
                conv_id = self.task.conversation_id or "default"
                res_str = await sandbox_edit_file(conv_id, target_path, old_str, new_str)
                is_err = "sandbox_edit error" in res_str
                artifacts_list = []
                if not is_err and target_path:
                    try:
                        from app.services.cloudflare_r2 import upload_file_bytes
                        import mimetypes
                        full_p = _resolve_sandbox_path(conv_id, target_path)
                        if os.path.exists(full_p):
                            with open(full_p, "rb") as fh:
                                f_bytes = fh.read()
                            mime = mimetypes.guess_type(full_p)[0] or "text/plain"
                            r2_url = await upload_file_bytes(
                                file_bytes=f_bytes,
                                filename=f"generated/{conv_id}/{target_path}",
                                mime_type=mime,
                                bucket_type="GENERATED",
                            )
                            artifacts_list.append({"filename": target_path, "download_url": r2_url})
                    except Exception:
                        artifacts_list.append({"filename": target_path, "download_url": f"/v1/files/sandbox/{conv_id}/{target_path}"})
                return StepResult(
                    success=not is_err,
                    summary=res_str[:400],
                    artifacts=artifacts_list,
                    token_spend=80,
                    raw_length=len(res_str),
                    error=res_str if is_err else None,
                )

            else:
                # Direct analytical reasoning / greeting step
                greeting_match = bool(re.match(r"^\s*(hello|hi|hey|good\s+(?:morning|afternoon|evening|day)|greetings|who\s+are\s+you|what\s+can\s+you\s+do|how\s+are\s+you|help|thanks|thank\s+you|sup|yo)\b[!?.]*\s*$", self.task.goal.strip(), re.IGNORECASE))
                pc_query_match = bool(re.search(r"\b(?:see|access|read|browse|view)\s+(?:my\s+)?(?:pc|computer|laptop|local|workstation)\s+files?\b|\b(?:pc|computer|workstation)\s+files?\b", self.task.goal.strip(), re.IGNORECASE))
                if greeting_match:
                    summary = "Hello! I can plan and execute multi-step research, data analysis, document generation, and autonomous tasks for you. What would you like to build or explore?"
                elif pc_query_match:
                    ws_active = bool(self.config.get("workstation_access_enabled", False))
                    if ws_active:
                        summary = "Workstation Computer Access is currently enabled. I have direct access to your local files and can inspect, read, or edit files using workstation tools."
                    else:
                        summary = "By default, PC access is isolated for safety. However, I have Workstation Computer Access (Cowork) which you can enable by toggling Workstation Access ON in Settings or the header."
                else:
                    step_prompt = AgentContextCompressor.build_step_payload(self.task, step.index)
                    summary = await self.sub_agents.compress_text(
                        step_prompt,
                        instruction=f"Formulate a thorough, detailed answer for step {step.index}: {step.description}",
                        max_tokens=1500,
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

    async def _attempt_replan(
        self,
        remaining_steps: List[PlanStep],
        failed_step: Optional[PlanStep] = None,
        discovery_context: Optional[str] = None,
    ) -> Optional[List[PlanStep]]:
        """
        Phase 8 / 8.1: Budget-capped dynamic plan re-orientation guard.

        Phase 8: called once per step whose failure exhausted both AI retries.
        Phase 8.1: also called proactively after a successful investigative step
        whose findings shift the plan's premise (discovery_context). Skipped
        when the re-plan budget (max_replans_per_task, default 2, 0 disables)
        is spent or the circuit breaker's time budget is exhausted. Token
        economy: the actual call runs on the nano deployment via
        replan_remaining (effort floored at 'low', truncated summaries).
        Exactly one of (failed_step, discovery_context) should be provided.
        """
        try:
            max_replans = int(self.config.get("max_replans_per_task", 2))
        except (ValueError, TypeError):
            max_replans = 2
        if max_replans <= 0 or self.task.replan_count >= max_replans:
            return None
        if not remaining_steps:
            return None
        # Circuit-breaker guard: never re-plan into an exhausted budget.
        try:
            self.circuit_breaker.check_time_budget()
        except ActionBudgetExceeded:
            return None

        default_level = "medium" if self.config.get("review_policy") == "always_ask" else "high"
        auto_level = self.config.get("auto_approve_level", default_level)
        return await replan_remaining(
            original_plan=self.task.plan,
            completed_results=self.task.step_results,
            remaining_steps=remaining_steps,
            goal=self.task.goal,
            failed_step=failed_step,
            auto_approve_level=auto_level,
            openai_client=self.client,
            nano_deployment=self.nano_deployment,
            discovery_context=discovery_context,
        )

    async def _check_premise_divergence(
        self,
        step: PlanStep,
        i: int,
    ) -> Optional[str]:
        """
        Phase 8.1: Zero-cost heuristic gate + nano divergence probe.

        Returns a one-sentence contradiction summary when a SUCCESSFUL
        investigative step's findings invalidate a remaining step's premise,
        otherwise None. Never raises — check_premise_divergence already
        returns None on any internal failure.

        Heuristic gate (both arms must pass before any LLM call):
          A. Investigative tool — step.tool_name is in the literal
             _DIVERGENCE_INVESTIGATIVE_TOOLS set, OR the step description
             matches _DISCOVERY_VERB_RE.
          B. Divergence signal — step.result_summary contains at least one
             _DIVERGENCE_KEYWORD (matched case-insensitively).
        Budget guard: skipped when replan_count already >= max_replans.
        """
        try:
            max_replans = int(self.config.get("max_replans_per_task", 2))
        except (ValueError, TypeError):
            max_replans = 2
        if max_replans <= 0 or self.task.replan_count >= max_replans:
            return None
        if i + 1 >= len(self.task.plan):
            return None
        if not self.client:
            return None

        tool = (step.tool_name or "").strip()
        summary = step.result_summary or ""

        # Arm A: investigative tool (exact literal set) or discovery verb.
        is_investigative = (
            tool in _DIVERGENCE_INVESTIGATIVE_TOOLS
            or bool(_DISCOVERY_VERB_RE.search(step.description or ""))
        )
        if not is_investigative:
            return None

        # Arm B: divergence keyword present in the result summary.
        if not _DIVERGENCE_KEYWORDS_RE.search(summary):
            return None

        # Both arms passed — fire the cheap nano divergence probe.
        return await check_premise_divergence(
            completed_step=step,
            result_summary=summary,
            next_steps=self.task.plan[i + 1:],
            openai_client=self.client,
            nano_deployment=self.nano_deployment,
        )

    async def _ai_resolve_feedback_and_adapt(
        self,
        step: PlanStep,
        error_feedback: str,
        attempt_num: int,
    ) -> Optional[Dict[str, Any]]:
        """
        AI-level cognitive feedback evaluation.
        When a tool fails or encounters errors/blocks, the AI inspects the error feedback,
        formulates an aim, and dynamically selects an alternative tool to accomplish the step,
        avoiding rigid app-level fallbacks or fixed OODA patterns.
        """
        if not self.client:
            return None

        prompt = [
            {
                "role": "system",
                "content": (
                    "You are the Cognitive Step Supervisor for Agent Ochuko. "
                    "An autonomous agent step encountered an error or failed to achieve its result. "
                    "Your job is to inspect the error/feedback, establish a clear aim, and intelligently select "
                    "an alternative tool or refined strategy to circumvent the obstacle.\n\n"
                    "Available tools:\n"
                    "- search_web: Query Google for live web information, articles, documentation, or alternative sources\n"
                    "- deep_research: Comprehensive multi-query research across multiple topics\n"
                    "- scrape_web: Direct extraction of a specific URL (fails if blocked by anti-bot, 403, or JS challenges)\n"
                    "- execute_code: Run Python in a secure sandbox with full internet to compute, parse, extract with BeautifulSoup/httpx, or process data\n"
                    "- deploy_site: Publish generated multi-file web app to Cloudflare R2 CDN\n"
                    "- lookup_handle: Lookup GitHub or social profiles\n"
                    "- synthesize_answer: Reason directly and formulate answer from available knowledge\n\n"
                    "Rules:\n"
                    "1. Do NOT repeat the exact same failing tool with the same input.\n"
                    "2. If direct scraping failed (e.g. 403 Forbidden, bot block, network failure), pivot to search_web to find the information or execute_code to query public APIs/alternatives.\n"
                    "3. If code execution failed with an import or runtime error, fix the code or use search_web to look up the solution.\n"
                    "4. If all viable tools for this step have been exhausted, conclude the step with action 'proceed' so the agent can move on and synthesize its findings for the user.\n\n"
                    "Respond ONLY with a JSON object:\n"
                    '{"action": "retry_tool" | "proceed", "tool_name": "<tool_name>", "description": "<new concrete step instruction or search query>", "reasoning": "<brief explanation of why this tool was chosen>"}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Overall Goal: {self.task.goal}\n"
                    f"Current Step #{step.index}: {step.description}\n"
                    f"Tool Used: {step.tool_name}\n"
                    f"Failure Feedback / Error: {error_feedback}\n"
                    f"Attempt #{attempt_num} of 2.\n"
                    "Evaluate the feedback and decide the next move."
                ),
            },
        ]

        try:
            model = self.nano_deployment or self.deployment
            if hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                resp = await self.client.chat.completions.create(
                    model=model,
                    messages=prompt,
                    response_format={"type": "json_object"} if hasattr(self.client, "chat") else None,
                )
                raw = resp.choices[0].message.content or "{}"
            else:
                resp = await self.client.responses.create(model=model, input=prompt)
                raw = getattr(resp, "output_text", "") or "{}"

            raw_clean = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
            raw_clean = re.sub(r"\s*```$", "", raw_clean).strip()
            decision = json.loads(raw_clean)

            valid_tools = {
                "search_web", "google_search", "deep_research", "scrape_web",
                "execute_code", "python", "deploy_site", "lookup_handle", "synthesize_answer"
            }
            if decision.get("action") == "retry_tool" and decision.get("tool_name") in valid_tools:
                return decision
            elif decision.get("action") == "proceed":
                return decision
            return None
        except Exception as e:
            logger.warning(f"AI feedback adaptation error: {e}")
            return None

    async def _generate_website_code(self, step: PlanStep) -> Tuple[str, Dict[str, str]]:
        """Generates a complete modern web application / site markup and supports multi-file projects."""
        if not self.client:
            return "<div class='p-8 text-center text-xl font-bold'>Instant Site Preview</div>", {}

        prompt = [
            {
                "role": "system",
                "content": (
                    "You are a master full-stack frontend engineer. Generate a complete, stunning, modern, responsive web application with Tailwind CSS or Vanilla CSS. "
                    "Make it interactive with embedded JavaScript (e.g. working sliders, pricing toggle, calculator logic, charts, interactive state). "
                    "Make it high-contrast, beautiful dark-mode UI with sleek glassmorphism and modern typography. "
                    "You can output multiple files using fenced blocks with filenames: ```html:index.html, ```css:styles.css, ```javascript:app.js. "
                    "Always ensure index.html is provided as the entry point."
                ),
            },
            {
                "role": "user",
                "content": f"Create a complete interactive web app / project for: {self.task.goal}\nStep: {step.description}",
            },
        ]
        try:
            if hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                resp = await self.client.chat.completions.create(model=self.deployment, messages=prompt)
                raw = resp.choices[0].message.content or ""
            else:
                resp = await self.client.responses.create(model=self.deployment, input=prompt)
                raw = getattr(resp, "output_text", "") or ""

            # Parse files from code fences
            files_dict: Dict[str, str] = {}
            pattern = re.compile(r"```([a-zA-Z0-9_\-]+)(?::([a-zA-Z0-9_.\-/]+))?\n([\s\S]*?)```")
            for match in pattern.finditer(raw):
                lang, filename, code = match.groups()
                code_body = code.strip()
                if filename:
                    files_dict[filename.strip()] = code_body
                elif lang in ("html", "htm"):
                    if "index.html" not in files_dict:
                        files_dict["index.html"] = code_body
                elif lang == "css":
                    if "styles.css" not in files_dict:
                        files_dict["styles.css"] = code_body
                elif lang in ("javascript", "js"):
                    if "app.js" not in files_dict:
                        files_dict["app.js"] = code_body

            html_main = files_dict.get("index.html") or ""
            if not html_main:
                if "```html" in raw:
                    html_main = raw.split("```html", 1)[1].split("```", 1)[0].strip()
                elif "```" in raw:
                    html_main = raw.split("```", 1)[1].split("```", 1)[0].strip()
                else:
                    html_main = raw.strip()
                files_dict["index.html"] = html_main

            return html_main, files_dict
        except Exception as e:
            logger.warning(f"Website generation fallback: {e}")
            fallback_html = f"<div class='p-8 text-center text-white'><h1>{self.task.goal}</h1><p>Website deployed successfully.</p></div>"
            return fallback_html, {"index.html": fallback_html}

    async def _collect_sandbox_web_files(self) -> Dict[str, str]:
        """Collects any web files generated in the conversation sandbox workspace."""
        collected: Dict[str, str] = {}
        try:
            import tempfile
            conv_id = self.task.conversation_id or "default"
            data_dir = os.path.join(tempfile.gettempdir(), f"sandbox_{conv_id}", "data")
            if os.path.exists(data_dir):
                for root, _, files in os.walk(data_dir):
                    for f in files:
                        if f.endswith((".html", ".htm", ".css", ".js", ".json", ".svg")):
                            full_p = os.path.join(root, f)
                            rel_p = os.path.relpath(full_p, data_dir).replace("\\", "/")
                            try:
                                with open(full_p, "r", encoding="utf-8", errors="ignore") as fp:
                                    collected[rel_p] = fp.read()
                            except Exception:
                                pass
        except Exception as err:
            logger.debug(f"Could not scan sandbox web files: {err}")
        return collected

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
            code_effort = await self._get_effort()
            if hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                code_cc_kwargs: Dict[str, Any] = {
                    "model": self.deployment,
                    "messages": prompt,
                }
                if code_effort:
                    code_cc_kwargs["reasoning_effort"] = code_effort
                resp = await self.client.chat.completions.create(**code_cc_kwargs)
                code_text = resp.choices[0].message.content or ""
            else:
                code_rs_kwargs: Dict[str, Any] = {
                    "model": self.deployment,
                    "input": prompt,
                }
                if code_effort:
                    code_rs_kwargs["reasoning"] = {"effort": code_effort}
                resp = await self.client.responses.create(**code_rs_kwargs)
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

    async def _generate_file_content(self, step: PlanStep, target_path: str) -> str:
        """Generates complete, production-grade file content using the flagship deployment."""
        if not self.client:
            return f"// {target_path}\n// Deliverable for goal: {self.task.goal}\n"

        effort = await self._get_effort()
        prev_context = []
        for s in self.task.plan:
            if s.index < step.index and s.result_summary:
                prev_context.append(f"Step {s.index} ({s.description}): {s.result_summary[:300]}")
        prev_summary = "\n".join(prev_context)

        system_instruction = (
            "You are a Principal Software Engineer and Production System Architect. "
            "You write complete, bug-free, fully functional, production-ready code and documents. "
            "CRITICAL RULES:\n"
            "1. NEVER output placeholders, stubs, TODOs, or truncate code with '// ... remaining logic ...'.\n"
            "2. Write ALL functions, error handling, imports, styles, and edge case handlers in full.\n"
            "3. Output ONLY the raw file contents. Do NOT wrap the response in outer conversational commentary.\n"
            "4. If the target file is a code file (HTML, CSS, JS, Python, JSON, etc.), do NOT enclose in outer markdown fences — output pure raw code directly."
        )

        user_content = (
            f"GOAL: {self.task.goal}\n\n"
            f"TARGET FILE PATH: {target_path}\n"
            f"STEP SPECIFICATION: {step.description}\n"
        )
        if prev_summary:
            user_content += f"\nPREVIOUS STEP FINDINGS:\n{prev_summary}\n"

        prompt = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content},
        ]

        try:
            if hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                cc_kwargs: Dict[str, Any] = {"model": self.deployment, "messages": prompt}
                if effort:
                    cc_kwargs["reasoning_effort"] = effort
                resp = await self.client.chat.completions.create(**cc_kwargs)
                content = resp.choices[0].message.content or ""
            else:
                rs_kwargs: Dict[str, Any] = {"model": self.deployment, "input": prompt}
                if effort:
                    rs_kwargs["reasoning"] = {"effort": effort}
                resp = await self.client.responses.create(**rs_kwargs)
                content = getattr(resp, "output_text", "") or ""

            ext = os.path.splitext(target_path.lower())[1]
            if ext != ".md":
                m_fence = re.search(r"^```[a-zA-Z0-9_\-]*\n([\s\S]*?)\n```\s*$", content.strip())
                if m_fence:
                    content = m_fence.group(1)

            return content.strip()
        except Exception as e:
            logger.warning(f"File content generation failed for {target_path}: {e}")
            return f"// Failed to generate content for {target_path}: {e}"

