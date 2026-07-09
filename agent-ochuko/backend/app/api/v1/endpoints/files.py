# app/api/v1/endpoints/files.py
"""
Files API routes — /v1/files/*
Generates secure SAS tokens for client-side uploads.
"""
import uuid
import logging
import os
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
import httpx
from jose import jwt, JWTError

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


@router.get("/download-proxy", summary="Proxy download of a remote file to conserve R2 storage")
async def download_file_proxy(
    url: str = Query(..., description="Target file URL to download"),
    filename: str = Query(None, description="Filename for disposition"),
    token: str = Query(None, description="Auth token passed in query string for browser redirects"),
    request: Request = None
):
    """
    Acts as a pass-through proxy to stream files from remote URLs (like GitHub).
    This ensures that large files do not consume Cloudflare R2 storage while
    remaining downloadable by the user.
    """
    # 1. Extract token from Header or Query
    auth_token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        auth_token = auth_header.split(" ")[1]
    elif token:
        auth_token = token

    if not auth_token:
        raise HTTPException(status_code=401, detail="Authentication token required.")

    # 2. Validate token
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    if not jwt_secret:
        raise HTTPException(status_code=500, detail="JWT validator is not configured.")

    try:
        jwt.decode(
            auth_token, jwt_secret, algorithms=["HS256"], options={"verify_aud": False}
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")

    # 3. Stream validation & fetching
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL protocol. Only HTTP/HTTPS are supported.")

    if not filename:
        try:
            filename = url.split("/")[-1].split("?")[0]
        except Exception:
            filename = "downloaded_file"

    async def file_streamer():
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        logger.error("Failed to fetch file from remote source: HTTP %d", response.status_code)
                        return
                    async for chunk in response.iter_bytes(chunk_size=1024 * 64):
                        yield chunk
        except Exception as e:
            logger.error("Error streaming file from %s: %s", url, e)

    # Guess MIME type
    import mimetypes
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    disposition = "inline" if mime_type.startswith(("image/", "application/pdf")) else "attachment"
    headers = {
        "Content-Disposition": f"{disposition}; filename=\"{filename}\""
    }

    return StreamingResponse(
        file_streamer(),
        media_type=mime_type,
        headers=headers
    )


@router.get("/sandbox/{conversation_id}/{filename}", summary="Serve sandboxed files locally during development/testing")
async def serve_sandbox_file(
    conversation_id: str,
    filename: str
):
    """
    Serves a generated file from the local workspace sandbox directory.
    """
    # Standardize path matching execute_code_in_sandbox
    work_dir = os.path.abspath(os.path.join("/tmp", f"sandbox_{conversation_id}")).replace("\\", "/")
    file_path = os.path.join(work_dir, filename)

    if not os.path.exists(file_path):
        # Check case-insensitive fallback just in case
        for f in os.listdir(work_dir) if os.path.exists(work_dir) else []:
            if f.lower() == filename.lower():
                file_path = os.path.join(work_dir, f)
                break
        else:
            raise HTTPException(status_code=404, detail="File not found in sandbox.")

    import mimetypes
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"

    # Serve file
    return FileResponse(
        path=file_path,
        media_type=mime_type,
        filename=filename
    )

