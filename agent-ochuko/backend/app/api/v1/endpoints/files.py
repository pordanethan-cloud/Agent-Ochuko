# app/api/v1/endpoints/files.py
"""
Files API routes — /v1/files/*
Generates secure SAS tokens for client-side uploads.
"""
import uuid
import logging
import os
import io
import asyncio
from typing import Any, Dict, Optional
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

ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".docx", ".jpeg", ".webp", ".gif",
    ".txt", ".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".java", 
    ".py", ".c", ".cpp", ".h", ".cs", ".sh", ".json", ".md", 
    ".yaml", ".yml", ".xml", ".sql", ".csv", ".rs", ".go", ".rb", 
    ".php", ".kt", ".gradle", ".properties", ".ipynb", ".ini", ".cfg",
    ".bat", ".cmd", ".ps1"
}


class UploadRequest(BaseModel):
    filename: str = Field(..., description="The name of the file to upload")
    mime_type: str = Field(..., description="The MIME type of the file (e.g. application/pdf, image/png)")
    conversation_id: str = Field(..., description="The conversation UUID associated with this upload")


class UploadResponse(BaseModel):
    upload_url: str = Field(..., description="The presigned SAS URL to PUT the file content directly to Azure Blob Storage")
    blob_url: str = Field(..., description="The public/private direct URL to the stored blob")
    file_id: str = Field(..., description="The logical path/identifier of the file in the uploads container")


class SyncRequest(BaseModel):
    file_id: str = Field(..., description="The R2 key of the uploaded file")
    filename: str = Field(..., description="The original filename")
    conversation_id: str = Field(..., description="The active conversation ID")


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


@router.post("/sync-google", summary="Sync a user uploaded file from R2 to their Google Drive in the background")
async def sync_to_google(
    payload: SyncRequest,
    user: Dict[str, Any] = Depends(verify_jwt)
):
    """
    Downloads file bytes from R2 and syncs them to the user's personal Google Drive
    under the 'Ochuko Workspace/uploads/{conversation_id}' folder in the background.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    async def _bg_sync():
        try:
            # 1. Fetch file bytes from R2
            from app.services.cloudflare_r2 import get_r2_client
            s3_client, bucket_name, _ = get_r2_client("UPLOADS")
            
            key = payload.file_id
            
            def _get_bytes():
                res = s3_client.get_object(Bucket=bucket_name, Key=key)
                return res["Body"].read()
                
            file_bytes = await asyncio.to_thread(_get_bytes)
            
            # 2. Get Google Drive Client
            from app.services.google_drive import get_drive_client, get_conversation_folders
            drive = get_drive_client(user_id)
            if not drive:
                logger.warning(f"Google Drive client not available for user {user_id} during sync.")
                return
                
            folders = get_conversation_folders(drive, payload.conversation_id)
            uploads_folder_id = folders.get("uploads")
            if not uploads_folder_id:
                logger.error(f"Could not resolve uploads folder ID for convo {payload.conversation_id}")
                return
                
            # 3. Upload to Google Drive
            import mimetypes
            mime_type, _ = mimetypes.guess_type(payload.filename)
            if not mime_type:
                mime_type = "application/octet-stream"
                
            from googleapiclient.http import MediaIoBaseUpload
            media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
            
            existing_id = None
            try:
                q = f"name = '{payload.filename}' and '{uploads_folder_id}' in parents and trashed = false"
                res = drive.files().list(q=q, spaces='drive', fields='files(id)').execute()
                files = res.get('files', [])
                if files:
                    existing_id = files[0]['id']
            except Exception as check_err:
                logger.warning(f"Failed to check existing file {payload.filename} on Drive: {check_err}")
                
            if existing_id:
                drive.files().update(
                    fileId=existing_id,
                    media_body=media,
                    fields='id'
                ).execute()
                logger.info(f"Successfully updated synced file on Google Drive: {payload.filename}")
            else:
                file_metadata = {
                    'name': payload.filename,
                    'parents': [uploads_folder_id]
                }
                drive.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                logger.info(f"Successfully uploaded synced file to Google Drive: {payload.filename}")
        except Exception as sync_err:
            logger.error(f"Failed to background sync uploaded file {payload.filename} to Google Drive: {sync_err}", exc_info=True)

    asyncio.create_task(_bg_sync())
    return {"status": "sync_initiated"}


@router.get("/download-proxy", summary="Proxy download of a remote file to conserve R2 storage")
async def download_file_proxy(
    url: str = Query(..., description="Target file URL to download"),
    filename: str = Query(None, description="Filename for disposition"),
    token: str = Query(None, description="Auth token passed in query string for browser redirects"),
    request: Request = None
):
    """
    Acts as a pass-through proxy to stream files from remote URLs (like GitHub).
    Also detects R2 cache misses (evicted after 7 days) and restores files from the
    user's personal Google Drive automatically.
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
        decoded_token = jwt.decode(
            auth_token, jwt_secret, algorithms=["HS256"], options={"verify_aud": False}
        )
        token_user_id = decoded_token.get("sub")
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

    # Guess MIME type
    import mimetypes
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    async def file_streamer():
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("GET", url) as response:
                    # If R2 returns 404 (evicted by 7 days lifecycle rule), restore from Google Drive
                    if response.status_code == 404 and ("uploads/" in url or "generated/" in url):
                        logger.info(f"R2 cache miss / eviction for {url}. Attempting recovery from Google Drive...")
                        user_id_parsed = None
                        conversation_id_parsed = None
                        file_name_parsed = None
                        folder_type = None
                        raw_filename = None

                        if "uploads/" in url:
                            part = url.split("uploads/")[-1]
                            parts = part.split("/")
                            if len(parts) >= 3:
                                user_id_parsed = parts[0]
                                conversation_id_parsed = parts[1]
                                raw_filename = parts[2]
                                if len(raw_filename) > 33 and "_" in raw_filename[:34]:
                                    file_name_parsed = raw_filename.split("_", 1)[1]
                                else:
                                    file_name_parsed = raw_filename
                                folder_type = "uploads"
                        elif "generated/" in url:
                            part = url.split("generated/")[-1]
                            parts = part.split("/")
                            if len(parts) >= 2:
                                conversation_id_parsed = parts[0]
                                file_name_parsed = parts[1]
                                user_id_parsed = token_user_id
                                folder_type = "sandbox_file"

                        if user_id_parsed and conversation_id_parsed and file_name_parsed:
                            try:
                                from app.services.google_drive import get_drive_client, get_conversation_folders
                                drive = get_drive_client(user_id_parsed)
                                if drive:
                                    folders = get_conversation_folders(drive, conversation_id_parsed)
                                    folder_id = folders.get(folder_type)
                                    if folder_id:
                                        q = f"name = '{file_name_parsed}' and '{folder_id}' in parents and trashed = false"
                                        drive_res = drive.files().list(q=q, spaces='drive', fields='files(id)').execute()
                                        files = drive_res.get('files', [])
                                        if files:
                                            file_id = files[0]['id']
                                            logger.info(f"Restoring file {file_name_parsed} from Google Drive ID: {file_id}")
                                            
                                            request_media = drive.files().get_media(fileId=file_id)
                                            fh = io.BytesIO()
                                            from googleapiclient.http import MediaIoBaseDownload
                                            downloader = MediaIoBaseDownload(fh, request_media)
                                            done = False
                                            while not done:
                                                _, done = downloader.next_chunk()
                                            file_bytes = fh.getvalue()

                                            # Upload back to R2 to re-cache
                                            if folder_type == "uploads":
                                                r2_key = f"uploads/{user_id_parsed}/{conversation_id_parsed}/{raw_filename}"
                                            else:
                                                r2_key = f"generated/{conversation_id_parsed}/{file_name_parsed}"

                                            from app.services.cloudflare_r2 import get_r2_client
                                            s3_client, bucket_name, _ = get_r2_client("UPLOADS" if folder_type == "uploads" else "GENERATED")
                                            
                                            def _put_back():
                                                s3_client.put_object(
                                                    Bucket=bucket_name,
                                                    Key=r2_key,
                                                    Body=file_bytes,
                                                    ContentType=mime_type
                                                )
                                            await asyncio.to_thread(_put_back)
                                            logger.info(f"Successfully re-cached {file_name_parsed} to R2: {r2_key}")
                                            
                                            yield file_bytes
                                            return
                            except Exception as recovery_err:
                                logger.error(f"Failed to recover file from Google Drive: {recovery_err}", exc_info=True)

                    if response.status_code != 200:
                        logger.error("Failed to fetch file from remote source: HTTP %d", response.status_code)
                        return
                    async for chunk in response.iter_bytes(chunk_size=1024 * 64):
                        yield chunk
        except Exception as e:
            logger.error("Error streaming file from %s: %s", url, e)

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
    data_dir = os.path.join(work_dir, "data")
    file_path = os.path.join(data_dir, filename)

    if not os.path.exists(file_path):
        # Check case-insensitive fallback in data_dir
        for f in os.listdir(data_dir) if os.path.exists(data_dir) else []:
            if f.lower() == filename.lower():
                file_path = os.path.join(data_dir, f)
                break
        else:
            # Fallback to root work_dir
            file_path = os.path.join(work_dir, filename)
            if not os.path.exists(file_path):
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

