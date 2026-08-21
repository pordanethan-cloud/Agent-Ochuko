"""
Google Calendar Connector — list events, create events, check availability.
Uses Google OAuth 2.0 with Calendar API scopes.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.connectors.google_calendar_connector")

CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


class GoogleCalendarConnector:
    """Encapsulates Google Calendar API operations."""

    def __init__(self, access_token: Optional[str] = None, service: Optional[Any] = None):
        self.access_token = access_token
        self._service = service

    def _get_service(self):
        if self._service:
            return self._service
        if not self.access_token:
            raise ValueError("Google access token required for GoogleCalendarConnector")

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials(token=self.access_token)
            self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            return self._service
        except Exception as e:
            logger.error(f"Failed to initialize Google Calendar API service: {e}")
            raise

    async def list_events(
        self, time_min: Optional[str] = None, time_max: Optional[str] = None, max_results: int = 15
    ) -> List[Dict[str, Any]]:
        """List calendar events in a date/time range."""
        service = self._get_service()
        if not time_min:
            time_min = datetime.now(timezone.utc).isoformat()

        req = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=min(max_results, 50),
            singleEvents=True,
            orderBy="startTime",
        )
        events_result = req.execute()
        items = events_result.get("items", [])

        events = []
        for item in items:
            start = item.get("start", {}).get("dateTime", item.get("start", {}).get("date"))
            end = item.get("end", {}).get("dateTime", item.get("end", {}).get("date"))
            events.append({
                "id": item.get("id"),
                "summary": item.get("summary", "(No title)"),
                "start": start,
                "end": end,
                "location": item.get("location"),
                "description": item.get("description"),
                "html_link": item.get("htmlLink"),
            })
        return events

    async def create_event(
        self, summary: str, start: str, end: str, description: str = "", location: str = ""
    ) -> Dict[str, Any]:
        """Create a new calendar event. HIGH RISK action."""
        service = self._get_service()
        body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start} if "T" in start else {"date": start},
            "end": {"dateTime": end} if "T" in end else {"date": end},
        }
        event = service.events().insert(calendarId="primary", body=body).execute()
        return {
            "id": event.get("id"),
            "status": "created",
            "summary": summary,
            "start": start,
            "end": end,
            "html_link": event.get("htmlLink"),
        }

    async def check_availability(self, date_str: str) -> Dict[str, Any]:
        """Check free/busy status for a specific date (YYYY-MM-DD)."""
        service = self._get_service()
        time_min = f"{date_str}T00:00:00Z"
        time_max = f"{date_str}T23:59:59Z"

        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": "primary"}],
        }
        freebusy = service.freebusy().query(body=body).execute()
        busy_slots = freebusy.get("calendars", {}).get("primary", {}).get("busy", [])

        return {
            "date": date_str,
            "busy_slots": busy_slots,
            "is_busy": len(busy_slots) > 0,
        }

    async def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Dispatches tool call to appropriate method."""
        try:
            if tool_name == "calendar_list_events":
                res = await self.list_events(
                    time_min=arguments.get("time_min"),
                    time_max=arguments.get("time_max"),
                    max_results=int(arguments.get("max_results", 15)),
                )
                return str(res)
            elif tool_name == "calendar_create_event":
                res = await self.create_event(
                    summary=arguments.get("summary", ""),
                    start=arguments.get("start", ""),
                    end=arguments.get("end", ""),
                    description=arguments.get("description", ""),
                    location=arguments.get("location", ""),
                )
                return f"Event created: {res.get('summary')} ({res.get('start')} to {res.get('end')})"
            elif tool_name == "calendar_check_availability":
                res = await self.check_availability(date_str=arguments.get("date", ""))
                return str(res)
            return f"Unknown Calendar tool: {tool_name}"
        except Exception as e:
            return f"Calendar operation error: {str(e)}"

    @classmethod
    def get_tool_definitions(cls) -> List[Dict[str, Any]]:
        """Returns OpenAI function definitions for Calendar tools."""
        return [
            {
                "type": "function",
                "name": "calendar_list_events",
                "description": "List upcoming events on the user's primary Google Calendar within an optional ISO-8601 time window.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "time_min": {"type": "string", "description": "Start ISO-8601 timestamp (e.g. 2026-08-21T09:00:00Z)"},
                        "time_max": {"type": "string", "description": "End ISO-8601 timestamp (e.g. 2026-08-21T18:00:00Z)"},
                        "max_results": {"type": "integer", "default": 15},
                    },
                },
            },
            {
                "type": "function",
                "name": "calendar_create_event",
                "description": "Create a new event on the user's primary Google Calendar. HIGH RISK: Requires human approval.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "Title/summary of the meeting or event"},
                        "start": {"type": "string", "description": "Start ISO-8601 timestamp (e.g. 2026-08-22T14:00:00Z) or date (YYYY-MM-DD)"},
                        "end": {"type": "string", "description": "End ISO-8601 timestamp (e.g. 2026-08-22T15:00:00Z) or date (YYYY-MM-DD)"},
                        "description": {"type": "string", "description": "Optional details or agenda for the event"},
                        "location": {"type": "string", "description": "Optional physical location or meeting URL"},
                    },
                    "required": ["summary", "start", "end"],
                },
            },
            {
                "type": "function",
                "name": "calendar_check_availability",
                "description": "Check free/busy schedule slots for a specific date (YYYY-MM-DD).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Date in YYYY-MM-DD format (e.g. 2026-08-22)"},
                    },
                    "required": ["date"],
                },
            },
        ]
