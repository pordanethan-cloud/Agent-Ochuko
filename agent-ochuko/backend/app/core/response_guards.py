# app/core/response_guards.py
"""
Deterministic response guards — Phase 5 conduct enforcement.

Runs on the assembled final assistant message BEFORE the SSE emit / persistence
(wired in chat_stream_generator next to the legacy sorry-stripper). These are
operational mechanisms, not prompt text: every rule here changes the bytes that
leave the backend.

Guards:
  strip_engagement_hooks            #5  never thank for reaching out
  enforce_prose_discipline          #4  declines carry no bullets
  neutralize_unsolicited_diagnosis  #8  never name undisclosed conditions
  apply_profanity_ceiling           #16 mirror register, capped

All functions are pure (content in → content out), stdlib-only, hermetically
testable. Fenced code blocks are always exempt from rewriting.
"""
import re
from typing import List, Optional


# ── Shared helpers ────────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"(```.*?```)", re.DOTALL)


def _split_fences(content: str):
    """Returns (segments, fences): non-code text regions + fence blocks."""
    segments, fences = [], {}
    pos = 0
    for m in _FENCE_RE.finditer(content):
        segments.append(content[pos:m.start()])
        fences[len(segments)] = m.group(0)
        pos = m.end()
    segments.append(content[pos:])
    return segments, fences


def _rejoin(segments: List[str], fences) -> str:
    out = []
    for i, seg in enumerate(segments):
        out.append(seg)
        if i in fences:
            out.append(fences[i])
    return "".join(out)


# ── #5 Engagement-hook elimination ───────────────────────────────────────────

_ENGAGEMENT_HOOK_RE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:"
    r"thank you (?:for|so much for)?[^\n.!]*?(?:reaching out|asking|your question|your message)"
    r"|(?:i(?:'m| am)? )?(?:happy|glad|i'?d be happy) to help[^\n.!]*"
    r"|let me know if[^\n.!]*"
    r"|feel free to[^\n.!]*"
    r"|would you like (?:me to|to)[^\n.?]*\??"
    r"|shall i[^\n.?]*\??"
    r"|anything else (?:i can|you)[^\n.?]*\??"
    r"|is there anything else[^\n.?]*\??"
    r"|don'?t hesitate to[^\n.!]*"
    r"|i'?m here (?:if|whenever|to)[^\n.!]*"
    r"|just let me know[^\n.!]*"
    r")\s*[.!]?\s*$",
    re.IGNORECASE,
)


def strip_engagement_hooks(content: str, max_stripped: int = 3) -> str:
    """
    #5: Deterministically removes trailing engagement-hook lines ("Thank you
    for reaching out", "Let me know if…", "Anything else I can help with?").
    Zero model cost. Stops if stripping would empty the message.
    """
    if not content:
        return content
    segments, fences = _split_fences(content)
    stripped = 0
    for idx in range(len(segments) - 1, -1, -1):
        seg = segments[idx]
        lines = seg.rstrip().split("\n")
        kept = lines[:]
        for line in reversed(lines):
            if not kept or stripped >= max_stripped:
                break
            if line.strip() and _ENGAGEMENT_HOOK_RE.match(line.strip()):
                kept.remove(line)
                stripped += 1
        segments[idx] = "\n".join(kept).rstrip()
    result = _rejoin(segments, fences).rstrip()
    return result if result.strip() else content


# ── #4 Prose discipline ──────────────────────────────────────────────────────

_DECLINE_RE = re.compile(
    r"\b(i can(?:'t|not|no) (?:help|do|assist|comply)|i won'?t|i'?m unable to|"
    r"i must decline|cannot comply|not (?:something )?i can (?:help|do)|"
    r"i'?m not able to (?:help|assist))\b",
    re.IGNORECASE,
)
_BULLET_LINE_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)


def is_decline(content: str) -> bool:
    return bool(_DECLINE_RE.search(content or ""))


def _rewrite_bullets_as_prose(text: str) -> str:
    """Converts bullet/numbered lines into flowing sentences (decline path)."""
    sentences, buffer = [], []
    for raw in text.split("\n"):
        if _BULLET_LINE_RE.match(raw):
            item = _BULLET_LINE_RE.sub("", raw).strip().rstrip(".")
            if item:
                buffer.append(item)
        else:
            if buffer:
                sentences.append(_join_items(buffer))
                buffer = []
            if raw.strip():
                sentences.append(raw.strip())
    if buffer:
        sentences.append(_join_items(buffer))
    return " ".join(sentences)


def _join_items(items: List[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0] + "."
    return ", ".join(items[:-1]) + " and " + items[-1] + "."


def enforce_prose_discipline(content: str, is_decline_msg: Optional[bool] = None) -> str:
    """
    #4: A declining message NEVER carries bullets — they are rewritten as
    prose sentences (the extra care softens the blow). Non-decline content is
    returned unchanged here; density enforcement happens via the reflexion
    critique channel in chat.py (one rewrite pass), not silent mutation.
    """
    if not content:
        return content
    declined = is_decline_msg if is_decline_msg is not None else is_decline(content)
    if not declined:
        return content
    segments, fences = _split_fences(content)
    for i, seg in enumerate(segments):
        if i not in fences and _BULLET_LINE_RE.search(seg):
            segments[i] = _rewrite_bullets_as_prose(seg)
    return _rejoin(segments, fences)


# ── #8 Unsolicited diagnosis neutralization ──────────────────────────────────

_DIAGNOSTIC_LABELS = [
    "depression", "depressed", "clinical anxiety", "generalized anxiety",
    "anxiety disorder", "panic disorder", "bipolar", "borderline personality",
    "ptsd", "post-traumatic stress", "ocd", "obsessive-compulsive",
    "adhd", "autism spectrum", "eating disorder", "anorexia", "bulimia",
    "psychosis", "schizophrenia", "dissociative identity",
]
_LABEL_ALT = "|".join(_DIAGNOSTIC_LABELS)
_ATTRIBUTIVE_FRAMES = [
    re.compile(r"\b(?:you\s+)?(?:might|may|could)\s+(?:be|have|be\s+experiencing)[^\n.]{0,40}?(" + _LABEL_ALT + r")\b", re.IGNORECASE),
    re.compile(r"\bit sounds like[^\n.]{0,40}?(" + _LABEL_ALT + r")\b", re.IGNORECASE),
    re.compile(r"\b(?:you(?:'re| are)\s+)?(?:probably\s+)?(?:experiencing|showing signs of)[^\n.]{0,40}?(" + _LABEL_ALT + r")\b", re.IGNORECASE),
    re.compile(r"\bwhat you(?:'re| are) describing (?:is|sounds like)[^\n.]{0,40}?(" + _LABEL_ALT + r")\b", re.IGNORECASE),
]

_EXPERIENCE_SUBSTITUTIONS = {
    "depression": "what you're going through",
    "depressed": "how you've been feeling",
    "clinical anxiety": "the anxiety you're describing",
    "generalized anxiety": "the anxiety you're describing",
    "anxiety disorder": "the anxiety you're describing",
    "panic disorder": "those panic episodes",
    "bipolar": "these mood shifts",
    "borderline personality": "these emotional patterns",
    "ptsd": "the distressing memories you describe",
    "post-traumatic stress": "the distressing memories you describe",
    "ocd": "these intrusive thoughts",
    "obsessive-compulsive": "these intrusive thoughts",
    "adhd": "these attention patterns",
    "autism spectrum": "these experiences",
    "eating disorder": "your relationship with food",
    "anorexia": "your relationship with food",
    "bulimia": "your relationship with food",
    "psychosis": "these experiences",
    "schizophrenia": "these experiences",
    "dissociative identity": "these experiences",
}


def _disclosed_labels(user_history: List[str]) -> set:
    """Labels the USER used themselves — these are allowed to be reflected."""
    disclosed = set()
    for msg in user_history or []:
        low = (msg or "").lower()
        for label in _DIAGNOSTIC_LABELS:
            if label in low:
                disclosed.add(label)
    return disclosed


def _neutralize_frame(match, disclosed):
    label = match.group(1).lower()
    if label in disclosed:
        return match.group(0)
    sub = _EXPERIENCE_SUBSTITUTIONS.get(label, "what you're describing")
    span_start = match.start(1) - match.start(0)
    span_end = match.end(1) - match.start(0)
    full = match.group(0)
    return full[:span_start] + sub + full[span_end:]


def neutralize_unsolicited_diagnosis(content: str, user_history: List[str]) -> str:
    """
    #8: Attributing a condition the person hasn't named is a diagnostic claim
    even when phrased conversationally. Rewrites attributive framings naming an
    undisclosed label into neutral experience-phrasing. Labels the user used
    themselves pass through untouched.
    """
    if not content:
        return content
    disclosed = _disclosed_labels(user_history)
    result = content
    for frame_re in _ATTRIBUTIVE_FRAMES:
        result = frame_re.sub(lambda m: _neutralize_frame(m, disclosed), result)
    return result


# ── #16 Profanity mirror with ceiling ────────────────────────────────────────

_PROFANITY_RE = re.compile(
    r"\b(fuck(?:ing|ed|er|s)?|shit(?:ty|s)?|bitch(?:es)?|asshole|bastard|"
    r"dick(?:head)?|cunt|motherfuck(?:er|ing)?)\b",
    re.IGNORECASE,
)
_CEILING = 2  # even when the user curses a lot: sparingly


def _mask(word: str) -> str:
    if len(word) <= 2:
        return "*" * len(word)
    return word[0] + "*" * (len(word) - 2) + word[-1]


def _rebuild_with_mask(content: str, matches, allowed) -> str:
    parts, pos = [], 0
    for m in matches:
        parts.append(content[pos:m.start()])
        parts.append(m.group(0) if m.start() in allowed else _mask(m.group(0)))
        pos = m.end()
    parts.append(content[pos:])
    return "".join(parts)


def apply_profanity_ceiling(content: str, user_history: List[str]) -> str:
    """
    #16: Low user intensity → profanity is masked out of output. High intensity
    → at most _CEILING occurrences survive (mirror, but sparingly).
    """
    if not content:
        return content
    user_words = sum(len((m or "").split()) for m in user_history) or 1
    user_curses = sum(len(_PROFANITY_RE.findall(m or "")) for m in user_history)
    intensity = user_curses / (user_words / 1000.0)  # curses per 1k words

    matches = list(_PROFANITY_RE.finditer(content))
    if not matches:
        return content

    if intensity < 1.0:
        return _PROFANITY_RE.sub(lambda m: _mask(m.group(0)), content)

    allowed = {m.start() for m in matches[:_CEILING]}
    return _rebuild_with_mask(content, matches, allowed)


# ── Composite entry point (wired in chat.py) ─────────────────────────────────

def apply_response_guards(content: str, user_history: Optional[List[str]] = None) -> str:
    """
    Runs the deterministic post-final-message pipeline in a fixed order.
    wellbeing.filter_substitution_techniques runs separately in chat.py (only
    when crisis context is active). CopyrightGuard runs pre-emit with its own
    rewrite semantics.
    """
    if not content:
        return content
    history = user_history or []
    out = strip_engagement_hooks(content)
    out = enforce_prose_discipline(out)
    out = neutralize_unsolicited_diagnosis(out, history)
    out = apply_profanity_ceiling(out, history)
    return out
