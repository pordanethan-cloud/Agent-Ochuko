# app/middleware/audit_logger.py
"""
Audit Logger Middleware.

Writes an append-only audit log entry to Supabase for every request.
Uses FastAPI's BackgroundTasks pattern (via starlette) so the write
happens AFTER the response is sent — zero impact on response latency.

Logged fields:
  - user_id, action (HTTP method), resource (path), ip_address,
    status_code, latency_ms, routing_mode (if chat), timestamp
"""

import time
import logging
import os
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from supabase import create_client

logger = logging.getLogger("app.middleware.audit_logger")

_supabase = None


def _get_supabase():
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            _supabase = create_client(url, key)
    return _supabase


def _write_audit_log(entry: dict):
    """Background task: writes audit log entry to Supabase and updates last_seen."""
    try:
        db = _get_supabase()
        if db:
            db.table("audit_log").insert(entry).execute()
            
            # Also update last_seen for the active user if user_id is present
            user_id = entry.get("user_id")
            if user_id:
                db.table("profiles").update({
                    "last_seen": datetime.now(timezone.utc).isoformat()
                }).eq("id", user_id).execute()
    except Exception as e:
        # Never fail the request because of audit logging
        logger.error(f"Failed to write audit log: {e}")


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip logging for health probes (too noisy)
        if request.url.path in ("/health", "/ready"):
            return await call_next(request)

        start_time = time.monotonic()

        # Process the request
        response = await call_next(request)

        # Calculate latency
        latency_ms = int((time.monotonic() - start_time) * 1000)

        # Extract user info (may not be available for unauthenticated requests)
        from app.core.jwt_validator import get_auth_user
        user = get_auth_user(request)
        user_id = user.get("sub") if user else None

        # Extract client IP
        ip_address = request.client.host if request.client else "unknown"

        # Build audit entry
        entry = {
            "user_id": user_id,
            "action": request.method,
            "resource": request.url.path,
            "ip_address": ip_address,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        }

        # Add routing_mode if available (set by chat endpoint)
        routing_mode = getattr(request.state, "routing_mode", None)
        if routing_mode:
            entry["routing_mode"] = routing_mode

        # Fire-and-forget: write audit log in background
        # Using a simple fire-and-forget pattern since we can't use
        # BackgroundTasks from middleware. The write is non-blocking
        # because it runs after response is already being sent.
        import asyncio
        asyncio.get_event_loop().run_in_executor(None, _write_audit_log, entry)

        return response
