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


class ConversationUpdate(BaseModel):
    mode: str | None = Field(None, description="The mode to switch to (think, solve, or discuss)")
    title: str | None = Field(None, min_length=1, max_length=120, description="New conversation title")
    is_shared: bool | None = Field(None, description="Toggle shared status of the conversation")


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
            .select("id, title, model, mode, message_count, last_compacted_at, created_at, updated_at, is_shared, share_token")
            .eq("user_id", user_id)
            .eq("is_archived", False)
            .order("updated_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to list conversations for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error while fetching conversations.")


@router.get("/search", summary="Search user's active conversations by title or message content")
async def search_conversations(
    q: str,
    user: Dict[str, Any] = Depends(verify_jwt)
) -> List[Dict[str, Any]]:
    """
    Search conversations using Full-Text Search on title and message content.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    q = q.strip()
    if not q:
        return []

    try:
        supabase = get_supabase_admin()

        # 1. Search conversations by title matching query
        title_res = (
            supabase.table("conversations")
            .select("id, title, model, mode, message_count, last_compacted_at, created_at, updated_at")
            .eq("user_id", user_id)
            .eq("is_archived", False)
            .text_search("title", q, options={"config": "english", "type": "web_search"})
            .execute()
        )
        conversations = {c["id"]: c for c in (title_res.data or [])}

        # 2. Search message content matching query (filtered by user's conversations)
        # Get user's conversation IDs first
        user_conv_res = (
            supabase.table("conversations")
            .select("id")
            .eq("user_id", user_id)
            .eq("is_archived", False)
            .execute()
        )
        user_conv_ids = [c["id"] for c in (user_conv_res.data or [])]
        
        if not user_conv_ids:
            return list(conversations.values())
        
        # Search messages within user's conversations using ILIKE (case-insensitive search)
        msg_res = (
            supabase.table("messages")
            .select("conversation_id")
            .in_("conversation_id", user_conv_ids)
            .ilike("content", f"%{q}%")
            .limit(100)
            .execute()
        )
        msg_conv_ids = list({m["conversation_id"] for m in (msg_res.data or []) if m.get("conversation_id")})

        needed_ids = [cid for cid in msg_conv_ids if cid not in conversations]
        if needed_ids:
            content_res = (
                supabase.table("conversations")
                .select("id, title, model, mode, message_count, last_compacted_at, created_at, updated_at")
                .eq("user_id", user_id)
                .eq("is_archived", False)
                .in_("id", needed_ids)
                .execute()
            )
            for c in (content_res.data or []):
                conversations[c["id"]] = c

        results = list(conversations.values())
        results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return results
    except Exception as e:
        logger.error(f"Failed to search conversations for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error during search.")


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


@router.patch("/{id}", summary="Update conversation settings (mode and/or title)")
async def update_conversation(
    id: str,
    body: ConversationUpdate,
    user: Dict[str, Any] = Depends(verify_jwt)
) -> Dict[str, Any]:
    """
    Update a conversation mode and/or title. Both fields are optional.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    if body.mode is not None and body.mode not in VALID_MODES:
        raise HTTPException(status_code=422, detail=f"Invalid mode. Must be one of: {VALID_MODES}")

    if body.mode is None and body.title is None and body.is_shared is None:
        raise HTTPException(status_code=422, detail="At least one of 'mode', 'title' or 'is_shared' must be provided.")

    try:
        supabase = get_supabase_admin()
        conv_res = (
            supabase.table("conversations")
            .select("user_id, share_token, is_shared")
            .eq("id", id)
            .maybe_single()
            .execute()
        )
        if not conv_res.data:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        if conv_res.data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to modify this conversation.")

        update_payload: Dict[str, Any] = {}
        if body.mode is not None:
            update_payload["mode"] = body.mode
        if body.title is not None:
            update_payload["title"] = body.title.strip()
        if body.is_shared is not None:
            update_payload["is_shared"] = body.is_shared

        if update_payload:
            supabase.table("conversations").update(update_payload).eq("id", id).execute()
            logger.info("Conversation %s updated %s by user %s", id, list(update_payload.keys()), user_id)
            
        return {
            "status": "updated",
            "is_shared": body.is_shared if body.is_shared is not None else conv_res.data.get("is_shared"),
            "share_token": conv_res.data.get("share_token")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update conversation %s: %s", id, e)
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


@router.get("/{id}/files", summary="List generated files for a conversation")
async def list_generated_files(
    id: str,
    user: Dict[str, Any] = Depends(verify_jwt)
) -> List[Dict[str, Any]]:
    """
    Return all files generated by the code executor for this conversation.
    Used by the frontend to re-render download cards when the user returns to a session.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    try:
        supabase = get_supabase_admin()

        # Verify ownership
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

        files_res = (
            supabase.table("generated_files")
            .select("id, filename, r2_url, size_bytes, mime_type, created_at")
            .eq("conversation_id", id)
            .order("created_at", desc=False)
            .execute()
        )
        return files_res.data or []
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch generated files for conversation %s: %s", id, e)
        raise HTTPException(status_code=500, detail="Database error while fetching files.")
