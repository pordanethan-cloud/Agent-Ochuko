"""
Connectors Management API — manage MCP and external service integrations per user.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.supabase_admin import get_supabase_admin
from app.core.jwt_validator import verify_jwt

logger = logging.getLogger("app.api.v1.endpoints.connectors")

router = APIRouter(prefix="/connectors", tags=["connectors"])


class UpdateConnectorRequest(BaseModel):
    is_active: Optional[bool] = None
    permissions: Optional[List[str]] = None
    review_policy: Optional[str] = Field(None, description="'always_ask' or 'always_proceed'")
    access_token: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None


class ConnectRequest(BaseModel):
    connector_type: str = "mcp"  # "mcp" | "google_api" | "oauth2" | "custom"
    access_token: Optional[str] = None
    permissions: List[str] = Field(default_factory=lambda: ["read"])
    review_policy: str = "always_ask"
    config_json: Dict[str, Any] = Field(default_factory=dict)


# Default catalog of connectors available on Ochuko
CONNECTOR_CATALOG = [
    {
        "name": "gmail",
        "title": "Gmail (Google Workspace)",
        "description": "Read inbox, search emails, and compose drafts or messages.",
        "type": "google_api",
        "category": "Communication",
        "icon": "mail",
        "default_permissions": ["read", "write"],
    },
    {
        "name": "google_calendar",
        "title": "Google Calendar",
        "description": "View upcoming events, schedule meetings, and verify availability.",
        "type": "google_api",
        "category": "Productivity",
        "icon": "calendar",
        "default_permissions": ["read", "write"],
    },
    {
        "name": "google_photos",
        "title": "Google Photos",
        "description": "Search photos by category/date, retrieve high-res image assets, and upload media.",
        "type": "google_api",
        "category": "Media",
        "icon": "image",
        "default_permissions": ["read", "write"],
    },
    {
        "name": "filesystem",
        "title": "Local Sandbox Filesystem MCP",
        "description": "Secure workspace storage access for project files and codebases.",
        "type": "mcp",
        "category": "System",
        "icon": "folder",
        "default_permissions": ["read", "write"],
    },
    {
        "name": "workstation_access",
        "title": "Workstation Computer Access MCP",
        "description": "Direct read, write, directory navigation, and terminal command execution on your workstation (Agent Mode only).",
        "type": "mcp",
        "category": "System",
        "icon": "cpu",
        "default_permissions": ["read", "write", "execute"],
    },
]


@router.get("")
async def list_connectors(user: Dict[str, Any] = Depends(verify_jwt)):
    """List all available connectors with user's connection status and permissions."""
    user_id = user.get("id") or user.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    supabase = get_supabase_admin()
    try:
        res = await asyncio.to_thread(
            lambda: supabase.table("user_connectors")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        user_conns = {r["connector_name"]: r for r in (res.data or [])}
    except Exception as e:
        logger.warning(f"Error fetching user connectors: {e}")
        user_conns = {}

    items = []
    for cat in CONNECTOR_CATALOG:
        c_name = cat["name"]
        user_entry = user_conns.get(c_name)
        is_connected = bool(user_entry and user_entry.get("is_active"))
        items.append({
            **cat,
            "is_connected": is_connected,
            "permissions": user_entry.get("permissions", cat["default_permissions"]) if user_entry else cat["default_permissions"],
            "review_policy": user_entry.get("review_policy", "always_ask") if user_entry else "always_ask",
            "last_used_at": user_entry.get("last_used_at") if user_entry else None,
            "connected_at": user_entry.get("connected_at") if user_entry else None,
        })

    # Include any custom MCP servers configured by the user
    for c_name, r in user_conns.items():
        if not any(c["name"] == c_name for c in CONNECTOR_CATALOG):
            items.append({
                "name": c_name,
                "title": c_name.capitalize(),
                "description": "Custom user-configured MCP server",
                "type": r.get("connector_type", "custom"),
                "category": "Custom",
                "icon": "cpu",
                "default_permissions": ["read"],
                "is_connected": bool(r.get("is_active")),
                "permissions": r.get("permissions", ["read"]),
                "review_policy": r.get("review_policy", "always_ask"),
                "last_used_at": r.get("last_used_at"),
                "connected_at": r.get("connected_at"),
            })

    return {"connectors": items}


@router.post("/{connector_name}/connect")
async def connect_connector(
    connector_name: str,
    req: ConnectRequest,
    user: Dict[str, Any] = Depends(verify_jwt),
):
    """Connect or register credentials for a connector."""
    user_id = user.get("id") or user.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    supabase = get_supabase_admin()
    payload = {
        "user_id": user_id,
        "connector_name": connector_name,
        "connector_type": req.connector_type,
        "access_token_encrypted": req.access_token,
        "permissions": req.permissions,
        "review_policy": req.review_policy,
        "is_active": True,
        "config_json": req.config_json,
    }

    try:
        await asyncio.to_thread(
            lambda: supabase.table("user_connectors")
            .upsert(payload, on_conflict="user_id,connector_name")
            .execute()
        )
        return {"success": True, "connector_name": connector_name, "status": "connected"}
    except Exception as e:
        logger.error(f"Error saving connector {connector_name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{connector_name}/permissions")
async def update_permissions(
    connector_name: str,
    req: UpdateConnectorRequest,
    user: Dict[str, Any] = Depends(verify_jwt),
):
    """Update active state, review policy ('always_ask' / 'always_proceed'), or permissions."""
    user_id = user.get("id") or user.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    supabase = get_supabase_admin()
    updates: Dict[str, Any] = {}
    if req.is_active is not None:
        updates["is_active"] = req.is_active
    if req.permissions is not None:
        updates["permissions"] = req.permissions
    if req.review_policy is not None:
        if req.review_policy not in ("always_ask", "always_proceed"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid review_policy")
        updates["review_policy"] = req.review_policy
    if req.access_token is not None:
        updates["access_token_encrypted"] = req.access_token
    if req.config_json is not None:
        updates["config_json"] = req.config_json

    if not updates:
        return {"success": True, "message": "No changes made"}

    try:
        await asyncio.to_thread(
            lambda: supabase.table("user_connectors")
            .update(updates)
            .eq("user_id", user_id)
            .eq("connector_name", connector_name)
            .execute()
        )
        return {"success": True, "updated": updates}
    except Exception as e:
        logger.error(f"Error updating connector permissions for {connector_name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{connector_name}")
async def disconnect_connector(
    connector_name: str,
    user: Dict[str, Any] = Depends(verify_jwt),
):
    """Disconnect and revoke connector access."""
    user_id = user.get("id") or user.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    supabase = get_supabase_admin()
    try:
        await asyncio.to_thread(
            lambda: supabase.table("user_connectors")
            .delete()
            .eq("user_id", user_id)
            .eq("connector_name", connector_name)
            .execute()
        )
        return {"success": True, "connector_name": connector_name, "status": "disconnected"}
    except Exception as e:
        logger.error(f"Error disconnecting {connector_name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
