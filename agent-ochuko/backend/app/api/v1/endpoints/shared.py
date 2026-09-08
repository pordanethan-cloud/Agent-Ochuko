# app/api/v1/endpoints/shared.py
"""
Shared Conversations public routes — /v1/shared/*
No authentication required.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException

from app.core.jwt_validator import verify_jwt
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


@router.post("/{share_token}/fork", summary="Fork a shared conversation into the authenticated user's account")
async def fork_shared_conversation(
    share_token: str,
    user: Dict[str, Any] = Depends(verify_jwt)
) -> Dict[str, Any]:
    """
    Fork (clone) an active shared conversation into the authenticated user's account.
    Copies the conversation metadata and all associated messages.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    try:
        supabase = get_supabase_admin()

        # 1. Fetch original shared conversation where is_shared is True
        conv_res = (
            supabase.table("conversations")
            .select("id, title, model, mode")
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

        orig_convo = conv_res.data
        orig_convo_id = orig_convo["id"]

        # 2. Fetch all messages from original conversation
        msg_res = (
            supabase.table("messages")
            .select("role, content, routing_mode, routing_reason, content_parts, created_at")
            .eq("conversation_id", orig_convo_id)
            .order("created_at", desc=False)
            .execute()
        )
        orig_messages = msg_res.data or []

        # 3. Create the new conversation for user
        new_convo_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()

        new_conv_payload = {
            "id": new_convo_id,
            "user_id": user_id,
            "title": orig_convo.get("title") or "Shared Conversation",
            "model": orig_convo.get("model") or "gpt-4o",
            "mode": orig_convo.get("mode") or "solve",
            "is_shared": False,
            "message_count": len(orig_messages),
            "created_at": now_str,
            "updated_at": now_str,
        }
        supabase.table("conversations").insert(new_conv_payload).execute()

        # 4. Bulk insert cloned messages if any
        if orig_messages:
            cloned_msgs = [
                {
                    "id": str(uuid.uuid4()),
                    "conversation_id": new_convo_id,
                    "role": m.get("role", "user"),
                    "content": m.get("content", ""),
                    "routing_mode": m.get("routing_mode"),
                    "routing_reason": m.get("routing_reason"),
                    "content_parts": m.get("content_parts"),
                    "created_at": m.get("created_at") or now_str,
                }
                for m in orig_messages
            ]
            supabase.table("messages").insert(cloned_msgs).execute()

        logger.info(
            "Successfully forked shared conversation %s to user %s as %s (%d messages)",
            share_token, user_id, new_convo_id, len(orig_messages)
        )

        return {
            "conversation_id": new_convo_id,
            "title": new_conv_payload["title"],
            "mode": new_conv_payload["mode"],
            "model": new_conv_payload["model"],
            "message_count": len(orig_messages)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fork shared conversation with token %s: %s", share_token, e)
        raise HTTPException(
            status_code=500,
            detail="Database error while forking shared conversation."
        )

