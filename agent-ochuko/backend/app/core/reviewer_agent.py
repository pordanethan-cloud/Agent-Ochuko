"""
Reviewer Agent Module for Agent Ochuko.
Independent marker sub-agent evaluating output deliverables against original user requirements
before final delivery.
"""
import logging
from typing import Tuple, Optional, List
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ReviewResult(BaseModel):
    is_approved: bool
    feedback: str
    missing_requirements: List[str] = []


class ReviewerAgent:
    """Audits builder output against user requirements."""

    @staticmethod
    def audit_output(user_prompt: str, generated_output: str, generated_files: List[str] = None) -> ReviewResult:
        """
        Audits output deliverable.
        Checks for missing sub-requirements or unfulfilled prompt constraints.
        """
        generated_files = generated_files or []
        missing = []

        prompt_lower = user_prompt.lower()
        
        # Heuristic checks for common requested items
        if "signature" in prompt_lower and not any("sign" in f.lower() or "doc" in f.lower() or "pdf" in f.lower() for f in generated_files):
            if "signature" not in generated_output.lower():
                missing.append("Extracted signature placement")

        if "letterhead" in prompt_lower and not generated_files:
            if "letterhead" not in generated_output.lower():
                missing.append("Document letterhead application")

        if missing:
            feedback = f"ReviewerAgent flag: Output is missing key elements: {missing}"
            logger.warning(feedback)
            return ReviewResult(is_approved=False, feedback=feedback, missing_requirements=missing)

        logger.info("ReviewerAgent approved output deliverable.")
        return ReviewResult(is_approved=True, feedback="Output approved.")


reviewer_agent = ReviewerAgent()
