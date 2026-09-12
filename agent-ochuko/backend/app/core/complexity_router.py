"""Fast, deterministic prompt-complexity routing.

``classify`` is intentionally dependency-free and has no I/O on its hot path. It
uses precompiled regular expressions and bounded integer scoring to assign one
of four reasoning-effort tiers:

    low | medium | high | xhigh

The returned score is useful for observability, while ``signals`` identifies
which scoring families affected the decision. Scores are not a measure of user
intent or message quality; they are routing heuristics only.

Constraint precedence is deliberate: a caller-supplied ``cap`` is a hard upper
bound, including for live-data requests. This permits safety, latency, and
product-policy callers to override the classifier. With no cap, live-data
requests are always routed at least to ``medium``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Pattern, Set

# Bump on any change to scoring, thresholds, or signal patterns. Callers that
# log ComplexityDecision alongside this string can correlate tier drift with
# a specific calibration, which matters once this feeds a billing- or
# quota-sensitive router.
__version__ = "1.1.0"

Tier = str

TIER_ORDER = {"low": 0, "medium": 1, "high": 2, "xhigh": 3}
_ORDER_TO_TIER = {value: name for name, value in TIER_ORDER.items()}

# Score-to-tier thresholds. Keep these module constants so calibration changes
# are explicit and covered by router tests.
_XHIGH_THRESHOLD = 14
_HIGH_THRESHOLD = 9
_MEDIUM_THRESHOLD = 4

# Hard cap on how many characters get regex-scanned for lexical signals. Every
# pattern here is linear (no nested quantifiers), so there's no catastrophic-
# backtracking risk, but ~20 linear passes over an unbounded paste is still
# unbounded total cost on a hot path. This flattens worst-case latency to a
# constant regardless of input size. `prompt_length` (used for the long-input
# score bonus) is measured on the *untruncated* text, so a huge paste still
# reads as "long" even though only its lead is scanned for lexical signals.
# 12,000 chars comfortably covers realistic single-file code pastes and long
# prompts; if production logs show "truncated" firing on legitimate traffic,
# raise this rather than lower the regex budget.
_MAX_SCAN_CHARS = 12_000

# ---------------------------------------------------------------------------
# Precompiled signal patterns
# ---------------------------------------------------------------------------

_TRIVIAL_RE = re.compile(
    r"^(hi|hey|hello|yo|sup|howdy|hola|good\s*(morning|afternoon|evening|night)|"
    r"thanks|thank\s*you|thx|ty|ok|okay|sure|cool|great|nice|got\s*it|noted|"
    r"yes|no|yeah|nah|yep|nope|yup|bye|goodbye|see\s*ya)[\s!?.]*$",
    re.IGNORECASE,
)

_SIMPLE_LOOKUP_RE = re.compile(
    r"\b(weather|temperature|forecast|time\s*in|timezone|what\s*time|local\s*time|"
    r"capital\s+of|who\s+is|what\s+is|where\s+is|when\s+was|how\s+old\s+is|define|"
    r"meaning\s+of|score|scores|standings|fixtures)\b",
    re.IGNORECASE,
)

# Kept dependency-free because model_router imports this module, not vice versa.
_LIVE_QUERY_RE = re.compile(
    r"\b(latest|current|currently|today|now|recent|recently|breaking|news|"
    r"price|prices|rate|rates|update|updated|trending|market|live|forecast)\b",
    re.IGNORECASE,
)

# These verbs are strong evidence of an implementation request. Ambiguous
# verbs such as "write" and "create" are deliberately omitted: on their own,
# they commonly describe non-technical work (for example, "write a poem").
_CODEGEN_VERBS_RE = re.compile(
    r"\b(build|implement|develop|refactor|debug|fix|migrate|program|architect|"
    r"scaffold|integrate|automate|deploy)\b",
    re.IGNORECASE,
)

# Ambiguous authoring verbs count only when technical context is also present.
_AUTHORING_VERBS_RE = re.compile(
    r"\b(create|write|generate|design)\b",
    re.IGNORECASE,
)

_CODE_NOUNS_RE = re.compile(
    r"\b(app|application|api|endpoints?|service|component|functions?|classes?|"
    r"schema|migrations?|databases?|models?|modules?|packages?|libraries?|bots?|"
    r"dashboards?|integrations?|pipelines?|microservices?|crud|backend|frontend|"
    r"full[\s-]?stack|websites?|web\s*apps?|landing\s*pages?|cli|sdk|wrappers?|"
    r"features?|systems?|workflows?|scripts?)\b",
    re.IGNORECASE,
)

_DELIVERABLE_SCALE_RE = re.compile(
    r"\b(full|complete|production[\s-]?ready|from\s+scratch|end[\s-]?to[\s-]?end|"
    r"entire|whole|comprehensive|thorough|robust|scalable|enterprise[\s-]?grade|"
    r"ultra[\s-]?grade|polished)\b",
    re.IGNORECASE,
)

_FILE_EXT_RE = re.compile(
    r"\.(py|ts|tsx|js|jsx|java|go|rs|sql|ya?ml|json|bicep|tf|sh|cs|cpp|c|php|rb|kt|swift|html|css)\b",
    re.IGNORECASE,
)

_FRAMEWORKS_RE = re.compile(
    r"\b(fastapi|react|next(?:\.js)?|vue|angular|svelte|django|flask|"
    r"node(?:\.js)?|express|kubernetes|k8s|docker|terraform|supabase|"
    r"postgres(?:ql)?|mysql|redis|kafka|tailwind|typescript|javascript|python|"
    r"openai|langchain|pydantic|graphql|azure|aws|gcp)\b",
    re.IGNORECASE,
)

# A fenced block or recognisable, line-anchored syntax is strong evidence that
# the user supplied code for implementation, review, or debugging. Anchoring
# avoids treating prose such as "class action" as source code.
_CODE_SYNTAX_RE = re.compile(
    r"```|"
    r"^\s*(?:def|class)\s+[A-Za-z_]\w*\s*(?:\(|:)|"
    r"^\s*(?:from\s+\S+\s+import|import\s+\S+|function\s+\w+\s*\(|"
    r"(?:const|let|var)\s+\w+\s*=|SELECT\b|CREATE\s+TABLE\b)",
    re.IGNORECASE | re.MULTILINE,
)

_LIST_MARKER_RE = re.compile(r"^[ \t]*(?:\d+[.)]|[-*\u2022])[ \t]+", re.MULTILINE)

_CONNECTIVE_RE = re.compile(
    r"\b(and\s+then|step\s*by\s*step|first\b[^.?!]{0,60}\bthen\b|in\s+addition|"
    r"as\s+well\s+as|make\s+sure\s+(?:to|that)|don'?t\s+forget|"
    r"also\s+(?:include|add|make|ensure))\b",
    re.IGNORECASE,
)

_TECH_DEPTH_RE = re.compile(
    r"\b(architecture|scal(?:e|able|ability|ing)|concurren(?:cy|t)|async|parallel(?:ism)?|"
    r"thread(?:ing|s)?|race\s+conditions?|deadlocks?|optimi[sz]e|optimi[sz]ation|"
    r"performance|latency|throughput|cach(?:e|ing)|algorithms?|big[\s-]?o|"
    r"data\s+structures?|security|secure|auth(?:entication|orization)?|encryption|jwt|oauth|"
    r"rate\s+limits?|load\s+balanc\w*|sharding|replication|transactions?|acid|"
    r"normali[sz]ation|design\s+patterns?|unit\s+tests?|ci/?cd|devops|observability|"
    r"technical\s+debt)\b",
    re.IGNORECASE,
)

_ANALYSIS_RE = re.compile(
    r"\b(compare|comparison|versus|vs\.?|pros\s+and\s+cons|trade[\s-]?offs?|"
    r"advantages?|disadvantages?|analy[sz]e|analysis|evaluate|evaluation|assess|"
    r"critique|audit|deep\s+dive|research|investigate|"
    r"why\s+(?:does|is|do|are|would)|how\s+does|explain\s+(?:how|why)|"
    r"implications?|impacts?|recommend\w*|"
    r"best\s+(?:approach|way|practices?|option|strategy))\b",
    re.IGNORECASE,
)

_MATH_RE = re.compile(
    r"\b(calculate|compute|solve\s+(?:for|the)|equations?|probability|derivatives?|"
    r"integrals?|percent(?:age)?|statistics|regression|forecasts?|projections?|"
    r"compound\s+interest|matrices?|algebra|geometry|calculus|variance|medians?)\b",
    re.IGNORECASE,
)

# A bare hyphen between two numbers is far more often a range (pages 3-5,
# 2020-2024, v1-v2) than subtraction, so it only counts when spaced like an
# operator ("10 - 5"). Other operators are unambiguous even unspaced.
_MATH_OPS_RE = re.compile(r"\d+\s*[+*/x^%]\s*\d+|\d+\s+-\s+\d+", re.IGNORECASE)

_STRONG_VERB_RE = re.compile(
    r"\b(design|plan|architect|audit|strategy|roadmap|blueprint|specification)\b",
    re.IGNORECASE,
)


@dataclass
class ComplexityDecision:
    """The deterministic result of a complexity classification."""

    tier: Tier
    score: int
    signals: List[str] = field(default_factory=list)


def _unique_matches(pattern: Pattern[str], text: str) -> Set[str]:
    """Return unique full matches, case-folded, without regex group coupling."""
    return {match.group(0).casefold() for match in pattern.finditer(text)}


def _clamp_tier(
    tier: Tier,
    floor: Optional[Tier] = None,
    cap: Optional[Tier] = None,
) -> Tier:
    """Apply valid constraints; invalid constraints are ignored for compatibility.

    If valid constraints conflict, ``cap`` wins. A cap is used by callers as a
    hard cost ceiling, so it must never be defeated by a classifier floor.
    """
    value = TIER_ORDER.get(tier, TIER_ORDER["medium"])

    floor_value = TIER_ORDER.get(floor.lower()) if isinstance(floor, str) else None
    cap_value = TIER_ORDER.get(cap.lower()) if isinstance(cap, str) else None

    if floor_value is not None:
        value = max(value, floor_value)
    if cap_value is not None:
        value = min(value, cap_value)

    return _ORDER_TO_TIER[value]


def _tier_for_score(score: int) -> Tier:
    """Map a non-negative weighted score to a tier."""
    if score >= _XHIGH_THRESHOLD:
        return "xhigh"
    if score >= _HIGH_THRESHOLD:
        return "high"
    if score >= _MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def classify(
    text: str,
    floor: Optional[Tier] = None,
    cap: Optional[Tier] = None,
) -> ComplexityDecision:
    """Classify a user message into a reasoning-effort tier.

    Args:
        text: User message text. It must be a string.
        floor: Optional minimum tier. Invalid values are ignored for backwards
            compatibility.
        cap: Optional maximum tier. Invalid values are ignored. A valid cap
            takes precedence if it conflicts with ``floor``.

    Returns:
        A ``ComplexityDecision`` containing the selected tier, non-negative raw
        score, and deterministic scoring signals.

    Raises:
        TypeError: If ``text`` is not a string.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    if not text or not text.strip():
        return ComplexityDecision(
            tier=_clamp_tier("low", floor, cap),
            score=0,
            signals=["empty"],
        )

    prompt = text.strip()
    signals: List[str] = []

    # Short-circuit only genuine acknowledgements. A greeting followed by an
    # actual task intentionally falls through to normal scoring.
    if len(prompt) <= 40 and _TRIVIAL_RE.fullmatch(prompt):
        return ComplexityDecision(
            tier=_clamp_tier("low", floor, cap),
            score=0,
            signals=["trivial"],
        )

    if len(prompt) > _MAX_SCAN_CHARS:
        scan_text = prompt[:_MAX_SCAN_CHARS]
        signals.append("truncated")
    else:
        scan_text = prompt

    score = 0

    # -----------------------------------------------------------------------
    # Implementation and technical-artifact signals
    # -----------------------------------------------------------------------
    codegen_hits = _unique_matches(_CODEGEN_VERBS_RE, scan_text)
    if codegen_hits:
        points = min(3 * len(codegen_hits), 6)
        score += points
        signals.append(f"codegen:{len(codegen_hits)}")

    noun_hits = _unique_matches(_CODE_NOUNS_RE, scan_text)
    if noun_hits:
        points = min(len(noun_hits), 3)
        score += points
        signals.append(f"code_nouns:{len(noun_hits)}")

    framework_hits = _unique_matches(_FRAMEWORKS_RE, scan_text)
    extension_hits = _unique_matches(_FILE_EXT_RE, scan_text)
    artifact_points = min(len(framework_hits) + len(extension_hits), 3)
    if artifact_points:
        score += artifact_points
        signals.append(f"tech_artifacts:{artifact_points}")

    # Authoring verbs are intentionally context-sensitive to avoid routing
    # ordinary creative requests as code generation.
    authoring_hits = _unique_matches(_AUTHORING_VERBS_RE, scan_text)
    if authoring_hits and (noun_hits or framework_hits or extension_hits):
        points = min(2 * len(authoring_hits), 4)
        score += points
        signals.append(f"technical_authoring:{len(authoring_hits)}")

    syntax_hits = len(_CODE_SYNTAX_RE.findall(scan_text))
    if syntax_hits:
        points = min(3 + (syntax_hits - 1), 5)
        score += points
        signals.append("code_syntax")

    # -----------------------------------------------------------------------
    # Scale and multi-part specification signals
    # -----------------------------------------------------------------------
    scale_hits = _unique_matches(_DELIVERABLE_SCALE_RE, scan_text)
    if scale_hits:
        points = min(2 * len(scale_hits), 4)
        score += points
        signals.append(f"scale:{len(scale_hits)}")

    structure_points = 0
    list_markers = len(_LIST_MARKER_RE.findall(scan_text))
    if list_markers >= 2:
        structure_points += 2 + min(list_markers - 2, 2)

    connective_hits = len(_CONNECTIVE_RE.findall(scan_text))
    if connective_hits:
        structure_points += min(connective_hits, 2)

    structure_points = min(structure_points, 5)
    if structure_points:
        score += structure_points
        signals.append(f"multi_part:{structure_points}")

    # -----------------------------------------------------------------------
    # Reasoning and quantitative signals
    # -----------------------------------------------------------------------
    depth_hits = _unique_matches(_TECH_DEPTH_RE, scan_text)
    if depth_hits:
        points = min(2 * len(depth_hits), 6)
        score += points
        signals.append(f"tech_depth:{len(depth_hits)}")

    analysis_hits = _unique_matches(_ANALYSIS_RE, scan_text)
    if analysis_hits:
        points = min(2 * len(analysis_hits), 4)
        score += points
        signals.append(f"analysis:{len(analysis_hits)}")

    math_hits = len(_unique_matches(_MATH_RE, scan_text)) + len(_MATH_OPS_RE.findall(scan_text))
    if math_hits:
        points = min(2 * math_hits, 4)
        score += points
        signals.append(f"math:{math_hits}")

    planning_hits = _unique_matches(_STRONG_VERB_RE, scan_text)
    if planning_hits:
        points = min(len(planning_hits), 2)
        score += points
        signals.append(f"planning_verbs:{len(planning_hits)}")

    # Short messages should not be promoted by a single weak lexical match.
    # Do not apply the discount once the prompt has independently accumulated
    # medium-level evidence. This fixes under-routing of requests such as
    # "Build a React app" while keeping "write a poem" inexpensive.
    prompt_length = len(prompt)
    if prompt_length < 80 and score < _MEDIUM_THRESHOLD:
        score = max(0, score - 2)
        signals.append("length:<80")
    elif prompt_length > 600:
        score += 4
        signals.append("length:>600")
    elif prompt_length > 200:
        score += 2
        signals.append("length:>200")

    tier = _tier_for_score(score)

    # -----------------------------------------------------------------------
    # Routing guards
    # -----------------------------------------------------------------------
    # Cheap factual lookups remain cheap only when they have no signals of
    # implementation, deep technical reasoning, comparison, or math work.
    if (
        tier in ("low", "medium")
        and not codegen_hits
        and not authoring_hits
        and not syntax_hits
        and not depth_hits
        and not analysis_hits
        and not math_hits
        and _SIMPLE_LOOKUP_RE.search(scan_text)
    ):
        tier = "low"
        signals.append("simple_lookup_cap")

    # Fresh-data requests need at least normal effort unless the caller has
    # explicitly set a cap. The final clamp below enforces that cap.
    if _LIVE_QUERY_RE.search(scan_text):
        tier = _clamp_tier(tier, floor="medium")
        signals.append("live_query_floor")

    return ComplexityDecision(
        tier=_clamp_tier(tier, floor, cap),
        score=score,
        signals=signals,
    )
