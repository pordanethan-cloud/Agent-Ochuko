# app/core/model_router.py
"""
ModelRouter — 3-layer intelligent model routing (ADR-002 aligned).

Routing layers:
  Layer 0: DISCUSS mode → always gpt-5.4-nano (cheapest, no interception)
  Layer 1: Silent Nano Interceptor → trivial messages in THINK/SOLVE mode
           get routed to nano for NANO_MAX_TURNS turns before handing off
  Layer 2: Mode-based → THINK=gpt-5.4, SOLVE=gpt-5.4-mini

All deployment names and prompts are read from Azure App Configuration
so they can be updated at runtime without redeploying.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

from app.core.config import get_config

logger = logging.getLogger("app.core.model_router")

# Patterns that indicate a trivial/greeting message → Nano intercept candidate
_TRIVIAL_PATTERNS = [
    r"^(hi|hey|hello|yo|sup|howdy|hola|good\s*(morning|afternoon|evening|night))[\s!?.]*$",
    r"^(thanks|thank\s*you|thx|ty|ok|okay|sure|cool|great|nice|got\s*it|noted)[\s!?.]*$",
    r"^(yes|no|yeah|nah|yep|nope|yup)[\s!?.]*$",
    r"^(how\s*are\s*you|what\'?s\s*up|how\'?s\s*it\s*going)[\s!?.]*$",
    r"^(bye|goodbye|see\s*ya|later|good\s*night)[\s!?.]*$",
]

# Compiled once at module load
_TRIVIAL_RE = re.compile("|".join(_TRIVIAL_PATTERNS), re.IGNORECASE)


@dataclass
class RoutingDecision:
    """Result of the model router's decision."""
    deployment: str        # Azure OpenAI deployment name (e.g. "gpt-5.4")
    system_prompt: str     # System prompt text for this mode
    routing_mode: str      # "think", "solve", "discuss", or "nano"
    routing_reason: str    # Human-readable explanation for audit/debug
    was_intercepted: bool  # True if Nano interceptor fired (silent redirect)


def _is_trivial(message_text: str) -> bool:
    """Check if a message is trivial (greeting, acknowledgment, etc.)."""
    if not message_text:
        return False
    stripped = message_text.strip()
    # Short messages (< 15 chars) that match trivial patterns
    if len(stripped) <= 40 and _TRIVIAL_RE.match(stripped):
        return True
    # Very short messages that don't look like code or structured content
    if len(stripped) <= 8 and not any(c in stripped for c in "{}[]()=<>|&;"):
        return True
    return False


async def route(
    user_message: str,
    mode: str,
    conversation_id: Optional[str] = None,
    nano_turn_count: int = 0,
) -> RoutingDecision:
    """
    Determine which model deployment and system prompt to use.

    Args:
        user_message: The latest user message text
        mode: Requested mode from frontend ("think", "solve", "discuss")
        conversation_id: For nano turn tracking (optional)
        nano_turn_count: Current nano turn count for this conversation

    Returns:
        RoutingDecision with deployment, prompt, mode, and reasoning
    """
    # Load deployment names from App Configuration (cached in memory)
    think_deployment = await get_config("THINK_MODEL_DEPLOYMENT", "gpt-5.4")
    solve_deployment = await get_config("SOLVE_MODEL_DEPLOYMENT", "gpt-5.4-mini")
    nano_deployment = await get_config("NANO_MODEL_DEPLOYMENT", "gpt-5.4-nano")

    # Load system prompts
    think_prompt = await get_config("THINK_PROMPT", (
        "You are a deep-thinking AI assistant. Analyze problems thoroughly, "
        "consider multiple angles, reflect on your reasoning, and provide "
        "comprehensive, well-structured answers."
    ))
    solve_prompt = await get_config("SOLVE_PROMPT", (
        "You are a precise problem-solving AI. Focus on accuracy, logic, "
        "and deterministic solutions. Show your work step by step. "
        "Prioritize correctness over creativity."
    ))
    discuss_prompt = await get_config("DISCUSS_PROMPT", (
        "You are a friendly, conversational AI assistant. Be warm, concise, "
        "and helpful. Keep responses natural and engaging."
    ))
    nano_prompt = await get_config("NANO_PROMPT", (
        "You are a concise AI assistant. Respond in 1-3 sentences maximum. "
        "Be helpful but extremely brief."
    ))

    # Load nano interceptor config
    nano_max_turns_str = await get_config("NANO_MAX_TURNS", "3")
    try:
        nano_max_turns = int(nano_max_turns_str)
    except ValueError:
        nano_max_turns = 3

    # ── Layer 0: DISCUSS mode → always nano ───────────────────────────────
    if mode == "discuss":
        return RoutingDecision(
            deployment=nano_deployment,
            system_prompt=discuss_prompt,
            routing_mode="discuss",
            routing_reason="Mode is DISCUSS — routed to nano (cheapest)",
            was_intercepted=False,
        )

    # ── Layer 1: Silent Nano Interceptor ──────────────────────────────────
    # For THINK/SOLVE mode: if the message is trivial AND we haven't
    # exceeded NANO_MAX_TURNS, silently route to nano instead of
    # burning expensive tokens on "hi" or "thanks".
    if _is_trivial(user_message) and nano_turn_count < nano_max_turns:
        return RoutingDecision(
            deployment=nano_deployment,
            system_prompt=nano_prompt,
            routing_mode="nano",
            routing_reason=(
                f"Nano intercepted: trivial message "
                f"(turn {nano_turn_count + 1}/{nano_max_turns})"
            ),
            was_intercepted=True,
        )

    # ── Layer 2: Mode-based routing ───────────────────────────────────────
    if mode == "solve":
        return RoutingDecision(
            deployment=solve_deployment,
            system_prompt=solve_prompt,
            routing_mode="solve",
            routing_reason="Mode is SOLVE — routed to gpt-5.4-mini",
            was_intercepted=False,
        )

    # Default: THINK mode
    return RoutingDecision(
        deployment=think_deployment,
        system_prompt=think_prompt,
        routing_mode="think",
        routing_reason="Mode is THINK — routed to gpt-5.4",
        was_intercepted=False,
    )
