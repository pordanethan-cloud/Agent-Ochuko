# app/core/sub_agent_pool.py
"""
Sub-Agent Pool & Context Isolation Layer.
Spawns lightweight worker executions for search and code runs.
Compresses raw tool outputs before returning them to the orchestrator,
preventing context bloat and saving ~70-85% in cumulative turn tokens.
"""
import asyncio
import logging
from typing import Optional, List, Dict, Any
from openai import AsyncAzureOpenAI
from app.core.agent_task_models import SubAgentResult

logger = logging.getLogger("app.core.sub_agent_pool")


class SubAgentPool:
    """Manages isolated sub-agent executions for token-efficient delegation."""

    def __init__(
        self,
        openai_client: Optional[AsyncAzureOpenAI] = None,
        nano_deployment: str = "gpt-5.4-nano",
    ):
        self.client = openai_client
        self.nano_deployment = nano_deployment

    async def compress_text(
        self,
        raw_text: str,
        instruction: str = "Extract key facts, numbers, dates, and conclusions in 2-4 concise sentences.",
        max_tokens: int = 250,
    ) -> str:
        """
        Uses nano model to distill verbose data into a high-density summary.
        Fallback to clean truncation if client is not provided or API fails.
        """
        if not raw_text or not raw_text.strip():
            return ""

        # If already concise, return directly
        if len(raw_text) <= max_tokens * 4:
            return raw_text.strip()

        if not self.client:
            # Clean boundary truncation
            truncated = raw_text[: max_tokens * 4]
            last_nl = truncated.rfind("\n")
            if last_nl > 100:
                truncated = truncated[:last_nl]
            return truncated.strip() + " [...truncated]"

        try:
            prompt_input = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert context compression worker. "
                        f"{instruction}\n"
                        "Do not include filler or preamble. Output only the compressed factual summary."
                    ),
                },
                {
                    "role": "user",
                    "content": f"RAW DATA TO SUMMARIZE:\n{raw_text[:6000]}",
                },
            ]

            if hasattr(self.client, "responses") and hasattr(self.client.responses, "create"):
                response = await asyncio.wait_for(
                    self.client.responses.create(
                        model=self.nano_deployment,
                        input=prompt_input,
                    ),
                    timeout=4.0,
                )
                summary = (getattr(response, "output_text", "") or "").strip()
            elif hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.nano_deployment,
                        messages=prompt_input,
                    ),
                    timeout=4.0,
                )
                summary = (response.choices[0].message.content or "").strip()
            else:
                summary = ""

            if summary:
                return summary
        except Exception as e:
            logger.debug(f"SubAgent compression skipped (fallback to truncation): {e}")

        # Fallback truncation
        truncated = raw_text[: max_tokens * 4]
        last_nl = truncated.rfind("\n")
        if last_nl > 100:
            truncated = truncated[:last_nl]
        return truncated.strip() + " [...truncated]"

    async def delegate_search(
        self,
        query: str,
        search_fn,
        history: Optional[List[Dict]] = None,
    ) -> SubAgentResult:
        """
        Executes a web search through search_fn in an isolated worker turn.
        Compresses the retrieved search context into a clean 150-200 token result.
        """
        try:
            search_data = await search_fn(
                query,
                synthesis_deployment=self.nano_deployment,
                history=history,
                return_raw=True,
            )
            raw_context = search_data.get("google_context", "") or ""
            sources = search_data.get("sources", []) or []

            # Fast-path: if search context already contains a grounded synthesis, use it directly (0ms)
            if "Search Synthesis:" in raw_context:
                parts = raw_context.split("Search Synthesis:", 1)[1]
                if "Supporting Grounding Context:" in parts:
                    compressed_summary = parts.split("Supporting Grounding Context:", 1)[0].strip()
                else:
                    compressed_summary = parts.strip()
            elif len(raw_context) <= 800:
                compressed_summary = raw_context.strip()
            else:
                compressed_summary = await self.compress_text(
                    raw_context,
                    instruction=f"Extract the specific answer and facts for the search query: '{query}'. Include numbers, names, and key metrics.",
                    max_tokens=200,
                )

            # Estimated token spend for sub-agent operation
            est_tokens = (len(raw_context) // 4) + 150

            return SubAgentResult(
                success=True,
                summary=compressed_summary or f"Search completed ({len(sources)} sources found).",
                artifacts=[],
                token_spend=est_tokens,
                raw_length=len(raw_context),
            )
        except Exception as e:
            logger.error(f"SubAgent search failed: {e}")
            return SubAgentResult(
                success=False,
                summary=f"Search failed: {str(e)[:150]}",
                error=str(e),
            )

    async def delegate_code_execution(
        self,
        code: str,
        language: str,
        conversation_id: str,
        user_id: str,
    ) -> SubAgentResult:
        """
        Executes code inside the isolated sandbox.
        Captures output files and summarizes long terminal logs.
        """
        try:
            from app.services.code_sandbox import execute_code_in_sandbox

            exec_output, exec_files = await execute_code_in_sandbox(
                code=code,
                language=language,
                conversation_id=conversation_id,
                user_id=user_id,
                timeout_seconds=60,
            )

            compressed_summary = await self.compress_text(
                exec_output,
                instruction="Summarize the script output, calculation results, or data metrics produced.",
                max_tokens=200,
            )

            is_error = "error" in exec_output.lower() or "exception" in exec_output.lower()
            est_tokens = (len(exec_output) // 4) + 100

            return SubAgentResult(
                success=not is_error,
                summary=compressed_summary or "Code executed successfully.",
                artifacts=exec_files or [],
                token_spend=est_tokens,
                raw_length=len(exec_output),
                error=exec_output[:300] if is_error else None,
            )
        except Exception as e:
            logger.error(f"SubAgent code execution failed: {e}")
            return SubAgentResult(
                success=False,
                summary=f"Code execution error: {str(e)[:150]}",
                error=str(e),
            )
