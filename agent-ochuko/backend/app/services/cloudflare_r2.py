# app/services/cloudflare_r2.py
"""
Cloudflare R2 Storage Service.
Provides S3-compatible methods for generating presigned upload URLs
to enable direct client-side uploads.
"""
import os
import logging
import boto3
from botocore.config import Config

logger = logging.getLogger("app.services.cloudflare_r2")

def generate_r2_upload_url(filename: str, content_type: str, expiry_seconds: int = 900) -> str:
    """
    Generates a presigned PUT URL allowing clients to upload files directly to Cloudflare R2.
    """
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    endpoint = os.environ.get("R2_ENDPOINT")
    bucket_name = os.environ.get("R2_BUCKET_NAME", "agent-ochuko-storage")

    if not all([access_key, secret_key, endpoint]):
        raise RuntimeError("Cloudflare R2 credentials (R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT) are not configured in the environment.")

    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4")
        )

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
        logger.error(f"Failed to generate R2 presigned URL: {e}", exc_info=True)
        raise
