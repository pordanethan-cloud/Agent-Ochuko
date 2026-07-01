# app/api/v1/endpoints/audio.py
"""
Audio API endpoints — /v1/audio/*
Handles synchronous dictation chunk transcriptions and stitching.
"""
import io
import os
import asyncio
import logging
import itertools
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.core.jwt_validator import verify_jwt
from app.api.v1.endpoints.chat import get_openai_client

logger = logging.getLogger("app.api.v1.endpoints.audio")
router = APIRouter()

# Round-robin iterator over Groq API keys for load distribution and high reliability
_groq_key_cycle = None

def _get_next_groq_key() -> str:
    """Returns the next Groq API key from the comma-separated pool, cycling round-robin."""
    global _groq_key_cycle
    if _groq_key_cycle is None:
        raw = os.environ.get("GROQ_API_KEYS", "")
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        if not keys:
            # Fallback to single key
            single = os.environ.get("GROQ_API_KEY", "")
            if single:
                keys = [single]
            else:
                raise RuntimeError("GROQ_API_KEYS is not configured.")
        _groq_key_cycle = itertools.cycle(keys)
    return next(_groq_key_cycle)


async def groq_transcribe(audio_bytes: bytes, filename: str) -> str:
    """Transcribes audio bytes using Groq Whisper Large v3 Turbo with key fallback support."""
    raw_keys = os.environ.get("GROQ_API_KEYS", "")
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if not keys:
        single = os.environ.get("GROQ_API_KEY", "")
        if single:
            keys = [single]
        else:
            raise RuntimeError("GROQ_API_KEYS is not configured.")

    last_err = None
    for api_key in keys:
        try:
            # Groq client creation and call is blocking, run in executor
            def _call():
                from groq import Groq
                client = Groq(api_key=api_key)
                file_obj = io.BytesIO(audio_bytes)
                file_obj.name = filename
                return client.audio.transcriptions.create(
                    file=file_obj,
                    model="whisper-large-v3-turbo",
                    response_format="json"
                )
            res = await asyncio.to_thread(_call)
            return res.text.strip()
        except Exception as e:
            logger.warning("Groq transcription failed with key %s...: %s", api_key[:10], e)
            last_err = e
    raise last_err or RuntimeError("All Groq keys exhausted.")


async def nano_stitch(existing_text: str, new_transcript: str) -> str:
    """Stitches new transcription chunk with existing text using Azure OpenAI gpt-5.4-nano."""
    deploy = os.getenv("NANO_MODEL_DEPLOYMENT", "gpt-5.4-nano")
    az_client = get_openai_client()
    
    system_prompt = (
        "You are an assistant that stitches real-time voice transcription chunks into a single, cohesive text block. "
        "Combine the existing text and the new transcription chunk seamlessly. "
        "Correct any obvious transcription errors, grammar, punctuation, and capitalization. "
        "Do NOT change the user's intent or meaning. "
        "Output ONLY the final stitched and corrected text, with no explanations, introduction, or conversational filler."
    )
    
    user_prompt = f"Existing Text:\n{existing_text}\n\nNew Chunk:\n{new_transcript}\n\nStitched Text:"
    
    try:
        az_response = await az_client.responses.create(
            model=deploy,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return az_response.output_text.strip()
    except Exception as e:
        logger.error("Nano stitching failed: %s. Falling back to simple concatenation.", e)
        # Fallback to simple concatenation if LLM fails
        if existing_text.endswith(" ") or new_transcript.startswith(" "):
            return f"{existing_text}{new_transcript}".strip()
        return f"{existing_text} {new_transcript}".strip()


class TranscriptionResponse(BaseModel):
    text: str


@router.post("/audio/transcriptions", response_model=TranscriptionResponse, summary="Synchronous voice dictation transcription and stitching")
async def transcribe_audio(
    file: UploadFile = File(...),
    existing_text: str = Form(default=""),
    user: Dict[str, Any] = Depends(verify_jwt)
) -> TranscriptionResponse:
    """
    Synchronous dictation: accepts a webm/mp4 audio chunk, transcribes via Groq Whisper,
    and optionally stitches with existing text via Azure OpenAI gpt-5.4-nano.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Audio file is empty.")

        filename = file.filename or "chunk.webm"
        transcript = await groq_transcribe(audio_bytes, filename)

        if not transcript.strip():
            # If nothing was transcribed, just return the existing text
            return TranscriptionResponse(text=existing_text)

        if existing_text.strip():
            stitched = await nano_stitch(existing_text, transcript)
            return TranscriptionResponse(text=stitched)

        return TranscriptionResponse(text=transcript)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to process dictation chunk for user %s: %s", user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to transcribe dictation: {str(e)}")
