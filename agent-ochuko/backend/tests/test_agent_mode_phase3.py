"""
Tests for Agent Mode Phase 3: Google Workspace Connectors and HITL Integration.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.connectors.gmail_connector import GmailConnector
from app.connectors.google_calendar_connector import GoogleCalendarConnector
from app.core.agent_task_models import AgentTask, PlanStep, RiskLevel, StepStatus
from app.core.hitl_gates import HITLGate
from app.core.agent_task_manager import AgentTaskManager


# -- 1. Gmail Connector Tests ---------------------------------------------------

@pytest.mark.asyncio
async def test_gmail_connector_operations():
    """Verifies Gmail connector tool calls."""
    mock_service = MagicMock()
    # Mock search
    mock_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg_001"}]
    }
    mock_service.users().messages().get().execute.return_value = {
        "id": "msg_001",
        "payload": {
            "headers": [
                {"name": "From", "value": "partner@corp.com"},
                {"name": "Subject", "value": "Q3 Contract Review"},
                {"name": "Date", "value": "2026-08-21"},
            ],
            "body": {"data": ""},
        },
        "snippet": "Please review the attached contract.",
    }

    connector = GmailConnector(service=mock_service)

    # Search
    search_res = await connector.handle_tool_call("gmail_search", {"query": "contract"})
    assert "Q3 Contract Review" in search_res

    # Send
    mock_service.users().messages().send().execute.return_value = {"id": "sent_123"}
    send_res = await connector.handle_tool_call(
        "gmail_send",
        {"to": "partner@corp.com", "subject": "Re: Contract", "body": "Approved."},
    )
    assert "Email sent successfully" in send_res


# -- 2. Google Calendar Connector Tests -----------------------------------------

@pytest.mark.asyncio
async def test_google_calendar_connector_operations():
    """Verifies Google Calendar connector tool calls."""
    mock_service = MagicMock()
    mock_service.events().list().execute.return_value = {
        "items": [
            {
                "id": "event_001",
                "summary": "Sprint Planning",
                "start": {"dateTime": "2026-08-22T10:00:00Z"},
                "end": {"dateTime": "2026-08-22T11:00:00Z"},
            }
        ]
    }

    connector = GoogleCalendarConnector(service=mock_service)

    list_res = await connector.handle_tool_call("calendar_list_events", {"max_results": 5})
    assert "Sprint Planning" in list_res

    # Create event
    mock_service.events().insert().execute.return_value = {
        "id": "event_002",
        "summary": "Design Sync",
        "htmlLink": "https://calendar.google.com/event?id=002",
    }
    create_res = await connector.handle_tool_call(
        "calendar_create_event",
        {
            "summary": "Design Sync",
            "start": "2026-08-22T14:00:00Z",
            "end": "2026-08-22T15:00:00Z",
        },
    )
    assert "Event created: Design Sync" in create_res


# -- 3. Google Photos Connector Tests ------------------------------------------

@pytest.mark.asyncio
async def test_google_photos_connector_operations():
    """Verifies Google Photos connector tool calls."""
    from app.connectors.google_photos_connector import GooglePhotosConnector

    connector = GooglePhotosConnector(access_token="fake_token")

    # Mock photos search
    mock_search_res = MagicMock()
    mock_search_res.status_code = 200
    mock_search_res.json.return_value = {
        "mediaItems": [
            {
                "id": "photo_001",
                "filename": "sunset.jpg",
                "baseUrl": "https://lh3.googleusercontent.com/photo001",
                "mediaMetadata": {"creationTime": "2026-08-20T18:00:00Z"},
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_search_res)):
        search_out = await connector.handle_tool_call("photos_search", {"category": "LANDSCAPES"})
        assert "sunset.jpg" in search_out
        assert "photo_001" in search_out

    # Mock photos get
    mock_get_res = MagicMock()
    mock_get_res.status_code = 200
    mock_get_res.json.return_value = {
        "id": "photo_001",
        "filename": "sunset.jpg",
        "baseUrl": "https://lh3.googleusercontent.com/photo001",
        "mimeType": "image/jpeg",
        "mediaMetadata": {"width": "3840", "height": "2160", "creationTime": "2026-08-20T18:00:00Z"},
    }

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_get_res)):
        get_out = await connector.handle_tool_call("photos_get", {"media_item_id": "photo_001"})
        assert "3840x2160" in get_out
        assert "sunset.jpg" in get_out


# -- 4. HITL Risk Classification Tests ------------------------------------------

def test_hitl_connector_risk_classification():
    """Verifies write operations are classified as HIGH risk and reads as LOW risk."""
    # Write actions -> HIGH risk
    assert HITLGate.classify_risk(PlanStep(index=1, description="Send client confirmation", tool_name="gmail_send")) == RiskLevel.HIGH
    assert HITLGate.classify_risk(PlanStep(index=1, description="Schedule meeting with team", tool_name="calendar_create_event")) == RiskLevel.HIGH
    assert HITLGate.classify_risk(PlanStep(index=1, description="Upload asset to library", tool_name="photos_upload")) == RiskLevel.HIGH

    # Read actions -> LOW risk
    assert HITLGate.classify_risk(PlanStep(index=1, description="Search inbox for receipt", tool_name="gmail_search")) == RiskLevel.LOW
    assert HITLGate.classify_risk(PlanStep(index=1, description="Check availability tomorrow", tool_name="calendar_check_availability")) == RiskLevel.LOW
    assert HITLGate.classify_risk(PlanStep(index=1, description="Search photos of mountains", tool_name="photos_search")) == RiskLevel.LOW


# -- 5. Task Manager Step Dispatch Tests ----------------------------------------

@pytest.mark.asyncio
async def test_agent_task_manager_phase3_step_dispatch():
    """Verifies AgentTaskManager dispatches Phase 3 connector tool steps accurately."""
    task = AgentTask(goal="Check inbox and reply", conversation_id="conv-123", user_id="user-456")
    mock_client = MagicMock()
    manager = AgentTaskManager(task=task, openai_client=mock_client, deployment="test", nano_deployment="test")

    # Step: gmail_search
    step = PlanStep(index=1, description="Search for contract updates", tool_name="gmail_search")
    with patch("app.connectors.gmail_connector.GmailConnector.handle_tool_call", new=AsyncMock(return_value="Found 2 emails")):
        res = await manager._execute_single_step(step)
        assert res.success is True
        assert "Found 2 emails" in res.summary
