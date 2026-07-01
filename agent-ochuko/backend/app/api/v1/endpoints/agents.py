# app/api/v1/endpoints/agents.py
"""
Agents API routes — /v1/agents/*
Handles queuing asynchronous background agent tasks (OCR, Vision)
via the storage queue (Pattern B).
"""
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.jwt_validator import verify_jwt
from app.services.supabase_admin import get_supabase_admin
from app.services.queue_dispatcher import enqueue_job

logger = logging.getLogger("app.api.v1.endpoints.agents")
router = APIRouter()


class OCRRequest(BaseModel):
    conversation_id: str = Field(..., description="The conversation UUID associated with this job")
    blob_url: str = Field(..., description="The direct Azure Blob URL to the PDF document")


class VisionRequest(BaseModel):
    conversation_id: str = Field(..., description="The conversation UUID associated with this job")
    blob_url: str = Field(..., description="The direct Azure Blob URL to the image")
    prompt: str = Field("Describe the content in this image.", description="The prompt/inquiry for vision analysis")


class ImageGenRequest(BaseModel):
    conversation_id: str = Field(..., description="The conversation UUID associated with this job")
    prompt: str = Field(..., description="Text description of the image to generate")
    style: str = Field("photorealistic", description="Visual style: photorealistic | illustration | abstract | sketch")


class JobResponse(BaseModel):
    job_id: str = Field(..., description="The created background job UUID")
    status: str = Field("pending", description="The current status of the job")


def _safe_execute(query) -> Optional[Any]:
    """Run a Supabase query and return the response, or None on any error."""
    try:
        return query.execute()
    except Exception as exc:
        logger.warning("Supabase query failed (non-fatal): %s", exc)
        return None


def _ensure_conversation(supabase, conversation_id: str, user_id: str) -> None:
    """
    Upsert a conversation row so the FK on jobs.conversation_id is always satisfied.
    The frontend may generate a UUID locally before the backend has created the DB row.
    If the row already exists this is a no-op.
    """
    try:
        supabase.table("conversations").upsert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "title": "Agent Job",
                "message_count": 0,
            },
            on_conflict="id"
        ).execute()
    except Exception as exc:
        # Non-fatal if row already exists — FK will be satisfied either way
        logger.warning("Could not upsert conversation %s: %s", conversation_id, exc)


@router.post("/ocr", response_model=JobResponse, status_code=202, summary="Queue a document OCR / layout extraction task")
async def queue_ocr_job(
    payload: OCRRequest,
    user: Dict[str, Any] = Depends(verify_jwt)
) -> JobResponse:
    """
    Validates monthly OCR quota limits, inserts a pending task into the jobs table,
    enqueues it to Azure Queue Storage, and returns 202 Accepted.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    conversation_id = payload.conversation_id.strip()
    blob_url = payload.blob_url.strip()

    supabase = get_supabase_admin()

    try:
        # 1. Enforce monthly agent quota limit (soft-fail: if table missing, allow through)
        current_period = datetime.now(timezone.utc).strftime("%Y-%m")
        quota_res = _safe_execute(
            supabase.table("agent_quotas")
            .select("ocr_pages_used")
            .eq("user_id", user_id)
            .eq("period", current_period)
            .maybe_single()
        )
        pages_used = 0
        if quota_res and quota_res.data and isinstance(quota_res.data, dict):
            pages_used = quota_res.data.get("ocr_pages_used", 0) or 0

        settings_res = _safe_execute(
            supabase.table("admin_settings")
            .select("value")
            .eq("key", "max_ocr_pages_per_user")
            .maybe_single()
        )
        limit = 50
        if settings_res and settings_res.data and isinstance(settings_res.data, dict):
            try:
                limit = int(settings_res.data.get("value", 50))
            except (ValueError, TypeError):
                limit = 50

        if pages_used >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Monthly OCR pages quota exceeded ({pages_used}/{limit} pages processed)."
            )

        # 2. Ensure conversation row exists before inserting the job (avoids FK violation)
        _ensure_conversation(supabase, conversation_id, user_id)

        # 3. Insert pending job row
        job_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "type": "ocr",
            "status": "pending",
            "input_metadata": {"blob_url": blob_url}
        }
        job_res = _safe_execute(supabase.table("jobs").insert(job_data))
        if not job_res or not job_res.data:
            raise HTTPException(status_code=500, detail="Could not create the background job. Please try again.")

        job_id = job_res.data[0]["id"]

        # 4. Dispatch to Azure Queue Storage
        enqueue_job(
            job_id=job_id,
            job_type="ocr",
            input_metadata={"blob_url": blob_url},
            user_id=user_id
        )

        return JobResponse(job_id=job_id, status="pending")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to queue OCR job for user %s: %s", user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to queue the document analysis job. Please try again.")


@router.post("/vision", response_model=JobResponse, status_code=202, summary="Queue a vision image analysis task")
async def queue_vision_job(
    payload: VisionRequest,
    user: Dict[str, Any] = Depends(verify_jwt)
) -> JobResponse:
    """
    Validates monthly Vision quota limits, inserts a pending task into the jobs table,
    enqueues it to Azure Queue Storage, and returns 202 Accepted.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    conversation_id = payload.conversation_id.strip()
    blob_url = payload.blob_url.strip()
    prompt = payload.prompt.strip()

    supabase = get_supabase_admin()

    try:
        # 1. Enforce monthly agent quota limit (soft-fail: if table missing, allow through)
        current_period = datetime.now(timezone.utc).strftime("%Y-%m")
        quota_res = _safe_execute(
            supabase.table("agent_quotas")
            .select("vision_calls_used")
            .eq("user_id", user_id)
            .eq("period", current_period)
            .maybe_single()
        )
        calls_used = 0
        if quota_res and quota_res.data and isinstance(quota_res.data, dict):
            calls_used = quota_res.data.get("vision_calls_used", 0) or 0

        settings_res = _safe_execute(
            supabase.table("admin_settings")
            .select("value")
            .eq("key", "max_vision_calls")
            .maybe_single()
        )
        limit = 5000
        if settings_res and settings_res.data and isinstance(settings_res.data, dict):
            try:
                limit = int(settings_res.data.get("value", 5000))
            except (ValueError, TypeError):
                limit = 5000

        if calls_used >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Monthly Vision calls quota exceeded ({calls_used}/{limit} calls processed)."
            )

        # 2. Ensure conversation row exists before inserting the job (avoids FK violation)
        _ensure_conversation(supabase, conversation_id, user_id)

        # 3. Insert pending job row
        job_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "type": "vision",
            "status": "pending",
            "input_metadata": {"blob_url": blob_url, "prompt": prompt}
        }
        job_res = _safe_execute(supabase.table("jobs").insert(job_data))
        if not job_res or not job_res.data:
            raise HTTPException(status_code=500, detail="Could not create the background job. Please try again.")

        job_id = job_res.data[0]["id"]

        # 4. Dispatch to Azure Queue Storage
        enqueue_job(
            job_id=job_id,
            job_type="vision",
            input_metadata={"blob_url": blob_url, "prompt": prompt},
            user_id=user_id
        )

        return JobResponse(job_id=job_id, status="pending")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to queue Vision job for user %s: %s", user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to queue the image analysis job. Please try again.")


@router.post("/image-gen", response_model=JobResponse, status_code=202, summary="Queue an AI image generation task")
async def queue_image_gen_job(
    payload: ImageGenRequest,
    user: Dict[str, Any] = Depends(verify_jwt)
) -> JobResponse:
    """
    Validates monthly image-gen quota, inserts a pending task into the jobs table,
    enqueues it to Azure Queue Storage for FLUX processing, and returns 202 Accepted.

    This endpoint is the direct/fallback path. The primary path is the AI tool call
    intercepted in chat.py — Ochuko calls generate_image autonomously during streaming.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    conversation_id = payload.conversation_id.strip()
    prompt = payload.prompt.strip()
    style = payload.style.strip() or "photorealistic"

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    supabase = get_supabase_admin()

    try:
        # 1. Enforce monthly image-gen quota
        current_period = datetime.now(timezone.utc).strftime("%Y-%m")
        quota_res = _safe_execute(
            supabase.table("agent_quotas")
            .select("image_gen_used")
            .eq("user_id", user_id)
            .eq("period", current_period)
            .maybe_single()
        )
        calls_used = 0
        if quota_res and quota_res.data and isinstance(quota_res.data, dict):
            calls_used = quota_res.data.get("image_gen_used", 0) or 0

        settings_res = _safe_execute(
            supabase.table("admin_settings")
            .select("value")
            .eq("key", "max_image_gen_calls")
            .maybe_single()
        )
        limit = 50  # conservative default
        if settings_res and settings_res.data and isinstance(settings_res.data, dict):
            try:
                limit = int(settings_res.data.get("value", 50))
            except (ValueError, TypeError):
                limit = 50

        if calls_used >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Monthly image generation quota exceeded ({calls_used}/{limit} images generated)."
            )

        # 2. Ensure conversation row exists before inserting the job (avoids FK violation)
        _ensure_conversation(supabase, conversation_id, user_id)

        # 3. Insert pending job row
        job_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "type": "image_gen",
            "status": "pending",
            "input_metadata": {"prompt": prompt, "style": style}
        }
        job_res = _safe_execute(supabase.table("jobs").insert(job_data))
        if not job_res or not job_res.data:
            raise HTTPException(status_code=500, detail="Could not create the background job. Please try again.")

        job_id = job_res.data[0]["id"]

        # 4. Dispatch to Azure Queue Storage
        enqueue_job(
            job_id=job_id,
            job_type="image_gen",
            input_metadata={"prompt": prompt, "style": style},
            user_id=user_id
        )

        return JobResponse(job_id=job_id, status="pending")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to queue image-gen job for user %s: %s", user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to queue the image generation job. Please try again.")
