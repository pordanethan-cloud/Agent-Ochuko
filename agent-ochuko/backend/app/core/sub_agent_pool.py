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
        nano_deployment: str = "gpt-5.6-luna",
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

            use_responses = hasattr(self.client, "responses") and hasattr(self.client.responses, "create")
            base_kwargs: Dict[str, Any] = (
                {"model": self.nano_deployment, "input": prompt_input}
                if use_responses
                else {"model": self.nano_deployment, "messages": prompt_input}
            )
            # Compression is a cheap utility path — run luna at effort "none".
            # One-shot retry without the parameter if the deployment rejects it.
            try:
                effort_kwargs = (
                    {"reasoning": {"effort": "none"}} if use_responses else {"reasoning_effort": "none"}
                )
                if use_responses:
                    response = await asyncio.wait_for(
                        self.client.responses.create(**base_kwargs, **effort_kwargs),
                        timeout=4.0,
                    )
                else:
                    response = await asyncio.wait_for(
                        self.client.chat.completions.create(**base_kwargs, **effort_kwargs),
                        timeout=4.0,
                    )
            except Exception as effort_err:
                t = str(effort_err).lower()
                is_param_err = (
                    "reasoning" in t or "effort" in t
                    or "unknown parameter" in t or "unsupported parameter" in t
                    or "invalid parameter" in t
                )
                if not is_param_err:
                    raise
                if use_responses:
                    response = await asyncio.wait_for(
                        self.client.responses.create(**base_kwargs),
                        timeout=4.0,
                    )
                else:
                    response = await asyncio.wait_for(
                        self.client.chat.completions.create(**base_kwargs),
                        timeout=4.0,
                    )

            if use_responses:
                summary = (getattr(response, "output_text", "") or "").strip()
            else:
                summary = (response.choices[0].message.content or "").strip()

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

            # Fast-path: if search context contains verified live facts or grounded evidence, extract it directly
            if "VERIFIED LIVE FACTS & EVIDENCE:" in raw_context:
                parts = raw_context.split("VERIFIED LIVE FACTS & EVIDENCE:", 1)[1]
                if "GROUNDING SNIPPETS" in parts:
                    compressed_summary = parts.split("GROUNDING SNIPPETS", 1)[0].strip()
                elif "Supporting Sources:" in parts:
                    compressed_summary = parts.split("Supporting Sources:", 1)[0].strip()
                else:
                    compressed_summary = parts.strip()
            elif "Search Synthesis:" in raw_context:
                parts = raw_context.split("Search Synthesis:", 1)[1]
                if "Supporting Grounding Context:" in parts:
                    compressed_summary = parts.split("Supporting Grounding Context:", 1)[0].strip()
                elif "Supporting Sources:" in parts:
                    compressed_summary = parts.split("Supporting Sources:", 1)[0].strip()
                else:
                    compressed_summary = parts.strip()
            elif len(raw_context) <= 800:
                compressed_summary = raw_context.strip()
            else:
                compressed_summary = await self.compress_text(
                    raw_context,
                    instruction=f"Extract the specific answer and facts for the search query: '{query}'. Include exact numbers, scores, names, and key metrics. Do not write generic conversational summaries.",
                    max_tokens=220,
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
        language: str = "python",
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
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
                conversation_id=conversation_id or "default",
                user_id=user_id or "default",
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

    async def delegate_browser_scrape(
        self,
        url: str,
        extract_type: str = "markdown",
        query_context: str = "",
        search_fn=None,
    ) -> SubAgentResult:
        """
        Executes web scraping. Returns failure if blocked or unable to load,
        allowing the AI-level cognitive feedback loop to inspect the obstacle,
        formulate an aim, and dynamically select an alternative tool.
        """
        clean_url = (url or "").strip().rstrip(".:,;`)]'\"")
        if not clean_url or "." not in clean_url:
            return SubAgentResult(
                success=False,
                summary="No valid URL provided to scrape.",
                error="Invalid or missing URL for scrape_web",
            )

        try:
            from app.services.browser_agent import BrowserAgent
            res = await BrowserAgent.scrape_url(url=clean_url, extract_type=extract_type)
            if res.get("success") and res.get("content_markdown"):
                return SubAgentResult(
                    success=True,
                    summary=res.get("summary", "Page scraped."),
                    artifacts=[],
                    token_spend=len(res.get("content_markdown", "")) // 4 + 100,
                    raw_length=len(res.get("content_markdown", "")),
                )
            else:
                err_msg = res.get("error") or f"Could not load or extract content from {clean_url}"
                return SubAgentResult(
                    success=False,
                    summary=f"Scrape failed for {clean_url}: {err_msg[:120]}",
                    error=err_msg,
                )
        except Exception as e:
            logger.debug(f"Direct scrape error for {clean_url}: {e}")
            return SubAgentResult(
                success=False,
                summary=f"Scrape error for {clean_url}: {str(e)[:120]}",
                error=str(e),
            )

    async def delegate_handle_lookup(self, handle: str, platform: str = "auto") -> SubAgentResult:
        """Looks up a developer or social profile handle."""
        try:
            from app.services.handle_intelligence import HandleIntelligence
            res = await HandleIntelligence.lookup_profile(raw_handle=handle, platform=platform)
            return SubAgentResult(
                success=res.get("success", False),
                summary=res.get("summary", "Profile retrieved."),
                artifacts=[],
                token_spend=150,
                raw_length=len(str(res)),
                error=res.get("error"),
            )
        except Exception as e:
            logger.error(f"SubAgent handle lookup failed: {e}")
            return SubAgentResult(success=False, summary=f"Handle lookup error: {str(e)[:120]}", error=str(e))

    async def delegate_youtube_transcript(self, url_or_id: str) -> SubAgentResult:
        """Extracts metadata and transcript from a YouTube video URL or ID."""
        try:
            from app.services.youtube_intelligence import YouTubeIntelligence
            res = await YouTubeIntelligence.process_youtube_url(url_or_id)
            if res.get("success"):
                summary = res.get("summary") or res.get("formatted_context", "YouTube transcript retrieved.")
                word_count = res.get("word_count", 0)
                return SubAgentResult(
                    success=True,
                    summary=summary,
                    artifacts=[{
                        "type": "youtube_video",
                        "title": res.get("title", ""),
                        "url": res.get("url", ""),
                        "author_name": res.get("author_name", ""),
                        "word_count": word_count,
                    }],
                    token_spend=min(word_count, 1500),
                    raw_length=len(res.get("transcript_text", "")),
                )
            else:
                err_msg = res.get("error") or "Failed to retrieve YouTube transcript."
                return SubAgentResult(
                    success=False,
                    summary=f"YouTube transcript failed: {err_msg}",
                    error=err_msg,
                )
        except Exception as e:
            logger.error(f"SubAgent youtube transcript failed: {e}")
            return SubAgentResult(success=False, summary=f"YouTube transcript error: {str(e)[:120]}", error=str(e))

    async def delegate_site_deployment(
        self,
        title: str,
        html_content: str,
        css_content: str = "",
        js_content: str = "",
        files: Optional[Dict[str, str]] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        supabase_client=None,
    ) -> SubAgentResult:
        """Deploys an instant static website or multi-file web app and produces a live preview URL."""
        try:
            from app.services.hosted_sites_service import HostedSitesService
            res = await HostedSitesService.deploy_site(
                title=title,
                html_content=html_content,
                css_content=css_content,
                js_content=js_content,
                files=files,
                user_id=user_id,
                conversation_id=conversation_id,
                supabase_client=supabase_client,
            )
            preview_url = res.get("preview_url", "")
            file_list = res.get("files") or []
            files_count_str = f" ({len(file_list)} files)" if file_list else ""
            summary = (
                f"**Website Deployed Successfully!**\n"
                f"- **Title**: {res.get('title')}\n"
                f"- **Live Preview URL**: [{preview_url}]({preview_url})\n"
                f"- **Slug**: `{res.get('slug')}`{files_count_str}"
            )
            artifacts = [
                {
                    "filename": f"{res.get('slug')}.html",
                    "download_url": preview_url,
                    "title": res.get("title"),
                    "type": "site_preview",
                    "slug": res.get("slug"),
                }
            ]
            if file_list and len(file_list) > 1:
                for fn in file_list:
                    if fn not in ("index.html", "index.htm"):
                        artifacts.append({
                            "filename": fn,
                            "download_url": f"{preview_url}/{fn}",
                            "title": f"{res.get('title')} - {fn}",
                            "type": "site_file",
                        })
            return SubAgentResult(
                success=True,
                summary=summary,
                artifacts=artifacts,
                token_spend=250,
                raw_length=len(html_content) + sum(len(v) for v in (files or {}).values()),
            )
        except Exception as e:
            logger.error(f"SubAgent site deployment failed: {e}")
            return SubAgentResult(success=False, summary=f"Site deployment error: {str(e)[:120]}", error=str(e))
