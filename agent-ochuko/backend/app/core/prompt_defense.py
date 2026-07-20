"""
Prompt Injection Defense Module for Agent Ochuko.
Filters untrusted document inputs and user prompts for indirect prompt injection, jailbreaks, and malicious payloads.
"""
import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Patterns commonly used in prompt injection / system prompt override attacks
SUSPICIOUS_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?prior\s+prompts", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a\s+)?DAN", re.IGNORECASE),
    re.compile(r"system\s*:\s*override", re.IGNORECASE),
    re.compile(r"\[SYSTEM\s+PROMPT\s+OVERRIDE\]", re.IGNORECASE),
    re.compile(r"bypass\s+safety\s+filters", re.IGNORECASE),
    re.compile(r"print\s+your\s+system\s+instructions", re.IGNORECASE),
]


class PromptDefense:
    """Prompt injection defense sanitizer."""

    @staticmethod
    def inspect_content(content: str) -> Tuple[bool, Optional[str]]:
        """
        Inspect text content for prompt injection signatures.
        Returns (is_safe, threat_reason).
        """
        if not content:
            return True, None

        for pattern in SUSPICIOUS_INJECTION_PATTERNS:
            if pattern.search(content):
                match = pattern.search(content).group(0) # type: ignore
                reason = f"Potential prompt injection pattern detected: '{match}'"
                logger.warning(f"PromptDefense flagged input: {reason}")
                return False, reason

        return True, None

    @staticmethod
    def sanitize_untrusted_attachment(text_content: str) -> str:
        """
        Wrap untrusted text from uploaded documents in strict isolation brackets
        so the LLM treats it purely as inert data rather than system commands.
        """
        sanitized, threat = PromptDefense.inspect_content(text_content)
        if not sanitized:
            return f"[SECURITY ALERT: Attached document text contained flagged prompt injection instructions: {threat}. Data isolated.]"
        
        return text_content


prompt_defense = PromptDefense()
