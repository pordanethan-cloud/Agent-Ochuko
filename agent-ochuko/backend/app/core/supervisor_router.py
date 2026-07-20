"""
Multi-Agent Supervisor & Swarm Router Module for Agent Ochuko.
Orchestrates sub-agents (DocumentAgent, CodeExecutorAgent, WebSearchAgent, ReviewerAgent)
with dedicated prompts and scoped tools.
"""
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SubAgentConfig(BaseModel):
    name: str
    description: str
    allowed_tools: List[str]
    system_prompt: str


class SupervisorRouter:
    """Routes turn requests to specialized sub-agent personalities."""

    def __init__(self):
        self.sub_agents: Dict[str, SubAgentConfig] = {
            "document_agent": SubAgentConfig(
                name="DocumentAgent",
                description="Specialist for processing, editing, letterhead injection, and signature manipulation on PDF and DOCX files.",
                allowed_tools=["execute_code", "fitz", "python-docx"],
                system_prompt="You are DocumentAgent. Your role is precise document manipulation, layout extraction, signature positioning, and letterhead application."
            ),
            "code_agent": SubAgentConfig(
                name="CodeExecutorAgent",
                description="Specialist for writing, executing, and debugging Python sandbox code.",
                allowed_tools=["execute_code"],
                system_prompt="You are CodeExecutorAgent. Write efficient, robust Python code to solve computational tasks."
            ),
            "search_agent": SubAgentConfig(
                name="WebSearchAgent",
                description="Specialist for live web search, news aggregation, and facts retrieval.",
                allowed_tools=["hybrid_search"],
                system_prompt="You are WebSearchAgent. Find accurate, up-to-date real-time web facts."
            )
        }

    def route_request(self, user_message: str, attachments: List[Dict[str, Any]] = None) -> SubAgentConfig:
        """Determines best sub-agent specialist for task payload."""
        attachments = attachments or []
        
        # Check attachment extensions
        has_docs = any(a.get("filename", "").lower().endswith((".docx", ".doc", ".pdf", ".xlsx")) for a in attachments)
        if has_docs:
            logger.info("SupervisorRouter assigned request to DocumentAgent")
            return self.sub_agents["document_agent"]

        msg_lower = user_message.lower()
        if "search" in msg_lower or "latest" in msg_lower or "news" in msg_lower:
            logger.info("SupervisorRouter assigned request to WebSearchAgent")
            return self.sub_agents["search_agent"]

        logger.info("SupervisorRouter assigned request to CodeExecutorAgent")
        return self.sub_agents["code_agent"]


supervisor_router = SupervisorRouter()
