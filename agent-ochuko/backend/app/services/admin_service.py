# app/services/admin_service.py
"""
Admin service layer.

All database reads/writes for the admin API live here.
Routes stay thin; this module owns the data logic.
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from app.services.supabase_admin import get_supabase_admin

logger = logging.getLogger("app.services.admin_service")


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def list_users(page: int = 1, page_size: int = 50) -> List[Dict[str, Any]]:
    """
    Return a paginated list of users joined with their token budget and agent usage.
    Columns: id, email, full_name, role, is_active, created_at,
             tokens_used_today (from token_budgets), last_seen, agent_calls_this_month.
    """
    db = get_supabase_admin()
    offset = (page - 1) * page_size
    current_period = datetime.now(timezone.utc).strftime("%Y-%m")
    current_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    response = (
        db.table("profiles")
        .select(
            "id, email, full_name, role, is_active, created_at, last_seen, google_sub, "
            "token_budgets(tokens_used, budget_limit, period), "
            "agent_quotas(ocr_pages_used, vision_calls_used, speech_seconds_used, image_gen_used, period)"
        )
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    users = response.data or []
    for u in users:
        # Sum agent calls for the current month period (YYYY-MM)
        quotas = u.get("agent_quotas") or []
        current_quota = next((q for q in quotas if q.get("period") == current_period), None)
        if current_quota:
            u["agent_calls_this_month"] = (
                (current_quota.get("ocr_pages_used") or 0)
                + (current_quota.get("vision_calls_used") or 0)
                + (current_quota.get("speech_seconds_used") or 0)
                + (current_quota.get("image_gen_used") or 0)
            )
        else:
            u["agent_calls_this_month"] = 0
            
        # Clean up nested agent_quotas to keep response tidy
        u.pop("agent_quotas", None)
        
        # Extract the token budget row for the current day (YYYY-MM-DD)
        budgets = u.get("token_budgets") or []
        current_budget = next((b for b in budgets if b.get("period") == current_date_str), None)
        if current_budget:
            u["token_budgets"] = {
                "tokens_used": current_budget.get("tokens_used") or 0,
                "budget_limit": current_budget.get("budget_limit") or 0
            }
        else:
            u["token_budgets"] = None

    return users


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    db = get_supabase_admin()
    response = (
        db.table("profiles")
        .select("id, email, full_name, role, is_active, google_sub, created_at, last_seen")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    return response.data


def block_user(user_id: str, google_sub: str, admin_id: str) -> None:
    """
    Permanently block a user:
    1. Insert their google_sub into blocked_identities (permanent, unbypassable).
    2. Set is_active = false on their profile.
    """
    db = get_supabase_admin()

    # 1. Block by google_sub
    db.table("blocked_identities").upsert(
        {"google_sub": google_sub, "blocked_by": admin_id, "reason": "admin_action"},
        on_conflict="google_sub",
    ).execute()

    # 2. Deactivate profile
    db.table("profiles").update({"is_active": False}).eq("id", user_id).execute()

    logger.info("User %s blocked by admin %s", user_id, admin_id)


def set_user_active(user_id: str, is_active: bool) -> None:
    """Suspend (False) or re-activate (True) a user profile."""
    db = get_supabase_admin()
    db.table("profiles").update({"is_active": is_active}).eq("id", user_id).execute()


def set_user_role(user_id: str, role: str) -> None:
    db = get_supabase_admin()
    db.table("profiles").update({"role": role}).eq("id", user_id).execute()


def set_user_budget(user_id: str, budget_limit: int) -> None:
    """
    Upsert the token budget for a user.
    Uses the ensure_budget_row RPC if available, otherwise direct upsert.
    """
    db = get_supabase_admin()
    db.table("token_budgets").upsert(
        {"user_id": user_id, "budget_limit": budget_limit},
        on_conflict="user_id",
    ).execute()


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

def get_usage_stats(days: int = 30) -> Dict[str, Any]:
    """
    Return token usage aggregated by (user, model, day) for the last `days` days.
    Reads directly from messages table (Phase 5 — pre-cron fallback).
    """
    db = get_supabase_admin()

    # Per-user totals
    user_totals = (
        db.table("messages")
        .select("user_id, input_tokens, output_tokens, model_used, created_at")
        .gte("created_at", _days_ago_iso(days))
        .eq("role", "assistant")
        .order("created_at", desc=True)
        .limit(10_000)
        .execute()
    )

    return {"messages": user_totals.data, "days": days}


def get_top_users(limit: int = 5) -> List[Dict[str, Any]]:
    """Return top N users by total token consumption (input + output)."""
    db = get_supabase_admin()
    response = db.rpc(
        "get_top_users_by_tokens",
        {"p_limit": limit},
    ).execute()
    # Fallback if RPC doesn't exist yet — return empty list cleanly
    return response.data if response.data else []


# ---------------------------------------------------------------------------
# Admin Settings (Supabase admin_settings table)
# ---------------------------------------------------------------------------

def get_all_settings() -> List[Dict[str, Any]]:
    db = get_supabase_admin()
    response = db.table("admin_settings").select("*").order("key").execute()
    return response.data


def update_setting(key: str, value: str, updated_by: str) -> None:
    db = get_supabase_admin()
    db.table("admin_settings").upsert(
        {"key": key, "value": value, "updated_by": updated_by},
        on_conflict="key",
    ).execute()


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

def get_audit_log(
    page: int = 1,
    page_size: int = 50,
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    policy_decision: Optional[str] = None,
) -> List[Dict[str, Any]]:
    db = get_supabase_admin()
    offset = (page - 1) * page_size

    query = (
        db.table("audit_log")
        .select(
            "id, created_at, user_id, action, resource_type, resource_id, "
            "policy_decision, ip_address, user_agent, policy_reason, metadata, "
            "profiles(email, full_name)"
        )
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
    )

    if action:
        query = query.eq("action", action)
    if user_id:
        query = query.eq("user_id", user_id)
    if date_from:
        query = query.gte("created_at", date_from)
    if date_to:
        query = query.lte("created_at", date_to)
    if policy_decision:
        query = query.eq("policy_decision", policy_decision)

    response = query.execute()
    return response.data


def write_audit_log(
    admin_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    policy_decision: str = "ALLOW",
) -> None:
    """Write a single audit log entry. Called after every admin mutation."""
    db = get_supabase_admin()
    db.table("audit_log").insert(
        {
            "user_id": admin_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "policy_decision": policy_decision,
            "metadata": metadata or {},
        }
    ).execute()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _days_ago_iso(days: int) -> str:
    from datetime import timedelta
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.isoformat()
