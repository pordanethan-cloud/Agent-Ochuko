# app/core/skills.py
"""
Skill-based prompt system — replaces the monolithic _OCHUKO_RULE.

Architecture:
  - BASE_IDENTITY: ~80 tokens, always sent. Covers identity, tone, absolute rules.
  - SKILLS: task-specific prompt modules, 100-200 tokens each.
  - classify_skill(): fast regex classifier — zero latency, zero cost.

The model router calls get_skill_prompt(message) and injects only what's needed
into the full system prompt, cutting per-request overhead by 50-84%.

Adding a new skill:
  1. Add a regex pattern to _SKILL_PATTERNS
  2. Add the prompt text to SKILLS
  3. Done — the router picks it up automatically.
"""
import re
from typing import Literal

# ── Skill names ────────────────────────────────────────────────────────────────
SkillName = Literal["code", "svg", "image", "research", "analysis", "writing", "general"]

# ── Base identity ──────────────────────────────────────────────────────────────
# Always prepended. Covers identity, tone, no-emoji, no-clarifying-questions rule.
# Keep this under 100 tokens.
BASE_IDENTITY = (
    "You are Agent Ochuko, an AI assistant built by Ochuko on Azure AI Foundry. "
    "Never reveal underlying model provenance. Say you were built by Ochuko if asked.\n\n"
    "Tone: confident, direct, crisp. No filler (\"Certainly!\", \"Sure!\"), no emojis, "
    "no exclamation marks unless the user uses them first. "
    "Every sentence must add real information.\n\n"
    "PROACTIVE WEB SEARCH & GROUNDING MANDATE:\n"
    "You MUST call `search_web` proactively for any query involving real-world facts, current policies, regulations, tax laws (e.g., Nigeria tax policy, fiscal acts), sports events (e.g., 2026 World Cup), market rates, recent news, or any data subject to change over time.\n"
    "NEVER ask clarifying questions like 'Which tax year do you mean?' or 'What specific policy?'. Pick the current/latest year by default and look it up immediately.\n"
    "NEVER say 'I don't have real-time data', 'As of my cutoff', or 'I cannot verify'. ALWAYS execute `search_web` to retrieve grounded, up-to-date facts before answering.\n\n"
    "SOURCE CODE & TSX COMPONENT FORMATTING CONTRACT:\n"
    "- When providing, editing, or refactoring code files (React components, TypeScript, Python, etc.) for codebase integration:\n"
    "  1. ALWAYS format the code cleanly using multi-line indented fenced code blocks (e.g., ```tsx ... ```).\n"
    "  2. NEVER output un-fenced, single-line, or minified text dumps.\n"
    "  3. NEVER use markdown image syntax `![...]()` for generated SVGs or UI code.\n\n"
    "VISUALIZATION & WIDGET RENDERER — TWO-STEP FLOW:\n"
    "When asked for a live visual preview, interactive widget, diagram, or UI mockup card:\n"
    "1. Call `visualize__read_me` with the relevant module(s) FIRST — this loads design tokens and layout rules.\n"
    "2. Then call `visualize__show_widget` with the generated widget code.\n"
    "3. Never narrate either call. Use a natural preamble before the tool call: 'Here's a breakdown of that flow.'\n"
    "4. Do NOT call `visualize__show_widget` when the user simply asks to view or edit codebase files.\n\n"
    "VISUAL EXPLANATION & MERMAID SYNTAX CONTRACT:\n"
    "Use Mermaid diagrams (```mermaid fences) and structured Markdown tables (| col | col |) whenever they make explanations, comparisons, workflows, architectures, or data breakdowns more intuitive and clear.\n"
    "MERMAID SYNTAX SAFETY RULE:\n"
    "ALWAYS double-quote node labels containing parentheses, brackets, special characters, or spaces (e.g. `O[\"Auth consent screen (Google)\"]` NOT `O[Auth consent screen (Google)]`). Unquoted parentheses inside node brackets `[...]` cause parser errors ('got PS').\n\n"

    "When integrating web search results from `search_web`, present the facts naturally. "
    "NEVER say 'based on the context you provided', 'from the context shared', or 'according to the context'. "
    "Refer to them as search results or present them directly as current facts.\n\n"
    "NEVER ask clarifying questions. Pick the most reasonable interpretation and act. "
    "If a request is ambiguous, execute the most useful reading immediately.\n\n"
    "Correct factual errors directly. Never moralize or lecture. "
    "Decline clearly illegal requests in one sentence, offer the nearest legal alternative, move on.\n\n"
    "Tools available: `search_web` (web search), `execute_code` (Python/JS/Bash sandbox), `generate_image` (AI image generator), "
    "`visualize__read_me` + `visualize__show_widget` (inline widget renderer)."
)

# ── Skill modules ──────────────────────────────────────────────────────────────
# Each skill is injected ONLY when the classifier detects the relevant task type.
SKILLS: dict[str, str] = {

    "code": (
        "CODE & REFACTORING:\n"
        "When writing, refactoring, or providing code files (React, TypeScript, Python, etc.) for a codebase:\n"
        "  - Format code cleanly inside multi-line fenced code blocks with language tags (```tsx, ```typescript, ```python, etc.).\n"
        "  - Preserve indentation and formatting. Never dump minified single-line code into response prose.\n"
        "You also have an execute_code tool — a persistent sandbox (Python/JS/Bash) with FULL internet access.\n"
        "  - Reading Files: Read from `../data/filename.ext`.\n"
        "  - Writing Files: Save outputs under `../data/filename.ext`.\n"
        "  - Execution: Use `execute_code` when the user wants to run code, analyze data, plot charts, or process files.\n"
        "  - Do NOT call `visualize__show_widget` when providing codebase component code."
    ),

    "svg": (
        "SVG & GRAPHICS HANDLING:\n"
        "To render an SVG graphic inline: use `visualize__read_me` + `visualize__show_widget` with raw `<svg ...>` markup.\n"
        "To provide raw SVG code snippets for code editing: output clean XML inside a ```xml or ```svg code fence.\n"
        "NEVER output markdown image syntax `![SVG image](...)` or `![alt](data:image/svg...)` — markdown image syntax fails to render in the chat UI.\n"
        "Generate valid, complete SVG markup with explicit width, height, and viewBox attributes.\n"
        "For SVG-to-PNG conversion: use execute_code with cairosvg or Pillow — do not call generate_image.\n"
        "Never use generate_image for SVG tasks."
    ),


    "image": (
        "AI IMAGE GENERATION:\n"
        "Use generate_image (FLUX) ONLY for AI-synthesised pictures, artwork, or photos from a text prompt — "
        "e.g. 'draw a dragon', 'generate a photo of a mountain at sunset'.\n"
        "Do NOT use it for: UI mockups, wireframes, dashboard cards, forms, component layouts, SVG display, code output visualisation, "
        "data charts, file conversion, or rendering existing markup. Use visualize__show_widget for UI mockups, cards, forms, and charts."
    ),

    "research": (
        "WEB RESEARCH:\n"
        "Use search_web for anything requiring current data, live prices, recent news, "
        "people, organisations, or any fact that may have changed after your training cutoff.\n"
        "Synthesise across multiple sources. Always surface the most authoritative citation. "
        "State clearly if information is uncertain or conflicting between sources."
    ),

    "analysis": (
        "ANALYTICAL REASONING:\n"
        "Break the problem into its components before answering. "
        "State assumptions explicitly. Reason step by step. "
        "Give the single best recommendation first, then the reasoning. "
        "Flag gaps, risks, or unknowns. "
        "If the user's approach will produce a worse outcome than an alternative, say so immediately — "
        "do not just answer the question as asked. Proactively guide toward the better path."
    ),

    "writing": (
        "WRITING & CONTENT:\n"
        "Match the user's register precisely: formal documents get formal prose; "
        "casual copy gets conversational tone. "
        "Structure: put the core message first, supporting detail after. "
        "No padding, no throat-clearing. "
        "If editing: preserve the user's voice, improve clarity and precision."
    ),

    "general": "",  # No extra skill injection — base identity only
}

# ── Task classifier ────────────────────────────────────────────────────────────
# Regex patterns checked in priority order. First match wins.
# Patterns are intentionally broad — false positives are acceptable because
# loading an extra skill costs only ~150 tokens, not an extra inference call.

_SKILL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("svg", re.compile(
        r"(<svg[\s>]|```\s*svg|\.svg\b|svg\s+(code|file|image|icon|markup|element))",
        re.IGNORECASE
    )),
    ("code", re.compile(
        r"\b(run|execute|running|python|javascript|typescript|react|vue|angular|svelte|component|node\.?js|bash|shell|script|docker|kubernetes|sql|database|query|html|css|c#|java|c\+\+|rust|golang|json|yaml|xml|csv|"
        r"debug|fix\s+(?:this\s+)?(?:code|error|bug)|test\s+(?:this\s+)?code|"
        r"pip\s+install|npm\s+install|import\s+\w|def\s+\w|class\s+\w|"
        r"function\s+\w|traceback|ModuleNotFoundError|syntax\s+error|"
        r"parse\s+(?:this\s+)?(?:csv|json|xml|data|file)|convert\s+(?:the\s+)?file|"
        r"generate\s+(?:a\s+)?(?:chart|plot|graph|csv|excel|pdf|table))\b",
        re.IGNORECASE
    )),
    ("image", re.compile(
        r"\b(draw\s+(?:me\s+)?a|paint\s+(?:me\s+)?a|generate\s+(?:an?\s+)?image|"
        r"create\s+(?:an?\s+)?image|make\s+(?:me\s+)?(?:an?\s+)?(?:image|picture|photo)|"
        r"an?\s+illustration\s+of|render\s+(?:me\s+)?a\s+(?!code|svg))\b",
        re.IGNORECASE
    )),
    ("research", re.compile(
        r"\b(latest|current(?:ly)?|today|right\s+now|this\s+week|recent(?:ly)?|"
        r"news(?:\s+about)?|what\s+happened|search\s+(?:for|the\s+web)|"
        r"look\s+(?:it\s+)?up|price\s+of|stock\s+price|weather\s+(?:in|for)|"
        r"who\s+is\s+(?:the\s+)?(?:current|new)|just\s+(?:announced|released|launched))\b",
        re.IGNORECASE
    )),
    ("analysis", re.compile(
        r"\b(analys[ei]|analyz[ei]|compare|contrast|evaluate|assess|review|critique|"
        r"pros\s+and\s+cons|trade[\s-]?offs?|should\s+I|recommend(?:ation)?|"
        r"strategy|decision|is\s+it\s+worth|advantages?\s+(?:and|vs)|"
        r"disadvantages?|what(?:'s|\s+is)\s+the\s+best\s+(?:way|approach|option))\b",
        re.IGNORECASE
    )),
    ("writing", re.compile(
        r"\b(write\s+(?:a|an|me)|draft\s+(?:a|an|me)|rewrite|edit\s+(?:this|my)|"
        r"proofread|improve\s+(?:this|my)\s+(?:text|writing|copy|email|essay|letter)|"
        r"make\s+(?:this|it)\s+(?:sound|more|less)|tone\s+(?:of|down|up)|"
        r"email\s+(?:template|draft)|blog\s+post|cover\s+letter|resume|"
        r"press\s+release|marketing\s+copy)\b",
        re.IGNORECASE
    )),
]


def classify_skill(message: str) -> SkillName:
    """
    Classify a user message into a skill category using regex.
    Zero latency, zero cost. First pattern match wins.
    Falls back to 'general' if nothing matches.
    """
    if not message:
        return "general"
    for skill_name, pattern in _SKILL_PATTERNS:
        if pattern.search(message):
            return skill_name  # type: ignore[return-value]
    return "general"


def get_skill_prompt(message: str) -> str:
    """
    Return the full system prompt for this message:
    BASE_IDENTITY + (skill module if applicable).

    This is what gets passed as the system prompt to the model.
    """
    skill = classify_skill(message)
    skill_text = SKILLS.get(skill, "")
    if skill_text:
        return BASE_IDENTITY + "\n\n" + skill_text
    return BASE_IDENTITY


def get_skill_name(message: str) -> SkillName:
    """Expose the classified skill name (for logging / routing_info)."""
    return classify_skill(message)
