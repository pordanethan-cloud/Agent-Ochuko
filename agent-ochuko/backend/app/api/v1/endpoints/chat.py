# app/api/v1/endpoints/chat.py
import os
import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.core.jwt_validator import verify_jwt
from app.core.config import get_config
from openai import AsyncAzureOpenAI

logger = logging.getLogger("app.api.v1.endpoints.chat")
router = APIRouter()

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
    previous_response_id: Optional[str] = None,
):
    """
    Streams a response from the Azure OpenAI Responses API (ADR-002).

    Uses client.responses.stream() — the current-generation interface.
    Accepts `previous_response_id` for stateful multi-turn: when provided,
    Azure maintains conversation state server-side and only the new user
    message needs to be sent (no full message history resend).

    Emits SSE events:
      - content_block_delta: incremental text chunk
      - response_id:         the response ID to persist and pass on next turn
      - [DONE]:              stream termination signal
    """
    client = get_openai_client()
    try:
        stream_kwargs: Dict[str, Any] = {
            "model": deployment,
        }

        if previous_response_id:
            # Stateful multi-turn: Azure holds full history — send only the new message
            stream_kwargs["previous_response_id"] = previous_response_id
            # Extract the last user message only
            user_messages = [m for m in messages if m.get("role") == "user"]
            stream_kwargs["input"] = user_messages[-1:] if user_messages else messages
        else:
            # First turn or fresh conversation: send full input list
            stream_kwargs["input"] = messages

        async with client.responses.stream(**stream_kwargs) as stream:
            async for event in stream:
                # Text delta events
                if event.type == "response.output_text.delta":
                    yield (
                        "data: "
                        + json.dumps({"type": "content_block_delta", "delta": {"text": event.delta}})
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
      - messages (list):           Full message history (used on first turn or if no previous_response_id)
      - previous_response_id (str, optional): Response ID from last turn — enables stateful
                                               multi-turn without resending full history (ADR-002)
      - conversation_id (str):     Used for quota/audit tracking
      - model (str, optional):     Ignored here — deployment resolved by model_router (Phase 7)
    """
    messages = payload.get("messages", [])
    previous_response_id: Optional[str] = payload.get("previous_response_id")

    if not messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty.")

    # Default to DISCUSS mode deployment (gpt-5.4-nano) until model_router is wired in Phase 7
    think_deployment = await get_config("THINK_MODEL_DEPLOYMENT", "gpt-5.4")

    # If user asks for test, return mock stream
    if messages[-1].get("content") == "__test_scaffold__":
        return StreamingResponse(
            mock_stream_generator(),
            media_type="text/event-stream"
        )

    # Stream from Azure OpenAI Responses API
    return StreamingResponse(
        chat_stream_generator(messages, think_deployment, previous_response_id),
        media_type="text/event-stream"
    )
