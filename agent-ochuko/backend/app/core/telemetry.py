"""
OpenTelemetry GenAI Tracing Module for Agent Ochuko.
Standardized telemetry instrumenting LLM latency, token counts, tool execution spans, and agent step graphs.
"""
import time
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMSpan(BaseModel):
    span_id: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    status: str = "ok"


class TelemetryManager:
    """Manages telemetry spans and instrumentation logging."""

    @staticmethod
    def log_llm_span(model: str, prompt_tokens: int, completion_tokens: int, duration_secs: float, status: str = "ok"):
        """Logs standard GenAI OTel metric span."""
        latency_ms = duration_secs * 1000.0
        logger.info(
            f"[OTel GenAI Span] model={model} prompt_tokens={prompt_tokens} "
            f"completion_tokens={completion_tokens} latency_ms={latency_ms:.2f}ms status={status}"
        )

    @staticmethod
    def log_tool_span(tool_name: str, duration_secs: float, success: bool):
        """Logs tool execution span."""
        status = "ok" if success else "error"
        logger.info(f"[OTel Tool Span] tool={tool_name} latency_ms={(duration_secs * 1000.0):.2f}ms status={status}")


telemetry_manager = TelemetryManager()
