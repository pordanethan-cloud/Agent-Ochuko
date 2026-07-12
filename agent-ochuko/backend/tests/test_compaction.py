from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from app.api.v1.endpoints.chat import (
    build_llm_context,
    persist_user_message_and_build_context,
)


@pytest.mark.asyncio
async def test_build_llm_context_filtering():
    # Mock data returned by Supabase (simulating active messages)
    mock_messages_data = [
        {"role": "system", "content": "Summary of conversation", "is_summary": True},
        {"role": "user", "content": "Recent message", "is_summary": False},
        {"role": "assistant", "content": "Recent response", "is_summary": False},
    ]

    mock_response = MagicMock()
    mock_response.data = mock_messages_data

    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.execute.return_value = mock_response

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = mock_table

    with patch("app.api.v1.endpoints.chat.get_supabase_admin", return_value=mock_supabase):
        context = await build_llm_context("test-conv-id")

        # Verify database interaction
        mock_supabase.table.assert_any_call("messages")
        mock_table.select.assert_any_call("role, content, is_summary")

        # Verify output formats only role and content fields
        assert len(context) == 3
        assert context[0] == {"role": "system", "content": "Summary of conversation"}
        assert context[1] == {"role": "user", "content": "Recent message"}
        assert context[2] == {"role": "assistant", "content": "Recent response"}


@pytest.mark.asyncio
async def test_current_user_message_is_saved_before_context_is_loaded():
    events = []
    mock_table = MagicMock()
    mock_table.insert.return_value = mock_table
    mock_table.execute.side_effect = lambda: events.append("message_saved")

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = mock_table

    async def load_context(_conversation_id):
        events.append("context_loaded")
        return [{"role": "user", "content": "Who is Myles Munroe?"}]

    with (
        patch(
            "app.api.v1.endpoints.chat.get_supabase_admin",
            return_value=mock_supabase,
        ),
        patch(
            "app.api.v1.endpoints.chat.build_llm_context",
            new=AsyncMock(side_effect=load_context),
        ),
    ):
        context = await persist_user_message_and_build_context(
            "test-conv-id",
            "Who is Myles Munroe?",
        )

    assert events == ["message_saved", "context_loaded"]
    assert context[-1] == {"role": "user", "content": "Who is Myles Munroe?"}
    mock_table.insert.assert_called_once_with({
        "conversation_id": "test-conv-id",
        "role": "user",
        "content": "Who is Myles Munroe?",
    })


@pytest.mark.asyncio
async def test_retry_with_same_request_id_does_not_duplicate_user_message():
    existing_response = MagicMock()
    existing_response.data = [{"id": "existing-message-id"}]

    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.contains.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.execute.return_value = existing_response

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = mock_table

    with (
        patch(
            "app.api.v1.endpoints.chat.get_supabase_admin",
            return_value=mock_supabase,
        ),
        patch(
            "app.api.v1.endpoints.chat.build_llm_context",
            new=AsyncMock(return_value=[{"role": "user", "content": "Hello"}]),
        ),
    ):
        context = await persist_user_message_and_build_context(
            "test-conv-id",
            "Hello",
            "18e02e43-2482-4637-9b79-4ed586500cad",
        )

    assert context == [{"role": "user", "content": "Hello"}]
    mock_table.insert.assert_not_called()
