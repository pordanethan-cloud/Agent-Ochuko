# app/api/v1/endpoints/shared.py
"""
Shared Conversations public routes — /v1/shared/*
No authentication required.
"""
import logging
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from app.services.supabase_admin import get_supabase_admin

logger = logging.getLogger("app.api.v1.endpoints.shared")
router = APIRouter()


@router.get("/{share_token}", summary="Fetch a shared conversation by token")
async def get_shared_conversation(share_token: str) -> Dict[str, Any]:
    """
    Fetch a shared conversation's title and its complete message history.
    Accessible publicly without authentication.
    """
    try:
        supabase = get_supabase_admin()
        
        # 1. Fetch conversation details where is_shared is True
        conv_res = (
            supabase.table("conversations")
            .select("id, title, model, mode, created_at")
            .eq("share_token", share_token)
            .eq("is_shared", True)
            .maybe_single()
            .execute()
        )
        
        if not conv_res.data:
            raise HTTPException(
                status_code=404,
                detail="Shared conversation not found or link has been deactivated."
            )
            
        convo = conv_res.data
        convo_id = convo["id"]
        
        # 2. Fetch all messages for the conversation sorted by created_at ascending
        msg_res = (
            supabase.table("messages")
            .select("id, role, content, routing_mode, routing_reason, created_at, content_parts")
            .eq("conversation_id", convo_id)
            .order("created_at", desc=False)
            .execute()
        )
        
        return {
            "title": convo["title"],
            "created_at": convo["created_at"],
            "messages": msg_res.data or []
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch shared conversation with token %s: %s", share_token, e)
        raise HTTPException(
            status_code=500,
            detail="Database error while fetching shared conversation."
        )
