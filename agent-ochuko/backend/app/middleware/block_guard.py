# app/middleware/block_guard.py
"""
Block Guard Middleware.

Extracts the google_sub from the verified JWT user context and checks it
against the `blocked_identities` table in Supabase. If the user's google_sub
is found, the request is rejected with 403 — permanently, unbypassably.

Why google_sub?
  - Permanent per Google account — cannot be changed by the user.
  - Even if user creates a new email alias, same Google account = same sub.
  - To fully bypass: they'd need a brand new Google account on a different device.
"""

import logging
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from supabase import create_client

logger = logging.getLogger("app.middleware.block_guard")

# Lazy Supabase client (service role — bypasses RLS)
_supabase = None


def _get_supabase():
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            _supabase = create_client(url, key)
    return _supabase


class BlockGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip for unauthenticated paths
        if request.url.path in ("/health", "/ready", "/docs", "/openapi.json"):
            return await call_next(request)

        # Get user from JWT claims
        from app.core.jwt_validator import get_auth_user
        user = get_auth_user(request)
        if not user:
            return await call_next(request)

        user_id = user.get("sub")
        google_sub = user.get("user_metadata", {}).get("sub")

        db = _get_supabase()
        if db:
            # 1. Check profile is_active status
            if user_id:
                try:
                    profile_res = (
                        db.table("profiles")
                        .select("is_active")
                        .eq("id", user_id)
                        .maybe_single()
                        .execute()
                    )
                    if profile_res.data and not profile_res.data.get("is_active", True):
                        logger.warning(f"Blocked inactive user request: user_id={user_id}")
                        return JSONResponse(
                            status_code=403,
                            content={
                                "error": {
                                    "code": "USER_INACTIVE",
                                    "message": "Your account has been deactivated. Please contact an administrator.",
                                }
                            },
                        )
                except Exception as profile_err:
                    logger.error(f"Error checking profile activation status: {profile_err}")

            # 2. Check blocked_identities table
            if google_sub:
                try:
                    result = (
                        db.table("blocked_identities")
                        .select("id")
                        .eq("google_sub", google_sub)
                        .limit(1)
                        .execute()
                    )
                    if result.data:
                        logger.warning(
                            f"Blocked identity detected: google_sub={google_sub}, "
                            f"user_id={user_id}"
                        )
                        return JSONResponse(
                            status_code=403,
                            content={
                                "error": {
                                    "code": "ACCOUNT_BLOCKED",
                                    "message": "Account access has been revoked. Contact an administrator.",
                                }
                            },
                        )
                except Exception as e:
                    logger.error(f"Error checking blocked_identities: {e}")

        return await call_next(request)
