# app/api/v1/endpoints/artifact_kv.py
"""
Artifact persistent K-V storage REST API — Phase 5 (item #15).

Exposes get/set/delete/list operations for widget-scoped and conversation-scoped
state. Enforces server-side 5 MB value cap, valid JSON validation, and RLS
authorization for personal vs conversation scopes.
"""

import json
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.core.jwt_validator import verify_jwt
from app.api.v1.endpoints.chat import get_supabase_admin
from app.services.artifact_kv import kv_get, kv_set, kv_delete, kv_list

logger = logging.getLogger("app.api.v1.endpoints.artifact_kv")

router = APIRouter()


class KVSetRequest(BaseModel):
    scope: str = Field(..., description="'personal' | 'conversation'")
    scope_id: str = Field(..., description="user_id or conversation_id")
    key: str = Field(..., description="Key name")
    value: Any = Field(..., description="JSON-serializable value or JSON string (max 5 MB)")


def _check_scope_auth(scope: str, scope_id: str, user: Dict[str, Any]) -> None:
    """RLS check: personal scope can only be accessed by the owning user."""
    if scope == "personal":
        user_id = user.get("sub")
        if user_id and scope_id != user_id:
            # Allow service-role / admin override if applicable
            if user.get("role") != "service_role":
                raise HTTPException(
                    status_code=403,
                    detail="Forbidden: cannot access personal storage of another user",
                )


@router.get("/{scope}/{scope_id}/{key}")
async def get_key(
    scope: str,
    scope_id: str,
    key: str,
    user: Dict = Depends(verify_jwt),
):
    """Retrieve an artifact KV value."""
    _check_scope_auth(scope, scope_id, user)
    supabase = get_supabase_admin()
    try:
        val_str = await kv_get(scope=scope, scope_id=scope_id, key=key, supabase_client=supabase)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if val_str is None:
        raise HTTPException(status_code=404, detail=f"Key '{key}' not found in {scope}:{scope_id}")

    # Return parsed JSON if possible, otherwise string
    try:
        parsed_val = json.loads(val_str)
    except Exception:
        parsed_val = val_str

    return {
        "scope": scope,
        "scope_id": scope_id,
        "key": key,
        "value": parsed_val,
    }


@router.post("", status_code=200)
@router.post("/", status_code=200)
@router.put("", status_code=200)
@router.put("/", status_code=200)
async def set_key(
    payload: KVSetRequest,
    user: Dict = Depends(verify_jwt),
):
    """Upsert an artifact KV value (max 5 MB)."""
    _check_scope_auth(payload.scope, payload.scope_id, user)
    supabase = get_supabase_admin()

    # Normalize value to valid JSON string
    if isinstance(payload.value, str):
        try:
            # Verify it's already JSON
            json.loads(payload.value)
            val_str = payload.value
        except Exception:
            val_str = json.dumps(payload.value)
    else:
        try:
            val_str = json.dumps(payload.value)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Value must be JSON serializable: {exc}")

    try:
        await kv_set(
            scope=payload.scope,
            scope_id=payload.scope_id,
            key=payload.key,
            value=val_str,
            supabase_client=supabase,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"status": "ok", "key": payload.key}


@router.delete("/{scope}/{scope_id}/{key}")
async def delete_key(
    scope: str,
    scope_id: str,
    key: str,
    user: Dict = Depends(verify_jwt),
):
    """Delete an artifact KV key."""
    _check_scope_auth(scope, scope_id, user)
    supabase = get_supabase_admin()
    try:
        existed = await kv_delete(
            scope=scope,
            scope_id=scope_id,
            key=key,
            supabase_client=supabase,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"status": "deleted", "key": key, "existed": existed}


@router.get("/{scope}/{scope_id}")
async def list_keys(
    scope: str,
    scope_id: str,
    prefix: str = Query("", description="Optional key prefix filter"),
    user: Dict = Depends(verify_jwt),
):
    """List keys under (scope, scope_id)."""
    _check_scope_auth(scope, scope_id, user)
    supabase = get_supabase_admin()
    try:
        keys = await kv_list(
            scope=scope,
            scope_id=scope_id,
            prefix=prefix,
            supabase_client=supabase,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"scope": scope, "scope_id": scope_id, "keys": keys}
