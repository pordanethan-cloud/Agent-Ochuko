# app/api/v1/endpoints/agents.py
"""
Agents API routes — /v1/agents/*
Handles queuing asynchronous background agent tasks (OCR, Vision)
via the storage queue (Pattern B).
"""
import logging
from typing import Any, Dict
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


class JobResponse(BaseModel):
    job_id: str = Field(..., description="The created background job UUID")
    status: str = Field("pending", description="The current status of the job")


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
        # 1. Enforce monthly agent quota limit
        current_period = datetime.now(timezone.utc).strftime("%Y-%m")
        res = (
            supabase.table("agent_quotas")
            .select("ocr_pages_used")
            .eq("user_id", user_id)
            .eq("period", current_period)
            .maybe_single()
            .execute()
        )
        pages_used = res.data.get("ocr_pages_used", 0) if res.data else 0

        settings_res = (
            supabase.table("admin_settings")
            .select("value")
            .eq("key", "max_ocr_pages_per_user")
            .maybe_single()
            .execute()
        )
        limit = int(settings_res.data["value"]) if settings_res.data else 50

        if pages_used >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Monthly OCR pages quota exceeded ({pages_used}/{limit} pages processed)."
            )

        # 2. Ensure conversation row exists (frontend may have generated a UUID locally
        #    before the backend created the DB row — upsert to avoid FK violation)
        supabase.table("conversations").upsert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "title": "Agent Job",
                "message_count": 0,
            },
            on_conflict="id"
        ).execute()

        # 3. Insert pending job row
        job_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "type": "ocr",
            "status": "pending",
            "input_metadata": {"blob_url": blob_url}
        }
        job_res = supabase.table("jobs").insert(job_data).execute()
        if not job_res or not job_res.data:
            raise HTTPException(status_code=500, detail="Failed to write job entry to database.")

        job_id = job_res.data[0]["id"]

        # 3. Dispatch to Azure Queue Storage
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
        logger.error(f"Failed to queue OCR job for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to queue OCR job: {str(e)}")


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
        # 1. Enforce monthly agent quota limit
        current_period = datetime.now(timezone.utc).strftime("%Y-%m")
        res = (
            supabase.table("agent_quotas")
            .select("vision_calls_used")
            .eq("user_id", user_id)
            .eq("period", current_period)
            .maybe_single()
            .execute()
        )
        calls_used = res.data.get("vision_calls_used", 0) if res.data else 0

        settings_res = (
            supabase.table("admin_settings")
            .select("value")
            .eq("key", "max_vision_calls")
            .maybe_single()
            .execute()
        )
        limit = int(settings_res.data["value"]) if settings_res.data else 5000

        if calls_used >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Monthly Vision calls quota exceeded ({calls_used}/{limit} calls processed)."
            )

        # 2. Ensure conversation row exists (frontend may have generated a UUID locally
        #    before the backend created the DB row — upsert to avoid FK violation)
        supabase.table("conversations").upsert(
            {
                "id": conversation_id,
                "user_id": user_id,
                "title": "Agent Job",
                "message_count": 0,
            },
            on_conflict="id"
        ).execute()

        # 3. Insert pending job row
        job_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "type": "vision",
            "status": "pending",
            "input_metadata": {"blob_url": blob_url, "prompt": prompt}
        }
        job_res = supabase.table("jobs").insert(job_data).execute()
        if not job_res or not job_res.data:
            raise HTTPException(status_code=500, detail="Failed to write job entry to database.")


        job_id = job_res.data[0]["id"]

        # 3. Dispatch to Azure Queue Storage
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
        logger.error(f"Failed to queue Vision job for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to queue Vision job: {str(e)}")
