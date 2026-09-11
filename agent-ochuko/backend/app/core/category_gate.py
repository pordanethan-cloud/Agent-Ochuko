"""
app/core/category_gate.py
─────────────────────────
Pre-Model Category Gate — Phase 6 Architecture Upgrade.

Sits BEFORE the Complexity Classifier in the OODA loop.
Classifies the incoming user message into a tool category and returns
ONLY the tool schemas relevant to that category, slashing prompt-token
cost on the ~80% of turns that are purely conversational.

Categories
----------
none       → conversational prose, no tool schemas loaded (0 tokens)
research   → search_web, deep_research, fetch_url
file_ops   → sandbox_ls/read/write/edit, execute_code, terminal
display    → render_*, visualize__read_me, visualize__show_widget
memory     → memory_save, memory_recall, memory_edit
media      → generate_image, fetch_stock_image
realtime   → weather_fetch
agency     → ask_user_input, end_conversation
all        → full roster (ambiguous / multi-intent / iteration > 0)
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Any, Tuple

logger = logging.getLogger(__name__)

# ── Category Membership ─────────────────────────────────────────────────────

# Maps each category name to the tool names that belong to it.
# "all" is the safe fallback; tools not matching any category go to "all".
_CATEGORY_TOOLS: Dict[str, set] = {
    "none": set(),          # purposely empty — no schemas injected
    "research": {
        "search_web", "deep_research", "fetch_url",
    },
    "file_ops": {
        "sandbox_ls", "sandbox_read", "sandbox_write", "sandbox_edit",
        "execute_code", "terminal",
    },
    "display": {
        "render_options_card", "render_step_flow", "render_itinerary",
        "render_map", "render_quiz", "render_translation",
        "visualize__read_me", "visualize__show_widget",
    },
    "memory": {
        "memory_save", "memory_recall", "memory_edit",
    },
    "media": {
        "generate_image", "fetch_stock_image",
    },
    "realtime": {
        "weather_fetch",
    },
    "agency": {
        "ask_user_input", "end_conversation",
    },
}

# ── Keyword Signal Sets ───────────────────────────────────────────────────────

_NONE_RE = re.compile(
    r"^(hello|hi+|hey|good\s+(morning|afternoon|evening|day)|greetings|"
    r"who\s+are\s+you|what\s+can\s+you\s+do|how\s+are\s+you|"
    r"thanks|thank\s+you|sup|yo|testing|test|okay|ok|got\s+it|sure|"
    r"sounds\s+good|perfect|great|nice|cool|awesome|interesting|"
    r"what\s+is\s+(your\s+name|this)|tell\s+me\s+about\s+yourself|"
    r"explain|define|describe|summarize\s+this|help\s+me\s+understand)"
    r"([,\s].*|[!?.]*)$",
    re.IGNORECASE,
)

_RESEARCH_KW = re.compile(
    r"\b(search|find|look up|look for|google|research|news|latest|recent|"
    r"current|update|how much|price of|buy|purchase|"
    r"fetch\s+(?:this\s+|the\s+)?(?:https?://|url|link|page|site|web|data|html)|read this (?:url|link|page)|check this site|scrape|browse|"
    r"trending|breaking|announcement|according to|"
    r"source|citation|reference|verify|fact.?check)\b",
    re.IGNORECASE,
)

_FILE_OPS_KW = re.compile(
    r"\b(write\s+(?:a\s+|the\s+)?(?:\w+\s+)?(?:file|script|code|program|function|class|module)|"
    r"create\s+(?:a\s+|the\s+)?(?:\w+\s+)?(?:file|script|project|app|application)|"
    r"edit\s+(?:this\s+|the\s+)?(?:file|code|script)|fix\s+(?:this\s+|the\s+)?(?:bug|error|code)|"
    r"run\s+(?:this\s+|the\s+)?(?:code|script|command|test)|execute|install|"
    r"terminal|bash|shell|\bls\b|list files|read\s+(?:the\s+|this\s+)?file|open file|"
    r"sandbox|build|compile|refactor|implement|debug|deploy)\b",
    re.IGNORECASE,
)

_DISPLAY_KW = re.compile(
    r"\b(compare|comparison|versus|vs\.?|chart|graph|diagram|"
    r"show me a (chart|table|card|map|quiz|recipe|steps|itinerary)|"
    r"visualize|render|display|draw|plot|table of|side.?by.?side|"
    r"options (card|list)|step.?by.?step|how.?to|recipe for|"
    r"plan (my |a |the )?trip|travel plan|itinerary|directions|route|"
    r"quiz|flashcard|translate|translation|map (of|for|showing))\b",
    re.IGNORECASE,
)

_MEMORY_KW = re.compile(
    r"\b(remember|recall|don.?t forget|save (this|that|my)|"
    r"store (this|that|my)|what did (i|you) say|what (do|did) you know about me|"
    r"my preference|my name is|i prefer|update (my|the) memory|"
    r"correct (that|this)|change (what you know|my preference)|"
    r"forget (that|this))\b",
    re.IGNORECASE,
)

_MEDIA_KW = re.compile(
    r"\b(generate (an?|the) image|create (an?|the) image|draw|illustrate|"
    r"picture of|photo of|stock (image|photo|picture)|fetch (an?|a) (image|photo)|"
    r"image (of|for|showing)|render (an? )?(image|photo))\b",
    re.IGNORECASE,
)

_REALTIME_KW = re.compile(
    r"\b(weather|forecast|temperature|rain|snow|wind|humidity|"
    r"will it rain|umbrella|hot today|cold today|degrees|celsius|fahrenheit|"
    r"outdoor (event|activity)|climate (today|tomorrow|this week))\b",
    re.IGNORECASE,
)

_AGENCY_KW = re.compile(
    r"\b(ask me|what (would|do) you (prefer|want)|give me options|"
    r"do you want (me to|to)|should i (use|do|pick)|choose (from|between)|"
    r"end (this )?(conversation|chat|session)|stop chatting|goodbye|bye)\b",
    re.IGNORECASE,
)

# ── Classifier ───────────────────────────────────────────────────────────────

def classify_intent(query: str) -> str:
    """
    Classify a user message into one of: none, research, file_ops,
    display, memory, media, realtime, agency, all.

    Returns 'all' for multi-intent or ambiguous messages so the model
    always has every tool available when the intent is unclear.
    """
    if not query or not query.strip():
        return "none"

    q = query.strip()

    # Pure conversational → skip all schemas
    if _NONE_RE.match(q):
        logger.debug("CategoryGate: intent=none (conversational)")
        return "none"

    # Score each non-none category
    hits: List[str] = []
    if _RESEARCH_KW.search(q):
        hits.append("research")
    if _FILE_OPS_KW.search(q):
        hits.append("file_ops")
    if _DISPLAY_KW.search(q):
        hits.append("display")
    if _MEMORY_KW.search(q):
        hits.append("memory")
    if _MEDIA_KW.search(q):
        hits.append("media")
    if _REALTIME_KW.search(q):
        hits.append("realtime")
    if _AGENCY_KW.search(q):
        hits.append("agency")

    if len(hits) == 0:
        # No clear signal → safe fallback: full roster
        logger.debug("CategoryGate: intent=all (no signal)")
        return "all"
    if len(hits) == 1:
        logger.debug("CategoryGate: intent=%s", hits[0])
        return hits[0]
    # Multiple signals → full roster to avoid mis-routing
    logger.debug("CategoryGate: intent=all (multi-signal: %s)", hits)
    return "all"


def route_tools(
    query: str,
    all_tools: List[Dict[str, Any]],
    iteration: int = 0,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Returns (category_name, filtered_tool_list).

    Rules:
    - Iteration > 0 (model is already mid-loop, executing a plan):
      always return full roster so it can use any tool freely.
    - Iteration == 0:
      classify the user message and return only the matching slice.
    - 'none' category: returns (category, []) — caller must omit
      the 'tools' key from stream_kwargs entirely.
    """
    # Mid-loop: never prune the roster
    if iteration > 0:
        return "all", all_tools

    category = classify_intent(query)

    if category == "none":
        return "none", []

    if category == "all":
        return "all", all_tools

    # Build the filtered subset
    allowed = _CATEGORY_TOOLS.get(category, set())
    filtered = [t for t in all_tools if t.get("name") in allowed]

    # Safety net: if no tools survive the filter, fall back to full roster
    if not filtered:
        logger.warning(
            "CategoryGate: category '%s' matched but filtered to 0 tools — "
            "falling back to full roster.",
            category,
        )
        return "all", all_tools

    logger.info(
        "CategoryGate: iteration=0 category=%s tools=%s (of %d total)",
        category,
        [t["name"] for t in filtered],
        len(all_tools),
    )
    return category, filtered
