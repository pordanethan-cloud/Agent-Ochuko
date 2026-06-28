# app/api/v1/endpoints/admin.py
"""
Admin API routes — /v1/admin/*

All routes require the caller to hold role 'admin' or 'superadmin'.
The `require_admin` dependency enforces this after JWT verification.
"""
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.jwt_validator import verify_jwt
from app.services import admin_service

logger = logging.getLogger("app.api.v1.endpoints.admin")
router = APIRouter()

ADMIN_ROLES = {"admin", "superadmin"}
VALID_ROLES = {"guest", "user", "power_user", "admin", "superadmin"}


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def require_admin(user: Dict[str, Any] = Depends(verify_jwt)) -> Dict[str, Any]:
    """
    Dependency: verifies the JWT is valid AND the profile role is admin/superadmin.
    Reads the role directly from the JWT app_metadata set by Supabase triggers.
    """
    role = (
        user.get("app_metadata", {}).get("role")
        or user.get("user_metadata", {}).get("role")
    )
    if role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: admin or superadmin role required.",
        )
    return user


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class BlockUserRequest(BaseModel):
    google_sub: str = Field(..., description="Permanent Google OAuth subject ID")


class RoleUpdateRequest(BaseModel):
    role: str = Field(..., description="New role to assign")


class BudgetUpdateRequest(BaseModel):
    budget_limit: int = Field(..., gt=0, description="Daily token budget limit")


class SettingsUpdateRequest(BaseModel):
    updates: Dict[str, str] = Field(
        ..., description="Key/value pairs to upsert in admin_settings"
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", summary="List all users (paginated)")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    users = admin_service.list_users(page=page, page_size=page_size)
    return {"page": page, "page_size": page_size, "users": users}


@router.patch("/users/{user_id}/block", summary="Permanently block a user by google_sub")
async def block_user(
    user_id: str,
    body: BlockUserRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, str]:
    profile = admin_service.get_user(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found.")

    admin_service.block_user(
        user_id=user_id,
        google_sub=body.google_sub,
        admin_id=admin["sub"],
    )
    admin_service.write_audit_log(
        admin_id=admin["sub"],
        action="block_user",
        resource_type="profile",
        resource_id=user_id,
        metadata={"google_sub": body.google_sub},
    )
    return {"status": "blocked", "user_id": user_id}


@router.patch("/users/{user_id}/suspend", summary="Suspend a user (reversible)")
async def suspend_user(
    user_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, str]:
    _assert_user_exists(user_id)
    admin_service.set_user_active(user_id, is_active=False)
    admin_service.write_audit_log(
        admin_id=admin["sub"],
        action="suspend_user",
        resource_type="profile",
        resource_id=user_id,
    )
    return {"status": "suspended", "user_id": user_id}


@router.patch("/users/{user_id}/activate", summary="Re-activate a suspended user")
async def activate_user(
    user_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, str]:
    _assert_user_exists(user_id)
    admin_service.set_user_active(user_id, is_active=True)
    admin_service.write_audit_log(
        admin_id=admin["sub"],
        action="activate_user",
        resource_type="profile",
        resource_id=user_id,
    )
    return {"status": "active", "user_id": user_id}


@router.patch("/users/{user_id}/role", summary="Change a user's role")
async def update_role(
    user_id: str,
    body: RoleUpdateRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, str]:
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{body.role}'. Must be one of: {sorted(VALID_ROLES)}",
        )
    _assert_user_exists(user_id)
    admin_service.set_user_role(user_id, body.role)
    admin_service.write_audit_log(
        admin_id=admin["sub"],
        action="change_role",
        resource_type="profile",
        resource_id=user_id,
        metadata={"new_role": body.role},
    )
    return {"status": "updated", "user_id": user_id, "role": body.role}


@router.patch("/users/{user_id}/budget", summary="Set a per-user token budget")
async def update_budget(
    user_id: str,
    body: BudgetUpdateRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    _assert_user_exists(user_id)
    admin_service.set_user_budget(user_id, body.budget_limit)
    admin_service.write_audit_log(
        admin_id=admin["sub"],
        action="set_budget",
        resource_type="token_budget",
        resource_id=user_id,
        metadata={"budget_limit": body.budget_limit},
    )
    return {"status": "updated", "user_id": user_id, "budget_limit": body.budget_limit}


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

@router.get("/usage", summary="Token usage stats (last N days)")
async def get_usage(
    days: int = Query(30, ge=1, le=90),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    data = admin_service.get_usage_stats(days=days)
    top_users = admin_service.get_top_users(limit=5)
    return {**data, "top_users": top_users}


# ---------------------------------------------------------------------------
# Admin Settings (Supabase admin_settings table)
# ---------------------------------------------------------------------------

@router.get("/settings", summary="Fetch all admin_settings rows")
async def get_settings(
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    settings = admin_service.get_all_settings()
    return {"settings": settings}


@router.patch("/settings", summary="Update one or more admin_settings values")
async def update_settings(
    body: SettingsUpdateRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    updated_keys = []
    for key, value in body.updates.items():
        admin_service.update_setting(key=key, value=value, updated_by=admin["sub"])
        updated_keys.append(key)

    admin_service.write_audit_log(
        admin_id=admin["sub"],
        action="update_settings",
        resource_type="admin_settings",
        metadata={"keys_updated": updated_keys},
    )
    return {"status": "updated", "keys": updated_keys}


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

@router.get("/audit", summary="Paginated audit log with optional filters")
async def get_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="ISO 8601 datetime"),
    date_to: Optional[str] = Query(None, description="ISO 8601 datetime"),
    policy_decision: Optional[str] = Query(None, pattern="^(ALLOW|DENY)$"),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    entries = admin_service.get_audit_log(
        page=page,
        page_size=page_size,
        action=action,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        policy_decision=policy_decision,
    )
    return {"page": page, "page_size": page_size, "entries": entries}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assert_user_exists(user_id: str) -> None:
    if not admin_service.get_user(user_id):
        raise HTTPException(status_code=404, detail="User not found.")
