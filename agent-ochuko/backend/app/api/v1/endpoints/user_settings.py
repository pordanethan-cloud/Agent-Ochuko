# app/api/v1/endpoints/user_settings.py
"""
User Settings API — /v1/user/settings
Stores per-user server-side settings (PIN hash, etc.) so they work across all devices.
"""
import hashlib
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.jwt_validator import verify_jwt
from app.services.supabase_admin import get_supabase_admin

logger = logging.getLogger("app.api.v1.endpoints.user_settings")
router = APIRouter()


def _hash_pin(pin: str) -> str:
    """SHA-256 hash of the PIN — never store plain text."""
    return hashlib.sha256(pin.encode()).hexdigest()


class PinSetRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")


class PinVerifyRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")


class PinChangeRequest(BaseModel):
    current_pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
    new_pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")


def _get_settings(supabase, user_id: str) -> Optional[Dict]:
    resp = supabase.table("user_settings").select("*").eq("user_id", user_id).maybe_single().execute()
    return resp.data


def _upsert_settings(supabase, user_id: str, data: Dict):
    supabase.table("user_settings").upsert({"user_id": user_id, **data}, on_conflict="user_id").execute()


# ---------------------------------------------------------------------------
# GET /v1/user/settings/pin  — check if PIN is enabled (doesn't expose hash)
# ---------------------------------------------------------------------------
@router.get("/pin", summary="Check if PIN lock is enabled for this account")
async def get_pin_status(user: Dict[str, Any] = Depends(verify_jwt)):
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")
    try:
        supabase = get_supabase_admin()
        settings = _get_settings(supabase, user_id)
        has_pin = bool(settings and settings.get("pin_hash"))
        return {"pin_enabled": has_pin}
    except Exception as e:
        logger.error(f"get_pin_status error for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch PIN status.")


# ---------------------------------------------------------------------------
# POST /v1/user/settings/pin  — set a new PIN (no existing PIN required)
# ---------------------------------------------------------------------------
@router.post("/pin", summary="Set or replace PIN lock")
async def set_pin(body: PinSetRequest, user: Dict[str, Any] = Depends(verify_jwt)):
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")
    try:
        supabase = get_supabase_admin()
        _upsert_settings(supabase, user_id, {"pin_hash": _hash_pin(body.pin)})
        return {"ok": True, "pin_enabled": True}
    except Exception as e:
        logger.error(f"set_pin error for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save PIN.")


# ---------------------------------------------------------------------------
# POST /v1/user/settings/pin/verify  — verify a PIN attempt
# ---------------------------------------------------------------------------
@router.post("/pin/verify", summary="Verify a PIN attempt")
async def verify_pin(body: PinVerifyRequest, user: Dict[str, Any] = Depends(verify_jwt)):
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")
    try:
        supabase = get_supabase_admin()
        settings = _get_settings(supabase, user_id)
        if not settings or not settings.get("pin_hash"):
            raise HTTPException(status_code=404, detail="No PIN set for this account.")
        correct = _hash_pin(body.pin) == settings["pin_hash"]
        if not correct:
            raise HTTPException(status_code=401, detail="Incorrect PIN.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"verify_pin error for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify PIN.")


# ---------------------------------------------------------------------------
# PATCH /v1/user/settings/pin  — change PIN (requires current PIN)
# ---------------------------------------------------------------------------
@router.patch("/pin", summary="Change PIN (requires current PIN)")
async def change_pin(body: PinChangeRequest, user: Dict[str, Any] = Depends(verify_jwt)):
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")
    try:
        supabase = get_supabase_admin()
        settings = _get_settings(supabase, user_id)
        if not settings or not settings.get("pin_hash"):
            raise HTTPException(status_code=404, detail="No PIN set for this account.")
        if _hash_pin(body.current_pin) != settings["pin_hash"]:
            raise HTTPException(status_code=401, detail="Current PIN is incorrect.")
        _upsert_settings(supabase, user_id, {"pin_hash": _hash_pin(body.new_pin)})
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"change_pin error for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to change PIN.")


# ---------------------------------------------------------------------------
# DELETE /v1/user/settings/pin  — disable PIN (requires current PIN)
# ---------------------------------------------------------------------------
@router.delete("/pin", summary="Disable PIN lock (requires current PIN)")
async def delete_pin(body: PinVerifyRequest, user: Dict[str, Any] = Depends(verify_jwt)):
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")
    try:
        supabase = get_supabase_admin()
        settings = _get_settings(supabase, user_id)
        if not settings or not settings.get("pin_hash"):
            raise HTTPException(status_code=404, detail="No PIN set for this account.")
        if _hash_pin(body.pin) != settings["pin_hash"]:
            raise HTTPException(status_code=401, detail="Incorrect PIN.")
        _upsert_settings(supabase, user_id, {"pin_hash": None})
        return {"ok": True, "pin_enabled": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"delete_pin error for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to disable PIN.")
