# app/core/entity_novelty.py
"""
Entity-novelty detection — Phase 5 (item #13).

"Searching costs seconds. Confabulating costs the user's trust."

Detects proper-noun candidates in the user's message that the conversation has
no knowledge of (not in history, not in prior tool outputs, not a known
stop-concept). When novel entities exist and the turn plans no search, the
router interception layer force-routes to the grounded pipeline so a real
search happens BEFORE synthesis. Unfamiliar capitalized words are almost
certainly names that postdate training — not common nouns.
"""
import re
from typing import Iterable, List, Optional, Set


# Words that are capitalized but never entities (sentence starts, common
# constructs, tool names, days/months, self-references).
_NON_ENTITY = {
    "i", "i'm", "i've", "ok", "okay", "please", "thanks", "thank", "hey", "hi",
    "hello", "yes", "no", "the", "a", "an", "and", "but", "or", "if", "it",
    "this", "that", "these", "those", "what", "who", "when", "where", "why",
    "how", "can", "could", "would", "should", "do", "does", "did", "is",
    "are", "was", "were", "will", "shall", "you", "your", "we", "my", "me",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december", "ochuko",
    "agent", "google", "wikipedia", "github", "youtube", "twitter", "x",
    "reddit", "api", "url", "http", "https", "ai", "ui", "us", "uk", "usa",
    "q1", "q2", "q3", "q4", "h1", "h2", "fy", "fy24", "fy25", "fy26",
}

# Generic sentence-start words that only appear capitalized due to position.
_SENTENCE_STARTERS = {
    "search", "find", "tell", "give", "show", "explain", "compare", "list",
    "make", "build", "write", "create", "get", "need", "want", "look", "check",
    "run", "use", "try", "help", "let", "also", "then", "now", "today",
    "please", "kindly", "quickly", "first", "next", "last", "finally",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]+")


def _candidate_entities(message: str) -> List[str]:
    """
    Capitalized tokens that are NOT sentence-initial-only artifacts.
    Multi-word runs ("Queens Park Rangers") collapse to one candidate.
    """
    candidates: List[str] = []
    tokens = _WORD_RE.findall(message)
    # Mark token positions: is this token sentence-initial?
    sentence_initial = set()
    start = True
    for tok in tokens:
        if start:
            sentence_initial.add(tok.lower())
        start = tok[-1] in ".!?" or tok in (".", "!", "?")
    # Simpler: recompute with punctuation-aware scan
    sentence_initial = set()
    pos_is_start = True
    for m in _WORD_RE.finditer(message):
        tok = m.group(0)
        if pos_is_start:
            sentence_initial.add(tok.lower())
        pos_is_start = message[m.end():m.end() + 2].lstrip(" ")[:1] in (".", "!", "?", "\n")

    for m in _WORD_RE.finditer(message):
        tok = m.group(0)
        low = tok.lower()
        if low in _NON_ENTITY or len(tok) < 2:
            continue
        if tok[0].isupper() and low not in sentence_initial:
            candidates.append(tok)
        elif tok[0].isupper() and low in sentence_initial:
            # Sentence-initial capitalization: only a candidate if the token
            # appears capitalized elsewhere too (mid-sentence occurrence).
            body = re.sub(r"^[\s\W]+|[\s\W]+$", "", message)
            occurrences = re.findall(rf"(?<![\w]){re.escape(tok)}(?![\w])", message[1:])
            if occurrences:
                candidates.append(tok)
    # Deduplicate, preserve order
    seen: Set[str] = set()
    unique = [c for c in candidates if not (c.lower() in seen or seen.add(c.lower()))]
    return unique


def build_known_lexicon(
    conversation_history: Optional[List[str]] = None,
    tool_outputs: Optional[List[str]] = None,
) -> Set[str]:
    """Lowercase vocabulary the conversation already knows about."""
    lexicon: Set[str] = set()
    for text in (conversation_history or []) + (tool_outputs or []):
        if not text:
            continue
        lexicon.update(w.lower() for w in _WORD_RE.findall(text)[:2000])
    return lexicon


def find_unknown_entities(
    message: str,
    known_lexicon: Optional[Set[str]] = None,
) -> List[str]:
    """
    Proper-noun candidates absent from the conversation's known lexicon.
    These are the "postdates training" risks that MUST trigger a search.
    """
    lexicon = known_lexicon or set()
    unknown = []
    for cand in _candidate_entities(message):
        # Split multi-word names: every part must be unknown to flag it.
        parts = [p for p in re.split(r"[-\s]", cand) if p]
        if all(p.lower() not in lexicon for p in parts):
            unknown.append(cand)
    return unknown


def should_force_grounding(
    message: str,
    conversation_history: Optional[List[str]] = None,
    tool_outputs: Optional[List[str]] = None,
    search_planned: bool = False,
) -> bool:
    """
    Router-interception decision: True when the message names entities the
    conversation doesn't know AND no search is planned this turn. The grounded
    pipeline (auto search_web) then runs before synthesis.
    """
    if search_planned:
        return False
    lexicon = build_known_lexicon(conversation_history, tool_outputs)
    return bool(find_unknown_entities(message, lexicon))
