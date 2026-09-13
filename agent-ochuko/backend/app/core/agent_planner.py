# app/core/agent_planner.py
"""
Agent Planner — task decomposition for complex multi-step goals.
Provides structured plan generation (List[PlanStep]) with risk classification
and tool hint mapping for Agent Mode, alongside backward-compatible prompt injection.
"""

import os
import asyncio
import json
import re
import logging
from typing import Optional, List, Dict, Any

from openai import AsyncAzureOpenAI
from app.core.agent_task_models import PlanStep, StepStatus, RiskLevel
from app.core.hitl_gates import HITLGate
from app.core.skills import AGENT_CONDUCT, ULTRA_IDENTITY

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
    "    \"tool_name\": \"search_web\" | \"deep_research\" | \"fetch_url\" | \"scrape_web\" | \"youtube_transcript\" | \"lookup_handle\" | \"deploy_site\" | \"execute_code\" | \"terminal\" | \"fetch_stock_image\" | \"sandbox_ls\" | \"sandbox_read\" | \"sandbox_write\" | \"sandbox_edit\" | \"generate_image\" | \"memory_save\" | \"memory_recall\" | \"gmail_search\" | \"gmail_read\" | \"gmail_send\" | \"calendar_list_events\" | \"calendar_create_event\" | \"calendar_check_availability\" | \"photos_search\" | \"photos_list\" | \"photos_get\" | \"photos_upload\" | \"visualize__show_widget\" | \"ask_user_input\" | \"present_deliverable\" | \"mcp_workstation_list\" | \"mcp_workstation_read\" | \"mcp_workstation_write\" | \"mcp_workstation_exec\" | null,\n"
    "    \"tool_args_hint\": {\"question\": \"...\", \"options\": [\"Option 1\", \"Option 2\"]} | {\"path\": \"...\"} | {\"project_name\": \"...\", \"entry_file\": \"index.html\"} | null,\n"
    "    \"risk_level\": \"low\" | \"medium\" | \"high\"\n"
    "  }\n"
    "]\n\n"
    "Tool Selection Directives:\n"
    "- When finishing a multi-file website, software project, or deliverable bundle: use tool_name=\"present_deliverable\" (risk_level=\"low\"). Include tool_args_hint with {\"project_name\": \"...\", \"entry_file\": \"index.html\"}.\n"
    "- When user asks to inspect, read, or list files/folders on their local computer or workstation: use tool_name=\"mcp_workstation_list\" (risk_level=\"low\"). Always include tool_args_hint with {\"path\": \"...\"} and optional {\"pattern\": \"*.ext\"}. Enforces compact 25-item limit.\n"
    "- When user asks to inspect or read content from a local file: use tool_name=\"mcp_workstation_read\" (risk_level=\"low\"). Always include tool_args_hint with {\"path\": \"...\"} and chunking hints like {\"start_line\": 1, \"end_line\": 100} for large files.\n"
    "- When user asks to write, create, or modify files on their local computer or workstation: use tool_name=\"mcp_workstation_write\" (risk_level=\"medium\").\n"
    "- When user asks to run shell or terminal commands on their local computer or workstation: use tool_name=\"mcp_workstation_exec\" (risk_level=\"high\").\n"
    "- When user asks to design or build a website, landing page, dashboard, or web tool: follow Think Mode's world-class engineering standards. Plan an architectural & design step, complete implementation with modern aesthetics (Google Fonts, custom Tailwind/CSS tokens, dark mode/gradients, responsive breakpoints), live deployment with tool_name=\"deploy_site\", and interactive presentation with tool_name=\"present_deliverable\".\n"
    "- ZIP PACKAGING & INDIVIDUAL FILE ACCESS:\n"
    "  * ONLY multi-file software projects (2+ files) are packaged into a zip file (`project.zip`).\n"
    "  * NEVER zip single-file software or individual scripts/documents. Present single files directly.\n"
    "  * In multi-file deliverables, EVERY individual file must remain separately accessible, demandable, and downloadable in addition to the zip.\n"
    "- When user provides a YouTube URL or asks about a YouTube video, transcript, or summary: use tool_name=\"youtube_transcript\" (risk_level=\"low\").\n"
    "- When user intent is ambiguous, requires decision between multiple paths, or needs user preference/clarification: use tool_name=\"ask_user_input\" (risk_level=\"low\"). Always include tool_args_hint with question and options list.\n"
    "- When user provides a URL or asks to scrape/crawl/browse a webpage: use tool_name=\"scrape_web\".\n"
    "- When user pastes a link or asks to read a specific page's content: use tool_name=\"fetch_url\".\n"
    "- When user asks to remember a preference or fact for later: use tool_name=\"memory_save\".\n"
    "- When a step creates files: use tool_name=\"sandbox_write\".\n"
    "- When a step modifies, patches, or edits an existing file: use tool_name=\"sandbox_edit\" or \"execute_code\".\n"
    "- When a step inspects or verifies existing files: use tool_name=\"sandbox_ls\" or \"sandbox_read\".\n"
    "- When user asks to look up a person or account on LinkedIn, Facebook, Twitter/X, or GitHub: use tool_name=\"lookup_handle\".\n"
    "- When user asks to build, deploy, or create a web app, website, landing page, or calculator: use tool_name=\"deploy_site\".\n"
    "- When user asks to search or read emails: use tool_name=\"gmail_search\" or \"gmail_read\".\n"
    "- When user asks to send or compose an email: use tool_name=\"gmail_send\" (risk_level=\"high\").\n"
    "- When user asks to check calendar or availability: use tool_name=\"calendar_list_events\" or \"calendar_check_availability\".\n"
    "- When user asks to schedule a meeting or create an event: use tool_name=\"calendar_create_event\" (risk_level=\"high\").\n"
    "- When user asks to find, browse, or fetch photos: use tool_name=\"photos_search\", \"photos_list\", or \"photos_get\".\n"
    "- When user asks for general web data, live facts, or research: use tool_name=\"search_web\". In the step description, write the exact keyword query with all pronouns resolved to real entity names and the current year (2026) included.\n\n"
    "Risk Level Guidelines:\n"
    "- 'low': Reading / research (search_web, deep_research, fetch_url, youtube_transcript, sandbox_ls, sandbox_read, memory_save, memory_recall, scrape_web, lookup_handle, gmail_search, gmail_read, calendar_list_events, calendar_check_availability, photos_search, photos_list, photos_get)\n"
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

# Tool roster a re-plan may emit — mirrors the tool_name enumeration in the
# _STRUCTURED_PLANNER_SYSTEM schema, plus ask_user_input (used by the
# programmatic fallback and specially handled by the HITL pause path).
_PLANNER_TOOL_ROSTER = frozenset({
    "search_web", "deep_research", "fetch_url", "scrape_web", "youtube_transcript",
    "lookup_handle", "deploy_site", "execute_code", "terminal", "fetch_stock_image",
    "sandbox_ls", "sandbox_read", "sandbox_write", "sandbox_edit", "generate_image",
    "memory_save", "memory_recall", "gmail_search", "gmail_read", "gmail_send",
    "calendar_list_events", "calendar_create_event", "calendar_check_availability",
    "photos_search", "photos_list", "photos_get", "visualize__show_widget",
    "ask_user_input", "present_deliverable",
    "mcp_workstation_list", "mcp_workstation_read", "mcp_workstation_write", "mcp_workstation_exec",
    "workstation_read", "workstation_list", "workstation_write", "workstation_exec",
})

# Phase 8: compact re-orientation prompt — deliberately terse to keep the
# re-plan call in the low hundreds of tokens on the nano deployment.
_REPLAN_SYSTEM = (
    "You re-orient an autonomous agent's plan after a step failed. "
    "Given the goal, completed results, the failed step, and the stale remaining steps, "
    "produce 1-6 replacement steps that accomplish the REMAINING work only. "
    "Never repeat completed work. Adapt the original approach if it is still viable; "
    "route around it if the failure showed the plan was wrong. "
    'Output ONLY a JSON array of step objects: '
    '[{"description": "concrete action + verification", "tool_name": "<tool or null>", '
    '"risk_level": "low" | "medium" | "high"}]. '
    "Keep the whole plan under 150 words."
)

# Phase 8.1: terse premise-divergence checker — the cheapest LLM call in the
# stack (nano deployment, reasoning effort "none", 3-second timeout). It only
# answers one boolean; anything it cannot answer cleanly must be a None.
_DIVERGENCE_SYSTEM = (
    "You detect when one completed step's findings invalidate the premise of "
    "the immediately following step. "
    "If the completed step's results clearly contradict or invalidate what the "
    "next step assumes, respond with exactly: "
    '{"diverged": true, "reason": "<one-sentence summary of the contradiction>"}. '
    "Otherwise respond with exactly: {\"diverged\": false}. "
    "If uncertain, default to {\"diverged\": false}. Only obvious contradictions count."
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


def _effort_api_kwargs(effort: Optional[str], responses_api: bool) -> Dict[str, Any]:
    """Builds the reasoning-effort kwargs for the target API shape."""
    if not effort:
        return {}
    return {"reasoning": {"effort": effort}} if responses_api else {"reasoning_effort": effort}


def _is_param_error(err: Exception) -> bool:
    """Detects API rejection of the reasoning-effort parameter (400-class)."""
    t = str(err).lower()
    return (
        "reasoning" in t
        or "effort" in t
        or "unknown parameter" in t
        or "unsupported parameter" in t
        or "invalid parameter" in t
        or ("unrecognized" in t and "parameter" in t)
    )


async def _resolve_planner_effort(
    text: str,
    nano_deployment: str,
    floor: Optional[str] = None,
) -> Optional[str]:
    """Rule-classified reasoning effort for planner calls (non-fatal)."""
    try:
        from app.core.complexity_router import classify
        from app.core.agent_config import get_reasoning_effort
        tier = classify(text, floor=floor).tier
        return await get_reasoning_effort("solve", tier, nano_deployment)
    except Exception:
        return None


async def generate_plan(
    user_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    openai_client: Optional[AsyncAzureOpenAI] = None,
    nano_deployment: str = "gpt-5.6-luna",
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

        use_responses = hasattr(openai_client, "responses") and hasattr(openai_client.responses, "create")
        planner_system_input = [{"role": "system", "content": _PLANNER_SYSTEM}] + planner_input
        effort = await _resolve_planner_effort(user_message, nano_deployment)

        async def _planner_call(with_effort: bool):
            kwargs: Dict[str, Any] = (
                {"model": nano_deployment, "input": planner_system_input}
                if use_responses
                else {"model": nano_deployment, "messages": planner_system_input}
            )
            if with_effort:
                kwargs.update(_effort_api_kwargs(effort, use_responses))
            if use_responses:
                return await asyncio.wait_for(openai_client.responses.create(**kwargs), timeout=4.0)
            return await asyncio.wait_for(openai_client.chat.completions.create(**kwargs), timeout=4.0)

        try:
            try:
                response = await _planner_call(True)
            except Exception as call_err:
                if effort and _is_param_error(call_err):
                    logger.debug(f"Planner effort '{effort}' rejected — retrying without it: {call_err}")
                    response = await _planner_call(False)
                else:
                    raise
            if use_responses:
                plan_text = (getattr(response, "output_text", "") or "").strip()
            else:
                plan_text = (response.choices[0].message.content or "").strip()
        except Exception as api_err:
            logger.debug(f"Planner API call skipped (non-fatal): {api_err}")
            return None

        if not plan_text or plan_text == "SINGLE_STEP":
            return None

        return plan_text
    except Exception as e:
        logger.warning(f"Plan generation failed (non-fatal): {e}")
        return None


def _programmatic_fallback_plan(goal: str, auto_approve_level: str = "high") -> List[PlanStep]:
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
    local_path_match = re.search(
        r'[A-Za-z]:\\[^"\'\n]+|[A-Za-z]:/[^"\'\n]+|'
        r'\b(?:my\s+)?download(?:s)?\b|\b(?:my\s+)?desktop\b|\b(?:my\s+)?documents?\b|'
        r'\b(?:on|from|in|see|access|read|browse|view)\s+(?:my\s+)?(?:computer|laptop|pc|workstation|machine)\b|'
        r'\b(?:pc|computer|workstation)\s+files?\b|\bcowork\b',
        goal,
        re.IGNORECASE,
    )
    needs_workstation = bool(local_path_match)
    needs_search = bool(re.search(r"\b(find|search|lookup|look up|research|who|what|when|where|latest|news|today|price|stock|weather)\b", goal, re.IGNORECASE)) or len(goal) > 25
    needs_code = bool(re.search(r"\b(code|python|script|calculate|compute|math|csv|excel|pdf|docx|file|chart|plot)\b", goal, re.IGNORECASE))

    fallback_steps = []
    step_idx = 1

    if needs_workstation:
        is_inquiry = bool(re.search(r'\b(?:can|do)\s+you\s+(?:see|access|read|browse|view)\b|\bsee\s+(?:my\s+)?pc\s+files\b', goal, re.IGNORECASE))
        if is_inquiry:
            fallback_steps.append(PlanStep(
                index=step_idx,
                description="Explain Workstation Computer Access (Cowork) capabilities and setup instructions",
                tool_name=None,
                risk_level=RiskLevel.LOW,
                status=StepStatus.PENDING,
            ))
            step_idx += 1
        else:
            extracted_p = "downloads"
            win_m = re.search(r'[A-Za-z]:\\[^"\'\s]+|[A-Za-z]:/[^"\'\s]+', goal)
            if win_m:
                extracted_p = win_m.group(0).rstrip(".:,;`)]'\"")
            elif "desktop" in goal.lower():
                extracted_p = "desktop"
            elif "document" in goal.lower():
                extracted_p = "documents"

            tool_to_use = "mcp_workstation_read" if ("." in os.path.basename(extracted_p) and not extracted_p.endswith(("/", "\\"))) else "mcp_workstation_list"
            fallback_steps.append(PlanStep(
                index=step_idx,
                description=f"Inspect workstation path: {extracted_p}",
                tool_name=tool_to_use,
                tool_args_hint={"path": extracted_p},
                risk_level=RiskLevel.LOW,
                status=StepStatus.PENDING,
            ))
            step_idx += 1

            fallback_steps.append(PlanStep(
                index=step_idx,
                description=f"Confirm file access method with user if host path needs authorization",
                tool_name="ask_user_input",
                tool_args_hint={
                    "question": f"To access '{os.path.basename(extracted_p) or extracted_p}' on your computer, please select how to provide access:",
                    "options": [
                        "Mount local folder via browser",
                        "Select and upload file",
                        "Start local workstation bridge",
                    ],
                    "select_type": "single_select",
                },
                risk_level=RiskLevel.LOW,
                status=StepStatus.PENDING,
            ))
            step_idx += 1
    elif needs_deploy:
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
    nano_deployment: str = "gpt-5.6-luna",
    auto_approve_level: str = "high",
    workspace_files: Optional[List[str]] = None,
    workstation_access_enabled: bool = False,
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
        if workstation_access_enabled:
            user_content = f"WORKSTATION ACCESS: ENABLED (User authorized local computer access via Workstation Cowork. Use mcp_workstation_* tools for local file operations).\n\n{user_content}"
        else:
            user_content = f"WORKSTATION ACCESS: INACTIVE BY DEFAULT (Sandboxed for safety. If user asks about seeing PC files, explain Workstation Access via Browser Folder Mount or Companion Bridge).\n\n{user_content}"
        if workspace_files:
            ws_str = ", ".join(f"'{f}'" for f in workspace_files)
            user_content = f"EXISTING ACTIVE WORKSPACE FILES: [{ws_str}]\n\n{user_content}"
        if history_snippet:
            user_content = f"CONTEXT:\n{history_snippet.strip()}\n\n{user_content}"

        prompt_input = [
            {"role": "system", "content": _STRUCTURED_PLANNER_SYSTEM},
            {"role": "user", "content": user_content},
        ]

        raw_json = ""
        use_responses = hasattr(openai_client, "responses") and hasattr(openai_client.responses, "create")
        effort = await _resolve_planner_effort(goal, nano_deployment, floor="medium")

        async def _structured_call(with_effort: bool):
            kwargs: Dict[str, Any] = (
                {"model": nano_deployment, "input": prompt_input}
                if use_responses
                else {"model": nano_deployment, "messages": prompt_input}
            )
            if with_effort:
                kwargs.update(_effort_api_kwargs(effort, use_responses))
            if use_responses:
                return await asyncio.wait_for(openai_client.responses.create(**kwargs), timeout=8.0)
            return await asyncio.wait_for(openai_client.chat.completions.create(**kwargs), timeout=8.0)

        try:
            try:
                response = await _structured_call(True)
            except Exception as call_err:
                if effort and _is_param_error(call_err):
                    logger.debug(f"Structured planner effort '{effort}' rejected — retrying without it: {call_err}")
                    response = await _structured_call(False)
                else:
                    raise
            if use_responses:
                raw_json = (getattr(response, "output_text", "") or "").strip()
            else:
                raw_json = (response.choices[0].message.content or "").strip()
        except Exception as api_err:
            logger.warning(f"Structured planner API call failed (falling back): {api_err}")
            return _programmatic_fallback_plan(goal, auto_approve_level=auto_approve_level)

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

                args_hint = item.get("tool_args_hint") or item.get("args") or item.get("parameters") or {}
                if not args_hint and tool == "ask_user_input":
                    args_hint = {
                        "question": desc,
                        "options": ["Mount local folder via browser", "Select and upload file", "Start local workstation bridge"],
                        "select_type": "single_select",
                    }
                elif not args_hint and tool and ("workstation" in tool or tool.startswith("mcp_workstation_")):
                    path_match = re.search(r'[A-Za-z]:\\[^"\'\s]+|[A-Za-z]:/[^"\'\s]+', f"{desc} {goal}")
                    if path_match:
                        args_hint = {"path": path_match.group(0).rstrip(".:,;`)]'\"")}
                    elif "download" in f"{desc} {goal}".lower():
                        args_hint = {"path": "downloads"}
                    elif "desktop" in f"{desc} {goal}".lower():
                        args_hint = {"path": "desktop"}
                    elif "document" in f"{desc} {goal}".lower():
                        args_hint = {"path": "documents"}

                step = PlanStep(
                    index=idx,
                    description=desc,
                    tool_name=tool if tool else None,
                    tool_args_hint=args_hint if args_hint else None,
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


async def replan_remaining(
    original_plan: List[PlanStep],
    completed_results: List[Dict[str, Any]],
    remaining_steps: List[PlanStep],
    goal: str,
    failed_step: Optional[PlanStep] = None,
    auto_approve_level: str = "high",
    openai_client: Optional[AsyncAzureOpenAI] = None,
    nano_deployment: str = "gpt-5.6-luna",
    discovery_context: Optional[str] = None,
) -> Optional[List[PlanStep]]:
    """
    Phase 8 / 8.1: Regenerates the remaining steps of a plan.

    Phase 8: invoked after an exhausted step failure. Phase 8.1: also invoked
    proactively after a SUCCESSFUL investigative step whose findings shift the
    plan's premise (discovery_context), so doomed downstream steps never run.

    Token economy is first-class: nano deployment, reasoning effort floored at
    'low', a sliding 5-result window (immediate predecessor expanded to 400
    chars + explicit artifact filenames; older steps 200 chars each, summaries
    only, never artifacts), and a dynamic step horizon of
    min(6, max(2, len(remaining_steps) + 1)) so the LLM neither over-generates
    near the finish line nor under-generates on early pivots.
    Returns a fresh List[PlanStep] re-indexed to continue the original
    numbering (every step HITL-gated), or None on ANY parse/validation
    failure so the caller can keep the original remaining steps.
    """
    if not remaining_steps:
        return None
    if openai_client is None:
        return None

    start_index = remaining_steps[0].index

    # --- Token-economical prompt: summaries only, weighted sliding window ---
    # Phase 8.1 breadcrumbs: the immediate predecessor gets 400 chars plus its
    # artifact filenames; older steps get 200 chars each. Summaries only —
    # artifacts never enter the prompt as content, only their names.
    window = completed_results[-5:]
    completed_trail = ""
    for res in window:
        width = 400 if res is window[-1] else 200
        summary = str(res.get("summary", "") or "")[:width]
        line = f"- #{res.get('step_index', '?')} {summary}\n"
        if res is window[-1]:
            art_names = [
                str(a.get("filename", ""))
                for a in (res.get("artifacts") or [])
                if isinstance(a, dict) and a.get("filename")
            ]
            if art_names:
                line = line.rstrip("\n") + f" [artifacts: {', '.join(art_names[:5])}]\n"
        completed_trail += line
    if len(completed_results) > 5:
        completed_trail = f"(+{len(completed_results) - 5} earlier steps omitted)\n" + completed_trail

    # Phase 8.1: dynamic step horizon — the LLM is told exactly how many steps
    # it may emit, so near-finish tails stay 2 steps and early pivots open up.
    max_replan_steps = min(6, max(2, len(remaining_steps) + 1))

    remaining_lines = ""
    for s in remaining_steps[:6]:
        remaining_lines += f"- #{s.index} [{s.tool_name or 'reason'}] {s.description[:150]}\n"

    # Obstacle block: exactly one of (premise shift | hard failure) is shown.
    obstacle = ""
    if discovery_context:
        obstacle = (
            f"OBSERVATION / PREMISE SHIFT: {discovery_context[:400]}\n"
            "A completed step revealed facts that invalidate the stale steps "
            "below — re-plan them around reality, do not repeat completed work.\n"
        )
    elif failed_step:
        obstacle = (
            f"FAILED STEP #{failed_step.index} [{failed_step.tool_name or 'reason'}]: "
            f"{failed_step.description[:200]}\n"
            f"ERROR: {(failed_step.error or 'unknown failure')[:300]}\n"
        )

    user_content = (
        f"GOAL: {goal[:500]}\n\n"
        f"{obstacle}"
        f"COMPLETED CONTEXT:\n{completed_trail}\n"
        f"STALE REMAINING STEPS:\n{remaining_lines}\n"
        f"Re-plan the remaining work ({max_replan_steps} steps max, JSON array only)."
    )

    prompt_input = [
        {"role": "system", "content": _REPLAN_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    try:
        use_responses = hasattr(openai_client, "responses") and hasattr(openai_client.responses, "create")
        effort = await _resolve_planner_effort(goal, nano_deployment, floor="low")

        async def _replan_call(with_effort: bool):
            kwargs: Dict[str, Any] = (
                {"model": nano_deployment, "input": prompt_input}
                if use_responses
                else {"model": nano_deployment, "messages": prompt_input}
            )
            if with_effort:
                kwargs.update(_effort_api_kwargs(effort, use_responses))
            if use_responses:
                return await asyncio.wait_for(openai_client.responses.create(**kwargs), timeout=6.0)
            return await asyncio.wait_for(openai_client.chat.completions.create(**kwargs), timeout=6.0)

        try:
            response = await _replan_call(True)
        except Exception as call_err:
            if effort and _is_param_error(call_err):
                logger.debug(f"Re-plan effort '{effort}' rejected — retrying without it: {call_err}")
                response = await _replan_call(False)
            else:
                raise

        if use_responses:
            raw_json = (getattr(response, "output_text", "") or "").strip()
        else:
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
        if not isinstance(parsed, list) or not parsed:
            return None

        new_steps: List[PlanStep] = []
        for offset, item in enumerate(parsed[:max_replan_steps]):
            desc = str(item.get("description", "")).strip()
            if not desc:
                return None
            tool = item.get("tool_name")
            tool_str = str(tool).strip() if tool else ""
            if tool_str and tool_str not in _PLANNER_TOOL_ROSTER:
                return None
            raw_risk = str(item.get("risk_level", "low")).lower()
            risk = RiskLevel.HIGH if raw_risk == "high" else (
                RiskLevel.MEDIUM if raw_risk == "medium" else RiskLevel.LOW
            )
            args_hint = item.get("tool_args_hint") if isinstance(item.get("tool_args_hint"), dict) else None
            step = PlanStep(
                index=start_index + offset,
                description=desc,
                tool_name=tool_str or None,
                tool_args_hint=args_hint,
                risk_level=risk,
                status=StepStatus.PENDING,
            )
            HITLGate.requires_approval(step, auto_approve_level=auto_approve_level)
            new_steps.append(step)
        return new_steps
    except Exception as err:
        logger.warning(f"replan_remaining failed, keeping original remaining steps: {err}")
        return None


async def check_premise_divergence(
    completed_step: PlanStep,
    result_summary: str,
    next_steps: List[PlanStep],
    openai_client: Optional[AsyncAzureOpenAI],
    nano_deployment: str = "gpt-5.6-luna",
) -> Optional[str]:
    """
    Phase 8.1: Terse premise-divergence nano-call.

    This is the CHEAPEST LLM call in the stack. Every clause below is a hard
    requirement — not a suggestion — because loose behavior here silently
    breaks the long-horizon OODA loop.

    BEHAVIOR (explicit, non-negotiable):
      1. Runs on the NANO deployment (``nano_deployment``, default gpt-5.6-luna).
      2. Reasoning effort is HARDCODED TO "none" — the absolute cheapest tier.
      3. RETRY ENVELOPE: if the API rejects the reasoning-effort parameter
         (detected via ``_is_param_error`` — a 400-class "unknown parameter"
         style error), retry the call ONCE without the effort kwarg. This is
         the same envelope used by the replan path.
      4. 3-SECOND HARD TIMEOUT: the entire API call is wrapped in
         ``asyncio.wait_for(..., timeout=3.0)``. A timeout of any kind fails
         GRACEFULLY BACK TO None — it never raises, never returns a partial
         string, never logs an error that surfaces to the user.
      5. GRACEFUL FAILURE: ANY of the following — timeout, API error, JSON
         parse failure, missing/invalid response shape, ``diverged=false``,
         or ``diverged=true`` with an empty/missing reason — returns None.
         The function MUST NEVER RAISE. The caller treats None as "no
         divergence, continue the plan unchanged."
      6. SUCCESS: returns the ``reason`` string ONLY when ``diverged`` is
         truthy AND ``reason`` is a non-empty string.

    Args:
        completed_step: The step that just finished successfully.
        result_summary: Its ``result_summary`` text (the facts discovered).
        next_steps: The still-pending steps whose premise we are checking.
        openai_client: An initialized AsyncAzureOpenAI client. If None, returns None.
        nano_deployment: Nano model id to call.

    Returns:
        A one-sentence contradiction summary if the completed step's findings
        clearly invalidate the next step's premise, otherwise None.
    """
    # Guard: no client, no call. Returns None (graceful).
    if openai_client is None or not next_steps:
        return None

    next_desc = (next_steps[0].description or "")[:300]
    completed_desc = (completed_step.description or "")[:300]
    summary = (result_summary or "")[:400]

    user_content = (
        f"COMPLETED STEP: {completed_desc}\n"
        f"RESULTS: {summary}\n\n"
        f"NEXT STEP (pending): {next_desc}\n\n"
        f"Do the completed step's results clearly contradict or invalidate the "
        f"premise the next step assumes? Answer per your instructions."
    )

    use_responses = hasattr(openai_client, "responses") and hasattr(
        openai_client.responses, "create"
    )

    async def _call(with_effort: bool) -> str:
        """Inner call. Effort HARDCODED TO 'none' (cheapest tier)."""
        kwargs: Dict[str, Any] = _effort_api_kwargs("none", use_responses) if with_effort else {}
        if use_responses:
            resp = await openai_client.responses.create(  # type: ignore[attr-defined]
                model=nano_deployment,
                input=[{"role": "system", "content": _DIVERGENCE_SYSTEM},
                       {"role": "user", "content": user_content}],
                **kwargs,
            )
            chunks = []
            for item in getattr(resp, "output", []) or []:
                for part in getattr(item, "content", []) or []:
                    if hasattr(part, "text"):
                        chunks.append(part.text)
            return "".join(chunks).strip()
        resp = await openai_client.chat.completions.create(  # type: ignore[attr-defined]
            model=nano_deployment,
            messages=[{"role": "system", "content": _DIVERGENCE_SYSTEM},
                      {"role": "user", "content": user_content}],
            **kwargs,
        )
        choice = resp.choices[0]
        return (choice.message.content or "").strip()

    try:
        # Try with effort "none" first; on param-rejection retry once without it.
        try:
            raw = await asyncio.wait_for(_call(True), timeout=3.0)
        except Exception as primary_err:
            if _is_param_error(primary_err):
                try:
                    raw = await asyncio.wait_for(_call(False), timeout=3.0)
                except Exception:
                    # Retry failed (timeout or other) — graceful None.
                    logger.debug("check_premise_divergence retry failed: %s", primary_err)
                    return None
            else:
                # Timeout or non-param error on first attempt — graceful None.
                logger.debug("check_premise_divergence failed: %s", primary_err)
                return None

        # Strip optional ```json fence.
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            return None  # invalid shape — graceful None

        diverged = bool(parsed.get("diverged"))
        reason = str(parsed.get("reason", "") or "").strip()

        if diverged and reason:
            return reason  # SUCCESS: one-sentence contradiction
        return None  # diverged=false, or empty reason — graceful None

    except Exception:
        # ANY failure (timeout, parse, shape, API) — graceful None. Never raises.
        return None


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
