# app/services/azure_blob.py
"""
Azure Blob Storage Service.
Encapsulates operations for generating secure, short-lived SAS tokens
allowing direct client-side uploads to private blob containers.
"""
import os
import logging
from typing import Tuple
from datetime import datetime, timedelta, timezone
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

logger = logging.getLogger("app.services.azure_blob")


def parse_connection_string(conn_str: str) -> Tuple[str, str]:
    """Helper to extract AccountName and AccountKey from a storage connection string."""
    parts = {}
    for item in conn_str.split(';'):
        if '=' in item:
            key, val = item.split('=', 1)
            parts[key.strip()] = val.strip()
    return parts.get("AccountName", ""), parts.get("AccountKey", "")


def generate_upload_sas_url(container_name: str, blob_name: str, expiry_minutes: int = 15) -> str:
    """
    Generates a secure SAS URL with write/create permission for a specific blob path.
    Enables direct client uploads to bypass the FastAPI backend.
    """
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING must be set in the environment.")

    account_name, account_key = parse_connection_string(conn_str)
    if not account_name or not account_key:
        raise RuntimeError("Could not extract AccountName or AccountKey from AZURE_STORAGE_CONNECTION_STRING.")

    permissions = BlobSasPermissions(write=True, create=True)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=permissions,
        expiry=expiry
    )

    blob_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
    return f"{blob_url}?{sas_token}"
