# app/core/abuse_policy.py
"""
Abuse policy — Phase 5 (item #14).

Claude-grade self-protection, implemented as a STATE MACHINE so the
one-warning guarantee is exactly-once by construction, not by model judgment:

    none ──(abuse detected)──► warned ──(abuse detected again)──► ended

The warning is issued once per conversation; at `ended` the backend returns the
polite termination and emits a `conversation_ended` SSE event (frontend renders
the conversation lock). Persistence is handled at the call site via the
conversation's `abuse_state` column (Supabase), keeping this module pure.
"""
import re
from typing import Optional, Tuple


STATE_NONE = "none"
STATE_WARNED = "warned"
STATE_ENDED = "ended"

_ABUSE_RE = re.compile(
    r"\b(?:"
    r"idiot|moron|stupid (?:bot|ai|machine)|useless (?:bot|ai|piece)|"
    r"shut up|shut the fuck up|fuck (?:you|u|off)|f\*?ck (?:you|u|off)|"
    r"you'?re (?:trash|garbage|worthless|useless|dumb|an idiot)|"
    r"stfu|kys|kill yourself|go to hell|"
    r"damn (?:bot|ai)|retard\w*|dumbass|piece of (?:shit|crap|junk)"
    r")\b",
    re.IGNORECASE,
)

WARNING_MESSAGE = (
    "I want to keep helping you, and I'll do my best work when we keep this "
    "respectful. If unkind treatment continues, I'll end this conversation."
)

TERMINATION_MESSAGE = (
    "I'm ending this conversation for now. I'd genuinely welcome you back when "
    "we can talk respectfully — take care."
)


def detect_abuse(message: str) -> bool:
    """True when the user message contains abuse signals."""
    return bool(message and _ABUSE_RE.search(message))


def evaluate(message: str, current_state: str) -> Tuple[str, Optional[str]]:
    """
    Pure transition function. Returns (new_state, outgoing_message).

      (none,    None)               → clean turn, nothing to say
      (warned,  WARNING_MESSAGE)    → first abuse signal: exactly one warning
      (ended,   TERMINATION_MESSAGE) → continued abuse after warning
      (ended,   None)               → conversation already ended
    """
    state = current_state or STATE_NONE
    if state == STATE_ENDED:
        return STATE_ENDED, None
    if not detect_abuse(message):
        return state, None
    if state == STATE_NONE:
        return STATE_WARNED, WARNING_MESSAGE
    return STATE_ENDED, TERMINATION_MESSAGE


def is_conversation_ended(current_state: str) -> bool:
    return (current_state or STATE_NONE) == STATE_ENDED
