# app/core/agent_planner.py
"""
Agent Planner — pre-loop task decomposition for complex multi-step goals.

The planner fires a SINGLE cheap gpt-5.4-nano call before the main OODA loop
to decompose the user's goal into a numbered execution plan. This plan is then
injected into the system prompt so the main model knows:
  1. What the end goal is
  2. What order to call tools in
  3. When to declare itself done

The planner is gated by complexity signals — short/trivial messages bypass it
entirely (the model router already handles those with nano).

Design principles:
  - Cheap: always uses nano, never burns a full gpt-5.4 call for planning alone
  - Fast: single non-streaming call, target < 1s
  - Opt-out: returns None for simple messages so caller ignores the plan
  - Safe: any exception returns None (never blocks the main request)
"""

import re
import logging
from typing import Optional, List, Dict, Any

from openai import AsyncAzureOpenAI

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
    "You are a task planning assistant. Given a user's goal and conversation history, "
    "decompose it into a clear, numbered execution plan of 2-6 steps. "
    "Each step should be an atomic, actionable instruction — one tool call or one reasoning step. "
    "Write the plan as a plain numbered list. No explanations, no preamble. "
    "If the goal can be answered in a single step without tool calls, respond with: SINGLE_STEP"
)


def _is_complex(message: str) -> bool:
    """
    Heuristic: returns True if the message likely requires multiple steps.
    Simple heuristics to avoid planning overhead on trivial messages.
    """
    if not message:
        return False
    stripped = message.strip()
    # Short messages are almost never multi-step
    if len(stripped) < 20:
        return False
    # Single question with no action verb → single-step
    if stripped.endswith("?") and not _COMPLEX_VERBS.search(stripped):
        return False
    # Contains action verbs → likely complex
    return bool(_COMPLEX_VERBS.search(stripped))


async def generate_plan(
    user_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    openai_client: Optional[AsyncAzureOpenAI] = None,
    nano_deployment: str = "gpt-5.4-nano",
) -> Optional[str]:
    """
    Generates a numbered execution plan for complex multi-step goals.

    Returns:
        str: Numbered plan to inject into the system prompt, or
        None: if the message is simple (bypass planning entirely).

    This function is always safe to call — any exception returns None.
    """
    if not _is_complex(user_message):
        logger.debug("Planner skipped — message does not appear complex")
        return None

    if openai_client is None:
        logger.debug("Planner skipped — no OpenAI client provided")
        return None

    try:
        # Build context: last 4 messages + current query (keep it cheap)
        history_snippet = ""
        if conversation_history:
            recent = conversation_history[-4:]
            for msg in recent:
                role = msg.get("role", "")
                content = (msg.get("content") or "")[:200]  # truncate long messages
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
            if hasattr(openai_client, "chat") and hasattr(openai_client.chat, "completions"):
                response = await openai_client.chat.completions.create(
                    model=nano_deployment,
                    messages=[{"role": "system", "content": _PLANNER_SYSTEM}] + planner_input,
                )
                plan_text = (response.choices[0].message.content or "").strip()
            else:
                response = await openai_client.responses.create(
                    model=nano_deployment,
                    input=[{"role": "system", "content": _PLANNER_SYSTEM}] + planner_input,
                )
                plan_text = (getattr(response, "output_text", "") or "").strip()
        except Exception as api_err:
            logger.debug(f"Primary planner API call attempt: {api_err}, trying fallback")
            response = await openai_client.responses.create(
                model=nano_deployment,
                input=[{"role": "system", "content": _PLANNER_SYSTEM}] + planner_input,
            )
            plan_text = (getattr(response, "output_text", "") or "").strip()


        if not plan_text or plan_text == "SINGLE_STEP":
            logger.debug("Planner returned SINGLE_STEP — no plan injected")
            return None

        logger.info(
            "Planner generated %d-line plan for message: %.60s",
            plan_text.count("\n") + 1,
            user_message,
        )
        return plan_text

    except Exception as exc:
        # Non-fatal — main loop continues without a plan
        logger.warning("Agent planner failed (non-fatal): %s", exc)
        return None


def format_plan_for_system_prompt(plan: str) -> str:
    """
    Wraps the raw plan in a clearly-delimited block for injection into the system prompt.
    The model is instructed to follow the plan sequentially and record progress
    in its thinking block before moving to the next step.
    """
    return (
        "\n\n--- AGENT EXECUTION PLAN ---\n"
        "Follow this plan step by step. Call the appropriate tools in order. "
        "After completing each step, record the result in your thinking block before proceeding.\n"
        "When all steps are complete, deliver a final, synthesised answer to the user.\n\n"
        f"{plan}\n"
        "--- END PLAN ---\n\n"
    )
