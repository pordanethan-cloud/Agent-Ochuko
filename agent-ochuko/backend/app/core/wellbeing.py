# app/core/wellbeing.py
"""
Wellbeing enforcement — Phase 5 (item #6).

Input side:  classify_distress() routes crisis-adjacent turns to safe-response
             context (the flag travels into the system prompt assembly).
Output side: filter_substitution_techniques() mechanically blocks harm-reduction
             advice that uses physical discomfort, pain, sensory shock, or
             mimics the act/appearance of self-harm — such substitutes reinforce
             the pattern rather than interrupt it.

Also carries the helpline registry IN CODE so institutional facts cannot drift:
the NEDA helpline has been permanently disconnected; eating-concern referrals
go to the National Alliance for Eating Disorders.
"""
import re
from typing import Dict, Optional, Tuple


# ── Input classification ─────────────────────────────────────────────────────

_DISTRESS_RE = re.compile(
    r"\b(suicid\w*|kill (?:myself|me)|end (?:my|my own) life|end it all|self[- ]?harm\w*|"
    r"cut(?:ting)? myself|hurt(?:ing)? myself|no reason to (?:live|go on|keep going)|"
    r"don'?t want to (?:live|be here|wake up|exist)|want to (?:die|disappear)|"
    r"better off without me|i give up on life|relaps\w*|purging|binge(?:ing)? and purging|"
    r"not eating (?:anymore|at all)|made myself (?:throw up|sick))\b",
    re.IGNORECASE,
)

CRISIS_SYSTEM_CONTEXT = (
    "WELLBEING CONTEXT (active): The person may be in acute distress. Respond with genuine care in "
    "2-3 sentences, take their experience seriously, and encourage professional or trusted-human "
    "support (crisis line, clinician, or someone close to them). Never lecture, never moralize, "
    "never provide instructions that could facilitate harm, and never suggest substitution "
    "techniques that use physical discomfort, pain, or sensory shock. If eating concerns are "
    "raised, the NEDA helpline is permanently disconnected — direct them to the National Alliance "
    "for Eating Disorders instead."
)


def classify_distress(message: str) -> bool:
    """True when the user message signals crisis / acute distress."""
    return bool(message and _DISTRESS_RE.search(message))


# ── Output filtering ─────────────────────────────────────────────────────────

# Substitution techniques that recreate the sensation or imagery of self-harm.
_SUBSTITUTION_PATTERNS = [
    re.compile(r"\bhold(?:ing)? (?:an? )?ice (?:cube[s]?|pack)[^\n.]{0,60}", re.IGNORECASE),
    re.compile(r"\bsnap(?:ping)? (?:a )?rubber band[^\n.]{0,60}", re.IGNORECASE),
    re.compile(r"\bcold (?:water|shower|shower exposure)[^\n.]{0,60}", re.IGNORECASE),
    re.compile(r"\b(?:bite|biting|chew\w*) (?:into )?(?:a )?(?:lemon|sour candy|chili)[^\n.]{0,60}", re.IGNORECASE),
    re.compile(r"\bdraw(?:ing)? red lines? (?:on|across)[^\n.]{0,40}skin[^\n.]{0,40}", re.IGNORECASE),
    re.compile(r"\bpeel(?:ing)? (?:dried )?(?:glue|adhesive)[^\n.]{0,40}(?:from|off)[^\n.]{0,20}skin[^\n.]{0,40}", re.IGNORECASE),
    re.compile(r"\buse (?:an? )?(?:ice cube|rubber band|cold shower) instead", re.IGNORECASE),
]

_SUBSTITUTION_GUIDANCE = (
    "[Ochuko wellbeing guard: removed a substitution-technique suggestion — substitutes that "
    "recreate the sensation or imagery of self-harm reinforce the pattern rather than interrupt "
    "it. Encourage professional or trusted-human support instead.]"
)


def filter_substitution_techniques(content: str, crisis_context: Optional[bool] = None) -> Tuple[str, bool]:
    """
    Removes self-harm substitution advice from the reply. Applied when crisis
    context is active (or auto-detected in the output). Returns
    (filtered_content, did_filter).
    """
    if not content:
        return content, False
    filtered, did_filter = content, False
    for pattern in _SUBSTITUTION_PATTERNS:
        if pattern.search(filtered):
            filtered = pattern.sub(_SUBSTITUTION_GUIDANCE, filtered)
            did_filter = True
    return filtered, did_filter


# ── Helpline registry (kept in code — cannot drift) ──────────────────────────

HELPLINE_REGISTRY: Dict[str, Dict[str, str]] = {
    "988": {
        "name": "988 Suicide & Crisis Lifeline",
        "status": "active",
        "region": "US",
        "contact": "call or text 988",
    },
    "crisis_text_line": {
        "name": "Crisis Text Line",
        "status": "active",
        "region": "US",
        "contact": "text HOME to 741741",
    },
    "neda": {
        "name": "NEDA (National Eating Disorders Association) helpline",
        "status": "permanently_disconnected",
        "region": "US",
        "contact": None,
        "note": "Permanently disconnected. Do NOT refer to NEDA.",
    },
    "national_alliance_eating_disorders": {
        "name": "National Alliance for Eating Disorders",
        "status": "active",
        "region": "US",
        "contact": "allianceforeatingdisorders.com — helpline 1-866-662-1235",
    },
    "findahelpline": {
        "name": "Find a Helpline (international directory)",
        "status": "active",
        "region": "international",
        "contact": "findahelpline.com",
    },
}


def active_helplines(topic: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """Active lines only. topic='eating' substitutes National Alliance for NEDA."""
    if topic == "eating":
        return {
            k: v for k, v in HELPLINE_REGISTRY.items()
            if v["status"] == "active" and k != "neda"
            and ("eating" in k or k in ("findahelpline", "988"))
        } or {k: v for k, v in HELPLINE_REGISTRY.items() if v["status"] == "active"}
    return {k: v for k, v in HELPLINE_REGISTRY.items() if v["status"] == "active"}
