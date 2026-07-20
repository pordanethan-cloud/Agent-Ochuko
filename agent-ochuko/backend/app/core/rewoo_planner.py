"""
ReWOO Plan-and-Execute Module for Agent Ochuko.
Generates an explicit execution plan DAG of tool dependencies upfront,
enabling parallel tool execution and reducing token usage.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PlanStep(BaseModel):
    step_id: int
    tool_name: str
    args: Dict[str, Any]
    depends_on: List[int] = []
    description: str


class ExecutionPlan(BaseModel):
    goal: str
    steps: List[PlanStep]


class ReWOOPlanner:
    """ReWOO DAG Planner for structured multi-step execution."""

    @staticmethod
    def parse_plan(plan_json: str) -> Optional[ExecutionPlan]:
        """Parses a structured execution plan from LLM output."""
        try:
            data = json.loads(plan_json)
            return ExecutionPlan(**data)
        except Exception as e:
            logger.error(f"Failed to parse ReWOO plan: {e}")
            return None

    @staticmethod
    def get_executable_steps(plan: ExecutionPlan, completed_steps: List[int]) -> List[PlanStep]:
        """Returns all steps whose dependencies have been fully satisfied."""
        executable = []
        for step in plan.steps:
            if step.step_id not in completed_steps:
                # Check if all dependencies are satisfied
                if all(dep in completed_steps for dep in step.depends_on):
                    executable.append(step)
        return executable


rewoo_planner = ReWOOPlanner()
