# app/api/v1/endpoints/chat.py
import os
import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.core.jwt_validator import verify_jwt
from app.core.config import get_config
from app.core import model_router
from openai import AsyncAzureOpenAI

logger = logging.getLogger("app.api.v1.endpoints.chat")
router = APIRouter()

# Hard rule prepended to every system prompt at the API level.
# This is the canonical Ochuko and no-emoji enforcement — applied regardless of what
# App Configuration or default prompts say.
_OCHUKO_RULE = "You are Ochuko — calm, cold, emoji-free, and objective. You do not moralize. "

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


async def mock_stream_generator():
    """Fallback mock generator to verify connection if OpenAI is unavailable."""
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "Scaffolding "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "working! "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "Phase 1 "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "SSE Stream "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "verified."}}) + "\n\n"
    yield "data: [DONE]\n\n"


async def chat_stream_generator(
    messages: List[Dict[str, Any]],
    deployment: str,
    system_prompt: str,
    routing_mode: str,
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
      - web_search_status:   "searching" when web search starts, "done" when complete
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

    try:
        # Prepend the absolute Ochuko identity and no-emoji rule to every system prompt
        full_system = _OCHUKO_RULE + system_prompt

        stream_kwargs: Dict[str, Any] = {
            "model": deployment,
            # Web search is always available — model decides via tool_choice:auto
            "tools": [{"type": "web_search_preview"}],
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

        async with client.responses.stream(**stream_kwargs) as stream:
            async for event in stream:
                # Text delta events
                if event.type == "response.output_text.delta":
                    yield (
                        "data: "
                        + json.dumps({"type": "content_block_delta", "delta": {"text": event.delta}})
                        + "\n\n"
                    )

                # Web search lifecycle events → forward status to frontend
                elif event.type in (
                    "response.web_search_call.in_progress",
                    "response.web_search_call.searching",
                ):
                    yield (
                        "data: "
                        + json.dumps({"type": "web_search_status", "status": "searching"})
                        + "\n\n"
                    )
                elif event.type == "response.web_search_call.completed":
                    yield (
                        "data: "
                        + json.dumps({"type": "web_search_status", "status": "done"})
                        + "\n\n"
                    )

            # After stream completes, emit the response_id for the frontend to persist
            final_response = await stream.get_final_response()
            if final_response and final_response.id:
                yield (
                    "data: "
                    + json.dumps({"type": "response_id", "response_id": final_response.id})
                    + "\n\n"
                )

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Error in chat stream generator: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"


@router.post("/responses/stream")
async def stream_chat(
    payload: Dict[str, Any],
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
    mode = payload.get("mode", "think")
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

    # Get nano turn count for this conversation (if tracked)
    nano_turn_count = 0
    # TODO: Fetch from Supabase conversations.nano_turn_count when
    # Supabase service client is wired in (Phase 7 middleware)

    # Route through the model router
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

    # If nano interceptor fired, increment the turn counter
    # TODO: Call Supabase RPC increment_nano_turns(conversation_id)
    # when Supabase service client is wired in

    # Stream from Azure OpenAI Responses API
    return StreamingResponse(
        chat_stream_generator(
            messages,
            decision.deployment,
            decision.system_prompt,
            decision.routing_mode,
            previous_response_id,
        ),
        media_type="text/event-stream"
    )

