# app/middleware/quota_guard.py
"""
Quota Guard Middleware.

Enforces monthly per-user agent quotas on agent endpoints (/v1/agents/*).
Each agent type has its own counter in the agent_quotas table:
  - ocr_pages_used      vs max_ocr_pages_per_user
  - vision_calls_used   vs max_vision_calls_per_user
  - speech_minutes_used vs max_speech_minutes_per_user
  - image_gen_used      vs max_image_gen_per_user
  - file_gen_used       vs max_file_gen_per_user

Limits are stored in admin_settings and can be adjusted by admins at runtime.
"""

import logging
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from supabase import create_client
from app.core.config import get_config

logger = logging.getLogger("app.middleware.quota_guard")

_supabase = None


def _get_supabase():
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            _supabase = create_client(url, key)
    return _supabase


# Map URL path segments to quota column names and their admin_settings limit keys
_AGENT_QUOTA_MAP = {
    "ocr": ("ocr_pages_used", "max_ocr_pages_per_user", "50"),
    "vision": ("vision_calls_used", "max_vision_calls_per_user", "5000"),
    "speech": ("speech_seconds_used", "max_speech_seconds", "3600"),
    "image_gen": ("image_gen_used", "max_image_gen_per_user", "100"),
    "file_gen": ("file_gen_used", "max_file_gen_per_user", "200"),
}


class QuotaGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only enforce on agent endpoints
        if not request.url.path.startswith("/v1/agents/"):
            return await call_next(request)

        # Extract agent type from path: /v1/agents/ocr → "ocr"
        path_parts = request.url.path.strip("/").split("/")
        agent_type = path_parts[2] if len(path_parts) > 2 else None

        if not agent_type or agent_type not in _AGENT_QUOTA_MAP:
            return await call_next(request)

        from app.core.jwt_validator import get_auth_user
        user = get_auth_user(request)
        if not user:
            return await call_next(request)

        user_id = user.get("sub")
        if not user_id:
            return await call_next(request)

        column_name, limit_key, default_limit = _AGENT_QUOTA_MAP[agent_type]

        db = _get_supabase()
        if not db:
            return await call_next(request)

        try:
            # Get the current month's period string
            from datetime import datetime, timezone
            period = datetime.now(timezone.utc).strftime("%Y-%m")

            # Fetch current usage
            result = (
                db.table("agent_quotas")
                .select(column_name)
                .eq("user_id", user_id)
                .eq("period", period)
                .limit(1)
                .execute()
            )

            current_usage = 0
            if result.data:
                current_usage = result.data[0].get(column_name, 0)

            # Fetch the limit from admin_settings (via App Config cache)
            limit_str = await get_config(limit_key, default_limit)
            try:
                limit = int(limit_str)
            except ValueError:
                limit = int(default_limit)

            if current_usage >= limit:
                logger.warning(
                    f"Agent quota exhausted: user={user_id}, "
                    f"agent={agent_type}, used={current_usage}, limit={limit}"
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "AGENT_QUOTA_EXHAUSTED",
                            "message": (
                                f"Monthly {agent_type} quota exhausted "
                                f"({current_usage}/{limit}). Resets on the 1st of next month."
                            ),
                        }
                    },
                )

        except Exception as e:
            logger.error(f"Error in quota guard check: {e}")
            # Fail open

        return await call_next(request)
