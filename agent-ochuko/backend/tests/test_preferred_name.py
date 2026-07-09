import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.api.v1.endpoints.chat import chat_stream_generator

@pytest.mark.asyncio
@patch("app.api.v1.endpoints.chat._load_agent_memory")
@patch("app.api.v1.endpoints.chat._select_tools")
@patch("app.api.v1.endpoints.chat.get_openai_client")
async def test_preferred_name_injection_in_system_prompt(mock_get_client, mock_select_tools, mock_load_memory):
    # Setup mocks
    mock_load_memory.return_value = {}
    mock_select_tools.return_value = []
    
    # Mock Azure OpenAI client and stream responses
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    
    # Mock async generator for stream
    mock_stream = AsyncMock()
    mock_stream.__aiter__.return_value = []
    mock_client.responses.stream.return_value.__aenter__.return_value = mock_stream

    # Create mock user claim dictionary containing preferred_name
    mock_user = {
        "sub": "test-user-id",
        "user_metadata": {
            "preferred_name": "Okon"
        }
    }

    # Consume the generator to trigger prompt construction
    generator = chat_stream_generator(
        messages=[{"role": "user", "content": "Hello Ochuko!"}],
        deployment="gpt-test-model",
        system_prompt="Custom system instructions.",
        routing_mode="discuss",
        routing_reason="Direct chat",
        conversation_id="test-convo-id",
        user_id="test-user-id",
        mode="discuss",
        estimated_tokens=100,
        user=mock_user
    )

    # Walk the generator
    async for event in generator:
        pass

    # Verify client.responses.stream was called
    mock_client.responses.stream.assert_called_once()
    args, kwargs = mock_client.responses.stream.call_args
    
    # Check that system prompt contains "Okon" and instructions to address them by name
    messages_input = kwargs["input"]
    system_msg = [m for m in messages_input if m["role"] == "system"][0]
    
    assert "Okon" in system_msg["content"]
    assert "Address naturally, sparingly" in system_msg["content"]
