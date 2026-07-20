import os
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
from app.core.verification_gates import verification_gates
from app.core.circuit_breaker import create_turn_circuit_breaker
from app.core.prompt_defense import prompt_defense
from app.core.reflexion_engine import create_reflexion_engine

logger = logging.getLogger("app.api.v1.endpoints.chat")
router = APIRouter()

# _OCHUKO_RULE removed — identity, tone, and capability instructions are now
# generated per-request by app.core.skills (skill-based prompt system).
# This eliminates ~350 tokens of overhead on every single request.

# Instruction injected into the system prompt for THINK/SOLVE modes only.
# Tells the model to show reasoning inside <thinking> tags before the answer.
# The backend strips these out, emits them as thinking_delta SSE events, and
# the frontend renders them in a collapsible panel — no new model required.
_THINKING_INSTRUCTION = (
    "\n\nREASONING FORMAT:\n"
    "Before giving your final answer, wrap your reasoning in <thinking> tags:\n"
    "<thinking>\n"
    "Think through the problem step by step. Question your first interpretation. "
    "Check for false assumptions. Consider what the user actually needs vs what they literally asked. "
    "If your initial reasoning has a flaw, correct it here before writing the answer.\n"
    "</thinking>\n"
    "After the closing tag, write the clean final answer with no reference to the thinking block."
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

async def _perform_google_search(
    query: str,
    synthesis_deployment: str = "",
    history: List[Dict[str, Any]] = None,
    return_raw: bool = False,
) -> Dict[str, Any]:
    """
    Two-phase multi-cloud hybrid search (reference architecture):

    Phase 1 — Google Retrieval (Gemini 2.5 Flash, google-genai SDK)
        Triggers the Google Search grounding tool to pull live web snippets
        and source metadata. Gemini is used ONLY for retrieval — it is the
        lightest, fastest path to real-time Google results.

    Phase 2 — Azure Synthesis (Azure OpenAI Responses API, async)
        The raw Google context is packaged into a system prompt and forwarded
        to the Azure OpenAI deployment for accurate, structured synthesis.
        Azure reasons over the live data; Gemini retrieves it.

    Returns { "answer": str, "sources": [{"title": str, "url": str}] }
    """
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured.")

    # ── Phase 1: Google Grounding via Gemini 2.5 Flash ────────────────────
    # Run the synchronous google-genai call off the event loop thread
    def _google_retrieval_phase() -> tuple:
        keys = []
        for var_name in ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4"]:
            key = os.getenv(var_name)
            if key and key.strip() and key not in keys:
                keys.append(key.strip())
        
        if not keys:
            raise RuntimeError("No Google/Gemini API keys configured in environment.")

        # Contextualize query with conversation history so search is aware of previous turns (e.g. "who won")
        gemini_query = query
        if history:
            history_context = "Recent conversation context:\n"
            for msg in history[-5:]:
                role = "User" if msg.get("role") == "user" else "Assistant"
                content = msg.get("content", "")
                if "[Google Search Result for:" in content:
                    parts = content.split("[Google Search Result for:")
                    content = parts[0].strip()
                history_context += f"{role}: {content}\n"
            gemini_query = (
                f"{history_context}\n"
                f"Current Query: {query}\n\n"
                "Please search Google and answer the Current Query using the conversation context above."
            )

        last_exc = None
        for idx, key in enumerate(keys):
            try:
                g_client = genai.Client(api_key=key)
                g_response = g_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=gemini_query,
                    config=genai_types.GenerateContentConfig(
                        tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                        temperature=0.1,  # near-zero: we want faithful retrieval, not creativity
                    ),
                )

                search_chunks: List[str] = []
                sources: List[Dict[str, str]] = []
                seen_urls: set = set()

                if g_response.candidates and g_response.candidates[0].grounding_metadata:
                    metadata = g_response.candidates[0].grounding_metadata

                    # Build deduplicated source list from grounding_chunks
                    for chunk in (getattr(metadata, "grounding_chunks", []) or []):
                        web = getattr(chunk, "web", None)
                        if web:
                            url = getattr(web, "uri", "") or ""
                            title = getattr(web, "title", "") or url
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                sources.append({"title": title, "url": url})

                    # Extract actual text segments from grounding_supports (preferred)
                    for support in (getattr(metadata, "grounding_supports", []) or []):
                        segment = getattr(support, "segment", None)
                        text = (getattr(segment, "text", "") or "").strip()
                        if text:
                            search_chunks.append(text)

                # Fallback: if grounding_supports is empty, format source titles as context
                if not search_chunks and sources:
                    for s in sources[:6]:
                        search_chunks.append(f"Source: {s['title']}\nURL: {s['url']}")

                google_context = "\n\n".join(search_chunks[:14]) if search_chunks else "No live web results found."
                return google_context, sources[:8]
            except Exception as e:
                logger.warning("Google search failed with key index %d: %s", idx, e)
                last_exc = e
                continue

        raise last_exc or RuntimeError("All Gemini API keys failed.")

    try:
        google_context, sources = await asyncio.to_thread(_google_retrieval_phase)
    except Exception as e:
        import traceback
        print("--- CHAT GOOGLE RETRIEVAL PHASE ERROR (FALLBACK TO AZURE KNOWLEDGE) ---")
        traceback.print_exc()
        print("------------------------------------------------------------------------")
        logger.warning("Google search retrieval failed, falling back to Azure: %s", e)
        google_context = "Google web search was unavailable. Fallback to your built-in search or training knowledge to answer."
        sources = []

    if return_raw:
        return {
            "google_context": google_context,
            "sources": sources,
            "answer": google_context
        }

    # ── Phase 2: Azure OpenAI Responses API Synthesis (async) ─────────────
    # The Google context is injected into the system prompt so Azure OpenAI
    # synthesises a grounded, cited answer — never raw Gemini output.
    deploy = (
        synthesis_deployment
        or os.getenv("SOLVE_MODEL_DEPLOYMENT")
        or os.getenv("AZURE_OPENAI_SOLVE_DEPLOYMENT")
        or "gpt-4o-mini"
    )

    system_prompt = (
        "You are an elite enterprise AI assistant. "
        "Answer the user's question accurately using the real-time web context below, "
        "retrieved directly from Google Search. Cite sources when referencing specific facts.\n\n"
        "--- GOOGLE LIVE WEB CONTEXT ---\n"
        f"{google_context}\n"
        "--- END CONTEXT ---"
    )

    try:
        az_client = get_openai_client()
        
        # Build input messages: system prompt + history + current query
        input_messages = [{"role": "system", "content": system_prompt}]
        if history:
            for msg in history:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "assistant" and "[Google Search Result for:" in content:
                    parts = content.split("[Google Search Result for:")
                    content = parts[0].strip()
                input_messages.append({"role": role, "content": content})
        input_messages.append({"role": "user", "content": query})

        az_response = await az_client.responses.create(
            model=deploy,
            input=input_messages,
        )

        answer: str = az_response.output_text or ""
        
        # Extract token usage or calculate fallback estimate if 0/None
        prompt_tokens = 0
        completion_tokens = 0
        if az_response and hasattr(az_response, "usage") and az_response.usage:
            prompt_tokens = getattr(az_response.usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(az_response.usage, "completion_tokens", 0) or 0
            
        est_input = sum(len(m.get("content", "")) for m in input_messages) // 4
        est_output = len(answer) // 4
        prompt_tokens = prompt_tokens if prompt_tokens > 0 else max(50, est_input)
        completion_tokens = completion_tokens if completion_tokens > 0 else max(10, est_output)

        return {
            "answer": answer,
            "sources": sources,
            "tokens_input": prompt_tokens,
            "tokens_output": completion_tokens,
            "model": deploy,
        }
    except Exception as e:
        import traceback
        print("--- CHAT AZURE SYNTHESIS PHASE ERROR ---")
        traceback.print_exc()
        print("-----------------------------------------")
        raise


async def _enqueue_image_gen(user_id: str, conversation_id: str, prompt: str, style: str = "") -> str:
    """
    Creates a pending image_gen job row in Supabase and dispatches it to the
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

    # enqueue_job is synchronous — run it off the event loop thread
    await asyncio.to_thread(
        enqueue_job,
        job_id=job_id,
        job_type="image_gen",
        input_metadata={"prompt": prompt, "style": style or "photorealistic"},
        user_id=user_id,
    )
    logger.info("Enqueued image_gen job %s for user %s — prompt: %.60s", job_id, user_id, prompt)
    return job_id


async def mock_stream_generator():
    """Fallback mock generator to verify connection if OpenAI is unavailable."""
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "Scaffolding "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "working! "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "Phase 1 "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "SSE Stream "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "verified."}}) + "\n\n"
    yield "data: [DONE]\n\n"


async def build_llm_context(conversation_id: str) -> List[Dict[str, Any]]:
    """
    Builds the context for the LLM by fetching non-archived messages from the database.
    This automatically includes the summary message (if compaction ran) and recent active turns.
    """
    supabase = get_supabase_admin()
    try:
        def fetch_msgs():
            return (
                supabase.table("messages")
                .select("role, content, is_summary")
                .eq("conversation_id", conversation_id)
                .eq("is_archived_msg", False)
                .order("created_at", desc=False)
                .execute()
            )
        response = await asyncio.to_thread(fetch_msgs)
        db_messages = response.data or []
        formatted_messages = []
        for msg in db_messages:
            formatted_messages.append({
                "role": msg.get("role"),
                "content": msg.get("content")
            })
        return formatted_messages
    except Exception as e:
        logger.error(f"Failed to build LLM context for conversation {conversation_id}: {e}")
        return []


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
    user_timezone: Optional[str] = None,
):
    """
    Streams a response from the Azure OpenAI Responses API (ADR-002).

    Uses client.responses.stream() — the current-generation interface.
    Accepts `previous_response_id` for stateful multi-turn: when provided,
    Azure maintains conversation state server-side and only the new user
    message needs to be sent (no full message history resend).

    Emits SSE events:
      - routing_info:        model deployment and routing mode metadata
      - search_activity:     step-by-step status while Google search runs
      - image_gen_queued:    when AI decides to generate an image
      - content_block_delta: incremental text chunk
      - response_id:         the response ID to persist and pass on next turn
      - [DONE]:              stream termination signal
    """
    client = get_openai_client()

    # Emit routing metadata so frontend knows which model was used
    yield (
        "data: "
        + json.dumps({
            "type": "routing_info",
            "deployment": deployment,
            "routing_mode": routing_mode,
        })
        + "\n\n"
    )

    # Emit conversation_id so frontend knows the real UUID of the conversation
    yield (
        "data: "
        + json.dumps({
            "type": "conversation_id",
            "conversation_id": conversation_id,
        })
        + "\n\n"
    )

    try:
        # Skills module generates the full system prompt (identity + task skill).
        # Inject the current datetime/day-of-week context into the system prompt so the model is aware of the exact date and day.
        from zoneinfo import ZoneInfo
        from datetime import timedelta
        
        local_now = None
        tz_label = "WAT"
        if user_timezone:
            try:
                tz = ZoneInfo(user_timezone)
                local_now = datetime.now(tz)
                tz_label = user_timezone
            except Exception as tz_err:
                logger.warning(f"Failed to load user timezone '{user_timezone}': {tz_err}")
                
        if local_now is None:
            # Fallback to WAT (UTC+1)
            tz = timezone(timedelta(hours=1))
            local_now = datetime.now(tz)
            
        datetime_context = (
            f"\n\n[System Context: Current User Time is {local_now.strftime('%I:%M %p')}, "
            f"Date is {local_now.strftime('%A, %B %d, %Y')} ({tz_label}).]"
        )
        full_system = system_prompt + datetime_context
        if routing_mode in ("think", "solve"):
            full_system = full_system + _THINKING_INSTRUCTION

        # Pre-loop agent task planning for complex multi-step goals
        try:
            from app.core.agent_planner import generate_plan, format_plan_for_system_prompt
            last_user_msg = ""
            if messages:
                for m in reversed(messages):
                    if m.get("role") == "user":
                        last_user_msg = m.get("content", "")
                        break
            if last_user_msg:
                plan_text = await generate_plan(
                    user_message=last_user_msg,
                    conversation_history=messages[:-1] if len(messages) > 1 else None,
                    openai_client=client,
                    nano_deployment=deployment,
                )
                if plan_text:
                    full_system += format_plan_for_system_prompt(plan_text)
                    logger.info("Injected execution plan into system prompt for user message: %.60s", last_user_msg)
        except Exception as plan_err:
            logger.warning("Task planning skipped (non-fatal): %s", plan_err)

        # State tracking for thinking-block extraction
        thinking_buffer = ""
        in_thinking_block = False
        accumulated_thinking = ""
        accumulated_image_jobs = []
        accumulated_files = []
        stream_kwargs: Dict[str, Any] = {
            "model": deployment,
            # Tools the model may call autonomously during the conversation
            "tools": [
                # Web search
                {
                    "type": "function",
                    "name": "search_web",
                    "description": (
                        "Search the web using Google for current, real-time information. "
                        "Call this whenever the user asks about recent events, news, prices, "
                        "people, weather, or anything that requires up-to-date knowledge."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The precise search query to submit to Google",
                            }
                        },
                        "required": ["query"],
                    },
                },
                # Code execution sandbox — Python / JavaScript / Bash with full internet access
                {
                    "type": "function",
                    "name": "execute_code",
                    "description": (
                        "Execute Python, JavaScript (Node.js), or Bash code in a persistent sandbox "
                        "that has FULL internet access. The sandbox can: install pip/npm packages automatically, "
                        "make HTTP/API requests, scrape web pages, process data, generate files (CSV, PNG, PDF, DOCX, ZIP), "
                        "create charts with matplotlib, perform numerical computation, convert file formats, "
                        "and more. Files produced are automatically uploaded and returned as download links.\n"
                        "Call this whenever the user wants to: run/test code, analyse data, plot charts, "
                        "fetch live data in code, convert or process files, perform computation, or any task "
                        "that benefits from actually executing code rather than describing it.\n"
                        "Do NOT use this for SVG display — output SVG in a ```svg fence instead. "
                        "Do NOT use this to generate AI images — use generate_image for that."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "The complete code to execute. Must be self-contained and runnable.",
                            },
                            "language": {
                                "type": "string",
                                "enum": ["python", "javascript", "bash"],
                                "description": "Programming language of the code snippet",
                            },
                        },
                        "required": ["code", "language"],
                    },
                },
                # AI image generation via FLUX — for new images from a text prompt only
                {
                    "type": "function",
                    "name": "generate_image",
                    "description": (
                        "Generate a brand-new image using AI (FLUX) from a natural language text description. "
                        "Use ONLY when the user wants an AI-synthesised picture from a text prompt — "
                        "e.g. 'draw a dragon', 'generate a photo of a sunset', 'create an illustration of X'. "
                        "Do NOT call this to render, convert, or execute code. "
                        "Do NOT call this for SVG-to-image conversion (output a ```svg fence instead). "
                        "Do NOT call this for data plots or charts (use execute_code with matplotlib instead)."
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
            ],
            "tool_choice": "auto",
        }

        # State tracking for thinking-block extraction and agent loop
        thinking_buffer = ""
        in_thinking_block = False
        accumulated_thinking = ""
        accumulated_image_jobs = []
        accumulated_files = []

        assistant_content = ""
        response_id = None
        prompt_tokens = 0
        completion_tokens = 0
        stream_failed = False
        error_message = ""

        # We construct a mutable copy of the messages for agent iterations
        local_messages = list(messages)
        iteration = 0
        max_iterations = 10
        circuit_breaker = create_turn_circuit_breaker(max_steps=max_iterations)
        reflexion = create_reflexion_engine(max_attempts=max_iterations)
        active_tool_step = 0

        while iteration < max_iterations:
            current_tool_calls = []
            current_stream_failed = False
            current_error_message = ""
            
            try:
                circuit_breaker.record_step(f"Turn iteration {iteration + 1}")
            except Exception as cb_err:
                logger.warning(f"Circuit breaker budget threshold: {cb_err}")

            is_final_step = (iteration == max_iterations - 1)
            
            stream_kwargs: Dict[str, Any] = {
                "model": deployment,
                "tools": [
                    {
                        "type": "function",
                        "name": "search_web",
                        "description": (
                            "Search the web using Google for current, real-time information. "
                            "Call this whenever the user asks about recent events, news, prices, "
                            "people, weather, or anything that requires up-to-date knowledge."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The precise search query to submit to Google",
                                }
                            },
                            "required": ["query"],
                        },
                    },
                    {
                        "type": "function",
                        "name": "execute_code",
                        "description": (
                            "Execute Python, JavaScript (Node.js), or Bash code in a persistent sandbox "
                            "that has FULL internet access. The sandbox can: install pip/npm packages automatically, "
                            "make HTTP/API requests, scrape web pages, process data, generate files (CSV, PNG, PDF, DOCX, ZIP), "
                            "create charts with matplotlib, perform numerical computation, convert file formats, "
                            "and more. Files produced are automatically uploaded and returned as download links.\n"
                            "Call this whenever the user wants to: run/test code, analyse data, plot charts, "
                            "fetch live data in code, convert or process files, perform computation, or any task "
                            "that benefits from actually executing code rather than describing it.\n"
                            "Do NOT use this for SVG display — output SVG in a ```svg fence instead. "
                            "Do NOT use this to generate AI images — use generate_image for that."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "code": {
                                    "type": "string",
                                    "description": "The complete code to execute. Must be self-contained and runnable.",
                                },
                                "language": {
                                    "type": "string",
                                    "enum": ["python", "javascript", "bash"],
                                    "description": "Programming language of the code snippet",
                                },
                            },
                            "required": ["code", "language"],
                        },
                    },
                    {
                        "type": "function",
                        "name": "generate_image",
                        "description": (
                            "Generate a brand-new image using AI (FLUX) from a natural language text description. "
                            "Use ONLY when the user wants an AI-synthesised picture from a text prompt — "
                            "e.g. 'draw a dragon', 'generate a photo of a sunset', 'create an illustration of X'. "
                            "Do NOT call this to render, convert, or execute code. "
                            "Do NOT call this for SVG-to-image conversion (output a ```svg fence instead). "
                            "Do NOT call this for data plots or charts (use execute_code with matplotlib instead)."
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
                ],
                "tool_choice": "none" if is_final_step else "auto",
            }

            # We use stateful multi-turn only on iteration 0 when previous_response_id is set
            if iteration == 0 and previous_response_id:
                stream_kwargs["previous_response_id"] = previous_response_id
                user_messages = [m for m in messages if m.get("role") == "user"]
                stream_kwargs["input"] = user_messages[-1:] if user_messages else messages
            else:
                # Send full accumulated messages for loop turns
                input_list = [{"role": "system", "content": full_system}] + local_messages
                stream_kwargs["input"] = input_list

            try:
                async with client.responses.stream(**stream_kwargs) as stream:
                    try:
                        async for event in stream:
                            # 1. Text delta
                            if event.type == "response.output_text.delta":
                                chunk = event.delta
                                if in_thinking_block:
                                    thinking_buffer += chunk
                                    close_pos = thinking_buffer.lower().find("</thinking")
                                    if close_pos != -1:
                                        tag_len = 10
                                        if thinking_buffer[close_pos:].startswith("</thinking>"):
                                            tag_len = 11
                                        thought_chunk = thinking_buffer[:close_pos]
                                        if thought_chunk:
                                            accumulated_thinking += thought_chunk
                                            yield (
                                                "data: "
                                                + json.dumps({"type": "thinking_delta", "delta": {"text": thought_chunk}})
                                                + "\n\n"
                                            )
                                        yield "data: " + json.dumps({"type": "thinking_done"}) + "\n\n"
                                        in_thinking_block = False
                                        after = thinking_buffer[close_pos + tag_len:].lstrip("\n")
                                        thinking_buffer = ""
                                        if after:
                                            assistant_content += after
                                            yield (
                                                "data: "
                                                + json.dumps({"type": "content_block_delta", "delta": {"text": after}})
                                                + "\n\n"
                                            )
                                    else:
                                        accumulated_thinking += chunk
                                        yield (
                                            "data: "
                                            + json.dumps({"type": "thinking_delta", "delta": {"text": chunk}})
                                            + "\n\n"
                                        )
                                else:
                                    thinking_buffer += chunk
                                    open_idx = thinking_buffer.lower().find("<thinking")
                                    if open_idx != -1:
                                        tag_len = 9
                                        if thinking_buffer[open_idx:].startswith("<thinking>"):
                                            tag_len = 10
                                        before = thinking_buffer[:open_idx]
                                        if before:
                                            assistant_content += before
                                            yield (
                                                "data: "
                                                + json.dumps({"type": "content_block_delta", "delta": {"text": before}})
                                                + "\n\n"
                                            )
                                        yield "data: " + json.dumps({"type": "thinking_start"}) + "\n\n"
                                        in_thinking_block = True
                                        thinking_buffer = thinking_buffer[open_idx + tag_len:]
                                    else:
                                        _tag = "<thinking>"
                                        if len(thinking_buffer) > len(_tag) * 2:
                                            flush = thinking_buffer[:-len(_tag)]
                                            thinking_buffer = thinking_buffer[-len(_tag):]
                                            assistant_content += flush
                                            yield (
                                                "data: "
                                                + json.dumps({"type": "content_block_delta", "delta": {"text": flush}})
                                                + "\n\n"
                                            )

                            # 2. Tool calls
                            elif event.type == "response.output_item.done":
                                item = getattr(event, "item", None)
                                if item is not None and getattr(item, "type", None) == "function_call":
                                    t_id = getattr(item, "id", None) or f"call_{len(current_tool_calls)}_{iteration}"
                                    t_name = getattr(item, "name", None)
                                    t_args = getattr(item, "arguments", "{}")
                                    current_tool_calls.append({
                                        "id": t_id,
                                        "name": t_name,
                                        "arguments": t_args
                                    })

                        # Flush any remaining buffer at the end of the stream
                        if thinking_buffer:
                            if in_thinking_block:
                                accumulated_thinking += thinking_buffer
                                yield (
                                    "data: "
                                    + json.dumps({"type": "thinking_delta", "delta": {"text": thinking_buffer}})
                                    + "\n\n"
                                )
                                yield "data: " + json.dumps({"type": "thinking_done"}) + "\n\n"
                                in_thinking_block = False
                            else:
                                assistant_content += thinking_buffer
                                yield (
                                    "data: "
                                    + json.dumps({"type": "content_block_delta", "delta": {"text": thinking_buffer}})
                                    + "\n\n"
                                )
                            thinking_buffer = ""
                    except Exception as iter_err:
                        current_stream_failed = True
                        current_error_message = str(iter_err)
                        logger.error(f"Error during stream iteration: {iter_err}")

                    # Check if the generated content contains an Azure content filter safety refusal
                    lower_content = assistant_content.lower()
                    refusal_indicators = [
                        "cannot assist with",
                        "cannot fulfill",
                        "i'm sorry, but i cannot",
                        "i am sorry, but i cannot",
                        "assist with that request",
                        "assist with this request"
                    ]
                    if any(indicator in lower_content for indicator in refusal_indicators):
                        logger.warning("Detected Azure OpenAI safety refusal in assistant content stream.")
                        current_stream_failed = True
                        current_error_message = "Content safety guardrails triggered."
                        # Strip the refusal message from the accumulated content to keep it clean
                        for indicator in refusal_indicators:
                            pos = lower_content.find(indicator)
                            if pos != -1:
                                sorry_pos = lower_content.find("i'm sorry")
                                if sorry_pos != -1:
                                    assistant_content = assistant_content[:sorry_pos].strip()
                                else:
                                    assistant_content = assistant_content[:pos].strip()
                                break

                    if not current_stream_failed:
                        try:
                            final_response = await stream.get_final_response()
                            response_id = final_response.id if final_response else None
                            if response_id:
                                yield (
                                    "data: "
                                    + json.dumps({"type": "response_id", "response_id": response_id})
                                    + "\n\n"
                                )
                            if final_response and hasattr(final_response, "usage") and final_response.usage:
                                prompt_tokens += getattr(final_response.usage, "prompt_tokens", 0) or 0
                                completion_tokens += getattr(final_response.usage, "completion_tokens", 0) or 0
                        except Exception as final_err:
                            logger.warning(f"Could not retrieve final response or tokens: {final_err}")
                            if not assistant_content and not current_tool_calls:
                                current_stream_failed = True
                                current_error_message = str(final_err)

            except Exception as stream_init_err:
                current_stream_failed = True
                current_error_message = str(stream_init_err)
                logger.error(f"Error initializing stream: {stream_init_err}")

            if current_stream_failed:
                stream_failed = True
                error_message = current_error_message
                break

            # If the model generated tool calls, execute them and continue the loop!
            if current_tool_calls:
                # Add assistant message with tool calls to local history
                tool_calls_desc = "".join(
                    f"\n\n[Executed Tool: {tc['name']} with arguments: {tc['arguments']}]"
                    for tc in current_tool_calls
                )
                local_messages.append({
                    "role": "assistant",
                    "content": (assistant_content or "") + tool_calls_desc
                })

                # Execute all tool calls in this turn
                tool_outputs = []
                for tc in current_tool_calls:
                    t_name = tc["name"]
                    t_args_str = tc["arguments"]
                    
                    # Increment tool step counter and emit dynamic agent step event
                    active_tool_step += 1
                    expected_total_steps = max(len(current_tool_calls), active_tool_step)
                    step_label = f"Executing {t_name}..."

                    try:
                        args = json.loads(t_args_str or "{}")
                        if t_name == "search_web":
                            q = args.get("query", "")
                            step_label = f"Searching web for: {q}" if q else "Searching web for information..."
                        elif t_name == "execute_code":
                            code_text = args.get("code", "").lower()
                            if any(kw in code_text for kw in ["fitz", "pdf", "docx", "signature", "document"]):
                                step_label = "Extracting document graphics & updating signatory..."
                            elif any(kw in code_text for kw in ["plot", "matplotlib", "df", "pandas"]):
                                step_label = "Processing data & generating chart..."
                            else:
                                step_label = "Running Python code in sandbox..."
                        elif t_name == "generate_image":
                            step_label = "Synthesizing image with FLUX..."
                    except Exception:
                        pass

                    yield (
                        "data: "
                        + json.dumps({
                            "type": "agent_step",
                            "step": active_tool_step,
                            "max_steps": expected_total_steps,
                            "label": step_label,
                        })
                        + "\n\n"
                    )

                    if t_name == "search_web":
                        try:
                            args = json.loads(t_args_str or "{}")
                            query = args.get("query", "")
                            if query:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": f"Searching the web for: {query}",
                                    })
                                    + "\n\n"
                                )
                                search_result = await _perform_google_search(
                                    query,
                                    synthesis_deployment=deployment,
                                    history=local_messages,
                                    return_raw=True,
                                )
                                sources = search_result.get("sources", [])
                                google_context = search_result.get("google_context", "")

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
                                tool_outputs.append(google_context)
                            else:
                                tool_outputs.append("Search query was empty.")
                        except Exception as e:
                            logger.error(f"Agent search_web failed: {e}")
                            tool_outputs.append(f"Web search error: {str(e)}")

                    elif t_name == "execute_code":
                        try:
                            from app.services.code_sandbox import execute_code_in_sandbox
                            args = json.loads(t_args_str or "{}")
                            code_str = args.get("code", "")
                            lang_str = args.get("language", "python")
                            if code_str:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": f"Running {lang_str} code...",
                                    })
                                    + "\n\n"
                                )
                                exec_output, exec_files = await execute_code_in_sandbox(
                                    code=code_str,
                                    language=lang_str,
                                    conversation_id=conversation_id,
                                    user_id=user_id,
                                    timeout_seconds=60,
                                )
                                if exec_files:
                                    accumulated_files.extend(exec_files)
                                    yield (
                                        "data: "
                                        + json.dumps({
                                            "type": "generated_files",
                                            "files": exec_files,
                                        })
                                        + "\n\n"
                                    )
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "done",
                                        "label": "Code execution complete.",
                                    })
                                    + "\n\n"
                                )
                                tool_outputs.append(f"Code execution stdout/stderr:\n{exec_output}")
                            else:
                                tool_outputs.append("Code snippet was empty.")
                        except Exception as e:
                            logger.error(f"Agent execute_code failed: {e}")
                            tool_outputs.append(f"Code sandbox error: {str(e)}")

                    elif t_name == "generate_image":
                        try:
                            args = json.loads(t_args_str or "{}")
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
                                accumulated_image_jobs.append({
                                    "job_id": job_id,
                                    "prompt": img_prompt,
                                    "status": "pending"
                                })
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "image_gen_queued",
                                        "job_id": job_id,
                                        "prompt": img_prompt,
                                    })
                                    + "\n\n"
                                )
                                tool_outputs.append(f"Image generation job queued successfully with ID: {job_id}.")
                            else:
                                tool_outputs.append("Image prompt was empty.")
                        except Exception as e:
                            logger.error(f"Agent generate_image failed: {e}")
                            tool_outputs.append(f"Image generation error: {str(e)}")
                    else:
                        tool_outputs.append(f"Unknown tool name: {t_name}")

                # Add tool response messages to local history
                for tc, t_out in zip(current_tool_calls, tool_outputs):
                    local_messages.append({
                        "role": "system",
                        "content": f"[Tool Output for {tc['name']}]:\n{t_out}"
                    })

                iteration += 1
                continue

            break

        if stream_failed:
            lower_err = error_message.lower()
            is_guardrail = (
                "content_filter" in lower_err 
                or "responsible_ai" in lower_err 
                or "policy" in lower_err 
                or "safety" in lower_err
                or "trigger" in lower_err
                or "completed event" in lower_err
            )
            is_rate_limit = (
                "rate limit" in lower_err
                or "too many requests" in lower_err
                or "429" in lower_err
                or "high demand" in lower_err
                or "provisioned throughput" in lower_err
                or "peak load" in lower_err
            )
            if is_guardrail:
                friendly_err = "The request or response was flagged by safety guardrails. Please modify your query and try again."
            elif is_rate_limit:
                friendly_err = f"The AI service is experiencing high demand: {error_message}"
            else:
                friendly_err = f"A streaming connection issue occurred: {error_message}"

            if assistant_content:
                # Append the safety/early stop notice to the partial text
                assistant_content += f"\n\n*(Note: Response stopped early: {friendly_err})*"
                yield (
                    "data: "
                    + json.dumps({"type": "content_block_delta", "delta": {"text": f"\n\n*(Note: Response stopped early: {friendly_err})*"}})
                    + "\n\n"
                )
            else:
                # No content was generated at all, yield error event and exit
                yield f"data: {json.dumps({'type': 'error', 'error': friendly_err})}\n\n"
                yield "data: [DONE]\n\n"
                return

        try:
            # Fallback estimation if actual tokens are 0/None
            est_input = sum(len(m.get("content", "")) for m in messages) // 4
            est_output = len(assistant_content) // 4
            actual_prompt_tokens = prompt_tokens if prompt_tokens > 0 else max(50, est_input)
            actual_completion_tokens = completion_tokens if completion_tokens > 0 else max(10, est_output)

            assistant_msg_insert = {
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": assistant_content,
                "routing_mode": routing_mode,
                "routing_reason": routing_reason,
                "response_id": response_id,
                "model": deployment,
                "tokens_input": actual_prompt_tokens,
                "tokens_output": actual_completion_tokens,
            }
            content_parts = {}
            if accumulated_thinking:
                content_parts["thinking_content"] = accumulated_thinking
            if accumulated_image_jobs:
                content_parts["image_jobs"] = accumulated_image_jobs
            if accumulated_files:
                content_parts["generated_files"] = [
                    {
                        "filename": f["filename"],
                        "download_url": f["download_url"],
                        "size_bytes": f["size_bytes"]
                    } for f in accumulated_files
                ]
            if content_parts:
                assistant_msg_insert["content_parts"] = content_parts
            supabase = get_supabase_admin()
            await asyncio.to_thread(
                lambda: supabase.table("messages").insert(assistant_msg_insert).execute()
            )

            # Reconcile token budget
            actual_total = actual_prompt_tokens + actual_completion_tokens
            diff = actual_total - estimated_tokens
            if diff != 0:
                try:
                    await asyncio.to_thread(
                        lambda: supabase.rpc("reconcile_token_budget", {
                            "p_user_id": user_id,
                            "p_diff": diff
                        }).execute()
                    )
                    logger.info(f"Reconciled token budget for user {user_id} via RPC: diff={diff}")
                except Exception as rpc_err:
                    logger.warning("Failed to call reconcile_token_budget RPC, falling back to read-modify-write: %s", rpc_err)
                    try:
                        current_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        def get_budget():
                            return (
                                supabase.table("token_budgets")
                                .select("tokens_used")
                                .eq("user_id", user_id)
                                .eq("period", current_date_str)
                                .maybe_single()
                                .execute()
                            )
                        budget_res = await asyncio.to_thread(get_budget)
                        if budget_res.data:
                            current_used = budget_res.data.get("tokens_used", 0)
                            new_used = max(0, current_used + diff)
                            await asyncio.to_thread(
                                lambda: supabase.table("token_budgets").update({
                                    "tokens_used": new_used
                                }).eq("user_id", user_id).eq("period", current_date_str).execute()
                            )
                            logger.info(f"Reconciled token budget for user {user_id} via fallback: new_used={new_used}")
                    except Exception as fallback_err:
                        logger.error("Failed in-memory fallback for token budget reconciliation: %s", fallback_err)

            # Update message count in conversation
            def count_msgs():
                return (
                    supabase.table("messages")
                    .select("id", count="exact")
                    .eq("conversation_id", conversation_id)
                    .execute()
                )
            count_res = await asyncio.to_thread(count_msgs)
            msg_count = count_res.count if count_res.count is not None else (len(messages) + 2)
            await asyncio.to_thread(
                lambda: supabase.table("conversations").update({
                    "message_count": msg_count,
                }).eq("id", conversation_id).execute()
            )

        except Exception as db_err:
            logger.error(f"Failed to save assistant response: {db_err}")

        # Log routing decision to audit log
        try:
            audit_entry = {
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
            }
            supabase = get_supabase_admin()
            await asyncio.to_thread(
                lambda: supabase.table("audit_log").insert(audit_entry).execute()
            )
        except Exception as audit_err:
            logger.error(f"Failed to log routing decision to audit_log: {audit_err}")

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Error in chat stream generator: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"


def is_code_or_text_file(filename: str, mime_type: str = "") -> bool:
    _, ext = os.path.splitext(filename.lower())
    code_extensions = {
        ".txt", ".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".java", 
        ".py", ".c", ".cpp", ".h", ".cs", ".sh", ".json", ".md", 
        ".yaml", ".yml", ".xml", ".sql", ".csv", ".rs", ".go", ".rb", 
        ".php", ".kt", ".gradle", ".properties", ".ipynb", ".ini", ".cfg",
        ".bat", ".cmd", ".ps1"
    }
    if ext in code_extensions:
        return True
    if mime_type and (mime_type.startswith("text/") or mime_type == "application/json" or mime_type == "application/javascript"):
        return True
    return False


_VALID_MODES = {"think", "solve", "discuss"}


@router.post("/responses/stream")
async def stream_chat(
    payload: Dict[str, Any],
    request: Request,
    user: Dict[str, Any] = Depends(verify_jwt)
):
    """
    POST /v1/responses/stream
    Streams chat completion responses using Server-Sent Events (SSE).

    Payload fields:
      - messages (list):              Full message history
      - mode (str):                   "think", "solve", or "discuss" (default: "think")
      - conversation_id (str):        For nano turn tracking and audit
      - previous_response_id (str):   Response ID from last turn (stateful multi-turn)
    """
    messages = payload.get("messages", [])
    raw_mode = payload.get("mode", "think")
    # Sanitise: coerce unknown values to the safest valid mode
    mode = raw_mode if raw_mode in _VALID_MODES else "think"
    conversation_id: Optional[str] = payload.get("conversation_id")
    previous_response_id: Optional[str] = payload.get("previous_response_id")

    if not messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty.")

    # If user asks for test, return mock stream
    if messages[-1].get("content") == "__test_scaffold__":
        return StreamingResponse(
            mock_stream_generator(),
            media_type="text/event-stream"
        )

    # Extract the latest user message text for routing analysis
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break

    supabase = get_supabase_admin()
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    # 1. Resolve or create conversation in the database
    is_new_conversation = False
    if not conversation_id or conversation_id == "00000000-0000-0000-0000-000000000000":
        is_new_conversation = True
        try:
            # Generate a title from the user's message (first 30 chars)
            title = last_user_msg[:30] + "..." if len(last_user_msg) > 30 else last_user_msg
            if not title:
                title = "New Chat"

            conv_insert = {
                "user_id": user_id,
                "title": title,
                "mode": mode,
                "agent_type": "chat",
            }

            conv_res = None
            _modes_to_try = [mode, "think"] if mode != "think" else ["think"]
            last_exc: Optional[Exception] = None
            for _attempt_mode in _modes_to_try:
                try:
                    conv_insert["mode"] = _attempt_mode
                    conv_res = await asyncio.to_thread(
                        lambda: supabase.table("conversations").insert(conv_insert).execute()
                    )
                    if conv_res.data:
                        if _attempt_mode != mode:
                            logger.warning(
                                f"conversations_mode_check blocked mode='{mode}' — "
                                f"inserted with fallback mode='{_attempt_mode}'. "
                                f"Apply scripts/016_fix_db_constraints.sql to your Supabase project."
                            )
                            mode = _attempt_mode
                        break  # success
                    # PostgREST returned success-status but empty data — unlikely but handle it
                    last_exc = Exception(f"Insert for mode='{_attempt_mode}' returned no data")
                except Exception as _ins_e:
                    last_exc = _ins_e
                    _err = str(_ins_e).lower()
                    if "mode_check" in _err or "check constraint" in _err or "constraint" in _err:
                        logger.warning(
                            f"DB constraint rejected mode='{_attempt_mode}': {_ins_e}. "
                            f"Trying fallback mode='think'."
                        )
                        continue
                    # Non-constraint error — don't bother retrying
                    raise

            if not (conv_res and conv_res.data):
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Failed to create conversation. "
                        "If mode='discuss' is not accepted, apply "
                        "scripts/016_fix_db_constraints.sql to your Supabase project. "
                        f"Last error: {last_exc}"
                    ),
                )

            conversation_id = conv_res.data[0]["id"]
            logger.info(f"Created new conversation {conversation_id} for user {user_id}")
            nano_turn_count = 0
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            raise HTTPException(status_code=500, detail=f"Database error during conversation creation: {e}")
    else:
        try:
            def fetch_conv():
                return (
                    supabase.table("conversations")
                    .select("user_id, mode, nano_turn_count")
                    .eq("id", conversation_id)
                    .maybe_single()
                    .execute()
                )
            conv_res = await asyncio.to_thread(fetch_conv)
            if not conv_res.data:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            if conv_res.data.get("user_id") != user_id:
                raise HTTPException(status_code=403, detail="Not authorized to access this conversation.")

            # Use the stored mode as the source of truth for routing
            db_mode = conv_res.data.get("mode")
            if db_mode:
                mode = db_mode
            nano_turn_count = conv_res.data.get("nano_turn_count", 0)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching conversation {conversation_id}: {e}")
            raise HTTPException(status_code=500, detail="Database error while fetching conversation details.")

    # 2. Route through the model router
    decision = await model_router.route(
        user_message=last_user_msg,
        mode=mode,
        conversation_id=conversation_id,
        nano_turn_count=nano_turn_count,
    )

    logger.info(
        f"ModelRouter decision: mode={decision.routing_mode}, "
        f"deployment={decision.deployment}, "
        f"reason={decision.routing_reason}"
    )

    # Download code/text or binary office/PDF attachments and place them in the sandbox, then inject them into the system prompt
    attachments = payload.get("attachments", [])
    injected_code_prompts = []
    injected_binary_files = []
    if attachments:
        import httpx
        for att in attachments:
            att_name = att.get("filename", "")
            att_url = att.get("url", "")
            att_mime = att.get("mime_type", "")
            
            if att_name and att_url:
                ext = os.path.splitext(att_name.lower())[1]
                is_code = is_code_or_text_file(att_name, att_mime)
                is_binary = ext in {".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls"}
                
                if is_code or is_binary:
                    try:
                        async with httpx.AsyncClient(timeout=15.0) as client:
                            r = await client.get(att_url)
                            if r.status_code == 200:
                                content_bytes = r.content
                                
                                # Standardize path matching serve_sandbox_file / execute_code_in_sandbox
                                work_dir = os.path.abspath(os.path.join("/tmp", f"sandbox_{conversation_id}")).replace("\\", "/")
                                data_dir = os.path.join(work_dir, "data")
                                os.makedirs(data_dir, exist_ok=True)
                                file_path = os.path.join(data_dir, att_name)
                                with open(file_path, "wb") as f:
                                    f.write(content_bytes)
                                    
                                logger.info(f"Successfully downloaded and placed file {att_name} in sandbox: {file_path}")
                                
                                if is_code:
                                    try:
                                        content_str = content_bytes.decode("utf-8", errors="replace")
                                    except Exception:
                                        content_str = "[Binary or non-UTF-8 content]"
                                        
                                    # Truncate content to avoid token limits (max 40k chars)
                                    if len(content_str) > 40000:
                                        content_str = content_str[:40000] + "\n... [TRUNCATED] ..."
                                        
                                    injected_code_prompts.append(
                                        f"--- START FILE: {att_name} ---\n{content_str}\n--- END FILE: {att_name} ---"
                                    )
                                else:
                                    injected_binary_files.append(att_name)
                    except Exception as e:
                        logger.error(f"Failed to process attachment {att_name}: {e}")
                        
    if injected_code_prompts or injected_binary_files:
        context_parts = []
        if injected_code_prompts:
            context_parts.append(
                "Here are the contents of the attached code/text files:\n" +
                "\n\n".join(injected_code_prompts)
            )
        if injected_binary_files:
            file_list = ", ".join(injected_binary_files)
            context_parts.append(
                f"The following binary documents have been saved to your active sandbox at `/tmp/sandbox_{conversation_id}/data/`:\n"
                f"[{file_list}]\n"
                "You cannot read them directly as text. However, you can write Python code using `execute_code` "
                "with libraries like `fitz` (PyMuPDF), `python-docx`, `docx`, `pdf2image`, `openpyxl`, or `Pillow` to "
                "manipulate them, extract visual elements/images/signatures, overlay layers (e.g. letterheads), "
                "or write new documents. Any generated/modified files will automatically be uploaded and returned as download links."
            )
            
        code_context_str = (
            "\n\n[System Context: The user has attached files to this conversation. "
            "These files have been temporarily saved to your active sandbox workspace directory data/ folder. "
            "You can run, test, read, edit, or modify them using your execute_code tool.\n\n" +
            "\n\n".join(context_parts) +
            "\n]\n\n"
        )
        decision.system_prompt += code_context_str

    # 3. If nano interceptor fired, increment the turn counter in the database
    if decision.was_intercepted:
        try:
            # We call the increment_nano_turns RPC to update the count
            await asyncio.to_thread(
                lambda: supabase.rpc("increment_nano_turns", {"p_conv_id": conversation_id}).execute()
            )
        except Exception as e:
            logger.error(f"Failed to increment nano turn count: {e}")

    # 4. Save the user's message to the database
    # Non-fatal: log the error and continue streaming — a missing user message row is
    # recoverable; aborting the entire stream is not.
    try:
        user_msg_insert = {
            "conversation_id": conversation_id,
            "role": "user",
            "content": last_user_msg,
        }
        await asyncio.to_thread(
            lambda: supabase.table("messages").insert(user_msg_insert).execute()
        )
    except Exception as e:
        logger.error(f"Failed to save user message to database (non-fatal, stream continues): {e}")

    # 5. Build context from active database messages (ignores archived/compacted ones)
    db_context_messages = await build_llm_context(conversation_id)

    # Extract the estimated tokens that were pre-deducted by the middleware
    estimated_tokens = getattr(request.state, "estimated_tokens", 0) or 0

    # Stream from Azure OpenAI Responses API
    return StreamingResponse(
        chat_stream_generator(
            db_context_messages,
            decision.deployment,
            decision.system_prompt,
            decision.routing_mode,
            decision.routing_reason,
            conversation_id,
            user_id,
            mode,
            estimated_tokens,
            previous_response_id,
            user_timezone=payload.get("timezone"),
        ),
        media_type="text/event-stream"
    )


async def _upload_generated_file(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    conversation_id: str,
    user_id: str,
) -> str:
    """Upload to R2, persist metadata. Returns public URL."""
    from app.services.cloudflare_r2 import upload_file_bytes

    # Uploads to the sharded GENERATED bucket
    r2_url = await upload_file_bytes(
        file_bytes=file_bytes,
        filename=filename,
        mime_type=mime_type,
        bucket_type="GENERATED",
        key_prefix=f"generated/{conversation_id}/"
    )

    try:
        get_supabase_admin().table("generated_files").insert({
            "conversation_id": conversation_id,
            "user_id":         user_id,
            "filename":        filename,
            "r2_url":          r2_url,
            "size_bytes":      len(file_bytes),
            "mime_type":       mime_type,
        }).execute()
    except Exception as db_err:
        logger.warning("Failed to save generated_file metadata: %s", db_err)

    return r2_url


