from unittest.mock import patch, MagicMock
import pytest
from app.api.v1.endpoints.chat import build_llm_context


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
