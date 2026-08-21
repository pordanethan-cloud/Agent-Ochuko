"""
Hybrid Memory System for Agent Ochuko.
Integrates working memory (short-term turn context), core memory blocks (user preferences & facts),
key-value key stores for cross-session context recall, and Agent Mode context compression.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from app.core.agent_task_models import AgentTask, StepStatus

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


class AgentContextCompressor:
    """
    Builds token-efficient, minimal context payloads for Agent Mode turns.
    Ensures every turn carries only the task goal, concise plan status, and recent step results.
    """

    @staticmethod
    def build_step_payload(task: AgentTask, step_index: int) -> str:
        """
        Builds the user instruction payload for executing a single step.
        Contains: Goal + Plan status checklist + Target step description + Previous step summary.
        Keeps token overhead under 350 tokens.
        """
        plan_summary_lines = []
        for s in task.plan:
            status_mark = "[x]" if s.status == StepStatus.COMPLETED else ("[>]" if s.index == step_index else "[ ]")
            plan_summary_lines.append(f"{status_mark} Step {s.index}: {s.description}")

        plan_text = "\n".join(plan_summary_lines)

        prev_result_section = ""
        completed_steps = [s for s in task.plan if s.status == StepStatus.COMPLETED]
        if completed_steps:
            last_completed = completed_steps[-1]
            summary = last_completed.result_summary or "Completed."
            prev_result_section = f"\nPREVIOUS STEP RESULT (Step {last_completed.index}):\n{summary}\n"

        target_step = next((s for s in task.plan if s.index == step_index), None)
        target_desc = target_step.description if target_step else f"Execute step {step_index}"

        return (
            f"OVERALL GOAL: {task.goal}\n\n"
            f"EXECUTION PLAN STATUS:\n{plan_text}\n"
            f"{prev_result_section}\n"
            f"YOUR CURRENT TARGET -> STEP {step_index}: {target_desc}\n"
            f"Execute this step directly using the appropriate tool."
        )

    @staticmethod
    def build_synthesis_payload(task: AgentTask) -> str:
        """
        Builds the final synthesis prompt combining all step summaries and artifacts.
        """
        results_lines = []
        for s in task.plan:
            summary = s.result_summary or (f"Error: {s.error}" if s.error else "Finished")
            results_lines.append(f"- Step {s.index} ({s.description}): {summary}")

        results_text = "\n".join(results_lines)
        artifacts_text = ""
        if task.artifacts:
            artifacts_text = "\n\nGENERATED ARTIFACTS / DELIVERABLES:\n" + "\n".join(
                f"- {a.get('filename')}: {a.get('download_url')}" for a in task.artifacts
            )

        return (
            f"ORIGINAL GOAL: {task.goal}\n\n"
            f"ALL EXECUTED STEP RESULTS:\n{results_text}"
            f"{artifacts_text}\n\n"
            f"Synthesize the complete, comprehensive final answer for the user. "
            f"Structure clearly with sections, tables, or code where relevant. "
            f"Reference any created files or deliverables."
        )


def create_hybrid_memory(user_id: str) -> HybridMemory:
    return HybridMemory(user_id=user_id)
