# app/middleware/maintenance_guard.py
"""
Maintenance Guard Middleware.

Checks the `maintenance_mode` key in admin_settings (Supabase).
If true, returns 503 for all non-admin requests.
Admins can still access the system during maintenance for debugging.
"""

import json
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.core.config import get_config

logger = logging.getLogger("app.middleware.maintenance_guard")


class MaintenanceGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip for health/ready probes — they must always be reachable
        if request.url.path in ("/health", "/ready"):
            return await call_next(request)

        # Check maintenance mode flag from App Configuration cache
        maintenance_mode = await get_config("MAINTENANCE_MODE", "false")
        if maintenance_mode.lower() == "true":
            # Allow admins through — check the user context if it's been set
            from app.core.jwt_validator import get_auth_user
            user = get_auth_user(request)
            if user and user.get("user_metadata", {}).get("role") in ("admin", "superadmin"):
                return await call_next(request)

            logger.warning(f"Maintenance mode active — blocking request to {request.url.path}")
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "MAINTENANCE",
                        "message": "System temporarily unavailable for maintenance. Please try again later.",
                    }
                },
            )

        return await call_next(request)
