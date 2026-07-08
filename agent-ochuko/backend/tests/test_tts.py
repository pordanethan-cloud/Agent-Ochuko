import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import FastAPI
from app.api.v1.endpoints.agents import verify_jwt

# Create local app for testing router isolated or use the main app
from app.main import chat_router, agents_router
from fastapi import FastAPI as FastAPIApp

test_app = FastAPIApp()
test_app.include_router(agents_router, prefix="/v1/agents")

# Mock the dependency verify_jwt
def mock_verify_jwt():
    return {"sub": "test-user-id"}

test_app.dependency_overrides[verify_jwt] = mock_verify_jwt
client = TestClient(test_app)

@patch("app.api.v1.endpoints.agents.get_supabase_admin")
@patch("app.api.v1.endpoints.agents._safe_execute")
@patch("app.api.v1.endpoints.agents.enqueue_job")
def test_queue_tts_job_validation(mock_enqueue, mock_safe_exec, mock_get_supabase):
    # Setup mock returns
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase
    
    # 1. Mock quota check to return a data dict
    mock_quota = MagicMock()
    mock_quota.data = {"tts_calls_used": 0}
    
    # 2. Mock admin settings limit
    mock_settings = MagicMock()
    mock_settings.data = {"value": "500"}
    
    # 3. Mock job insertion
    mock_job_insert = MagicMock()
    mock_job_insert.data = [{"id": "test-job-uuid"}]
    
    # Sequence of mock executions: quota check, admin settings check, job insert
    mock_safe_exec.side_effect = [mock_quota, mock_settings, mock_job_insert]

    # Valid payload matching exactly what the frontend sends
    payload = {
        "text": "This is a test of the text-to-speech engine.",
        "voice": "auto",
        "conversation_id": "00000000-0000-0000-0000-000000000000"
    }
    
    # Execute the request
    response = client.post("/v1/agents/speech/tts", json=payload)
    
    # Assert status code is 202 Accepted
    assert response.status_code == 202
    assert response.json()["job_id"] == "test-job-uuid"
    assert response.json()["status"] == "pending"
    
    # Verify R2/Azure Dispatch was called
    mock_enqueue.assert_called_once()
