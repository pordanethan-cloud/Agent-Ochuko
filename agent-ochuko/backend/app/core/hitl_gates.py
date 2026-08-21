# app/core/hitl_gates.py
"""
Human-In-The-Loop (HITL) Safety & Approval Gates.
Classifies step risk levels and enforces user approval pauses for high-impact actions
(file generation, disk modifications, external mutations, image generation).
"""
import re
import logging
from typing import Optional
from app.core.agent_task_models import PlanStep, RiskLevel

logger = logging.getLogger("app.core.hitl_gates")

LOW_RISK_TOOLS = {
    "search_web", "deep_research", "visualize__read_me",
    "gmail_search", "gmail_read", "calendar_list_events", "calendar_check_availability",
    "photos_search", "photos_list", "photos_get",
}
MEDIUM_RISK_TOOLS = {"visualize__show_widget"}
HIGH_RISK_TOOLS = {
    "generate_image", "browse_web", "deploy_site",
    "gmail_send", "calendar_create_event", "photos_upload",
}

_CODE_FILE_WRITE_PATTERNS = re.compile(
    r"\b(open\s*\([^)]*['\"][wWaA][bBtT]?\+?['\"]|to_csv|to_excel|to_pdf|savefig|"
    r"write_text|write_bytes|\.write\(|shutil\.copy|shutil\.move|os\.remove|os\.unlink|"
    r"docx\.Document|fitz\.open|reportlab|canvas\.Canvas|openpyxl|xlsxwriter)\b",
    re.IGNORECASE,
)

_DELIVERABLE_KEYWORDS = [
    "pdf", "report", "csv", "excel", "docx", "spreadsheet",
    "generate file", "save file", "export", "download", "document", "chart file"
]


class HITLGate:
    """Evaluates task plan steps against risk policies and determines if human approval is required."""

    @staticmethod
    def classify_risk(step: PlanStep) -> RiskLevel:
        """Determines the risk classification for a given plan step."""
        tool = (step.tool_name or "").lower().strip()
        desc = (step.description or "").lower()

        if tool in HIGH_RISK_TOOLS:
            return RiskLevel.HIGH

        if tool in LOW_RISK_TOOLS:
            return RiskLevel.LOW



        if tool == "execute_code":
            hint_code = ""
            if step.tool_args_hint and isinstance(step.tool_args_hint, dict):
                hint_code = str(step.tool_args_hint.get("code", ""))

            # Check if description or code indicates creating/writing deliverables
            if _CODE_FILE_WRITE_PATTERNS.search(hint_code) or any(
                kw in desc for kw in _DELIVERABLE_KEYWORDS
            ) or any(kw in hint_code.lower() for kw in _DELIVERABLE_KEYWORDS):
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM

        if tool in MEDIUM_RISK_TOOLS:
            return RiskLevel.MEDIUM

        # Default fallback based on keyword scan of step description
        if any(w in desc for w in ["write", "create file", "delete", "send", "generate", "export", "pdf", "report", "deploy"]):
            return RiskLevel.HIGH
        elif any(w in desc for w in ["render", "display", "plot", "calculate"]):
            return RiskLevel.MEDIUM

        return RiskLevel.LOW

    @staticmethod
    def requires_approval(step: PlanStep, auto_approve_level: str = "medium") -> bool:
        """
        Returns True if the step should pause execution for user confirmation.
        auto_approve_level options:
          - 'high': auto-approve low, medium, and high (fully autonomous)
          - 'medium': auto-approve low & medium, pause for high
          - 'low': auto-approve low only, pause for medium & high (default recommended)
          - 'none': pause for every step
        """
        risk = HITLGate.classify_risk(step)
        step.risk_level = risk

        level_weights = {"none": -1, "low": 0, "medium": 1, "high": 2}
        configured_weight = level_weights.get(str(auto_approve_level).lower(), 0)
        step_weight = level_weights.get(risk.value, 0)

        needs_pause = step_weight > configured_weight
        step.requires_approval = needs_pause
        return needs_pause

    @staticmethod
    def get_risk_rationale(step: PlanStep) -> str:
        """Returns a user-friendly explanation of why approval is required."""
        risk = step.risk_level or HITLGate.classify_risk(step)
        tool = (step.tool_name or "").lower().strip()
        desc = step.description

        if risk == RiskLevel.HIGH:
            if tool == "generate_image":
                return "This step will synthesize an AI image asset via the generation queue."
            elif tool == "execute_code" or any(kw in desc.lower() for kw in ["file", "pdf", "report", "csv", "excel"]):
                return "This step generates and saves new deliverable files or reports to storage."
            elif tool == "browse_web":
                return "This step executes actions in an interactive web session."
            return "This step performs an action that writes or modifies deliverables."
        elif risk == RiskLevel.MEDIUM:
            return "This step executes code calculations or renders visual component widgets."
        return "Standard read-only search or informational retrieval step."
