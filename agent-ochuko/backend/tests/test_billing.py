import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

from app.main import FastAPI
from app.api.v1.endpoints.admin import verify_jwt
from app.main import admin_router
from fastapi import FastAPI as FastAPIApp

# Create local app for routing tests
test_app = FastAPIApp()
test_app.include_router(admin_router, prefix="/v1/admin")

# Mock the verify_jwt dependency to bypass Supabase OAuth validation and return an admin profile
def mock_verify_admin_jwt():
    return {
        "sub": "test-admin-uuid",
        "app_metadata": {
            "role": "admin"
        }
    }

test_app.dependency_overrides[verify_jwt] = mock_verify_admin_jwt
client = TestClient(test_app)

@pytest.mark.asyncio
@patch("app.api.v1.endpoints.admin.admin_service.get_usage_stats")
@patch("app.api.v1.endpoints.admin.admin_service.get_top_users")
@patch("app.api.v1.endpoints.admin.admin_service.get_azure_billing_info")
async def test_admin_usage_billing_endpoint(mock_get_billing, mock_get_top_users, mock_get_usage_stats):
    # Setup service return mocks
    mock_get_usage_stats.return_value = {
        "messages": [
            {
                "user_id": "test-user-uuid",
                "input_tokens": 100,
                "output_tokens": 200,
                "model_used": "gpt-5.4-mini",
                "created_at": "2026-07-09T10:00:00Z"
            }
        ],
        "days": 30
    }
    
    mock_get_top_users.return_value = [
        {
            "user_id": "test-user-uuid",
            "email": "user@test.com",
            "total_tokens": 300
        }
    ]
    
    mock_get_billing.return_value = {
        "azure_actual_cost": 12.34,
        "azure_credit_limit": 150.00,
        "azure_is_fallback": True,
        "azure_balance": 137.66
    }

    # Execute request
    response = client.get("/v1/admin/usage?days=30")

    # Assert response details
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["days"] == 30
    assert len(res_data["messages"]) == 1
    assert res_data["azure_actual_cost"] == 12.34
    assert res_data["azure_credit_limit"] == 150.00
    assert res_data["azure_is_fallback"] is True
    assert res_data["azure_balance"] == 137.66
    assert len(res_data["top_users"]) == 1
    
    # Confirm service calls
    mock_get_usage_stats.assert_called_once_with(days=30)
    mock_get_top_users.assert_called_once_with(limit=5)
    mock_get_billing.assert_called_once()
