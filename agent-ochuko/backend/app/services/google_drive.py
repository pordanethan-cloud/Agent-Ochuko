# app/services/google_drive.py
"""
Google Drive Service Integration.
Manages OAuth credentials, downloads user-uploaded files, and uploads sandbox results
directly to the user's personal Google Drive account under the "Ochuko Workspace" folder.
"""
import os
import io
import logging
from typing import Optional, List, Dict
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from app.services.supabase_admin import get_supabase_admin

logger = logging.getLogger("app.services.google_drive")


def get_drive_credentials(user_id: str) -> Optional[Credentials]:
    """
    Fetches the Google refresh token for a user from supabase table public.user_google_credentials
    and returns a Credentials object. Falls back to environment variables for local testing.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        logger.warning("GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not configured in env.")
        
    refresh_token = None
    try:
        supabase = get_supabase_admin()
        res = supabase.table("user_google_credentials").select("refresh_token").eq("user_id", user_id).maybe_single().execute()
        if res and res.data:
            refresh_token = res.data.get("refresh_token")
    except Exception as e:
        logger.warning(f"Failed to query user_google_credentials for {user_id}: {e}")
        
    if not refresh_token:
        # Fallback to local dev testing env vars
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        
    if not refresh_token:
        logger.warning(f"No Google refresh token found for user {user_id}")
        return None
        
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )


def get_drive_client(user_id: str):
    """Returns a Google Drive API client built with the user's credentials."""
    creds = get_drive_credentials(user_id)
    if not creds:
        return None
    try:
        return build('drive', 'v3', credentials=creds)
    except Exception as build_err:
        logger.error(f"Failed to build drive client: {build_err}", exc_info=True)
        return None


def get_or_create_folder(drive_service, name: str, parent_id: str = None) -> str:
    """Helper to locate or create a folder in Google Drive."""
    q = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    else:
        q += " and 'root' in parents"
        
    try:
        res = drive_service.files().list(q=q, spaces='drive', fields='files(id, name)').execute()
        files = res.get('files', [])
        if files:
            return files[0]['id']
            
        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]
            
        folder = drive_service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')
    except Exception as e:
        logger.error(f"Error getting/creating folder {name}: {e}")
        raise


def get_conversation_folders(drive_service, conversation_id: str) -> Dict[str, Optional[str]]:
    """Returns folder IDs for uploads and sandbox_file directories of a conversation."""
    try:
        root_id = get_or_create_folder(drive_service, "Ochuko Workspace")
        uploads_root_id = get_or_create_folder(drive_service, "uploads", root_id)
        sandbox_root_id = get_or_create_folder(drive_service, "sandbox_file", root_id)
        
        convo_uploads_id = get_or_create_folder(drive_service, conversation_id, uploads_root_id)
        convo_sandbox_id = get_or_create_folder(drive_service, conversation_id, sandbox_root_id)
        
        return {
            "uploads": convo_uploads_id,
            "sandbox_file": convo_sandbox_id
        }
    except Exception as e:
        logger.error(f"Failed to resolve conversation folders: {e}")
        return {"uploads": None, "sandbox_file": None}


async def download_google_drive_files(user_id: str, conversation_id: str, local_data_dir: str) -> List[str]:
    """
    Downloads all files from the conversation's Google Drive folders (uploads & sandbox_file)
    into the local data_dir.
    """
    import asyncio
    
    def _do_download():
        drive = get_drive_client(user_id)
        if not drive:
            logger.info(f"Google Drive client not available for user {user_id}; skipping download.")
            return []
            
        folders = get_conversation_folders(drive, conversation_id)
        downloaded = []
        
        for folder_type, folder_id in folders.items():
            if not folder_id:
                continue
                
            q = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
            try:
                res = drive.files().list(q=q, spaces='drive', fields='files(id, name)').execute()
                files = res.get('files', [])
                for f in files:
                    file_id = f['id']
                    filename = f['name']
                    target_path = os.path.join(local_data_dir, filename)
                    
                    logger.info(f"Downloading file from Google Drive ({folder_type}): {filename} -> {target_path}")
                    
                    request = drive.files().get_media(fileId=file_id)
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                        
                    with open(target_path, 'wb') as local_file:
                        local_file.write(fh.getvalue())
                        
                    downloaded.append(filename)
            except Exception as e:
                logger.error(f"Failed to download files from {folder_type} folder ({folder_id}): {e}")
                
        return list(set(downloaded))
        
    return await asyncio.to_thread(_do_download)


async def upload_to_google_drive(user_id: str, conversation_id: str, local_data_dir: str) -> List[Dict[str, str]]:
    """
    Uploads all new or modified files from local_data_dir to the conversation's
    sandbox_file folder on Google Drive. Returns a list of uploaded files with their web view URLs.
    """
    import asyncio
    import mimetypes
    
    def _do_upload():
        drive = get_drive_client(user_id)
        if not drive:
            logger.info(f"Google Drive client not available for user {user_id}; skipping upload.")
            return []
            
        folders = get_conversation_folders(drive, conversation_id)
        sandbox_folder_id = folders.get("sandbox_file")
        if not sandbox_folder_id:
            logger.error("Could not resolve sandbox_file folder ID on Google Drive")
            return []
            
        uploaded_files = []
        
        # List existing files in this folder to avoid duplicates and perform updates instead of inserts
        existing_files = {}
        try:
            q = f"'{sandbox_folder_id}' in parents and trashed = false"
            res = drive.files().list(q=q, spaces='drive', fields='files(id, name)').execute()
            for f in res.get('files', []):
                existing_files[f['name']] = f['id']
        except Exception as e:
            logger.warning(f"Could not list existing files in sandbox folder: {e}")
            
        for file in os.listdir(local_data_dir):
            file_path = os.path.join(local_data_dir, file)
            if os.path.isdir(file_path):
                continue
                
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"
                
            try:
                media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
                
                if file in existing_files:
                    # Update existing file
                    file_id = existing_files[file]
                    logger.info(f"Updating existing file on Google Drive: {file} (ID: {file_id})")
                    drive_file = drive.files().update(
                        fileId=file_id,
                        media_body=media,
                        fields='id, name, webViewLink'
                    ).execute()
                else:
                    # Create new file
                    logger.info(f"Creating new file on Google Drive: {file}")
                    file_metadata = {
                        'name': file,
                        'parents': [sandbox_folder_id]
                    }
                    drive_file = drive.files().create(
                        body=file_metadata,
                        media_body=media,
                        fields='id, name, webViewLink'
                    ).execute()
                
                # Make the file readable by anyone with the link so it can be previewed/rendered in React iframe
                try:
                    drive.permissions().create(
                        fileId=drive_file.get('id'),
                        body={'type': 'anyone', 'role': 'reader'},
                        fields='id'
                    ).execute()
                except Exception as perm_err:
                    logger.warning(f"Could not update permission for file {file}: {perm_err}")
                
                uploaded_files.append({
                    "filename": file,
                    "download_url": drive_file.get('webViewLink'),
                    "size_bytes": os.path.getsize(file_path)
                })
            except Exception as e:
                logger.error(f"Failed to upload {file} to Google Drive: {e}")
                
        return uploaded_files
        
    return await asyncio.to_thread(_do_upload)
