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
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import get_config
from app.core.skills import get_skill_prompt, get_skill_name, BASE_IDENTITY

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

# Whitelist topics for explicitly simple informational lookup queries
_SIMPLE_QUERY_PATTERNS = [
    r"\b(weather|temperature|forecast|rain|sunny|wind|humidity|climate)\b",
    r"\b(score|scores|match|matches|football|soccer|basketball|nba|nfl|mlb|game|games|standings|fixtures|playoff|tournament)\b",
    r"\b(time\s*in|timezone|what\s*time|local\s*time)\b",
]

_SIMPLE_QUERY_RE = re.compile("|".join(_SIMPLE_QUERY_PATTERNS), re.IGNORECASE)

# Whitelist prefixes for short lookup questions
_SIMPLE_PREFIX_RE = re.compile(
    r"^(who\s*is|what\s*is|where\s*is|when\s*was|how\s*old\s*is|capital\s*of|define|meaning\s*of)\b",
    re.IGNORECASE
)


@dataclass
class RoutingDecision:
    """Result of the model router's decision."""
    deployment: str        # Azure OpenAI deployment name (e.g. "gpt-5.4")
    system_prompt: str     # System prompt text for this mode
    routing_mode: str      # "think", "solve", "discuss", or "nano"
    routing_reason: str    # Human-readable explanation for audit/debug
    was_intercepted: bool  # True if Nano interceptor fired (silent redirect)
    skill: str = "general" # Skill module injected for this request


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


def _is_simple_request(message_text: str) -> bool:
    """
    Check if a message is explicitly a simple informational lookup query
    (weather, sports scores, basic fact lookup prefixes) that is short.
    """
    if not message_text:
        return False
    stripped = message_text.strip()
    
    # Simple requests must be short (e.g. <= 90 characters) to avoid false positives on longer complex prompts
    if len(stripped) > 90:
        return False
        
    # Check if it explicitly matches weather, time, or sports patterns
    if _SIMPLE_QUERY_RE.search(stripped):
        return True
        
    # Check if it is a short question starting with simple lookup prefixes
    if _SIMPLE_PREFIX_RE.match(stripped):
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
        RoutingDecision with deployment, prompt, mode, and reasoning.
    """
    # Load deployment names from App Configuration (cached in memory)
    think_deployment = await get_config("THINK_MODEL_DEPLOYMENT", "gpt-5.4")

    solve_deployment = await get_config("SOLVE_MODEL_DEPLOYMENT", "gpt-5.4-mini")
    nano_deployment  = await get_config("NANO_MODEL_DEPLOYMENT",  "gpt-5.4-nano")

    # Nano override prompts (App Config only — skill system handles think/solve/discuss)
    nano_prompt = await get_config("NANO_PROMPT", (
        "You are Ochuko. Be direct and brief — 1 to 3 sentences only. No emojis. No filler."
    ))

    # Classify skill from user message (zero cost, pure regex)
    skill = get_skill_name(user_message)
    skill_prompt = get_skill_prompt(user_message)

    # Load nano interceptor config
    nano_max_turns_str = await get_config("NANO_MAX_TURNS", "3")
    try:
        nano_max_turns = int(nano_max_turns_str)
    except ValueError:
        nano_max_turns = 3

    # ── Layer 0: DISCUSS mode ────────────────────────────────────────────────
    # Discuss uses nano. System prompt is skill-based (compact).
    if mode == "discuss":
        return RoutingDecision(
            deployment=nano_deployment,
            system_prompt=skill_prompt,
            routing_mode="discuss",
            routing_reason=f"Mode is DISCUSS — routed to nano | skill={skill}",
            was_intercepted=False,
            skill=skill,
        )

    # ── Layer 1: Silent Nano Interceptor ──────────────────────────────────────
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
            skill="general",
        )

    # ── Layer 1b: Simple Query Interceptor ───────────────────────────────
    if _is_simple_request(user_message) and nano_turn_count < nano_max_turns:
        return RoutingDecision(
            deployment=nano_deployment,
            system_prompt=skill_prompt,  # skill-based even for simple queries
            routing_mode="nano",
            routing_reason=(
                f"Nano intercepted: simple query "
                f"(turn {nano_turn_count + 1}/{nano_max_turns}) | skill={skill}"
            ),
            was_intercepted=True,
            skill=skill,
        )

    # ── Layer 2: Mode-based routing ──────────────────────────────────────
    if mode == "solve":
        return RoutingDecision(
            deployment=solve_deployment,
            system_prompt=skill_prompt,
            routing_mode="solve",
            routing_reason=f"Mode is SOLVE — routed to gpt-5.4-mini | skill={skill}",
            was_intercepted=False,
            skill=skill,
        )

    # Default: THINK mode
    return RoutingDecision(
        deployment=think_deployment,
        system_prompt=skill_prompt,
        routing_mode="think",
        routing_reason=f"Mode is THINK — routed to gpt-5.4 | skill={skill}",
        was_intercepted=False,
        skill=skill,
    )
