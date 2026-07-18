# app/api/v1/endpoints/audio.py
"""
Audio API routes ΓÇö /v1/audio/*

Provides a SYNCHRONOUS real-time dictation endpoint (POST /v1/audio/transcriptions).
This is distinct from the async speech_stt_worker queue path, which handles full
audio file transcription jobs.

The dictation path is optimised for low-latency: the caller submits short audio
chunks produced by the browser's MediaRecorder (Γëñ30 s each), receives a
transcript within 1ΓÇô2 s, and may supply already-transcribed text so the Nano
model can stitch + grammar-correct the running transcript.
"""
import os
import io
import asyncio
import logging
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from groq import Groq

from app.core.jwt_validator import verify_jwt

logger = logging.getLogger("app.api.v1.endpoints.audio")
router = APIRouter()

# ---------------------------------------------------------------------------
# Groq client ΓÇö round-robin across multiple API keys (same pattern as chat.py)
# ---------------------------------------------------------------------------

_groq_key_index = 0
_groq_clients: list[Groq] = []


def _get_groq_client() -> Groq:
    """Return a Groq client, round-robining across all configured API keys."""
    global _groq_key_index, _groq_clients

    if not _groq_clients:
        raw = os.getenv("GROQ_API_KEYS", "")
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        if not keys:
            raise RuntimeError("GROQ_API_KEYS environment variable is not configured.")
        _groq_clients = [Groq(api_key=k) for k in keys]
        logger.info("Initialised %d Groq client(s) for audio transcription.", len(_groq_clients))

    client = _groq_clients[_groq_key_index % len(_groq_clients)]
    _groq_key_index = (_groq_key_index + 1) % len(_groq_clients)
    return client


# ---------------------------------------------------------------------------
# Azure OpenAI ΓÇö Nano model for grammar / capitalisation stitching
# ---------------------------------------------------------------------------

def _get_nano_deployment() -> str:
    deployment = os.getenv("NANO_MODEL_DEPLOYMENT", "gpt-5.4-nano")
    if not deployment:
        raise RuntimeError("NANO_MODEL_DEPLOYMENT is not configured.")
    return deployment


async def _stitch_text(existing_text: str, new_transcript: str) -> tuple[str, str]:
    """
    Use the Nano model to merge *existing_text* with *new_transcript* into a
    single grammatically-correct, well-capitalised sentence or paragraph.

    Returns a tuple: (full_stitched_text, incremental_delta)

    If *existing_text* is empty we skip the stitching call and return
    *new_transcript* directly ΓÇö avoids a round-trip for the first chunk.
    """
    if not existing_text.strip():
        return new_transcript.strip(), new_transcript.strip()

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")
    deployment = _get_nano_deployment()

    if not endpoint or not api_key:
        # If OpenAI is unavailable, degrade gracefully ΓÇö just concatenate
        logger.warning("Azure OpenAI not configured; skipping stitching, concatenating instead.")
        separator = " " if existing_text.endswith((" ", "\n")) else " "
        stitched = (existing_text + separator + new_transcript).strip()
        # Calculate delta: remove existing_text prefix from stitched
        delta = stitched[len(existing_text.rstrip()):].lstrip()
        return stitched, delta

    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    system_prompt = (
        "You are a transcription editor. The user will provide two pieces of text: "
        "an existing transcript fragment and a newly transcribed chunk. "
        "Merge them into a single grammatically-correct, properly-capitalised paragraph. "
        "Do NOT add any commentary ΓÇö output only the merged text."
    )
    user_message = (
        f"Existing transcript:\n{existing_text}\n\n"
        f"New chunk:\n{new_transcript}"
    )

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                url,
                headers={"api-key": api_key, "Content-Type": "application/json"},
                json={
                    "model": deployment,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "max_tokens": 512,
                    "temperature": 0.0,
                },
            )
            response.raise_for_status()
            data = response.json()
            stitched = data["choices"][0]["message"]["content"].strip()
            # Calculate delta: remove existing_text prefix from stitched
            delta = stitched[len(existing_text.rstrip()):].lstrip()
            return stitched, delta
    except Exception as exc:
        # Non-fatal: fall back to simple concatenation so the user always gets text
        logger.warning("Nano stitching failed (%s); falling back to concatenation.", exc)
        stitched = (existing_text + " " + new_transcript).strip()
        delta = stitched[len(existing_text.rstrip()):].lstrip()
        return stitched, delta


# ---------------------------------------------------------------------------
# POST /v1/audio/transcriptions
# ---------------------------------------------------------------------------

@router.post(
    "/transcriptions",
    summary="Synchronous dictation transcription",
    description=(
        "Accepts a short audio chunk (Γëñ30 s, audio/webm or audio/mp4) produced by the "
        "browser's MediaRecorder. Transcribes via Groq Whisper Large v3 Turbo and "
        "optionally stitches the result into *existing_text* using the Nano model for "
        "grammar and capitalisation correction. Returns the unified transcript immediately."
    ),
)
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio chunk ΓÇö audio/webm or audio/mp4"),
    existing_text: str = Form(default="", description="Already-transcribed text from previous chunks"),
    user: Dict[str, Any] = Depends(verify_jwt),
) -> dict:
    """
    Synchronous dictation path ΓÇö used by useVoice.ts on every VAD-triggered chunk.

    NOT the async queue path (speech_stt_worker) which handles full file uploads.
    """
    # ΓöÇΓöÇ Validate input ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No audio file provided.")

    audio_bytes = await file.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    # Clamp to 25 MB ΓÇö Groq Whisper limit is 25 MB
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="Audio chunk exceeds the 25 MB limit. Please use shorter recording intervals.",
        )

    logger.info(
        "Dictation chunk: user=%s, size=%d bytes, existing_text_len=%d",
        user.get("sub", "unknown"),
        len(audio_bytes),
        len(existing_text),
    )

    # ΓöÇΓöÇ Transcribe via Groq Whisper ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    try:
        groq_client = _get_groq_client()

        # Determine the correct filename/content-type for Groq
        # Groq accepts audio/webm (Chrome/Android) and audio/mp4 (Safari iOS)
        raw_content_type = file.content_type or "audio/webm"
        if "mp4" in raw_content_type:
            clean_content_type = "audio/mp4"
            filename = "chunk.mp4"
        else:
            clean_content_type = "audio/webm"
            filename = "chunk.webm"

        logger.debug("Transcribing via Groq Whisper: filename=%s type=%s size=%d", filename, clean_content_type, len(audio_bytes))

        def _call_groq():
            return groq_client.audio.transcriptions.create(
                file=(filename, io.BytesIO(audio_bytes), clean_content_type),
                model="whisper-large-v3-turbo",
                response_format="text",
                language="en",
            )

        transcription = await asyncio.to_thread(_call_groq)

        # Groq returns a string when response_format="text"
        raw_transcript: str = transcription if isinstance(transcription, str) else transcription.text
        raw_transcript = raw_transcript.strip()

        # Clean transcript to match common Whisper hallucinations on silent/noisy audio
        cleaned_transcript = "".join(c for c in raw_transcript if c.isalnum() or c.isspace()).lower().strip()
        whisper_hallucinations = {
            "thank you",
            "thank you very much",
            "thanks for watching",
            "you",
            "bye",
            "please subscribe",
            "subscribe",
            "subtitles by",
            "subtitles",
        }

        if not raw_transcript or cleaned_transcript in whisper_hallucinations:
            # Silent/hallucinated chunk — return existing text unchanged
            return {"text": existing_text}

    except Exception as exc:
        logger.error("Groq Whisper transcription failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Transcription service temporarily unavailable. Please try again.",
        )

    # ΓöÇΓöÇ Stitch with existing text via Nano model ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
    try:
        stitched, delta = await _stitch_text(existing_text, raw_transcript)
    except Exception as exc:
        logger.warning("Text stitching error (%s); returning concatenation.", exc)
        stitched = (existing_text + " " + raw_transcript).strip()
        delta = stitched[len(existing_text.rstrip()):].lstrip()

    return {"text": stitched, "delta": delta}
