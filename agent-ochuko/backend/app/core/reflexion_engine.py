"""
Reflexion Engine Module for Agent Ochuko.
Captures tool execution failures and python sandbox errors,
generating self-critiques to auto-correct execution code before retrying.
"""
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ExecutionTrial(BaseModel):
    attempt: int
    action: str
    error_output: str
    self_critique: Optional[str] = None


class ReflexionEngine:
    """Manages short-term trial history and verbal self-correction feedback loops."""

    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        self.trials: List[ExecutionTrial] = []

    def record_trial(self, action: str, error_output: str) -> ExecutionTrial:
        """Records a failed execution attempt and prepares self-correction prompt."""
        attempt_num = len(self.trials) + 1
        
        # Simple rule-based reflection heuristic (augmented by LLM self-critique in turn prompt)
        critique = f"Attempt {attempt_num} failed with error: {error_output}. Re-examine arguments, imports, and syntax before retrying."
        
        trial = ExecutionTrial(
            attempt=attempt_num,
            action=action,
            error_output=error_output,
            self_critique=critique
        )
        self.trials.append(trial)
        logger.info(f"ReflexionEngine recorded failed trial {attempt_num}: {error_output[:100]}")
        return trial

    def get_reflection_context(self) -> str:
        """Formats trial reflection history for system prompt injection."""
        if not self.trials:
            return ""

        lines = ["\n[Reflexion History - Previous Execution Errors & Critiques]:"]
        for trial in self.trials:
            lines.append(f"- Trial {trial.attempt} Action: {trial.action}")
            lines.append(f"  Error: {trial.error_output}")
            lines.append(f"  Self-Critique: {trial.self_critique}")

        lines.append("Use the critiques above to avoid repeating previous errors.\n")
        return "\n".join(lines)


def create_reflexion_engine(max_attempts: int = 3) -> ReflexionEngine:
    return ReflexionEngine(max_attempts=max_attempts)
