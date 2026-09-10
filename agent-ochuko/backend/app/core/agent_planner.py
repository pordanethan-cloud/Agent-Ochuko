# app/core/agent_planner.py
"""
Agent Planner — task decomposition for complex multi-step goals.
Provides structured plan generation (List[PlanStep]) with risk classification
and tool hint mapping for Agent Mode, alongside backward-compatible prompt injection.
"""

import asyncio
import json
import re
import logging
from typing import Optional, List, Dict, Any

from openai import AsyncAzureOpenAI
from app.core.agent_task_models import PlanStep, StepStatus, RiskLevel
from app.core.hitl_gates import HITLGate
from app.core.skills import AGENT_CONDUCT

logger = logging.getLogger("app.core.agent_planner")

# Action verbs that signal a multi-step request requiring planning
_COMPLEX_VERBS = re.compile(
    r"\b(find|search|look up|compare|analyse|analyze|research|investigate|"
    r"build|create|write|generate|summarise|summarize|explain|calculate|"
    r"list|gather|fetch|check|monitor|track|plan|decide|recommend|evaluate|"
    r"review|audit|draft|outline|breakdown|break down)\b",
    re.IGNORECASE,
)

_PLANNER_SYSTEM = (
    "You are a senior autonomous-task architect. Given a user's goal and conversation history, "
    "produce a compact OODA-style execution plan of 2-6 steps.\n\n"
    "For each step, think Observe → Orient → Decide → Act:\n"
    "- OBSERVE: what facts, files, or live data the step needs.\n"
    "- ORIENT: which tool fits and why (one clause).\n"
    "- DECIDE: the concrete action with exact arguments (queries, URLs, file paths).\n"
    "- ACT: what 'done' looks like for the step (the verification).\n\n"
    "Encode all of this in ONE crisp line per step, format:\n"
    "  N. [tool] action — verify: how we know it worked\n"
    "Example:\n"
    "  2. [deep_research] queries: ['iPhone 17 Pro Max camera 2026', 'S26 Ultra camera 2026'] — verify: specs table covers camera/battery/price\n\n"
    "CRITICAL RULE for comparative or multi-topic queries:\n"
    "If the goal asks to compare multiple subjects (phones, products, people, policies, etc.) "
    "or requests information across multiple dimensions/aspects/ramifications, your plan MUST include "
    "a deep_research step listing 3-6 specific, narrow sub-queries — one per subject or dimension.\n\n"
    "FILE DELIVERABLES: when the goal produces files, include a final verification step using "
    "sandbox_ls/sandbox_read to confirm files are complete before reporting done.\n\n"
    "Keep the whole plan under 250 words. Plain numbered list, no preamble. "
    "If the goal can be answered in a single step without tool calls, respond with: SINGLE_STEP"
)

_STRUCTURED_PLANNER_SYSTEM = (
    "You are an expert autonomous agent task architect. Decompose the user's goal into 2 to 6 atomic, sequential steps.\n"
    "Output ONLY valid JSON containing an array of step objects with the following schema:\n"
    "[\n"
    "  {\n"
    "    \"index\": 1,\n"
    "    \"description\": \"Specific step action description (e.g. Scrape pricing data from URL, Look up @handle on GitHub, Deploy landing page)\",\n"
    "    \"tool_name\": \"search_web\" | \"deep_research\" | \"fetch_url\" | \"scrape_web\" | \"lookup_handle\" | \"deploy_site\" | \"execute_code\" | \"sandbox_ls\" | \"sandbox_read\" | \"sandbox_write\" | \"generate_image\" | \"memory_save\" | \"memory_recall\" | \"gmail_search\" | \"gmail_read\" | \"gmail_send\" | \"calendar_list_events\" | \"calendar_create_event\" | \"calendar_check_availability\" | \"photos_search\" | \"photos_list\" | \"photos_get\" | \"photos_upload\" | \"visualize__show_widget\" | null,\n"
    "    \"risk_level\": \"low\" | \"medium\" | \"high\"\n"
    "  }\n"
    "]\n\n"
    "Tool Selection Directives:\n"
    "- When user provides a URL or asks to scrape/crawl/browse a webpage: use tool_name=\"scrape_web\".\n"
    "- When user pastes a link or asks to read a specific page's content: use tool_name=\"fetch_url\".\n"
    "- When user asks to remember a preference or fact for later: use tool_name=\"memory_save\".\n"
    "- When a step creates or modifies files: use tool_name=\"sandbox_write\" (complete files only).\n"
    "- When a step inspects or verifies existing files: use tool_name=\"sandbox_ls\" or \"sandbox_read\".\n"
    "- When user asks to look up a GitHub username or social profile: use tool_name=\"lookup_handle\".\n"
    "- When user asks to build, deploy, or create a web app, website, landing page, or calculator: use tool_name=\"deploy_site\".\n"
    "- When user asks to search or read emails: use tool_name=\"gmail_search\" or \"gmail_read\".\n"
    "- When user asks to send or compose an email: use tool_name=\"gmail_send\" (risk_level=\"high\").\n"
    "- When user asks to check calendar or availability: use tool_name=\"calendar_list_events\" or \"calendar_check_availability\".\n"
    "- When user asks to schedule a meeting or create an event: use tool_name=\"calendar_create_event\" (risk_level=\"high\").\n"
    "- When user asks to find, browse, or fetch photos: use tool_name=\"photos_search\", \"photos_list\", or \"photos_get\".\n"
    "- When user asks to upload or save a photo to Google Photos: use tool_name=\"photos_upload\" (risk_level=\"high\").\n"
    "- When user asks for general web data, live facts, or research: use tool_name=\"search_web\".\n\n"
    "Risk Level Guidelines:\n"
    "- 'low': Reading / research (search_web, deep_research, fetch_url, sandbox_ls, sandbox_read, memory_save, memory_recall, scrape_web, lookup_handle, gmail_search, gmail_read, calendar_list_events, calendar_check_availability, photos_search, photos_list, photos_get)\n"
    "- 'medium': Safe computation (execute_code without file writes, widget rendering, sandbox_write for user-requested deliverables)\n"
    "- 'high': External writes & file mutations (deploy_site, gmail_send, calendar_create_event, photos_upload, execute_code with PDF/Excel/file generation, generate_image)\n\n"
    "Rules:\n"
    "1. Keep descriptions crisp and actionable.\n"
    "2. If the goal is a simple greeting or direct single question, return a 1-step plan with tool_name=null and risk_level='low'.\n"
    "3. Output strictly valid JSON.\n"
    "4. Think OODA: order steps by dependency; each description names its concrete inputs (URLs, queries, paths) and its verification.\n"
    "5. File deliverables get a closing sandbox verification step (sandbox_ls/sandbox_read).\n\n"
    + AGENT_CONDUCT + "\n\n" + ULTRA_IDENTITY
)

# Patterns that signal research-intensive prompts
_RESEARCH_INTENSIVE_RE = re.compile(
    r"\b(compare|vs\.?|versus|rank(?:ing)?|ramification|all\s+(?:aspect|dimension|ramification)|"
    r"breakdown|head[\s-]to[\s-]head|side[\s-]by[\s-]side|pros\s+and\s+cons|"
    r"which\s+is\s+better|should\s+I\s+buy|worth\s+buying|"
    r"spec(?:ification)?s?\s+of|benchmark|all\s+(?:phone|device|product)s?)\b",
    re.IGNORECASE,
)


def _is_complex(message: str) -> bool:
    """Heuristic: returns True if the message likely requires multiple steps."""
    if not message:
        return False
    stripped = message.strip()
    if len(stripped) < 20:
        return False
    if stripped.endswith("?") and not _COMPLEX_VERBS.search(stripped):
        return False
    return bool(_COMPLEX_VERBS.search(stripped))


async def generate_plan(
    user_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    openai_client: Optional[AsyncAzureOpenAI] = None,
    nano_deployment: str = "gpt-5.4-nano",
) -> Optional[str]:
    """Generates a numbered text execution plan for chat system prompt injection."""
    is_research = bool(_RESEARCH_INTENSIVE_RE.search(user_message))
    if not _is_complex(user_message) and not is_research:
        return None

    if openai_client is None:
        return None

    try:
        history_snippet = ""
        if conversation_history:
            recent = conversation_history[-4:]
            for msg in recent:
                role = msg.get("role", "")
                content = (msg.get("content") or "")[:200]
                history_snippet += f"{role}: {content}\n"

        planner_input = []
        if history_snippet:
            planner_input.append({
                "role": "user",
                "content": f"Conversation so far:\n{history_snippet.strip()}\n\nUser's new goal: {user_message}",
            })
        else:
            planner_input.append({"role": "user", "content": user_message})

        try:
            if hasattr(openai_client, "responses") and hasattr(openai_client.responses, "create"):
                response = await asyncio.wait_for(
                    openai_client.responses.create(
                        model=nano_deployment,
                        input=[{"role": "system", "content": _PLANNER_SYSTEM}] + planner_input,
                    ),
                    timeout=2.5
                )
                plan_text = (getattr(response, "output_text", "") or "").strip()
            elif hasattr(openai_client, "chat") and hasattr(openai_client.chat, "completions"):
                response = await asyncio.wait_for(
                    openai_client.chat.completions.create(
                        model=nano_deployment,
                        messages=[{"role": "system", "content": _PLANNER_SYSTEM}] + planner_input,
                    ),
                    timeout=2.5
                )
                plan_text = (response.choices[0].message.content or "").strip()
            else:
                plan_text = ""
        except Exception as api_err:
            logger.debug(f"Planner API call skipped (non-fatal): {api_err}")
            return None

        if not plan_text or plan_text == "SINGLE_STEP":
            return None

        return plan_text
    except Exception as e:
        logger.warning(f"Plan generation failed (non-fatal): {e}")
        return None


def _programmatic_fallback_plan(goal: str, auto_approve_level: str = "low") -> List[PlanStep]:
    """Context-aware programmatic fallback plan generator."""
    pasted_full = re.search(r"\[Pasted Content:[^\]]*\]\s*```(?:[a-zA-Z0-9_-]*\n)?([\s\S]*?)```", goal, flags=re.IGNORECASE)
    if pasted_full:
        prefix = goal[:pasted_full.start()].strip()
        body = pasted_full.group(1).strip()
        goal = f"{prefix} {body}".strip() if prefix else body
    else:
        pasted_single = re.search(r"\[Pasted Content:\s*([^\]]+)\]", goal, flags=re.IGNORECASE)
        if pasted_single:
            goal = pasted_single.group(1).strip()

    needs_deploy = bool(re.search(r"\b(build\s+(?:and\s+)?deploy|deploy|create\s+(?:a\s+)?(?:web\s*app|website|landing\s*page|portfolio|calculator|dashboard)|interactive\s+web\s*app)\b", goal, re.IGNORECASE))
    needs_scrape = bool(re.search(r"\b(scrape|crawl|visit\s+https?://|extract\s+from\s+https?://|https?://[^\s]+)\b", goal, re.IGNORECASE))
    needs_profile = bool(re.search(r"\b(github|github\.com|profile\s+@|@\w+)\b", goal, re.IGNORECASE))
    needs_search = bool(re.search(r"\b(find|search|lookup|look up|research|who|what|when|where|latest|news|today|price|stock|weather)\b", goal, re.IGNORECASE)) or len(goal) > 25
    needs_code = bool(re.search(r"\b(code|python|script|calculate|compute|math|csv|excel|pdf|docx|file|chart|plot)\b", goal, re.IGNORECASE))

    fallback_steps = []
    step_idx = 1

    if needs_deploy:
        fallback_steps.append(PlanStep(
            index=step_idx,
            description=f"Design and deploy interactive web app: {goal[:60]}",
            tool_name="deploy_site",
            risk_level=RiskLevel.HIGH,
            status=StepStatus.PENDING,
        ))
        step_idx += 1
    elif needs_scrape:
        fallback_steps.append(PlanStep(
            index=step_idx,
            description=f"Scrape URL and extract content: {goal[:60]}",
            tool_name="scrape_web",
            risk_level=RiskLevel.LOW,
            status=StepStatus.PENDING,
        ))
        step_idx += 1
    elif needs_profile:
        fallback_steps.append(PlanStep(
            index=step_idx,
            description=f"Look up developer profile: {goal[:60]}",
            tool_name="lookup_handle",
            risk_level=RiskLevel.LOW,
            status=StepStatus.PENDING,
        ))
        step_idx += 1
    else:
        if needs_search:
            fallback_steps.append(PlanStep(
                index=step_idx,
                description=f"Gather data & facts for: {goal[:70]}",
                tool_name="search_web",
                risk_level=RiskLevel.LOW,
                status=StepStatus.PENDING,
            ))
            step_idx += 1

        if needs_code:
            fallback_steps.append(PlanStep(
                index=step_idx,
                description="Process computation and code execution",
                tool_name="execute_code",
                risk_level=RiskLevel.MEDIUM,
                status=StepStatus.PENDING,
            ))
            step_idx += 1

    fallback_steps.append(PlanStep(
        index=step_idx,
        description="Synthesize structured answer and takeaways",
        tool_name=None,
        risk_level=RiskLevel.LOW,
        status=StepStatus.PENDING,
    ))

    for s in fallback_steps:
        HITLGate.requires_approval(s, auto_approve_level=auto_approve_level)
    return fallback_steps


async def generate_structured_plan(
    goal: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    openai_client: Optional[AsyncAzureOpenAI] = None,
    nano_deployment: str = "gpt-5.4-nano",
    auto_approve_level: str = "low",
) -> List[PlanStep]:
    """
    Generates a structured List[PlanStep] for Agent Mode with risk levels and approval requirements.
    Falls back to a safe default 2-step plan if the planner call fails.
    """
    if not goal or not goal.strip():
        return [
            PlanStep(
                index=1,
                description="Process user request and formulate answer",
                tool_name=None,
                risk_level=RiskLevel.LOW,
                status=StepStatus.PENDING,
            )
        ]

    # 1. Immediate recognition for greetings & simple conversational inputs
    greeting_re = re.compile(
        r"^\s*(hello|hi|hey|good\s+(?:morning|afternoon|evening|day)|greetings|"
        r"who\s+are\s+you|what\s+can\s+you\s+do|how\s+are\s+you|help|thanks|thank\s+you|"
        r"sup|yo|testing|test)\b[!?.]*\s*$",
        re.IGNORECASE,
    )
    if greeting_re.match(goal.strip()):
        step = PlanStep(
            index=1,
            description="Respond directly to user inquiry and introduce available autonomous capabilities",
            tool_name=None,
            risk_level=RiskLevel.LOW,
            status=StepStatus.PENDING,
        )
        HITLGate.requires_approval(step, auto_approve_level=auto_approve_level)
        return [step]

    if openai_client is None:
        return _programmatic_fallback_plan(goal, auto_approve_level=auto_approve_level)

    try:
        history_snippet = ""
        if conversation_history:
            for msg in conversation_history[-3:]:
                role = msg.get("role", "")
                content = (msg.get("content") or "")[:200]
                history_snippet += f"{role}: {content}\n"

        user_content = f"GOAL: {goal}"
        if history_snippet:
            user_content = f"CONTEXT:\n{history_snippet.strip()}\n\n{user_content}"

        prompt_input = [
            {"role": "system", "content": _STRUCTURED_PLANNER_SYSTEM},
            {"role": "user", "content": user_content},
        ]

        raw_json = ""
        if hasattr(openai_client, "responses") and hasattr(openai_client.responses, "create"):
            response = await asyncio.wait_for(
                openai_client.responses.create(
                    model=nano_deployment,
                    input=prompt_input,
                ),
                timeout=3.5,
            )
            raw_json = (getattr(response, "output_text", "") or "").strip()
        elif hasattr(openai_client, "chat") and hasattr(openai_client.chat, "completions"):
            response = await asyncio.wait_for(
                openai_client.chat.completions.create(
                    model=nano_deployment,
                    messages=prompt_input,
                ),
                timeout=3.5,
            )
            raw_json = (response.choices[0].message.content or "").strip()

        # Clean JSON markdown formatting if present
        if raw_json.startswith("```"):
            lines = raw_json.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw_json = "\n".join(lines).strip()

        parsed = json.loads(raw_json)
        if isinstance(parsed, dict) and "steps" in parsed:
            parsed = parsed["steps"]

        if isinstance(parsed, list) and len(parsed) > 0:
            plan_steps = []
            for idx, item in enumerate(parsed, start=1):
                desc = str(item.get("description", f"Step {idx}")).strip()
                tool = item.get("tool_name")
                raw_risk = str(item.get("risk_level", "low")).lower()

                risk = RiskLevel.LOW
                if raw_risk == "high":
                    risk = RiskLevel.HIGH
                elif raw_risk == "medium":
                    risk = RiskLevel.MEDIUM

                step = PlanStep(
                    index=idx,
                    description=desc,
                    tool_name=tool if tool else None,
                    risk_level=risk,
                    status=StepStatus.PENDING,
                )
                # Check HITL approval policy
                HITLGate.requires_approval(step, auto_approve_level=auto_approve_level)
                plan_steps.append(step)

            if plan_steps:
                return plan_steps

    except Exception as err:
        logger.warning(f"Structured plan generation failed, using robust fallback: {err}")

    return _programmatic_fallback_plan(goal, auto_approve_level=auto_approve_level)


async def refine_plan(
    original_plan: List[PlanStep],
    user_edits: Dict[int, str],
) -> List[PlanStep]:
    """Applies user modifications to plan steps while preserving completed execution state."""
    updated_plan: List[PlanStep] = []
    for step in original_plan:
        new_step = step.model_copy()
        if step.index in user_edits:
            new_step.description = user_edits[step.index].strip()
            # Re-evaluate risk for updated description
            HITLGate.requires_approval(new_step)
        updated_plan.append(new_step)
    return updated_plan


def format_plan_for_system_prompt(plan_text: str) -> str:
    """Wraps a generated plan in system prompt instructions."""
    if not plan_text:
        return ""
    return (
        f"\n\n[EXECUTION PLAN]\n"
        f"You have already decomposed this task into the following steps:\n"
        f"{plan_text}\n\n"
        f"Execute these steps in order. Call the appropriate tool for each step. "
        f"When all steps are complete, synthesize the final response."
    )
