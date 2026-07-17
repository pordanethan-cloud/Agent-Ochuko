"""
Test script to measure upfront token consumption for a simple "hello" message.
This helps understand the baseline token cost before any actual response generation.
"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.api.v1.endpoints.chat import verify_jwt

# Mock the verify_jwt dependency
def mock_verify_jwt():
    return {
        "sub": "test-user-uuid",
        "email": "test@example.com"
    }

app.dependency_overrides[verify_jwt] = mock_verify_jwt

# Pricing constants (USD per 1M tokens)
TOKEN_PRICING = {
    "think": {"input": 15.0, "output": 60.0},
    "solve": {"input": 15.0, "output": 60.0},
    "discuss": {"input": 2.5, "output": 10.0},
    "nano": {"input": 0.15, "output": 0.60},
}

@pytest.mark.asyncio
@patch("app.api.v1.endpoints.chat.get_supabase_admin")
@patch("app.api.v1.endpoints.chat.model_router.route")
@patch("app.api.v1.endpoints.chat.get_config")
async def test_hello_message_token_consumption(mock_get_config, mock_route, mock_supabase):
    """
    Test that measures token consumption for a simple "hello" message.
    This tests the upfront token cost including system prompt, persona, and user message.
    """
    
    # Mock config responses
    async def mock_config_get(key, default):
        config_values = {
            "THINK_MODEL_DEPLOYMENT": "gpt-5.4",
            "DISCUSS_MODEL_DEPLOYMENT": "gpt-5.4-mini",
            "NANO_MODEL_DEPLOYMENT": "gpt-5.4-mini",
            "SOLVE_MODEL_DEPLOYMENT": "gpt-5.4",
            "MAX_COMPLETION_TOKENS_THINK": "16000",
            "MAX_COMPLETION_TOKENS_SOLVE": "8000",
            "REASONING_EFFORT_THINK": "medium",
            "REASONING_EFFORT_SOLVE": "medium",
            "MAX_ITERATIONS_THINK": "10",
            "MAX_ITERATIONS_SOLVE": "10",
            "AGENT_LOOP_ENABLED": "true",
            "STEP_TIMEOUT": "120",
        }
        return config_values.get(key, default)
    
    mock_get_config.side_effect = mock_config_get
    
    # Mock model routing
    from app.core.model_router import RoutingDecision
    mock_route.return_value = RoutingDecision(
        routing_mode="discuss",
        deployment="gpt-5.4-mini",
        routing_reason="Simple query, use discuss mode",
        was_intercepted=False,
        system_prompt="Custom system instructions."
    )
    
    # Mock Supabase
    mock_supabase_instance = MagicMock()
    mock_supabase_instance.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "test-conv-id"}])
    mock_supabase_instance.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data={"id": "test-conv-id"})
    mock_supabase_instance.table.return_value.update.return_value.execute.return_value = MagicMock(data=None)
    mock_supabase_instance.rpc.return_value.execute.return_value = MagicMock(data=None)
    mock_supabase.return_value = mock_supabase_instance
    
    # Mock OpenAI client streaming response
    mock_stream = AsyncMock()
    
    # Create mock events for streaming
    class MockEvent:
        def __init__(self, type, delta=None):
            self.type = type
            self.delta = delta
    
    # Simulate a simple response
    events = [
        MockEvent("response.output_text.delta", "Hello"),
        MockEvent("response.output_text.delta", "!"),
        MockEvent("response.output_text.done"),
    ]
    
    mock_response = MagicMock()
    mock_response.id = "test-response-id"
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 150  # System prompt + user message
    mock_response.usage.output_tokens = 2   # "Hello!"
    
    async def mock_stream_context(**kwargs):
        class MockStream:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def __aiter__(self):
                for event in events:
                    yield event
        return MockStream()
    
    mock_stream.return_value.__aenter__ = AsyncMock()
    mock_stream.return_value.__aexit__ = AsyncMock()
    mock_stream.return_value.__aiter__ = lambda self: iter(events)
    
    with patch("app.api.v1.endpoints.chat.AsyncAzureOpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.responses.stream = mock_stream
        mock_openai.return_value = mock_client
        
        # Create test client
        client = TestClient(app)
        
        # Send hello message
        response = client.post(
            "/v1/responses/stream",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "conversation_id": "00000000-0000-0000-0000-000000000000",
                "mode": "discuss"
            }
        )
        
        # Check response
        assert response.status_code == 200
        
        # Parse streaming response to extract token info
        # The response should include token counts in the final message
        lines = response.content.decode().split('\n')
        token_info = {}
        
        for line in lines:
            if line.startswith('data: '):
                import json
                try:
                    data = json.loads(line[6:])
                    if 'tokens_input' in data:
                        token_info['input_tokens'] = data['tokens_input']
                    if 'tokens_output' in data:
                        token_info['output_tokens'] = data['tokens_output']
                    if 'cost_usd' in data:
                        token_info['cost_usd'] = data['cost_usd']
                except:
                    pass
        
        print("\n" + "="*60)
        print("HELLO MESSAGE TOKEN CONSUMPTION TEST")
        print("="*60)
        print(f"Input tokens:  {token_info.get('input_tokens', 'N/A')}")
        print(f"Output tokens: {token_info.get('output_tokens', 'N/A')}")
        print(f"Total tokens:  {token_info.get('input_tokens', 0) + token_info.get('output_tokens', 0)}")
        print(f"Cost (USD):    ${token_info.get('cost_usd', 'N/A')}")
        print("="*60)
        
        # Calculate expected cost
        if 'input_tokens' in token_info and 'output_tokens' in token_info:
            pricing = TOKEN_PRICING["discuss"]
            input_cost = (token_info['input_tokens'] / 1_000_000) * pricing["input"]
            output_cost = (token_info['output_tokens'] / 1_000_000) * pricing["output"]
            total_cost = input_cost + output_cost
            
            print(f"Expected input cost:  ${input_cost:.6f}")
            print(f"Expected output cost: ${output_cost:.6f}")
            print(f"Expected total cost:  ${total_cost:.6f}")
            print("="*60)
            
            # Verify cost calculation
            assert abs(token_info['cost_usd'] - total_cost) < 0.000001, "Cost calculation mismatch"

if __name__ == "__main__":
    # Run the test directly
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
