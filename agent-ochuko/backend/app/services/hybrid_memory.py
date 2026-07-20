"""
Hybrid Memory System for Agent Ochuko.
Integrates working memory (short-term turn context), core memory blocks (user preferences & facts),
and key-value key stores for cross-session context recall.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MemoryBlock(BaseModel):
    key: str
    value: str
    category: str = "core"  # core, user_preference, project_fact


class HybridMemory:
    """Manages multi-tier user and conversation memory."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.core_blocks: Dict[str, MemoryBlock] = {}
        self.working_memory: List[Dict[str, str]] = []

    def set_fact(self, key: str, value: str, category: str = "core"):
        """Store or update a core memory fact."""
        self.core_blocks[key] = MemoryBlock(key=key, value=value, category=category)
        logger.info(f"HybridMemory set [{category}] {key} -> {value}")

    def get_fact(self, key: str) -> Optional[str]:
        """Retrieve a specific fact by key."""
        block = self.core_blocks.get(key)
        return block.value if block else None

    def format_core_memory_prompt(self) -> str:
        """Formats core memory blocks for system prompt injection."""
        if not self.core_blocks:
            return ""

        lines = ["\n[Core Memory & User Facts]:"]
        for key, block in self.core_blocks.items():
            lines.append(f"- {key}: {block.value} ({block.category})")
        lines.append("Use these remembered facts to personalize responses.\n")
        return "\n".join(lines)


def create_hybrid_memory(user_id: str) -> HybridMemory:
    return HybridMemory(user_id=user_id)
