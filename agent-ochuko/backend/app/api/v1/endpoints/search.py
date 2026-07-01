# app/api/v1/endpoints/search.py
"""
Hybrid Search Engine endpoint.

Reference architecture (two-phase multi-cloud):
  Phase 1 — Google Retrieval
    Gemini 2.5 Flash + google_search tool fetches real-time web snippets
    and source metadata. Gemini is used ONLY for retrieval.

  Phase 2 — Azure Synthesis
    Raw Google context is injected into the Azure OpenAI Responses API
    (async) for accurate, enterprise-grade synthesis. Azure reasons;
    Gemini retrieves.

Route: POST /v1/search/ask-hybrid
Auth:  Requires a valid JWT (same guard as the chat endpoints).
"""

import os
import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.jwt_validator import verify_jwt

logger = logging.getLogger("app.api.v1.endpoints.search")
router = APIRouter()

# ---------------------------------------------------------------------------
# Lazy-initialised async Azure client
# ---------------------------------------------------------------------------
_azure_async_client = None


def _get_azure_async_client():
    """Return a cached AsyncAzureOpenAI client, initialised on first call."""
    global _azure_async_client
    if _azure_async_client is None:
        from openai import AsyncAzureOpenAI

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")

        if not endpoint or not api_key:
            raise HTTPException(
                status_code=500,
                detail="Azure OpenAI credentials are not configured on this server.",
            )
        _azure_async_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        logger.info("AsyncAzureOpenAI client initialised for hybrid search.")
    return _azure_async_client


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class HybridSearchRequest(BaseModel):
    prompt: str


class Source(BaseModel):
    title: str
    url: str


class HybridSearchResponse(BaseModel):
    status: str
    answer: str
    sources: list[Source]
    raw_google_context_used: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/ask-hybrid",
    response_model=HybridSearchResponse,
    summary="Google-grounded + Azure-synthesised answer",
    description=(
        "Phase 1: Retrieves live web context via Google Gemini grounding. "
        "Phase 2: Synthesises a cited answer using Azure OpenAI Responses API."
    ),
)
async def ask_hybrid_engine(
    query: HybridSearchRequest,
    user: Dict[str, Any] = Depends(verify_jwt),
):
    """
    Two-phase hybrid search.

    Phase 1 — Google Retrieval (Gemini 2.5 Flash, sync SDK run in asyncio thread)
      Triggers the google_search grounding tool to pull live web snippets and
      source metadata. Temperature 0.1 for faithful retrieval, not creativity.

    Phase 2 — Azure Synthesis (AsyncAzureOpenAI Responses API, fully async)
      Raw Google context is packaged into the system prompt and forwarded to
      the configured Azure OpenAI deployment for structured, cited synthesis.
    """

    # ── Phase 1: Google Grounding ────────────────────────────────────────────
    def _google_retrieval_phase():
        from google import genai                          # type: ignore[import]
        from google.genai import types as genai_types    # type: ignore[import]

        keys = []
        for var_name in ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4"]:
            key = os.getenv(var_name)
            if key and key.strip() and key not in keys:
                keys.append(key.strip())
        
        if not keys:
            raise RuntimeError("No Google/Gemini API keys configured in environment.")

        last_exc = None
        for idx, key in enumerate(keys):
            try:
                g_client = genai.Client(api_key=key)
                g_response = g_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=query.prompt,
                    config=genai_types.GenerateContentConfig(
                        tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                        temperature=0.1,
                    ),
                )

                search_chunks: list[str] = []
                sources: list[Source] = []
                seen_urls: set[str] = set()

                if g_response.candidates and g_response.candidates[0].grounding_metadata:
                    metadata = g_response.candidates[0].grounding_metadata

                    # Map grounding_chunk index -> real text snippet from grounding_supports
                    snippet_map: dict[int, str] = {}
                    for support in (getattr(metadata, "grounding_supports", []) or []):
                        segment = getattr(support, "segment", None)
                        text = (getattr(segment, "text", "") or "").strip()
                        for idx_chunk in (getattr(support, "grounding_chunk_indices", []) or []):
                            if idx_chunk not in snippet_map and text:
                                snippet_map[idx_chunk] = text

                    # Build formatted context block + deduplicated source list
                    for i, chunk in enumerate(getattr(metadata, "grounding_chunks", []) or []):
                        web = getattr(chunk, "web", None)
                        if web:
                            url = getattr(web, "uri", "") or ""
                            title = getattr(web, "title", "") or url
                            snippet = snippet_map.get(i, title)

                            if snippet:
                                search_chunks.append(
                                    f"Source [{i + 1}]: {title}\n"
                                    f"URL: {url}\n"
                                    f"Snippet: {snippet}"
                                )

                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                sources.append(Source(title=title, url=url))

                google_context = (
                    "\n\n".join(search_chunks) if search_chunks else "No live web results retrieved."
                )
                return google_context, sources
            except Exception as e:
                logger.warning("Google search failed with key index %d in ask-hybrid: %s", idx, e)
                last_exc = e
                continue

        raise last_exc or RuntimeError("All Gemini API keys failed.")

    try:
        google_context, sources = await asyncio.to_thread(_google_retrieval_phase)
    except Exception as exc:
        import traceback
        print("--- SEARCH ENDPOINT GOOGLE RETRIEVAL PHASE ERROR (FALLBACK TO AZURE KNOWLEDGE) ---")
        traceback.print_exc()
        print("----------------------------------------------------------------------------------")
        logger.warning("Google search retrieval failed, falling back to Azure: %s", exc)
        google_context = "Google web search was unavailable. Fallback to your built-in search or training knowledge to answer."
        sources = []

    logger.info(
        "Google grounding: %d sources for query: %.60s", len(sources), query.prompt
    )

    # ── Phase 2: Azure OpenAI Responses API Synthesis (async) ───────────────
    deployment = (
        os.getenv("SOLVE_MODEL_DEPLOYMENT")
        or os.getenv("AZURE_DEPLOYMENT_NAME")
        or os.getenv("THINK_MODEL_DEPLOYMENT")
        or "gpt-4o"
    )

    system_prompt = (
        "You are Ochuko — an elite enterprise AI assistant built on Azure. "
        "Answer the user's question accurately and professionally. "
        "Use the real-time web context below, retrieved directly from Google Search, "
        "to ground your response. Cite sources when referencing specific facts. "
        "Use plain text only — no emoji.\n\n"
        "--- GOOGLE LIVE WEB CONTEXT ---\n"
        f"{google_context}\n"
        "--- END CONTEXT ---"
    )

    try:
        azure_client = _get_azure_async_client()
        az_response = await azure_client.responses.create(
            model=deployment,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query.prompt},
            ],
        )
        answer: str = az_response.output_text or ""
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        print("--- SEARCH ENDPOINT AZURE SYNTHESIS PHASE ERROR ---")
        traceback.print_exc()
        print("---------------------------------------------------")
        logger.error("Azure OpenAI synthesis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Azure OpenAI synthesis failed: {exc}")

    logger.info(
        "Hybrid search completed for user %s — deployment=%s, sources=%d",
        user.get("sub", "unknown"), deployment, len(sources),
    )

    return HybridSearchResponse(
        status="success",
        answer=answer,
        sources=sources,
        raw_google_context_used=google_context,
    )

