# app/core/model_router.py
"""
ModelRouter — 3-layer intelligent model routing (ADR-002 aligned).

Routing layers:
  Layer 0: DISCUSS mode → always gpt-5.6-luna @ reasoning effort "low" (cheapest)
  Layer 1: Silent Nano Interceptor → trivial messages in THINK/SOLVE mode
           get routed to nano (gpt-5.6-luna @ "low") for NANO_MAX_TURNS
           turns before handing off
  Layer 2: Mode + complexity-based → THINK=gpt-5.6-terra, SOLVE=gpt-5.6-luna,
           each with a rule-classified reasoning-effort tier (low→xhigh)
           from app.core.complexity_router (<1ms, zero cost, deterministic)

All deployment names, effort maps, and prompts are read from Azure App
Configuration so they can be updated at runtime without redeploying.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import get_config
from app.core.skills import get_skill_prompt, get_skill_name, BASE_IDENTITY
from app.core.complexity_router import classify, TIER_ORDER
from app.core.agent_config import get_reasoning_effort

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

# Live/current-data keywords — these need full-model tool capabilities
# (OODA web search with search_web/deep_research), never nano interception.
_LIVE_QUERY_RE = re.compile(
    r"\b(latest|current|currently|today|now|recent|recently|breaking|news|"
    r"price|prices|rate|rates|update|updated|trending|market|live|forecast)\b",
    re.IGNORECASE,
)

# Whitelist prefixes for short lookup questions
_SIMPLE_PREFIX_RE = re.compile(
    r"^(who\s*is|what\s*is|where\s*is|when\s*was|how\s*old\s*is|capital\s*of|define|meaning\s*of)\b",
    re.IGNORECASE
)

# Live-data terms that must never be answered by the cheap tier without
# grounded search — sports/scores (the confabulation class), weather, markets.
_SPORTS_LIVE_RE = re.compile(
    r"\b(score|scores|goal|goals|scorer|match|matches|game|games|standings|"
    r"fixtures?|playoff|tournament|league|brace|hat[\s-]?trick|highlights?|"
    r"transfer|injur\w+|lineup|kickoff|weather|temperature)\b",
    re.IGNORECASE,
)


def _needs_grounded_search(message_text: str) -> bool:
    """
    True when a query is live-data (sports, scores, weather, news, prices) and
    must route to a tool-capable grounded model. The cheap tier confabulates
    plausible match results when search results are thin — these never route
    to nano/discuss.
    """
    if not message_text:
        return False
    return bool(_LIVE_QUERY_RE.search(message_text) or _SPORTS_LIVE_RE.search(message_text))


@dataclass
class RoutingDecision:
    """Result of the model router's decision."""
    deployment: str        # Azure OpenAI deployment name (e.g. "gpt-5.6-terra")
    system_prompt: str     # System prompt text for this mode
    routing_mode: str      # "think", "solve", "discuss", or "nano"
    routing_reason: str    # Human-readable explanation for audit/debug
    was_intercepted: bool  # True if Nano interceptor fired (silent redirect)
    skill: str = "general" # Skill module injected for this request
    complexity: str = "medium"              # Rule-classified tier: low|medium|high|xhigh
    reasoning_effort: Optional[str] = None  # Reasoning effort passed to the API


def _is_trivial(message_text: str) -> bool:
    """Check if a message is trivial (greeting, acknowledgment, etc.)."""
    if not message_text:
        return False
    stripped = message_text.strip()
    
    # Do NOT intercept if the query contains digits/years
    if any(c.isdigit() for c in stripped):
        return False
        
    # Short messages (< 40 chars) that match trivial patterns
    if len(stripped) <= 40 and _TRIVIAL_RE.match(stripped):
        return True
        
    # Very short messages (e.g. <= 8 characters) that are greetings/ack
    if len(stripped) <= 8 and not any(c in stripped for c in "{}[]()=<>|&;"):
        # Explicit check to avoid matching search keywords
        keywords = {"wc", "cl", "tax", "gdp", "rate", "fed", "news", "info", "help", "run"}
        if stripped.lower() in keywords:
            return False
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
    
    # Temporal year lookups need full model tool capabilities (OODA web search)
    if any(yr in stripped for yr in ["2024", "2025", "2026", "2027"]):
        return False

    # Live/current-data questions need search grounding — route to full model
    if _LIVE_QUERY_RE.search(stripped):
        return False

    # Simple requests must be short (e.g. <= 90 characters)
    if len(stripped) > 90:
        return False
        
    # Check if it explicitly matches weather, time, or sports patterns
    if _SIMPLE_QUERY_RE.search(stripped):
        return True
        
    # Check if it is a short question starting with simple lookup prefixes
    if _SIMPLE_PREFIX_RE.match(stripped):
        return True
        
    return False


# Queries asking to summarize or inspect parsed non-OCR files
_DOC_INQUIRY_RE = re.compile(
    r"\b(summarize|summary|overview|what('?s|\s+is)\s+(in|inside)|explain|describe|read|list|contents?|outline)\b",
    re.IGNORECASE
)


async def route(
    user_message: str,
    mode: str,
    conversation_id: Optional[str] = None,
    nano_turn_count: int = 0,
    has_non_ocr_attachments: bool = False,
    has_ocr_attachments: bool = False,
) -> RoutingDecision:
    """
    Determine which model deployment and system prompt to use.

    Args:
        user_message: The latest user message text
        mode: Requested mode from frontend ("think", "solve", "discuss")
        conversation_id: For nano turn tracking (optional)
        nano_turn_count: Current nano turn count for this conversation
        has_non_ocr_attachments: True if text, code, tables, or archives are attached
        has_ocr_attachments: True if images or scanned documents requiring OCR/vision are attached

    Returns:
        RoutingDecision with deployment, prompt, mode, and reasoning.
    """
    # Load deployment names from App Configuration (cached in memory)
    think_deployment = await get_config("THINK_MODEL_DEPLOYMENT", "gpt-5.6-terra")

    solve_deployment = await get_config("SOLVE_MODEL_DEPLOYMENT", "gpt-5.6-luna")
    nano_deployment  = await get_config("NANO_MODEL_DEPLOYMENT",  "gpt-5.6-luna")

    # Nano override prompts (App Config only — skill system handles think/solve/discuss)
    nano_prompt = await get_config("NANO_PROMPT", (
        "You are Agent Ochuko. Respond to greetings naturally, warmly, and briefly (1 to 2 sentences) without reciting who built you. No emojis. No filler."
    ))

    # Classify skill from user message (zero cost, pure regex)
    skill = get_skill_name(user_message)
    skill_prompt = get_skill_prompt(user_message)

    # ── Rule-based complexity classification (<1ms, zero cost) ────────────
    # Runs on every request; feeds the reasoning-effort tier for terra/luna.
    # Runtime toggle: COMPLEXITY_ROUTER_ENABLED=false falls back to "medium".
    complexity_enabled = (await get_config("COMPLEXITY_ROUTER_ENABLED", "true")).lower() != "false"
    cd = classify(user_message) if complexity_enabled else None
    tier = cd.tier if cd else "medium"

    # Agent/Ultra requests never run at low effort — floor at medium.
    if mode == "agent":
        tier = max(tier, "medium", key=lambda x: TIER_ORDER.get(x, 1))

    # Load nano interceptor config
    nano_max_turns_str = await get_config("NANO_MAX_TURNS", "3")
    try:
        nano_max_turns = int(nano_max_turns_str)
    except ValueError:
        nano_max_turns = 3

    # ── Layer 0: DISCUSS mode ────────────────────────────────────────────────
    # Discuss uses nano @ effort "low" for chit-chat and static lookups.
    # Live-data queries escalate to the grounded solve pipeline — the cheap
    # tier fabricates plausible results when search returns thin snippets.
    if mode == "discuss":
        if _needs_grounded_search(user_message):
            mode = "solve"  # escalate: fall through to the mode-based path
        else:
            effort = await get_reasoning_effort("discuss", tier, nano_deployment)
            return RoutingDecision(
                deployment=nano_deployment,
                system_prompt=skill_prompt,
                routing_mode="discuss",
                routing_reason=(
                    f"Mode is DISCUSS — routed to nano | complexity={tier} | "
                    f"effort={effort} | skill={skill}"
                ),
                was_intercepted=False,
                skill=skill,
                complexity=tier,
                reasoning_effort=effort,
            )

    # ── Layer 0b: Non-OCR Document Fast Path ────────────────────────────────
    # Files decoded natively (text, tables, archive manifest) without OCR
    # route to nano for summarization and Q&A to optimize cost and latency.
    if (
        has_non_ocr_attachments
        and not has_ocr_attachments
        and mode != "agent"
        and not _needs_grounded_search(user_message)
    ):
        if _DOC_INQUIRY_RE.search(user_message) or len(user_message.strip()) <= 100:
            effort = await get_reasoning_effort("discuss", "low", nano_deployment)
            return RoutingDecision(
                deployment=nano_deployment,
                system_prompt=skill_prompt,
                routing_mode="nano",
                routing_reason=(
                    f"Non-OCR parsed attachment query — routed to nano ({nano_deployment}) | "
                    f"complexity=low | effort={effort} | skill={skill}"
                ),
                was_intercepted=True,
                skill=skill,
                complexity="low",
                reasoning_effort=effort,
            )

    # ── Layer 1: Silent Nano Interceptor ──────────────────────────────────────
    if skill != "help" and _is_trivial(user_message) and nano_turn_count < nano_max_turns:
        effort = await get_reasoning_effort("nano", tier, nano_deployment)
        return RoutingDecision(
            deployment=nano_deployment,
            system_prompt=nano_prompt,
            routing_mode="nano",
            routing_reason=(
                f"Nano intercepted: trivial message "
                f"(turn {nano_turn_count + 1}/{nano_max_turns}) | "
                f"complexity={tier} | effort={effort}"
            ),
            was_intercepted=True,
            skill="general",
            complexity=tier,
            reasoning_effort=effort,
        )

    # ── Layer 1b: Simple Query Interceptor ───────────────────────────────
    # Static lookups only — live-data (sports/scores/weather) is excluded so
    # those get the grounded think/solve pipeline instead of the cheap tier.
    if (
        _is_simple_request(user_message)
        and not _needs_grounded_search(user_message)
        and nano_turn_count < nano_max_turns
    ):
        effort = await get_reasoning_effort("nano", tier, nano_deployment)
        return RoutingDecision(
            deployment=nano_deployment,
            system_prompt=skill_prompt,  # skill-based even for simple queries
            routing_mode="nano",
            routing_reason=(
                f"Nano intercepted: simple query "
                f"(turn {nano_turn_count + 1}/{nano_max_turns}) | skill={skill} | "
                f"complexity={tier} | effort={effort}"
            ),
            was_intercepted=True,
            skill=skill,
            complexity=tier,
            reasoning_effort=effort,
        )

    # ── Layer 2: Mode + complexity-based routing ─────────────────────────
    if mode == "solve":
        effort = await get_reasoning_effort("solve", tier, solve_deployment)
        return RoutingDecision(
            deployment=solve_deployment,
            system_prompt=skill_prompt,
            routing_mode="solve",
            routing_reason=(
                f"Mode is SOLVE — routed to {solve_deployment} | "
                f"complexity={tier} (score={cd.score if cd else 0}) | "
                f"effort={effort} | skill={skill}"
            ),
            was_intercepted=False,
            skill=skill,
            complexity=tier,
            reasoning_effort=effort,
        )

    # Default: THINK mode (also serves agent/ultra requests via the router)
    effort = await get_reasoning_effort("think", tier, think_deployment)
    mode_label = "ULTRA/agent" if mode == "agent" else "THINK"
    return RoutingDecision(
        deployment=think_deployment,
        system_prompt=skill_prompt,
        routing_mode="think",
        routing_reason=(
            f"Mode is {mode_label} — routed to {think_deployment} | "
            f"complexity={tier} (score={cd.score if cd else 0}) | "
            f"effort={effort} | skill={skill}"
        ),
        was_intercepted=False,
        skill=skill,
        complexity=tier,
        reasoning_effort=effort,
    )
