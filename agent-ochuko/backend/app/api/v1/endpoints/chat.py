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


async def chat_stream_generator(messages: List[Dict[str, Any]], deployment: str):
    client = get_openai_client()
    try:
        # Standard format for Azure OpenAI completions stream
        response = await client.chat.completions.create(
            model=deployment,
            messages=messages,
            stream=True
        )
        async for chunk in response:
            if len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta.content:
                    # Map to the custom SSE Responses API format expected by client
                    yield f"data: {json.dumps({'type': 'content_block_delta', 'delta': {'text': delta.content}})}\n\n"
        
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
    """
    conversation_id = payload.get("conversation_id")
    messages = payload.get("messages", [])
    model = payload.get("model")

    if not messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty.")

    # In Phase 1, we default to DISCUSS mode (gpt-5.4-nano) or whatever think model deployment is set
    think_deployment = await get_config("THINK_MODEL_DEPLOYMENT", "gpt-5.4")

    # If user asks for test, return mock stream
    if messages[-1].get("content") == "__test_scaffold__":
        return StreamingResponse(
            mock_stream_generator(),
            media_type="text/event-stream"
        )

    # Otherwise stream from actual Azure OpenAI
    return StreamingResponse(
        chat_stream_generator(messages, think_deployment),
        media_type="text/event-stream"
    )

