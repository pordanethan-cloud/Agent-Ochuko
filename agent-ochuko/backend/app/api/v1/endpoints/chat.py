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
        response = (
            supabase.table("messages")
            .select("role, content, is_summary")
            .eq("conversation_id", conversation_id)
            .eq("is_archived_msg", False)
            .order("created_at", desc=False)
            .execute()
        )
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
        # For THINK/SOLVE modes, append the reasoning instruction so the model
        # wraps its chain-of-thought in <thinking> tags that we parse below.
        full_system = system_prompt
        if routing_mode in ("think", "solve"):
            full_system = system_prompt + _THINKING_INSTRUCTION

        # State tracking for thinking-block extraction
        thinking_buffer = ""
        in_thinking_block = False
        thinking_emitted = False  # emit thinking_start once
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

        if previous_response_id:
            # Stateful multi-turn: Azure holds full history — send only the new message
            stream_kwargs["previous_response_id"] = previous_response_id
            user_messages = [m for m in messages if m.get("role") == "user"]
            stream_kwargs["input"] = user_messages[-1:] if user_messages else messages
        else:
            # First turn or fresh conversation: prepend system prompt + full input list
            input_list = [{"role": "system", "content": full_system}] + messages
            stream_kwargs["input"] = input_list

        assistant_content = ""
        response_id = None
        prompt_tokens = 0
        completion_tokens = 0
        stream_failed = False
        error_message = ""

        try:
            async with client.responses.stream(**stream_kwargs) as stream:
                try:
                    async for event in stream:
                        # Text delta events
                        if event.type == "response.output_text.delta":
                            chunk = event.delta
                            assistant_content += chunk

                            # ── Thinking block interception ────────────────────────────────
                            # THINK/SOLVE modes receive _THINKING_INSTRUCTION which tells the
                            # model to wrap reasoning in <thinking>…</thinking> before answer.
                            # We intercept those chunks here and emit them as thinking_delta
                            # SSE events so the frontend can render them in a separate panel.
                            if in_thinking_block:
                                thinking_buffer += chunk
                                close_pos = thinking_buffer.lower().find("</thinking")
                                if close_pos != -1:
                                    # Strip closing tag (resilient to missing closing bracket)
                                    tag_len = 10  # len("</thinking")
                                    if thinking_buffer[close_pos:].startswith("</thinking>"):
                                        tag_len = 11
                                    thought_chunk = thinking_buffer[:close_pos]
                                    if thought_chunk:
                                        yield (
                                            "data: "
                                            + json.dumps({"type": "thinking_delta", "delta": {"text": thought_chunk}})
                                            + "\n\n"
                                        )
                                    # Signal end of thinking
                                    yield "data: " + json.dumps({"type": "thinking_done"}) + "\n\n"
                                    in_thinking_block = False
                                    # Forward any text AFTER </thinking> as normal content
                                    after = thinking_buffer[close_pos + tag_len:].lstrip("\n")
                                    thinking_buffer = ""
                                    if after:
                                        yield (
                                            "data: "
                                            + json.dumps({"type": "content_block_delta", "delta": {"text": after}})
                                            + "\n\n"
                                        )
                                else:
                                    # Still inside thinking block — emit as thinking_delta
                                    yield (
                                        "data: "
                                        + json.dumps({"type": "thinking_delta", "delta": {"text": chunk}})
                                        + "\n\n"
                                    )
                            else:
                                thinking_buffer += chunk
                                open_idx = thinking_buffer.lower().find("<thinking")
                                if open_idx != -1 and not thinking_emitted:
                                    # Strip opening tag (resilient to missing closing bracket)
                                    tag_len = 9  # len("<thinking")
                                    if thinking_buffer[open_idx:].startswith("<thinking>"):
                                        tag_len = 10
                                    # Emit any text before <thinking> as normal content
                                    before = thinking_buffer[:open_idx]
                                    if before:
                                        yield (
                                            "data: "
                                            + json.dumps({"type": "content_block_delta", "delta": {"text": before}})
                                            + "\n\n"
                                        )
                                    # Signal thinking panel open
                                    yield "data: " + json.dumps({"type": "thinking_start"}) + "\n\n"
                                    thinking_emitted = True
                                    in_thinking_block = True
                                    # Buffer only what comes after <thinking>
                                    thinking_buffer = thinking_buffer[open_idx + tag_len:]
                                elif not thinking_emitted:
                                    # Haven't hit <thinking> yet — keep a short trailing buffer
                                    # to catch tags that arrive split across chunks, flush older text
                                    _tag = "<thinking>"
                                    if len(thinking_buffer) > len(_tag) * 2:
                                        flush = thinking_buffer[:-len(_tag)]
                                        thinking_buffer = thinking_buffer[-len(_tag):]
                                        yield (
                                            "data: "
                                            + json.dumps({"type": "content_block_delta", "delta": {"text": flush}})
                                            + "\n\n"
                                        )
                                else:
                                    # thinking already done — forward as normal
                                    thinking_buffer = ""
                                    yield (
                                        "data: "
                                        + json.dumps({"type": "content_block_delta", "delta": {"text": chunk}})
                                        + "\n\n"
                                    )


                        # Function tool calls — AI autonomously called one of our tools
                        elif event.type == "response.output_item.done":
                            item = getattr(event, "item", None)
                            if item is None or getattr(item, "type", None) != "function_call":
                                pass  # not a function call, skip

                            elif getattr(item, "name", None) == "search_web":
                                # —— Google Web Search ——————————————————————
                                try:
                                    args = json.loads(getattr(item, "arguments", "{}") or "{}")
                                    query = args.get("query", "")
                                    if query:
                                        # Tell the frontend: search is starting
                                        yield (
                                            "data: "
                                            + json.dumps({
                                                "type": "search_activity",
                                                "status": "searching",
                                                "label": f"Searching Google for: {query[:60]}",
                                            })
                                            + "\n\n"
                                        )
                                        search_result = await _perform_google_search(
                                            query,
                                            synthesis_deployment=deployment,
                                            history=messages,
                                        )
                                        sources = search_result.get("sources", [])
                                        snippet = search_result.get("answer", "")[:1200]

                                        # Tell the frontend: search done + sources ready
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

                                        # Inject the search result as a text block so the model
                                        # can reference it in its streamed reply
                                        grounding_text = (
                                            f"[Google Search Result for: {query}]\n"
                                            f"{snippet}\n"
                                            f"Sources: {', '.join(s['url'] for s in sources[:5])}"
                                        )
                                        assistant_content += grounding_text
                                        yield (
                                            "data: "
                                            + json.dumps({
                                                "type": "content_block_delta",
                                                "delta": {"text": ""},  # empty — content injected server-side
                                            })
                                            + "\n\n"
                                        )
                                except Exception as search_err:
                                    import traceback
                                    print("--- GOOGLE SEARCH TOOL EXCEPTION ---")
                                    traceback.print_exc()
                                    print("-------------------------------------")
                                    logger.error("Google search tool call failed: %s", search_err, exc_info=True)
                                    yield (
                                        "data: "
                                        + json.dumps({
                                            "type": "search_activity",
                                            "status": "error",
                                            "label": f"Web search failed: {str(search_err)}",
                                        })
                                        + "\n\n"
                                    )

                            elif getattr(item, "name", None) == "generate_image":
                                # —— Image Generation ——————————————————————
                                try:
                                    args = json.loads(getattr(item, "arguments", "{}") or "{}")
                                    img_prompt = args.get("prompt", "")
                                    img_style = args.get("style", "photorealistic")
                                    if img_prompt:
                                        # Tell the frontend: image job is queued
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

                            elif getattr(item, "name", None) == "execute_code":
                                # ── Code Sandbox Execution (internet-enabled) ──────────────
                                try:
                                    from app.services.code_sandbox import execute_code_in_sandbox
                                    args = json.loads(getattr(item, "arguments", "{}") or "{}")
                                    code_str  = args.get("code", "")
                                    lang_str  = args.get("language", "python")

                                    if code_str:
                                        # Notify frontend that code is running
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

                                        # Notify frontend: execution done
                                        yield (
                                            "data: "
                                            + json.dumps({
                                                "type": "search_activity",
                                                "status": "done",
                                                "label": "Code execution complete.",
                                            })
                                            + "\n\n"
                                        )

                                        # Inject the execution output into the assistant reply so
                                        # the model can reason over it and narrate the result.
                                        result_block = f"\n\n**Code output:**\n```\n{exec_output[:6000]}\n```"
                                        if exec_files:
                                            file_list = ", ".join(f["filename"] for f in exec_files)
                                            result_block += f"\n\n**Generated files:** {file_list}"
                                        assistant_content += result_block

                                        # Stream the result block as a delta so it appears in the chat
                                        yield (
                                            "data: "
                                            + json.dumps({
                                                "type": "content_block_delta",
                                                "delta": {"text": result_block},
                                            })
                                            + "\n\n"
                                        )

                                        # Forward generated file cards to the frontend
                                        if exec_files:
                                            yield (
                                                "data: "
                                                + json.dumps({
                                                    "type": "generated_files",
                                                    "files": exec_files,
                                                })
                                                + "\n\n"
                                            )

                                except Exception as exec_err:
                                    logger.error("Code sandbox execution failed: %s", exec_err, exc_info=True)
                                    err_text = f"\n\n**Code execution error:** {exec_err}"
                                    assistant_content += err_text
                                    yield (
                                        "data: "
                                        + json.dumps({
                                            "type": "content_block_delta",
                                            "delta": {"text": err_text},
                                        })
                                        + "\n\n"
                                    )

                        # Legacy web_search_preview events — forward if they somehow still appear
                        elif event.type in (
                            "response.web_search_call.in_progress",
                            "response.web_search_call.searching",
                        ):
                            yield (
                                "data: "
                                + json.dumps({"type": "search_activity", "status": "searching", "label": "Searching the web..."})
                                + "\n\n"
                            )
                        elif event.type == "response.web_search_call.completed":
                            yield (
                                "data: "
                                + json.dumps({"type": "search_activity", "status": "done", "label": "Search complete."})
                                + "\n\n"
                            )
                except Exception as iter_err:
                    stream_failed = True
                    error_message = str(iter_err)
                    logger.error(f"Error during stream iteration: {iter_err}")

                if not stream_failed:
                    try:
                        final_response = await stream.get_final_response()
                        response_id = final_response.id if final_response else None
                        if response_id:
                            yield (
                                "data: "
                                + json.dumps({"type": "response_id", "response_id": response_id})
                                + "\n\n"
                            )

                        # Extract actual token usage details
                        if final_response and hasattr(final_response, "usage") and final_response.usage:
                            prompt_tokens = getattr(final_response.usage, "prompt_tokens", 0) or 0
                            completion_tokens = getattr(final_response.usage, "completion_tokens", 0) or 0
                    except Exception as final_err:
                        logger.warning(f"Could not retrieve final response or tokens: {final_err}")
                        # If get_final_response fails but we streamed content, don't crash the conversation
                        if not assistant_content:
                            stream_failed = True
                            error_message = str(final_err)

        except Exception as stream_init_err:
            stream_failed = True
            error_message = str(stream_init_err)
            logger.error(f"Error initializing stream: {stream_init_err}")

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
            if is_guardrail:
                friendly_err = "The request or response was flagged by safety guardrails. Please modify your query and try again."
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
            supabase = get_supabase_admin()
            supabase.table("messages").insert(assistant_msg_insert).execute()

            # Reconcile token budget
            actual_total = actual_prompt_tokens + actual_completion_tokens
            diff = actual_total - estimated_tokens
            if diff != 0:
                try:
                    supabase.rpc("reconcile_token_budget", {
                        "p_user_id": user_id,
                        "p_diff": diff
                    }).execute()
                    logger.info(f"Reconciled token budget for user {user_id} via RPC: diff={diff}")
                except Exception as rpc_err:
                    logger.warning("Failed to call reconcile_token_budget RPC, falling back to read-modify-write: %s", rpc_err)
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
                            current_used = budget_res.data.get("tokens_used", 0)
                            new_used = max(0, current_used + diff)
                            supabase.table("token_budgets").update({
                                "tokens_used": new_used
                            }).eq("user_id", user_id).eq("period", current_date_str).execute()
                            logger.info(f"Reconciled token budget for user {user_id} via fallback: new_used={new_used}")
                    except Exception as fallback_err:
                        logger.error("Failed in-memory fallback for token budget reconciliation: %s", fallback_err)

            # Update message count in conversation
            count_res = (
                supabase.table("messages")
                .select("id", count="exact")
                .eq("conversation_id", conversation_id)
                .execute()
            )
            msg_count = count_res.count if count_res.count is not None else (len(messages) + 2)
            supabase.table("conversations").update({
                "message_count": msg_count,
            }).eq("id", conversation_id).execute()

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
            supabase.table("audit_log").insert(audit_entry).execute()
        except Exception as audit_err:
            logger.error(f"Failed to log routing decision to audit_log: {audit_err}")

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Error in chat stream generator: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"


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
                    conv_res = supabase.table("conversations").insert(conv_insert).execute()
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

    # 3. If nano interceptor fired, increment the turn counter in the database
    if decision.was_intercepted:
        try:
            # We call the increment_nano_turns RPC to update the count
            supabase.rpc("increment_nano_turns", {"p_conv_id": conversation_id}).execute()
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
        supabase.table("messages").insert(user_msg_insert).execute()
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


