# app/middleware/token_budget.py
"""
Token Budget Middleware.

Enforces daily per-user token budgets on chat endpoints (/v1/responses/stream).
Uses an atomic UPDATE with RETURNING to prevent race conditions under concurrent requests.

Flow:
  1. ensure_budget_row(user_id) — creates today's row if missing (inherits custom limits)
  2. Estimate tokens from message length (rough heuristic: 1 token ≈ 4 chars)
  3. Atomic pre-deduction:
       UPDATE token_budgets
       SET tokens_used = tokens_used + :estimated
       WHERE user_id = :uid AND period = CURRENT_DATE
         AND tokens_used + :estimated <= budget_limit
       RETURNING tokens_used;
  4. If 0 rows returned → budget exhausted → 429
  5. After stream completes: reconcile with actual token counts (handled in chat.py)
"""

import logging
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from supabase import create_client

logger = logging.getLogger("app.middleware.token_budget")

_supabase = None


def _get_supabase():
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            _supabase = create_client(url, key)
    return _supabase


def _estimate_tokens(messages: list) -> int:
    """Rough token estimate: ~1 token per 4 characters across all messages."""
    total_chars = sum(len(m.get("content", "")) for m in messages if isinstance(m, dict))
    return max(total_chars // 4, 50)  # Minimum 50 tokens estimated


class TokenBudgetMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only enforce on chat streaming endpoints
        if request.url.path != "/v1/responses/stream":
            return await call_next(request)

        # Need user context from JWT
        user = getattr(request.state, "user", None)
        if not user:
            return await call_next(request)

        user_id = user.get("sub")
        if not user_id:
            return await call_next(request)

        db = _get_supabase()
        if not db:
            # If Supabase unavailable, let request through (fail open)
            return await call_next(request)

        try:
            # 1. Ensure budget row exists for today
            db.rpc("ensure_budget_row", {"p_user_id": user_id}).execute()

            # 2. Read the body to estimate tokens (cache for downstream)
            # Note: We read the raw body and re-attach it for downstream handlers
            body = await request.body()

            import json as _json
            try:
                payload = _json.loads(body) if body else {}
            except Exception:
                payload = {}

            messages = payload.get("messages", [])
            estimated_tokens = _estimate_tokens(messages)

            # Store estimate on request state for post-stream reconciliation
            request.state.estimated_tokens = estimated_tokens

            # 3. Atomic pre-deduction
            result = db.rpc("check_and_deduct_budget", {
                "p_user_id": user_id,
                "p_tokens": estimated_tokens,
            }).execute()

            # If RPC returns false or 0 rows → budget exhausted
            if result.data is False or result.data == 0:
                logger.warning(
                    f"Budget exhausted for user {user_id}. "
                    f"Estimated tokens: {estimated_tokens}"
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "BUDGET_EXHAUSTED",
                            "message": "Daily token budget exhausted. Resets at midnight UTC.",
                            "retry_after": 3600,
                        }
                    },
                )

        except Exception as e:
            logger.error(f"Error in token budget check: {e}")
            # Fail open — don't block users due to budget check errors

        return await call_next(request)
