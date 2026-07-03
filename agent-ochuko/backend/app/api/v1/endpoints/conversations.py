# app/api/v1/endpoints/conversations.py
"""
Conversations API routes — /v1/conversations/*
Handles listing conversations, loading message history, and patching conversation settings.
"""
import logging
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.jwt_validator import verify_jwt
from app.services.supabase_admin import get_supabase_admin

logger = logging.getLogger("app.api.v1.endpoints.conversations")
router = APIRouter()

VALID_MODES = {"think", "solve", "discuss"}


class ConversationModeUpdate(BaseModel):
    mode: str = Field(..., description="The mode to switch to (think, solve, or discuss)")


@router.get("", summary="List all active conversations for the user")
async def list_conversations(
    user: Dict[str, Any] = Depends(verify_jwt)
) -> List[Dict[str, Any]]:
    """
    Retrieve all non-archived conversations belonging to the authenticated user.
    Ordered by updated_at descending (most recent first).
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    try:
        supabase = get_supabase_admin()
        response = (
            supabase.table("conversations")
            .select("id, title, model, mode, message_count, last_compacted_at, created_at, updated_at")
            .eq("user_id", user_id)
            .eq("is_archived", False)
            .order("updated_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to list conversations for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error while fetching conversations.")


@router.get("/{id}/messages", summary="Load full message history for a conversation")
async def load_message_history(
    id: str,
    user: Dict[str, Any] = Depends(verify_jwt)
) -> List[Dict[str, Any]]:
    """
    Load all messages (archived and active) for the specified conversation.
    Ensures that the conversation belongs to the requesting user.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    try:
        supabase = get_supabase_admin()

        # 1. Verify ownership of the conversation
        conv_res = (
            supabase.table("conversations")
            .select("user_id")
            .eq("id", id)
            .maybe_single()
            .execute()
        )

        if not conv_res.data:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        if conv_res.data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this conversation.")

        # 2. Fetch all messages sorted by created_at ascending
        msg_res = (
            supabase.table("messages")
            .select("id, role, content, routing_mode, routing_reason, is_summary, is_archived_msg, created_at, content_parts")
            .eq("conversation_id", id)
            .order("created_at", desc=False)
            .execute()
        )
        return msg_res.data or []
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch messages for conversation {id}: {e}")
        raise HTTPException(status_code=500, detail="Database error while fetching message history.")


@router.patch("/{id}", summary="Update conversation settings (e.g. mode)")
async def update_conversation(
    id: str,
    body: ConversationModeUpdate,
    user: Dict[str, Any] = Depends(verify_jwt)
) -> Dict[str, Any]:
    """
    Update a conversation's mode mid-session.
    Ensures the user owns the conversation before executing the update.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    if body.mode not in VALID_MODES:
        raise HTTPException(status_code=422, detail=f"Invalid mode. Must be one of: {VALID_MODES}")

    try:
        supabase = get_supabase_admin()

        # 1. Verify ownership of the conversation
        conv_res = (
            supabase.table("conversations")
            .select("user_id")
            .eq("id", id)
            .maybe_single()
            .execute()
        )

        if not conv_res.data:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        if conv_res.data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to modify this conversation.")

        # 2. Update the conversation mode
        update_res = (
            supabase.table("conversations")
            .update({"mode": body.mode})
            .eq("id", id)
            .execute()
        )

        logger.info(f"Conversation {id} mode updated to {body.mode} by user {user_id}")
        return {"status": "updated", "mode": body.mode}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update conversation {id}: {e}")
        raise HTTPException(status_code=500, detail="Database error while updating conversation.")


@router.delete("/{id}", summary="Delete a conversation permanently")
async def delete_conversation(
    id: str,
    user: Dict[str, Any] = Depends(verify_jwt)
) -> Dict[str, Any]:
    """
    Permanently delete a conversation and cascade delete its messages.
    Ensures that the conversation belongs to the requesting user.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    try:
        supabase = get_supabase_admin()

        # 1. Verify ownership of the conversation
        conv_res = (
            supabase.table("conversations")
            .select("user_id")
            .eq("id", id)
            .maybe_single()
            .execute()
        )

        if not conv_res.data:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        if conv_res.data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this conversation.")

        # 2. Delete the conversation
        supabase.table("conversations").delete().eq("id", id).execute()

        logger.info(f"Conversation {id} permanently deleted by user {user_id}")
        return {"status": "deleted", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete conversation {id}: {e}")
        raise HTTPException(status_code=500, detail="Database error while deleting conversation.")

