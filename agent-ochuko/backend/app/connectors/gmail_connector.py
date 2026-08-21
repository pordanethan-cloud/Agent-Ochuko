"""
Gmail Connector — read inbox, search messages, send emails.
Uses Google OAuth 2.0 with Gmail API scopes.
"""
import base64
import logging
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.connectors.gmail_connector")

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
]


class GmailConnector:
    """Encapsulates Gmail API operations with Google credentials or access token."""

    def __init__(self, access_token: Optional[str] = None, service: Optional[Any] = None):
        self.access_token = access_token
        self._service = service

    def _get_service(self):
        if self._service:
            return self._service
        if not self.access_token:
            raise ValueError("Google access token required for GmailConnector")

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials(token=self.access_token)
            self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            return self._service
        except Exception as e:
            logger.error(f"Failed to initialize Gmail API service: {e}")
            raise

    async def search_emails(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search Gmail with query syntax (from:, subject:, after:, etc.)."""
        service = self._get_service()
        results = service.users().messages().list(
            userId="me", q=query, maxResults=min(max_results, 25)
        ).execute()

        messages = []
        for msg_ref in results.get("messages", []):
            try:
                msg = service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                ).execute()
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                messages.append({
                    "id": msg["id"],
                    "from": headers.get("From", ""),
                    "to": headers.get("To", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                    "snippet": msg.get("snippet", ""),
                })
            except Exception as e:
                logger.warning(f"Failed to fetch Gmail metadata for {msg_ref.get('id')}: {e}")

        return messages

    async def read_email(self, message_id: str) -> Dict[str, Any]:
        """Read full email content by message ID."""
        service = self._get_service()
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        payload = msg.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        body = self._extract_body(payload)

        return {
            "id": msg["id"],
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body or msg.get("snippet", ""),
        }

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """Extracts text/plain body from MIME parts."""
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                elif "parts" in part:
                    nested = self._extract_body(part)
                    if nested:
                        return nested
        else:
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return ""

    async def send_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Send an email on behalf of the user. HIGH RISK action."""
        service = self._get_service()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"id": sent.get("id"), "status": "sent", "to": to, "subject": subject}

    async def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Dispatches tool call to appropriate method."""
        try:
            if tool_name == "gmail_search":
                res = await self.search_emails(
                    query=arguments.get("query", ""),
                    max_results=int(arguments.get("max_results", 10)),
                )
                return str(res)
            elif tool_name == "gmail_read":
                res = await self.read_email(message_id=arguments.get("message_id", ""))
                return str(res)
            elif tool_name == "gmail_send":
                res = await self.send_email(
                    to=arguments.get("to", ""),
                    subject=arguments.get("subject", ""),
                    body=arguments.get("body", ""),
                )
                return f"Email sent successfully (Message ID: {res.get('id')})"
            return f"Unknown Gmail tool: {tool_name}"
        except Exception as e:
            return f"Gmail operation error: {str(e)}"

    @classmethod
    def get_tool_definitions(cls) -> List[Dict[str, Any]]:
        """Returns OpenAI function definitions for Gmail tools."""
        return [
            {
                "type": "function",
                "name": "gmail_search",
                "description": "Search the user's Gmail inbox using Gmail search queries (e.g. from:someone, subject:invoice, after:2026/01/01).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Gmail search query"},
                        "max_results": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            },
            {
                "type": "function",
                "name": "gmail_read",
                "description": "Read the full email body and headers of a specific email by its message ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string", "description": "The message ID returned from gmail_search"},
                    },
                    "required": ["message_id"],
                },
            },
            {
                "type": "function",
                "name": "gmail_send",
                "description": "Send an email on behalf of the user. HIGH RISK: Requires human approval before sending.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Email subject line"},
                        "body": {"type": "string", "description": "Email body content in plain text"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
        ]
