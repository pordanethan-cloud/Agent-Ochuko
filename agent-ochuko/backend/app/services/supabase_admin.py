# app/services/supabase_admin.py
"""
Supabase service-role client.

The client is initialised lazily on first use so that missing env vars at
module import time cause a clear, late-binding error instead of crashing the
entire server process at startup (e.g. during unit tests or cold-start checks).
"""
import os
import logging
from typing import Optional
from supabase import create_client, Client

logger = logging.getLogger("app.services.supabase_admin")

_supabase_client: Optional[Client] = None


def get_supabase_admin() -> Client:
    """
    Returns the service-role Supabase client, creating it on first call.
    Raises RuntimeError with a clear message if credentials are missing.
    """
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in the environment."
        )

    import httpx
    from supabase.client import ClientOptions

    custom_http_client = httpx.Client(
        timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=30.0),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=30.0),
        http2=False,
    )

    options = ClientOptions(
        httpx_client=custom_http_client,
        postgrest_client_timeout=30,
        storage_client_timeout=30,
    )

    _supabase_client = create_client(url, key, options=options)
    logger.info("Supabase admin client initialised with custom HTTP transport.")
    return _supabase_client
