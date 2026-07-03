# app/middleware/block_guard.py
"""
Block Guard Middleware.

Extracts the google_sub from the verified JWT user context and checks it
against the `blocked_identities` table in Supabase. If the user's google_sub
is found, the request is rejected with 403 — permanently, unbypassably.

Optimised with in-memory thread-safe TTL caching to eliminate database query overhead.
"""

import logging
import os
import time
import threading
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


# Thread-safe in-memory TTL caching
_lock = threading.Lock()
# Maps user_id -> (expiry_timestamp, is_active)
_ACTIVE_PROFILES_CACHE = {}
# Maps google_sub -> (expiry_timestamp, is_blocked)
_BLOCKED_IDENTITIES_CACHE = {}

ACTIVE_TTL = 60       # Cache active profile status for 60 seconds
BLOCKED_TTL = 300     # Cache blocked sub status for 5 minutes (slower eviction for rejected states)


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

        now = time.time()

        # 1. Check in-memory caches first
        with _lock:
            profile_cached = _ACTIVE_PROFILES_CACHE.get(user_id) if user_id else None
            sub_cached = _BLOCKED_IDENTITIES_CACHE.get(google_sub) if google_sub else None

        # Handle cached inactive profiles
        if profile_cached and now < profile_cached[0] and not profile_cached[1]:
            logger.warning(f"Blocked inactive user request (cached): user_id={user_id}")
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "USER_INACTIVE",
                        "message": "Your account has been deactivated. Please contact an administrator.",
                    }
                },
            )

        # Handle cached blocked identities
        if sub_cached and now < sub_cached[0] and sub_cached[1]:
            logger.warning(f"Blocked identity detected (cached): google_sub={google_sub}, user_id={user_id}")
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "ACCOUNT_BLOCKED",
                        "message": "Account access has been revoked. Contact an administrator.",
                    }
                },
            )

        # If both caches are warm, valid, and active, we can skip DB queries entirely
        profile_valid = profile_cached and now < profile_cached[0] and profile_cached[1]
        sub_valid = sub_cached and now < sub_cached[0] and not sub_cached[1]

        if profile_valid and (not google_sub or sub_valid):
            return await call_next(request)

        # 2. Query Supabase Database on cache miss
        db = _get_supabase()
        if db:
            # 2a. Check profile is_active status
            if user_id:
                is_active = True
                if not profile_cached or now >= profile_cached[0]:
                    try:
                        profile_res = (
                            db.table("profiles")
                            .select("is_active")
                            .eq("id", user_id)
                            .maybe_single()
                            .execute()
                        )
                        if profile_res.data:
                            is_active = profile_res.data.get("is_active", True)
                        
                        # Cache the result
                        with _lock:
                            _ACTIVE_PROFILES_CACHE[user_id] = (now + ACTIVE_TTL, is_active)
                    except Exception as profile_err:
                        logger.error(f"Error checking profile activation status: {profile_err}")
                        is_active = True  # fail open
                else:
                    is_active = profile_cached[1]

                if not is_active:
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

            # 2b. Check blocked_identities table
            if google_sub:
                is_blocked = False
                if not sub_cached or now >= sub_cached[0]:
                    try:
                        result = (
                            db.table("blocked_identities")
                            .select("id")
                            .eq("google_sub", google_sub)
                            .limit(1)
                            .execute()
                        )
                        is_blocked = bool(result.data)
                        
                        # Cache the result
                        with _lock:
                            _BLOCKED_IDENTITIES_CACHE[google_sub] = (
                                now + (BLOCKED_TTL if is_blocked else ACTIVE_TTL),
                                is_blocked
                            )
                    except Exception as e:
                        logger.error(f"Error checking blocked_identities: {e}")
                        is_blocked = False  # fail open
                else:
                    is_blocked = sub_cached[1]

                if is_blocked:
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

        return await call_next(request)
