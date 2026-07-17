# app/services/cloudflare_r2.py
"""
Cloudflare R2 Storage Service.
Provides S3-compatible methods for generating presigned upload URLs and uploading
file bytes directly, with support for sharded buckets based on content type.
"""
import os
import logging
import asyncio
import boto3
from botocore.config import Config
from typing import Tuple

logger = logging.getLogger("app.services.cloudflare_r2")

def get_r2_client(bucket_type: str = "UPLOADS") -> Tuple[boto3.client, str, str]:
    """
    Returns a tuple of (s3_client, bucket_name, public_domain) configured for the given
    bucket type. Falls back to default R2 credentials if the specific prefix variables
    are not defined in the environment.
    """
    prefix = f"R2_{bucket_type.upper()}_"

    access_key = os.environ.get(f"{prefix}ACCESS_KEY_ID")
    secret_key = os.environ.get(f"{prefix}SECRET_ACCESS_KEY")
    endpoint = os.environ.get(f"{prefix}ENDPOINT")
    bucket_name = os.environ.get(f"{prefix}BUCKET_NAME")
    public_domain = os.environ.get(f"{prefix}PUBLIC_DOMAIN")

    # Fallback to default credentials
    if not all([access_key, secret_key, endpoint]):
        access_key = os.environ.get("R2_ACCESS_KEY_ID")
        secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
        endpoint = os.environ.get("R2_ENDPOINT")
        bucket_name = os.environ.get("R2_BUCKET_NAME", "agent-ochuko-storage")
        public_domain = os.environ.get("R2_PUBLIC_DOMAIN", "https://pub-3aabaa1c09b9c0da240f1ae5ed8d8478.r2.dev")

    if not all([access_key, secret_key, endpoint]):
        raise RuntimeError(
            f"Cloudflare R2 credentials for {bucket_type} (or default R2_ACCESS_KEY_ID, "
            f"R2_SECRET_ACCESS_KEY, R2_ENDPOINT) are not configured in the environment."
        )

    public_domain = public_domain.rstrip("/")

    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4")
    )
    return s3_client, bucket_name, public_domain


def generate_r2_upload_url(filename: str, content_type: str, expiry_seconds: int = 900, bucket_type: str = "UPLOADS") -> str:
    """
    Generates a presigned PUT URL allowing clients to upload files directly to Cloudflare R2.
    """
    try:
        s3_client, bucket_name, _ = get_r2_client(bucket_type)

        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket_name,
                "Key": filename,
                "ContentType": content_type
            },
            ExpiresIn=expiry_seconds
        )
        return presigned_url
    except Exception as e:
        logger.error(f"Failed to generate R2 presigned URL for {bucket_type}: {e}", exc_info=True)
        raise


async def upload_file_bytes(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    bucket_type: str = "GENERATED",
    key_prefix: str = ""
) -> str:
    """
    Uploads file bytes directly to the specified R2 bucket type.
    Returns the public URL of the uploaded file.
    """
    s3_client, bucket_name, public_domain = get_r2_client(bucket_type)
    r2_key = f"{key_prefix}{filename}" if key_prefix else filename

    def _do_upload():
        s3_client.put_object(
            Bucket=bucket_name,
            Key=r2_key,
            Body=file_bytes,
            ContentType=mime_type
        )

    await asyncio.to_thread(_do_upload)
    return f"{public_domain}/{r2_key}"
