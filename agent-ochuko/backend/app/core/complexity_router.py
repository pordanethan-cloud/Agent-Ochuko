# app/core/complexity_router.py
"""
ComplexityRouter — rule-based prompt complexity classifier (<1ms, zero cost).

Maps every user message to a reasoning-effort tier:

    low | medium | high | xhigh

Design contract (rule-based, <1ms — the industry default when it works):
  - Pure precompiled regex / keyword / length-threshold heuristics.
  - No I/O, no model calls, no config reads in the hot path — safe to run
    on EVERY message before routing.
  - Deterministic: identical input always yields an identical tier.
  - Weighted signal scoring: each signal family adds points; the total maps
    to a tier via fixed thresholds. Matched signal names are returned for
    routing_reason observability.

Guards:
  - Trivial greetings/acks short-circuit to "low".
  - Simple lookups (weather/time/define) with no technical signals cap at "low".
  - Live/current-data keywords defensively floor the tier at "medium".
  - Callers may pass floor/cap tiers (e.g. agent mode floors at "medium").
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

TIER_ORDER = {"low": 0, "medium": 1, "high": 2, "xhigh": 3}
_ORDER_TO_TIER = {v: k for k, v in TIER_ORDER.items()}

# Score → tier thresholds (module constants — tune here, tests guard behavior)
_XHIGH_THRESHOLD = 14
_HIGH_THRESHOLD = 9
_MEDIUM_THRESHOLD = 4

# ── Precompiled signal patterns ──────────────────────────────────────────────

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

# Duplicated from model_router (kept dependency-free here — model_router
# imports this module, never the reverse).
_LIVE_QUERY_RE = re.compile(
    r"\b(latest|current|currently|today|now|recent|recently|breaking|news|"
    r"price|prices|rate|rates|update|updated|trending|market|live|forecast)\b",
    re.IGNORECASE,
)

_CODEGEN_VERBS_RE = re.compile(
    r"\b(build|create|implement|write|develop|design|refactor|debug|fix|migrate|"
    r"code|program|architect|generate|scaffold|integrate|automate|deploy)\b",
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
    r"claude[\s-]?grade|polished)\b",
    re.IGNORECASE,
)

_FILE_EXT_RE = re.compile(
    r"\.(py|ts|tsx|js|jsx|java|go|rs|sql|ya?ml|json|bicep|tf|sh|cs|cpp|c|php|rb|kt|swift|html|css)\b",
    re.IGNORECASE,
)

_FRAMEWORKS_RE = re.compile(
    r"\b(fastapi|react|next\.?js|vue|angular|svelte|django|flask|node\.?js?|express|"
    r"kubernetes|k8s|docker|terraform|supabase|postgres(?:ql)?|mysql|redis|kafka|"
    r"tailwind|typescript|javascript|python|openai|langchain|pydantic|graphql|"
    r"azure|aws|gcp)\b",
    re.IGNORECASE,
)

_LIST_MARKER_RE = re.compile(r"^[ \t]*(?:\d+[.\)]|[-*\u2022])[ \t]+", re.MULTILINE)

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

_MATH_OPS_RE = re.compile(r"\d+\s*[+\-*/x^%]\s*\d+")

_STRONG_VERB_RE = re.compile(
    r"\b(design|plan|architect|audit|strategy|roadmap|blueprint|specification)\b",
    re.IGNORECASE,
)


@dataclass
class ComplexityDecision:
    """Result of the rule-based complexity classification."""
    tier: str                                            # low|medium|high|xhigh
    score: int                                           # Raw weighted score
    signals: List[str] = field(default_factory=list)     # Matched signal names


def _clamp_tier(tier: str, floor: Optional[str] = None, cap: Optional[str] = None) -> str:
    value = TIER_ORDER.get(tier, 1)
    if floor and floor in TIER_ORDER:
        value = max(value, TIER_ORDER[floor])
    if cap and cap in TIER_ORDER:
        value = min(value, TIER_ORDER[cap])
    return _ORDER_TO_TIER[value]


def classify(
    text: str,
    floor: Optional[str] = None,
    cap: Optional[str] = None,
) -> ComplexityDecision:
    """
    Classify a user message into a reasoning-effort tier.

    Args:
        text: The user message text.
        floor: Optional minimum tier (e.g. "medium" for agent/live-data requests).
        cap: Optional maximum tier.

    Returns:
        ComplexityDecision with tier, raw score, and matched signal names.
    """
    if not text or not text.strip():
        return ComplexityDecision(tier=_clamp_tier("low", floor, cap), score=0, signals=["empty"])

    t = text.strip()
    signals: List[str] = []

    # ── Short-circuit: trivial greetings / acknowledgments ────────────────
    if len(t) <= 40 and _TRIVIAL_RE.match(t):
        return ComplexityDecision(tier=_clamp_tier("low", floor, cap), score=0, signals=["trivial"])

    score = 0

    # ── Code-gen intent ───────────────────────────────────────────────────
    codegen_hits = {h.lower() for h in _CODEGEN_VERBS_RE.findall(t)}
    if codegen_hits:
        pts = min(3 * len(codegen_hits), 6)
        score += pts
        signals.append(f"codegen:{len(codegen_hits)}")

    noun_hits = {h.lower() for h in _CODE_NOUNS_RE.findall(t)}
    if noun_hits:
        pts = min(len(noun_hits), 3)
        score += pts
        signals.append(f"code_nouns:{len(noun_hits)}")

    # ── Deliverable scale ─────────────────────────────────────────────────
    scale_hits = {h.lower() for h in _DELIVERABLE_SCALE_RE.findall(t)}
    if scale_hits:
        pts = min(2 * len(scale_hits), 4)
        score += pts
        signals.append(f"scale:{len(scale_hits)}")

    # ── Files & frameworks ────────────────────────────────────────────────
    ext_hits = _FILE_EXT_RE.findall(t)
    fw_hits = {h.lower() for h in _FRAMEWORKS_RE.findall(t)}
    artifact_pts = min(len(ext_hits) + len(fw_hits), 3)
    if artifact_pts:
        score += artifact_pts
        signals.append(f"tech_artifacts:{artifact_pts}")

    # ── Multi-part structure ──────────────────────────────────────────────
    structure_pts = 0
    list_markers = len(_LIST_MARKER_RE.findall(t))
    if list_markers >= 2:
        structure_pts += 2 + min(list_markers - 2, 2)
    connective_hits = len(_CONNECTIVE_RE.findall(t))
    if connective_hits:
        structure_pts += min(connective_hits, 2)
    structure_pts = min(structure_pts, 5)
    if structure_pts:
        score += structure_pts
        signals.append(f"multi_part:{structure_pts}")

    # ── Technical depth ───────────────────────────────────────────────────
    depth_hits = {h.lower() for h in _TECH_DEPTH_RE.findall(t)}
    if depth_hits:
        pts = min(2 * len(depth_hits), 6)
        score += pts
        signals.append(f"tech_depth:{len(depth_hits)}")

    # ── Analysis / comparison intent ──────────────────────────────────────
    analysis_hits = {h.lower() for h in _ANALYSIS_RE.findall(t)}
    if analysis_hits:
        pts = min(2 * len(analysis_hits), 4)
        score += pts
        signals.append(f"analysis:{len(analysis_hits)}")

    # ── Math / quantitative ───────────────────────────────────────────────
    math_hits = len(_MATH_RE.findall(t)) + len(_MATH_OPS_RE.findall(t))
    if math_hits:
        pts = min(2 * math_hits, 4)
        score += pts
        signals.append(f"math:{math_hits}")

    # ── Strong planning verbs ─────────────────────────────────────────────
    verb_hits = {h.lower() for h in _STRONG_VERB_RE.findall(t)}
    if verb_hits:
        pts = min(len(verb_hits), 2)
        score += pts
        signals.append(f"planning_verbs:{len(verb_hits)}")

    # ── Length band ───────────────────────────────────────────────────────
    n = len(t)
    if n < 80:
        score -= 2
    elif n > 600:
        score += 4
        signals.append("length:>600")
    elif n > 200:
        score += 2
        signals.append("length:>200")

    # ── Tier mapping ──────────────────────────────────────────────────────
    if score >= _XHIGH_THRESHOLD:
        tier = "xhigh"
    elif score >= _HIGH_THRESHOLD:
        tier = "high"
    elif score >= _MEDIUM_THRESHOLD:
        tier = "medium"
    else:
        tier = "low"

    # ── Guards ────────────────────────────────────────────────────────────
    # Simple lookups with zero technical signals stay cheap.
    if (
        tier == "medium"
        and not codegen_hits and not depth_hits and not analysis_hits
        and _SIMPLE_LOOKUP_RE.search(t)
    ):
        tier = "low"
        signals.append("simple_lookup_cap")

    # Live-data queries must never get lazy effort (defensive floor; callers
    # may apply a stronger floor via the `floor` argument).
    if _LIVE_QUERY_RE.search(t):
        tier = _clamp_tier(tier, floor="medium", cap=cap)
        signals.append("live_query_floor")

    return ComplexityDecision(tier=_clamp_tier(tier, floor, cap), score=score, signals=signals)
