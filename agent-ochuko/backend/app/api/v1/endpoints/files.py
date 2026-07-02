# app/api/v1/endpoints/files.py
"""
Files API routes — /v1/files/*
Generates secure SAS tokens for client-side uploads.
"""
import uuid
import logging
import os
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.jwt_validator import verify_jwt
from app.services.supabase_admin import get_supabase_admin
from app.services.cloudflare_r2 import generate_r2_upload_url

logger = logging.getLogger("app.api.v1.endpoints.files")
router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg",".docx", ".jpeg", ".webp", ".gif"}


class UploadRequest(BaseModel):
    filename: str = Field(..., description="The name of the file to upload")
    mime_type: str = Field(..., description="The MIME type of the file (e.g. application/pdf, image/png)")
    conversation_id: str = Field(..., description="The conversation UUID associated with this upload")


class UploadResponse(BaseModel):
    upload_url: str = Field(..., description="The presigned SAS URL to PUT the file content directly to Azure Blob Storage")
    blob_url: str = Field(..., description="The public/private direct URL to the stored blob")
    file_id: str = Field(..., description="The logical path/identifier of the file in the uploads container")


@router.post("/upload", response_model=UploadResponse, summary="Generate a presigned upload SAS URL for Azure Blob Storage")
async def get_upload_sas(
    payload: UploadRequest,
    user: Dict[str, Any] = Depends(verify_jwt)
) -> UploadResponse:
    """
    Validates file extension and size settings, then generates a secure, short-lived (15 min)
    Shared Access Signature (SAS) URL for direct upload to the 'uploads' container.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    filename = payload.filename.strip()
    mime_type = payload.mime_type.strip().lower()
    conversation_id = payload.conversation_id.strip()

    # 1. Validate file extension
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # 2. Construct the target path (isolating by user and conversation for safety)
    unique_id = uuid.uuid4().hex
    # Path inside the uploads container
    blob_name = f"{user_id}/{conversation_id}/{unique_id}_{filename}"

    try:
        # 3. Generate R2 Presigned Upload URL
        file_path = f"uploads/{blob_name}"
        upload_url = generate_r2_upload_url(
            filename=file_path,
            content_type=mime_type,
            expiry_seconds=900
        )

        # 4. Construct direct public R2 reference URL
        public_domain = os.getenv("R2_PUBLIC_DOMAIN", "https://pub-3aabaa1c09b9c0da240f1ae5ed8d8478.r2.dev").rstrip("/")
        blob_url = f"{public_domain}/{file_path}"

        return UploadResponse(
            upload_url=upload_url,
            blob_url=blob_url,
            file_id=file_path
        )

    except Exception as e:
        logger.error(f"Failed to generate upload SAS URL for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate upload target: {str(e)}")
