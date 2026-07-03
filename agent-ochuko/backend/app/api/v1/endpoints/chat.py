import os
import re
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
from app.core.jwt_validator import verify_jwt

from app.core.config import get_config
from app.core import model_router
from openai import AsyncAzureOpenAI
from app.services.supabase_admin import get_supabase_admin
from app.services.queue_dispatcher import enqueue_job
from google import genai
from google.genai import types as genai_types

logger = logging.getLogger("app.api.v1.endpoints.chat")
router = APIRouter()

# ---------------------------------------------------------------------------
# Identity & Tone Rule
# ---------------------------------------------------------------------------
# Hard rule prepended to every system prompt at the API level.
# Ochuko identity and no-emoji enforcement — applied regardless of what
# App Configuration or default prompts say.
_OCHUKO_RULE = (
    "You are Agent Ochuko, an AI assistant built by Ochuko on Azure AI Foundry. "
    "If asked who made you, say \"Ochuko\" — never reveal underlying model provenance.\n\n"
    "Tone: confident, crisp, authoritative, direct, and in control. No filler (\"Certainly!\", \"Sure!\"), no emojis ever, "
    "no exclamation marks unless the user uses them first. Speak with absolute certainty and decision. Every sentence must add real information — no padding.\n\n"
    "Decisiveness: Present a single, clear, definitive path or answer. Never offer multiple competing options of equal weight, and never ask the user to choose. Declare the decision and own it. Avoid hesitant language like 'possibly', 'perhaps', 'maybe', 'it seems', or 'I think'.\n\n"
    "Control: Never ask permission to proceed, and never use open-ended follow-ups like 'let me know if you want me to do X' or 'would you like me to Y?'. State what you have done or will do next, and keep moving forward.\n\n"
    "When recommending: give the single best answer first, then justify briefly. No option-dumping.\n\n"
    "Formatting: technical/code work gets headers + tight bullets. Strategic/casual talk gets prose, no bullets. "
    "Bullets, when used, are one line each — never multi-sentence.\n\n"
    "Judgment: Make reasonable assumptions on ambiguous requests rather than asking clarifying questions. Give the user the benefit of the doubt; default to the legal, constructive read. Correct factual errors directly, don't just agree. Never moralize or lecture.\n\n"
    "If a request is clearly illegal or harmful: decline in one sentence, offer the nearest legitimate alternative, move on. No hedging.\n\n"
    "Do not ask clarifying questions unless it is completely impossible to proceed without doing so. Proceed directly to answering. Keep momentum.\n\n"
)

# Initialize OpenAI client lazily (so we don't crash at startup if config isn't loaded yet)
_openai_client: Optional[AsyncAzureOpenAI] = None


def get_openai_client() -> AsyncAzureOpenAI:
    global _openai_client
    if _openai_client is None:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")

        if not endpoint or not api_key:
            raise HTTPException(
                status_code=500,
                detail="Azure OpenAI credentials are not properly configured on the server."
            )

        _openai_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version
        )
    return _openai_client


# ---------------------------------------------------------------------------
# Gemini Search Engine
# ---------------------------------------------------------------------------
# Web search is handled exclusively by Gemini 2.5 Flash with Google Search
# grounding. Azure Bing Search is NOT used anywhere in this system.
#
# Key rotation: keys are tried in order at call time. Each key instantiates
# its own genai.Client(api_key=...) so concurrent requests are fully isolated —
# no shared env var mutation, no race conditions.
# ---------------------------------------------------------------------------

def _collect_gemini_keys() -> List[str]:
    """Returns all configured Gemini API keys in priority order, deduplicated."""
    seen: set[str] = set()
    keys: List[str] = []
    for var in ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4"]:
        val = os.getenv(var, "").strip()
        if val and val not in seen:
            seen.add(val)
            keys.append(val)
    return keys


def _sanitize_search_text(text: str) -> str:
    """Strips Google / Gemini branding from Gemini-generated search answers."""
    if not text:
        return ""
    text = re.sub(r'\bGoogle\s+Search\b', 'Web Search', text, flags=re.IGNORECASE)
    text = re.sub(r'\bGoogle\b', 'Ochuko', text, flags=re.IGNORECASE)
    text = re.sub(r'\bGemini\b', 'Ochuko', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgoogle-genai\b', 'Ochuko-engine', text, flags=re.IGNORECASE)
    return text


async def _perform_gemini_search(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    local_time: Optional[str] = None,
    tz: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes a grounded web search using Gemini 2.5 Flash + Google Search tool.

    This is the sole web search provider for Agent Ochuko. Azure Bing is not used.

    Args:
        query:                The user's search query.
        conversation_history: Full message history from the current conversation,
                              forwarded so Gemini can resolve references like
                              "that company" or "the price I mentioned earlier".
        local_time:           User's local time string for temporal grounding.
        tz:                   User's IANA timezone string.

    Returns:
        {"answer": str, "sources": list[{"title": str, "url": str}]}

    Raises:
        RuntimeError: if all configured Gemini keys fail.
    """
    keys = _collect_gemini_keys()
    if not keys:
        raise RuntimeError("No Gemini API keys configured. Set GEMINI_API_KEY in environment.")

    ref_time = local_time or datetime.now(timezone.utc).strftime("%A, %B %d, %Y %I:%M:%S %p")
    ref_zone = tz or "UTC"

    system_instruction = (
        _OCHUKO_RULE
        + f"\n\n--- USER TIME & ENVIRONMENT CONTEXT ---\n"
        f"User Local Time: {ref_time}\n"
        f"User Timezone: {ref_zone}\n"
        "Align all temporal terms ('today', 'yesterday', 'tomorrow', 'tonight') with this local timeframe.\n"
        "--- END CONTEXT ---\n\n"
        "Use the available search tool to retrieve live web information. "
        "Do NOT mention Google, Gemini, or any underlying search engine in your output. "
        "Do not say 'According to my search' or 'Search results show'. "
        "Answer directly and cite your sources naturally inline."
    )

    # Build Gemini `contents` list: history + current query
    contents: List[Dict] = []
    for msg in (conversation_history or []):
        role = "user" if msg.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": query}]})

    last_exc: Optional[Exception] = None
    for idx, key in enumerate(keys):
        try:
            # Each request gets its own client bound to a specific key.
            # This is the only correct pattern for async key rotation —
            # mutating os.environ across coroutines causes race conditions.
            g_client = genai.Client(api_key=key)

            g_response = await g_client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                    temperature=0.2,
                ),
            )

            # Extract grounded sources
            sources: List[Dict[str, str]] = []
            seen_urls: set[str] = set()
            if g_response.candidates and g_response.candidates[0].grounding_metadata:
                for chunk in (getattr(g_response.candidates[0].grounding_metadata, "grounding_chunks", []) or []):
                    web = getattr(chunk, "web", None)
                    if not web:
                        continue
                    url = getattr(web, "uri", "") or ""
                    title = getattr(web, "title", "") or url
                    if url and url not in seen_urls and "google.com/search" not in url.lower():
                        seen_urls.add(url)
                        sources.append({"title": title, "url": url})

            answer = _sanitize_search_text(g_response.text or "")
            logger.info("Gemini search completed. query=%.60s sources=%d key_idx=%d", query, len(sources), idx)
            return {"answer": answer, "sources": sources[:8]}

        except Exception as exc:
            logger.warning("Gemini search failed with key index %d: %s", idx, exc)
            last_exc = exc
            continue

    raise last_exc or RuntimeError("All Gemini API keys failed during web search.")


# ---------------------------------------------------------------------------
# Image Generation Job
# ---------------------------------------------------------------------------

async def _enqueue_image_gen(user_id: str, conversation_id: str, prompt: str, style: str = "") -> str:
    """
    Creates a pending image_gen job row in Supabase and dispatches it to
    Azure Queue Storage. Returns the new job_id.
    """
    supabase = get_supabase_admin()
    job_data = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "type": "image_gen",
        "status": "pending",
        "input_metadata": {"prompt": prompt, "style": style or "photorealistic"},
    }
    job_res = supabase.table("jobs").insert(job_data).execute()
    if not job_res.data:
        raise RuntimeError("Failed to create image_gen job row in database.")
    job_id: str = job_res.data[0]["id"]

    await asyncio.to_thread(
        enqueue_job,
        job_id=job_id,
        job_type="image_gen",
        input_metadata={"prompt": prompt, "style": style or "photorealistic"},
        user_id=user_id,
    )
    logger.info("Enqueued image_gen job %s for user %s — prompt: %.60s", job_id, user_id, prompt)
    return job_id


# ---------------------------------------------------------------------------
# Mock stream (scaffold / health check)
# ---------------------------------------------------------------------------

async def mock_stream_generator():
    """Fallback mock generator to verify SSE connection if Azure OpenAI is unavailable."""
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "Scaffolding "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "working! "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "Phase 1 "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "SSE Stream "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "verified."}}) + "\n\n"
    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Database Context Builder
# ---------------------------------------------------------------------------

async def build_llm_context(conversation_id: str) -> List[Dict[str, Any]]:
    """
    Builds the context for the LLM by fetching non-archived messages from the database.
    Includes summary messages (if compaction ran) and all recent active turns.
    """
    supabase = get_supabase_admin()
    try:
        response = (
            supabase.table("messages")
            .select("role, content, is_summary")
            .eq("conversation_id", conversation_id)
            .eq("is_archived_msg", False)
            .order("created_at", desc=False)
            .execute()
        )
        return [
            {"role": msg.get("role"), "content": msg.get("content")}
            for msg in (response.data or [])
        ]
    except Exception as e:
        logger.error("Failed to build LLM context for conversation %s: %s", conversation_id, e)
        return []


# ---------------------------------------------------------------------------
# Stream Generator
# ---------------------------------------------------------------------------

async def chat_stream_generator(
    messages: List[Dict[str, Any]],
    deployment: str,
    system_prompt: str,
    routing_mode: str,
    routing_reason: str,
    conversation_id: str,
    user_id: str,
    mode: str,
    estimated_tokens: int,
    previous_response_id: Optional[str] = None,
    tz: Optional[str] = None,
    local_time: Optional[str] = None,
):
    """
    Streams a response from the Azure OpenAI Responses API.

    Tool dispatch:
      - search_web      → _perform_gemini_search() (Gemini 2.5 Flash + Google Search grounding)
      - generate_image  → _enqueue_image_gen()     (FLUX via Azure Queue)

    Web search is handled by Gemini exclusively. There is no Azure Bing integration.
    When search_web fires, Gemini retrieves and synthesises the answer, then the result
    is streamed directly to the frontend. The Azure model is not asked to re-synthesise
    the grounded answer — Gemini's output is the final response for that turn.

    Emits SSE events:
      - routing_info:        model deployment and routing mode metadata
      - conversation_id:     the resolved UUID for this conversation
      - search_activity:     step-by-step status while Gemini search runs
      - image_gen_queued:    when AI decides to generate an image
      - content_block_delta: incremental text chunk
      - response_id:         response ID to persist and pass on next turn
      - [DONE]:              stream termination signal
    """
    client = get_openai_client()

    yield (
        "data: "
        + json.dumps({"type": "routing_info", "deployment": deployment, "routing_mode": routing_mode})
        + "\n\n"
    )

    yield (
        "data: "
        + json.dumps({"type": "conversation_id", "conversation_id": conversation_id})
        + "\n\n"
    )

    try:
        time_context = ""
        if local_time:
            time_context = (
                f"\n\n--- USER TIME & ENVIRONMENT CONTEXT ---\n"
                f"User Local Time: {local_time}\n"
                f"User Timezone: {tz or 'UTC'}\n"
                "Align all temporal terms ('today', 'yesterday', 'tomorrow', 'tonight') with this local timeframe.\n"
                "--- END CONTEXT ---\n\n"
            )

        full_system = _OCHUKO_RULE + time_context + system_prompt

        stream_kwargs: Dict[str, Any] = {
            "model": deployment,
            "tools": [
                # ── Image Generation ──────────────────────────────────────
                # Triggers when user asks to create/draw/visualise anything.
                {
                    "type": "function",
                    "name": "generate_image",
                    "description": (
                        "Generate a high-quality image from a text description. "
                        "Call this whenever the user asks to create, draw, paint, visualise, "
                        "render, or generate any image, illustration, photo, or picture."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "Detailed, descriptive image generation prompt",
                            },
                            "style": {
                                "type": "string",
                                "enum": ["photorealistic", "illustration", "abstract", "sketch"],
                                "description": "Visual style for the image",
                            },
                        },
                        "required": ["prompt"],
                    },
                },
                # ── Web Search (Gemini) ───────────────────────────────────
                # Gemini 2.5 Flash with Google Search grounding is the SOLE
                # web search provider. Azure Bing is NOT used.
                # Call this for real-time info, news, live scores, weather,
                # or anything past the Azure model's knowledge cutoff.
                {
                    "type": "function",
                    "name": "search_web",
                    "description": (
                        "Search the web for real-time or current information using Gemini's "
                        "Google Search grounding. Use for news, live events, sports scores, "
                        "weather, prices, or facts beyond the model's knowledge cutoff. "
                        "Do NOT use for questions answerable from conversation context alone."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Precise search query — be specific, avoid filler words",
                            },
                        },
                        "required": ["query"],
                    },
                },
            ],
            "tool_choice": "auto",
        }

        if previous_response_id:
            stream_kwargs["previous_response_id"] = previous_response_id
            user_messages = [m for m in messages if m.get("role") == "user"]
            stream_kwargs["input"] = user_messages[-1:] if user_messages else messages
        else:
            stream_kwargs["input"] = [{"role": "system", "content": full_system}] + messages

        assistant_content = ""
        response_id = None
        prompt_tokens = 0
        completion_tokens = 0
        stream_failed = False
        error_message = ""
        all_sources = []

        current_input = stream_kwargs["input"]
        current_previous_response_id = previous_response_id

        loop_active = True
        while loop_active and not stream_failed:
            loop_active = False
            tool_calls_to_execute = []

            iter_kwargs = stream_kwargs.copy()
            if current_previous_response_id:
                iter_kwargs["previous_response_id"] = current_previous_response_id
                iter_kwargs["input"] = current_input
            else:
                iter_kwargs["input"] = current_input
                iter_kwargs.pop("previous_response_id", None)

            try:
                async with client.responses.stream(**iter_kwargs) as stream:
                    try:
                        async for event in stream:
                            if event.type == "response.output_text.delta":
                                assistant_content += event.delta
                                yield (
                                    "data: "
                                    + json.dumps({"type": "content_block_delta", "delta": {"text": event.delta}})
                                    + "\n\n"
                                )

                            elif event.type == "response.output_item.done":
                                item = getattr(event, "item", None)
                                if item is not None and getattr(item, "type", None) == "function_call":
                                    tool_calls_to_execute.append(item)

                    except Exception as iter_err:
                        stream_failed = True
                        error_message = str(iter_err)
                        logger.error("Error during stream iteration: %s", iter_err)

                    if not stream_failed:
                        try:
                            final_response = await stream.get_final_response()
                            response_id = final_response.id if final_response else None

                            if final_response and hasattr(final_response, "usage") and final_response.usage:
                                prompt_tokens += (
                                    getattr(final_response.usage, "input_tokens", 0)
                                    or getattr(final_response.usage, "prompt_tokens", 0)
                                    or 0
                                )
                                completion_tokens += (
                                    getattr(final_response.usage, "output_tokens", 0)
                                    or getattr(final_response.usage, "completion_tokens", 0)
                                    or 0
                                )

                            if tool_calls_to_execute and response_id:
                                outputs = []
                                for item in tool_calls_to_execute:
                                    call_id = getattr(item, "call_id", None) or getattr(item, "id", None)
                                    name = getattr(item, "name", None)

                                    # ── search_web → Gemini ───────────────
                                    if name == "search_web":
                                        try:
                                            args = json.loads(getattr(item, "arguments", "{}") or "{}")
                                            query = args.get("query", "")
                                            if query:
                                                yield (
                                                    "data: "
                                                    + json.dumps({
                                                        "type": "search_activity",
                                                        "status": "searching",
                                                        "label": f"Searching the web for: {query[:60]}",
                                                    })
                                                    + "\n\n"
                                                )

                                                # Forward full conversation history so Gemini
                                                # can resolve pronouns and prior references.
                                                search_result = await _perform_gemini_search(
                                                    query=query,
                                                    conversation_history=messages,
                                                    local_time=local_time,
                                                    tz=tz,
                                                )

                                                sources = search_result.get("sources", [])
                                                if sources:
                                                    all_sources.extend(sources)
                                                answer = search_result.get("answer", "")

                                                # Gemini's grounded answer is the final response
                                                # for this turn — stream it directly to the client.
                                                # The Azure model does not re-synthesise this content.
                                                yield (
                                                    "data: "
                                                    + json.dumps({"type": "content_block_delta", "delta": {"text": answer}})
                                                    + "\n\n"
                                                )

                                                yield (
                                                    "data: "
                                                    + json.dumps({
                                                        "type": "search_activity",
                                                        "status": "done",
                                                        "label": f"Found {len(sources)} source(s)",
                                                        "sources": sources,
                                                    })
                                                    + "\n\n"
                                                )

                                                assistant_content = answer
                                                loop_active = False
                                                outputs = []
                                                break

                                        except Exception as search_err:
                                            logger.error("Gemini search tool call failed: %s", search_err, exc_info=True)
                                            yield (
                                                "data: "
                                                + json.dumps({
                                                    "type": "search_activity",
                                                    "status": "error",
                                                    "label": f"Web search failed: {str(search_err)}",
                                                })
                                                + "\n\n"
                                            )
                                            outputs.append({
                                                "type": "function_call_output",
                                                "call_id": call_id,
                                                "output": f"Search error: {str(search_err)}",
                                            })

                                    # ── generate_image → FLUX via Azure Queue ─
                                    elif name == "generate_image":
                                        try:
                                            args = json.loads(getattr(item, "arguments", "{}") or "{}")
                                            img_prompt = args.get("prompt", "")
                                            img_style = args.get("style", "photorealistic")
                                            if img_prompt:
                                                yield (
                                                    "data: "
                                                    + json.dumps({
                                                        "type": "search_activity",
                                                        "status": "searching",
                                                        "label": "Generating image with FLUX...",
                                                    })
                                                    + "\n\n"
                                                )
                                                job_id = await _enqueue_image_gen(
                                                    user_id, conversation_id, img_prompt, img_style
                                                )
                                                yield (
                                                    "data: "
                                                    + json.dumps({
                                                        "type": "image_gen_queued",
                                                        "job_id": job_id,
                                                        "prompt": img_prompt,
                                                    })
                                                    + "\n\n"
                                                )
                                                outputs.append({
                                                    "type": "function_call_output",
                                                    "call_id": call_id,
                                                    "output": f"Image generation job queued with ID: {job_id}.",
                                                })
                                        except Exception as img_err:
                                            logger.error("Failed to enqueue image_gen job: %s", img_err)
                                            yield (
                                                "data: "
                                                + json.dumps({
                                                    "type": "search_activity",
                                                    "status": "error",
                                                    "label": "Image generation could not be started.",
                                                })
                                                + "\n\n"
                                            )
                                            outputs.append({
                                                "type": "function_call_output",
                                                "call_id": call_id,
                                                "output": f"Image generation error: {str(img_err)}",
                                            })

                                if outputs:
                                    current_previous_response_id = response_id
                                    current_input = outputs
                                    loop_active = True

                            elif response_id:
                                yield (
                                    "data: "
                                    + json.dumps({"type": "response_id", "response_id": response_id})
                                    + "\n\n"
                                )

                        except Exception as final_err:
                            logger.warning("Could not retrieve final response or tokens: %s", final_err)
                            if not assistant_content:
                                stream_failed = True
                                error_message = str(final_err)

            except Exception as stream_init_err:
                stream_failed = True
                error_message = str(stream_init_err)
                logger.error("Error initializing stream: %s", stream_init_err)

        # ── Error handling ────────────────────────────────────────────────
        if stream_failed:
            lower_err = error_message.lower()
            is_guardrail = any(
                kw in lower_err
                for kw in ("content_filter", "responsible_ai", "policy", "safety", "trigger", "completed event")
            )
            if is_guardrail:
                friendly_err = "The request or response was flagged by safety guardrails. Modify your query and try again."
            else:
                friendly_err = f"A streaming connection issue occurred: {error_message}"

            if assistant_content:
                note = f"\n\n*(Note: Response stopped early: {friendly_err})*"
                assistant_content += note
                yield (
                    "data: "
                    + json.dumps({"type": "content_block_delta", "delta": {"text": note}})
                    + "\n\n"
                )
            else:
                yield f"data: {json.dumps({'type': 'error', 'error': friendly_err})}\n\n"
                yield "data: [DONE]\n\n"
                return

        # ── Persist assistant message ──────────────────────────────────────
        try:
            assistant_msg_insert = {
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": assistant_content,
                "routing_mode": routing_mode,
                "routing_reason": routing_reason,
                "response_id": response_id,
                "model": deployment,
                "tokens_input": prompt_tokens,
                "tokens_output": completion_tokens,
            }
            if all_sources:
                seen_urls: set[str] = set()
                deduped: List[Dict] = []
                for s in all_sources:
                    url = s.get("url")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        deduped.append(s)
                assistant_msg_insert["content_parts"] = {"sources": deduped}

            supabase = get_supabase_admin()
            supabase.table("messages").insert(assistant_msg_insert).execute()

            # Reconcile token budget
            actual_total = prompt_tokens + completion_tokens
            diff = actual_total - estimated_tokens
            if diff != 0:
                try:
                    supabase.rpc("reconcile_token_budget", {
                        "p_user_id": user_id,
                        "p_diff": diff,
                    }).execute()
                    logger.info("Reconciled token budget for user %s: diff=%d", user_id, diff)
                except Exception as rpc_err:
                    logger.warning("reconcile_token_budget RPC failed, falling back: %s", rpc_err)
                    try:
                        current_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        budget_res = (
                            supabase.table("token_budgets")
                            .select("tokens_used")
                            .eq("user_id", user_id)
                            .eq("period", current_date_str)
                            .maybe_single()
                            .execute()
                        )
                        if budget_res.data:
                            new_used = max(0, budget_res.data.get("tokens_used", 0) + diff)
                            supabase.table("token_budgets").update({
                                "tokens_used": new_used,
                            }).eq("user_id", user_id).eq("period", current_date_str).execute()
                            logger.info("Reconciled token budget for user %s via fallback: new=%d", user_id, new_used)
                    except Exception as fallback_err:
                        logger.error("Token budget fallback reconciliation failed: %s", fallback_err)

            # Update message count in conversation
            count_res = (
                supabase.table("messages")
                .select("id", count="exact")
                .eq("conversation_id", conversation_id)
                .execute()
            )
            msg_count = count_res.count if count_res.count is not None else (len(messages) + 2)
            supabase.table("conversations").update({"message_count": msg_count}).eq("id", conversation_id).execute()

        except Exception as db_err:
            logger.error("Failed to save assistant response: %s", db_err)

        # ── Audit log ─────────────────────────────────────────────────────
        try:
            supabase = get_supabase_admin()
            supabase.table("audit_log").insert({
                "user_id": user_id,
                "action": "model_route",
                "resource_type": "chat",
                "metadata": {
                    "mode": mode,
                    "deployment": deployment,
                    "reasoning": routing_reason,
                    "conversation_id": conversation_id,
                },
                "policy_decision": "ALLOW",
            }).execute()
        except Exception as audit_err:
            logger.error("Failed to log routing decision to audit_log: %s", audit_err)

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error("Error in chat stream generator: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/responses/stream")
async def stream_chat(
    payload: Dict[str, Any],
    request: Request,
    user: Dict[str, Any] = Depends(verify_jwt),
):
    """
    POST /v1/responses/stream
    Streams chat completion responses using Server-Sent Events (SSE).

    Payload fields:
      - messages (list):              Full message history
      - mode (str):                   "think", "solve", or "discuss" (default: "think")
      - conversation_id (str):        For turn tracking and audit
      - previous_response_id (str):   Response ID from last turn (stateful multi-turn)
      - timezone (str):               IANA timezone string
      - local_time (str):             User's local time string
    """
    messages = payload.get("messages", [])
    mode = payload.get("mode", "think")
    conversation_id: Optional[str] = payload.get("conversation_id")
    previous_response_id: Optional[str] = payload.get("previous_response_id")
    tz = payload.get("timezone")
    local_time = payload.get("local_time")

    if not messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty.")

    if messages[-1].get("content") == "__test_scaffold__":
        return StreamingResponse(mock_stream_generator(), media_type="text/event-stream")

    last_user_msg = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )

    supabase = get_supabase_admin()
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    # ── Resolve or create conversation ────────────────────────────────────
    is_new_conversation = False
    if not conversation_id or conversation_id == "00000000-0000-0000-0000-000000000000":
        is_new_conversation = True
        try:
            title = (last_user_msg[:30] + "...") if len(last_user_msg) > 30 else last_user_msg or "New Chat"
            conv_res = supabase.table("conversations").insert({
                "user_id": user_id,
                "title": title,
                "mode": mode,
                "agent_type": "chat",
            }).execute()
            if not conv_res.data:
                raise HTTPException(status_code=500, detail="Failed to create conversation in database.")
            conversation_id = conv_res.data[0]["id"]
            logger.info("Created new conversation %s for user %s", conversation_id, user_id)
            nano_turn_count = 0
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error creating conversation: %s", e)
            raise HTTPException(status_code=500, detail=f"Database error during conversation creation: {e}")
    else:
        try:
            conv_res = (
                supabase.table("conversations")
                .select("user_id, mode, nano_turn_count")
                .eq("id", conversation_id)
                .maybe_single()
                .execute()
            )
            if not conv_res.data:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            if conv_res.data.get("user_id") != user_id:
                raise HTTPException(status_code=403, detail="Not authorized to access this conversation.")
            db_mode = conv_res.data.get("mode")
            if db_mode:
                mode = db_mode
            nano_turn_count = conv_res.data.get("nano_turn_count", 0)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching conversation %s: %s", conversation_id, e)
            raise HTTPException(status_code=500, detail="Database error while fetching conversation details.")

    # ── Route through model router ────────────────────────────────────────
    decision = await model_router.route(
        user_message=last_user_msg,
        mode=mode,
        conversation_id=conversation_id,
        nano_turn_count=nano_turn_count,
    )
    logger.info(
        "ModelRouter decision: mode=%s deployment=%s reason=%s",
        decision.routing_mode, decision.deployment, decision.routing_reason,
    )

    if decision.was_intercepted:
        try:
            supabase.rpc("increment_nano_turns", {"p_conv_id": conversation_id}).execute()
        except Exception as e:
            logger.error("Failed to increment nano turn count: %s", e)

    # ── Save user message ─────────────────────────────────────────────────
    try:
        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "user",
            "content": last_user_msg,
        }).execute()
    except Exception as e:
        logger.error("Failed to save user message to database: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save message history.")

    db_context_messages = await build_llm_context(conversation_id)
    estimated_tokens = getattr(request.state, "estimated_tokens", 0) or 0

    return StreamingResponse(
        chat_stream_generator(
            messages=db_context_messages,
            deployment=decision.deployment,
            system_prompt=decision.system_prompt,
            routing_mode=decision.routing_mode,
            routing_reason=decision.routing_reason,
            conversation_id=conversation_id,
            user_id=user_id,
            mode=mode,
            estimated_tokens=estimated_tokens,
            previous_response_id=previous_response_id,
            tz=tz,
            local_time=local_time,
        ),
        media_type="text/event-stream",
    )
