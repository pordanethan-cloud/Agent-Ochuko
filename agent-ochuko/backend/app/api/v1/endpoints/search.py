# app/api/v1/endpoints/search.py
"""
Grounded Search Engine endpoint.

Uses Gemini 2.5 Flash for both web search retrieval and synthesis to provide
a unified, low-latency grounded search experience.

Route: POST /v1/search/ask-hybrid
Auth:  Requires a valid JWT (same guard as the chat endpoints).
"""

import os
import re
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.jwt_validator import verify_jwt

logger = logging.getLogger("app.api.v1.endpoints.search")
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class HybridSearchRequest(BaseModel):
    prompt: str
    conversation_id: Optional[str] = None  # Accept conversation_id to carry history context
    timezone: Optional[str] = None
    local_time: Optional[str] = None


class Source(BaseModel):
    title: str
    url: str


class HybridSearchResponse(BaseModel):
    status: str
    answer: str
    sources: list[Source]
    raw_google_context_used: str


# ---------------------------------------------------------------------------
# Sanitization Helper
# ---------------------------------------------------------------------------

def sanitize_text(text: str) -> str:
    """Censors Google, Gemini, and search engine references to preserve Ochuko identity."""
    if not text:
        return ""
    text = re.sub(r'\bGoogle\s+Search\b', 'Web Search', text, flags=re.IGNORECASE)
    text = re.sub(r'\bGoogle\b', 'Ochuko', text, flags=re.IGNORECASE)
    text = re.sub(r'\bGemini\b', 'Ochuko', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgoogle-genai\b', 'Ochuko-engine', text, flags=re.IGNORECASE)
    return text


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/ask-hybrid",
    response_model=HybridSearchResponse,
    summary="Grounded search answer",
    description="Retrieves live web context and synthesises a cited answer using Gemini 2.5 Flash with search grounding.",
)
async def ask_hybrid_engine(
    query: HybridSearchRequest,
    user: Dict[str, Any] = Depends(verify_jwt),
) -> HybridSearchResponse:
    """
    Unified Grounded Search using Gemini.
    - Loads database conversation history context.
    - Runs a single generation call on Gemini 2.5 Flash with search grounding tool.
    - Sanitizes any Google/Gemini branding from the response.
    """
    from google import genai                          # type: ignore[import]
    from google.genai import types as genai_types    # type: ignore[import]
    from app.api.v1.endpoints.chat import _OCHUKO_RULE, build_llm_context

    # 1. Load conversation history context from Supabase
    db_messages = []
    if query.conversation_id and query.conversation_id != "00000000-0000-0000-0000-000000000000":
        try:
            db_messages = await build_llm_context(query.conversation_id)
        except Exception as db_err:
            logger.error("Failed to load conversation history for search: %s", db_err)

    # 2. Build system instructions (Ochuko identity + environmental context)
    ref_time = query.local_time if query.local_time else datetime.now(timezone.utc).strftime("%A, %B %d, %Y %I:%M:%S %p")
    ref_zone = query.timezone if query.timezone else "UTC"

    time_context = (
        f"\n\n--- USER TIME & ENVIRONMENT CONTEXT ---\n"
        f"User Local Time: {ref_time}\n"
        f"User Timezone: {ref_zone}\n"
        "Align all temporal terms ('today', 'yesterday', 'tomorrow', 'tonight') with this local timeframe.\n"
        "--- END CONTEXT ---\n\n"
    )

    system_instruction = (
        _OCHUKO_RULE + time_context +
        "You are Ochuko, an elite AI assistant. "
        "Use the Google Search tool to find real-time information to answer the user's query. "
        "Strictly do NOT mention Google, Gemini, Alphabet, or google-genai in your output. "
        "Do not say 'According to my search' or 'Google Search shows'. "
        "Just answer the question directly and naturally, citing your sources in your response. "
        "Your tone must be Ochuko's tone (confident, crisp, authoritative, direct, and in control)."
    )

    # 3. Load Gemini API keys (round-robin)
    keys = []
    for var_name in ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4"]:
        key = os.getenv(var_name)
        if key and key.strip() and key not in keys:
            keys.append(key.strip())
    
    if not keys:
        raise HTTPException(status_code=500, detail="No Gemini API keys configured in environment.")

    last_exc = None
    for idx, key in enumerate(keys):
        # Temporarily adjust env variables to force Google GenAI SDK to use this specific key
        orig_gemini = os.environ.get("GEMINI_API_KEY")
        orig_google = os.environ.get("GOOGLE_API_KEY")
        
        os.environ["GEMINI_API_KEY"] = key
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]

        try:
            g_client = genai.Client()
            
            # Format history for Gemini API
            contents = []
            for msg in db_messages:
                role = "user" if msg.get("role") == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.get("content", "")}]
                })
            
            # Add latest user message
            contents.append({
                "role": "user",
                "parts": [{"text": query.prompt}]
            })

            # Run generation and grounding together
            g_response = await g_client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                    temperature=0.2,
                ),
            )

            # Parse grounding sources
            sources: list[Source] = []
            seen_urls: set[str] = set()
            google_context = ""

            if g_response.candidates and g_response.candidates[0].grounding_metadata:
                metadata = g_response.candidates[0].grounding_metadata

                for chunk in (getattr(metadata, "grounding_chunks", []) or []):
                    web = getattr(chunk, "web", None)
                    if web:
                        url = getattr(web, "uri", "") or ""
                        title = getattr(web, "title", "") or url
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            # Do not add direct google search query/result pages as citations
                            if "google.com/search" not in url.lower():
                                sources.append(Source(title=title, url=url))

                # Collect snippet details for logs
                search_chunks = []
                for i, chunk in enumerate(getattr(metadata, "grounding_chunks", []) or []):
                    web = getattr(chunk, "web", None)
                    if web:
                        search_chunks.append(f"Source [{i + 1}]: {getattr(web, 'title', '')}\nURL: {getattr(web, 'uri', '')}")
                google_context = "\n".join(search_chunks)

            answer = g_response.text or ""
            sanitized_answer = sanitize_text(answer)

            logger.info("Grounded search completed. query=%.60s sources=%d", query.prompt, len(sources))

            return HybridSearchResponse(
                status="success",
                answer=sanitized_answer,
                sources=sources,
                raw_google_context_used=google_context or "No search context details available.",
            )

        except Exception as e:
            logger.warning("Gemini grounded search failed with key index %d: %s", idx, e)
            last_exc = e
            continue
        finally:
            # Restore original env variables
            if orig_gemini is not None:
                os.environ["GEMINI_API_KEY"] = orig_gemini
            else:
                os.environ.pop("GEMINI_API_KEY", None)
            if orig_google is not None:
                os.environ["GOOGLE_API_KEY"] = orig_google

    raise HTTPException(status_code=502, detail=f"Grounded search failed: {str(last_exc)}")
