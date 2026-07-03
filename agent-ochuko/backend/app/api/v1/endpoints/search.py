# app/api/v1/endpoints/search.py
"""
Grounded Search Engine endpoint.

Web search is performed exclusively by Gemini 2.5 Flash with Google Search grounding.
Azure Bing Search is NOT used anywhere in this system.

The Gemini model retrieves and synthesises the answer in a single generation call,
returning a cited, grounded response. Sources are extracted from grounding metadata
and returned alongside the answer.

Route: POST /v1/search/ask-hybrid
Auth:  Requires a valid JWT (same guard as the chat endpoints).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.jwt_validator import verify_jwt

# Re-use the shared Gemini search engine from the chat module.
# Both the chat tool-call path and the dedicated search endpoint
# go through the same _perform_gemini_search function so key
# rotation logic, sanitization, and grounding config stay in one place.
from app.api.v1.endpoints.chat import (
    _perform_gemini_search,
    _collect_gemini_keys,
    build_llm_context,
)

logger = logging.getLogger("app.api.v1.endpoints.search")
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class HybridSearchRequest(BaseModel):
    prompt: str
    conversation_id: Optional[str] = None
    timezone: Optional[str] = None
    local_time: Optional[str] = None


class Source(BaseModel):
    title: str
    url: str


class HybridSearchResponse(BaseModel):
    status: str
    answer: str
    sources: list[Source]
    search_engine: str   # always "gemini-2.5-flash+google-search" — documents provider explicitly


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/ask-hybrid",
    response_model=HybridSearchResponse,
    summary="Grounded search answer",
    description=(
        "Retrieves live web context and synthesises a cited answer using "
        "Gemini 2.5 Flash with Google Search grounding. "
        "Azure Bing Search is not used."
    ),
)
async def ask_hybrid_engine(
    query: HybridSearchRequest,
    user: Dict[str, Any] = Depends(verify_jwt),
) -> HybridSearchResponse:
    """
    Grounded search via Gemini 2.5 Flash + Google Search.

    Steps:
    1. Validate that at least one Gemini API key is available.
    2. Load conversation history from Supabase (if conversation_id provided)
       so Gemini can resolve references to prior context.
    3. Call _perform_gemini_search — the single, shared search implementation.
    4. Return the grounded answer with cited sources.
    """
    # Guard: fail fast if no Gemini keys are present
    if not _collect_gemini_keys():
        raise HTTPException(
            status_code=500,
            detail="No Gemini API keys configured. Set GEMINI_API_KEY in environment.",
        )

    # Load conversation history so Gemini has full context
    conversation_history = []
    if query.conversation_id and query.conversation_id != "00000000-0000-0000-0000-000000000000":
        try:
            conversation_history = await build_llm_context(query.conversation_id)
        except Exception as db_err:
            # Non-fatal: proceed without history rather than failing the search
            logger.warning("Failed to load conversation history for search: %s", db_err)

    try:
        result = await _perform_gemini_search(
            query=query.prompt,
            conversation_history=conversation_history,
            local_time=query.local_time,
            tz=query.timezone,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Grounded search failed: {exc}")

    answer = result.get("answer", "")
    raw_sources = result.get("sources", [])

    sources = [Source(title=s["title"], url=s["url"]) for s in raw_sources]

    logger.info(
        "Grounded search completed. query=%.60s sources=%d",
        query.prompt, len(sources),
    )

    return HybridSearchResponse(
        status="success",
        answer=answer,
        sources=sources,
        search_engine="gemini-2.5-flash+google-search",
    )
