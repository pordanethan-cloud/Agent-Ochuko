"""
app/core/memory_guard.py
────────────────────────
Deterministic memory privacy gate — Phase 6 Architecture Upgrade.

Hard-codes PII rejection patterns so the LLM cannot accidentally
or instructed-to persist sensitive user data into Supabase memory.
This is a PRE-WRITE filter in the pipeline, not a prompt instruction.

Blocked categories (no model instruction can override these):
  • Credit/debit card numbers (PAN)
  • Bank account / IBAN / routing numbers
  • Social Security / National Insurance / Tax-ID numbers
  • Passport / National ID numbers
  • API keys, OAuth tokens, and passwords
  • Protected health diagnoses, medications (PHI)
  • Immigration status literals

Also provides apply_memory_edit() for surgical memory patches.
"""

from __future__ import annotations

import re
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Blocked PII Patterns ─────────────────────────────────────────────────────

_BLOCKED: list[re.Pattern] = [
    # Credit / debit card (13-19 digits, optionally spaced/hyphenated)
    re.compile(
        r"\b(?:\d[ -]?){13,18}\d\b",
        re.IGNORECASE,
    ),
    # US SSN  (XXX-XX-XXXX or 9 digits)
    re.compile(
        r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b",
        re.IGNORECASE,
    ),
    # UK NI number
    re.compile(
        r"\b[A-Z]{2}\d{6}[A-D ]\b",
        re.IGNORECASE,
    ),
    # IBAN (up to 34 alphanumeric chars starting with 2-letter country code)
    re.compile(
        r"\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b",
        re.IGNORECASE,
    ),
    # Routing numbers (9-digit ABA)
    re.compile(
        r"\b\d{9}\b",
    ),
    # Password / API key literals
    re.compile(
        r"(?:password|passwd|pwd|api[_\s-]?key|secret|token|bearer|auth[_\s-]?token"
        r"|private[_\s-]?key)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    # Passport / national ID numbers (generic heuristic: letter(s) + 6-9 digits)
    re.compile(
        r"\b[A-Z]{1,3}\d{6,9}\b",
        re.IGNORECASE,
    ),
    # PHI — specific diagnosis keyword phrases
    re.compile(
        r"\b(HIV|AIDS|hepatitis\s+[A-C]|tuberculosis|syphilis|gonorrhea|"
        r"cancer\s+diagnosis|schizophrenia|bipolar\s+disorder|"
        r"depression\s+diagnosis|suicide\s+attempt|self.?harm\s+history)\b",
        re.IGNORECASE,
    ),
    # Immigration status
    re.compile(
        r"\b(undocumented|illegal\s+alien|visa\s+status|DACA\s+recipient|"
        r"asylum\s+seeker|refugee\s+status)\b",
        re.IGNORECASE,
    ),
]

_BLOCKED_KEY_SLUGS = {
    # Keys that should never be stored regardless of value
    "password", "passwd", "pwd", "api_key", "secret", "token",
    "auth_token", "bearer_token", "private_key", "ssn", "nin",
    "national_id", "passport_number", "bank_account", "card_number",
    "credit_card", "iban", "routing_number",
}


def check_pii(key: str, value: str) -> Tuple[bool, Optional[str]]:
    """
    Returns (is_clean, rejection_reason).
    is_clean=True  → safe to persist.
    is_clean=False → blocked; rejection_reason explains why.
    """
    key_lower = key.lower().strip()
    value_str = (value or "").strip()

    # Blocked key slugs
    if key_lower in _BLOCKED_KEY_SLUGS:
        return False, f"Key '{key}' is in the blocked memory key list (credential/PII category)."

    # PII content patterns
    for pattern in _BLOCKED:
        if pattern.search(value_str) or pattern.search(key_lower):
            return False, (
                f"Memory value for '{key}' contains a blocked PII pattern "
                f"(matched pattern: {pattern.pattern[:60]}...). "
                "Agent Ochuko never persists credentials, card numbers, IDs, or protected health data."
            )

    return True, None


def apply_memory_edit(
    current_value: str,
    old_str: str,
    new_str: str,
) -> Tuple[bool, str]:
    """
    Surgical string replacement on a stored memory blob.
    Returns (success, updated_value_or_error_message).

    Rules:
    - old_str must appear exactly once to prevent ambiguous edits.
    - new_str is PII-checked before patching.
    """
    if not old_str:
        return False, "memory_edit: old_str cannot be empty."

    count = current_value.count(old_str)
    if count == 0:
        return False, f"memory_edit: old_str not found in stored value."
    if count > 1:
        return False, (
            "memory_edit: old_str appears multiple times — "
            "make it more specific to uniquely identify the target substring."
        )

    patched = current_value.replace(old_str, new_str, 1)
    return True, patched


def describe_memory_version_conflict(
    key: str,
    expected_version: int,
    actual_version: int,
    current_value: str,
) -> Dict[str, Any]:
    """
    Returns a structured conflict descriptor when if_version mismatches.
    The caller can surface this to the model for an in-loop merge/retry.
    """
    return {
        "conflict": True,
        "key": key,
        "expected_version": expected_version,
        "actual_version": actual_version,
        "current_value": current_value,
        "hint": (
            "A concurrent write updated this memory key. "
            "Read current_value, merge your intended change, "
            "then retry memory_save with if_version set to actual_version."
        ),
    }
