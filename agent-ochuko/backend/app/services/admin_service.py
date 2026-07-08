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

    # Query profiles using existing columns (display_name instead of full_name, omit email)
    response = (
        db.table("profiles")
        .select(
            "id, display_name, role, is_active, created_at, last_seen, google_sub, "
            "token_budgets(tokens_used, budget_limit, period), "
            "agent_quotas(ocr_pages_used, vision_calls_used, speech_seconds_used, image_gen_used, period)"
        )
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    # Fetch auth users to resolve emails
    auth_users_res = []
    try:
        auth_users_res = db.auth.admin.list_users()
    except Exception as e:
        logger.error("Failed to list auth users in admin_service: %s", e)

    email_map = {}
    users_list = []
    if isinstance(auth_users_res, list):
        users_list = auth_users_res
    elif hasattr(auth_users_res, "users"):
        users_list = auth_users_res.users
    elif auth_users_res:
        users_list = getattr(auth_users_res, "data", [])

    for u in users_list:
        uid = getattr(u, "id", None) or u.get("id")
        email = getattr(u, "email", None) or u.get("email")
        if uid and email:
            email_map[uid] = email

    users = response.data or []
    for u in users:
        # Resolve email
        u["email"] = email_map.get(u["id"]) or "unknown@domain.com"
        # Map display_name to full_name for the admin UI
        u["full_name"] = u.get("display_name") or u["email"].split("@")[0]

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
        total_tokens_used = sum(b.get("tokens_used") or 0 for b in budgets)
        u["total_tokens_used"] = total_tokens_used

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
        .select("id, display_name, role, is_active, google_sub, created_at, last_seen")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    u = response.data
    if u:
        try:
            auth_user = db.auth.admin.get_user_by_id(user_id)
            user_obj = getattr(auth_user, "user", auth_user)
            u["email"] = getattr(user_obj, "email", None) or user_obj.get("email") or "unknown@domain.com"
        except Exception as e:
            logger.error("Failed to get auth user by id: %s", e)
            u["email"] = "unknown@domain.com"
        u["full_name"] = u.get("display_name") or u["email"].split("@")[0]
    return u


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
    from datetime import date
    db = get_supabase_admin()
    db.table("token_budgets").upsert(
        {
            "user_id": user_id,
            "period": str(date.today()),
            "budget_limit": budget_limit
        },
        on_conflict="user_id,period",
    ).execute()


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

def get_usage_stats(days: int = 30) -> Dict[str, Any]:
    """
    Return token usage aggregated by (user, model, day) for the last `days` days.
    Reads from messages table joined with conversations to get user_id.
    """
    db = get_supabase_admin()

    # Per-user totals
    user_totals = (
        db.table("messages")
        .select("created_at, tokens_input, tokens_output, model, conversations(user_id)")
        .gte("created_at", _days_ago_iso(days))
        .eq("role", "assistant")
        .order("created_at", desc=True)
        .limit(10_000)
        .execute()
    )

    mapped_messages = []
    for msg in user_totals.data or []:
        convo = msg.get("conversations", {})
        u_id = convo.get("user_id") if isinstance(convo, dict) else None
        mapped_messages.append({
            "user_id": u_id,
            "input_tokens": msg.get("tokens_input", 0),
            "output_tokens": msg.get("tokens_output", 0),
            "model_used": msg.get("model"),
            "created_at": msg.get("created_at")
        })

    return {"messages": mapped_messages, "days": days}


def get_top_users(limit: int = 5) -> List[Dict[str, Any]]:
    """Return top N users by total token consumption (input + output)."""
    db = get_supabase_admin()
    top_list = []
    try:
        response = db.rpc(
            "get_top_users_by_tokens",
            {"p_limit": limit},
        ).execute()
        if response.data:
            # The RPC returns user_id, display_name, email (null), and total_tokens
            top_list = response.data
    except Exception as e:
        logger.warning("Failed to call get_top_users_by_tokens RPC, falling back to in-memory: %s", e)

    if not top_list:
        # Fallback: Query messages and aggregate in-memory
        try:
            res = (
                db.table("messages")
                .select("tokens_input, tokens_output, conversations(user_id)")
                .eq("role", "assistant")
                .execute()
            )
            data = res.data or []
            user_sums = {}
            for m in data:
                convo = m.get("conversations", {})
                u_id = convo.get("user_id") if isinstance(convo, dict) else None
                if not u_id:
                    continue
                tokens = (m.get("tokens_input") or 0) + (m.get("tokens_output") or 0)
                user_sums[u_id] = user_sums.get(u_id, 0) + tokens

            # Sort and limit
            sorted_users = sorted(user_sums.items(), key=lambda x: x[1], reverse=True)[:limit]
            for uid, total in sorted_users:
                top_list.append({
                    "user_id": uid,
                    "total_tokens": total
                })
        except Exception as e:
            logger.error("Failed in-memory fallback for top users: %s", e)

    # Always resolve display names and emails for the users in top_list
    if top_list:
        try:
            u_ids = [u["user_id"] for u in top_list]
            profiles_res = db.table("profiles").select("id, display_name").in_("id", u_ids).execute()
            prof_map = {p["id"]: p.get("display_name") for p in (profiles_res.data or [])}

            email_map = {}
            try:
                auth_users_res = db.auth.admin.list_users()
                users_list = []
                if isinstance(auth_users_res, list):
                    users_list = auth_users_res
                elif hasattr(auth_users_res, "users"):
                    users_list = auth_users_res.users
                elif auth_users_res:
                    users_list = getattr(auth_users_res, "data", [])
                for u in users_list:
                    uid = getattr(u, "id", None) or u.get("id")
                    email = getattr(u, "email", None) or u.get("email")
                    if uid and email:
                        email_map[uid] = email
            except Exception as ex:
                logger.error("Failed to list auth users in top users email resolution: %s", ex)

            for u in top_list:
                uid = u["user_id"]
                u["email"] = email_map.get(uid) or u.get("email") or "unknown@domain.com"
                u["display_name"] = prof_map.get(uid) or u.get("display_name") or u["email"].split("@")[0]
        except Exception as e:
            logger.error("Failed to resolve profile names or emails for top users: %s", e)

    return top_list



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
            "profiles(id, display_name)"
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
    entries = response.data or []

    # Fetch auth users to resolve emails (same pattern as list_users)
    auth_users_res = []
    try:
        auth_users_res = db.auth.admin.list_users()
    except Exception as e:
        logger.error("Failed to list auth users in get_audit_log: %s", e)

    email_map = {}
    users_list = []
    if isinstance(auth_users_res, list):
        users_list = auth_users_res
    elif hasattr(auth_users_res, "users"):
        users_list = auth_users_res.users
    elif auth_users_res:
        users_list = getattr(auth_users_res, "data", [])

    for u in users_list:
        uid = getattr(u, "id", None) or u.get("id")
        email = getattr(u, "email", None) or u.get("email")
        if uid and email:
            email_map[uid] = email

    for entry in entries:
        profile = entry.get("profiles") or {}
        u_id = entry.get("user_id")
        email = email_map.get(u_id) or "system"
        display_name = profile.get("display_name") if isinstance(profile, dict) else None
        entry["profiles"] = {
            "email": email,
            "full_name": display_name or email.split("@")[0]
        }

    return entries


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
