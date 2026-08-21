# Phase 3: MCP Connectors & Google APIs

> **Parent**: [Master Plan](./00_master_plan.md)
> **Depends on**: [Phase 1](./01_phase1_foundation.md), [Phase 2](./02_phase2_browser_and_background.md)
> **Timeline**: Weeks 7–10
> **Status**: Draft

---

## Phase 3 Overview

Phase 3 builds a **connector framework** that lets Agent Ochuko interact with external services on behalf of the user. It uses two integration mechanisms:

1. **MCP (Model Context Protocol)** — the industry-standard protocol for connecting AI agents to external tools. We build an MCP host that can discover and connect to MCP servers, giving the agent access to any MCP-compatible tool
2. **Google APIs (direct)** — Gmail and Google Calendar via Google OAuth (extending our existing Google Drive integration)

By the end, the agent can read/send emails, check/create calendar events, interact with GitHub repos, and connect to any future MCP server with zero code changes.

### Deliverables

1. MCP Host Client (JSON-RPC 2.0 client that connects to MCP servers)
2. MCP Server Registry (discover, manage, and permission-scope MCP servers per user)
3. Gmail Connector (read inbox, search emails, send emails, manage drafts)
4. Google Calendar Connector (list events, create events, check availability)
5. GitHub MCP Server integration (repos, issues, PRs via existing MCP server)
6. Connector permission UI (frontend settings page for managing connections)
7. Dynamic tool injection (active connectors inject tools into agent mode tool set)
8. Database: `user_connectors` table for OAuth tokens and permissions

---

## 3.1 MCP Architecture

### What Is MCP?

The Model Context Protocol (MCP) is an open standard that standardizes how AI agents connect to external data and tools. It follows a **client-host-server** pattern:

```
┌──────────────────────────────────────────────────────────────────┐
│  Agent Ochuko (MCP Host)                                         │
│                                                                  │
│  ┌────────────────┐                                              │
│  │  MCP Client     │──── JSON-RPC 2.0 ───>  ┌────────────────┐  │
│  │  (per server)   │                         │  MCP Server    │  │
│  │                 │<── Tools, Resources ──  │  (e.g. GitHub) │  │
│  └────────────────┘                         └────────────────┘  │
│                                                                  │
│  ┌────────────────┐                         ┌────────────────┐  │
│  │  MCP Client     │──── JSON-RPC 2.0 ───>  │  MCP Server    │  │
│  │  (per server)   │                         │  (e.g. Notion) │  │
│  └────────────────┘                         └────────────────┘  │
│                                                                  │
│  ┌────────────────┐                         ┌────────────────┐  │
│  │  Google API     │──── REST/OAuth 2.0 ──>  │  Gmail API     │  │
│  │  Connector      │                         │  Calendar API  │  │
│  └────────────────┘                         └────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### MCP Primitives We Support

| Primitive | Description | How Agent Uses It |
|---|---|---|
| **Tools** | Functions the agent can call (e.g., `github_create_issue`) | Injected into the agent's tool set dynamically |
| **Resources** | Read-only data (e.g., file contents, database records) | Agent reads resources for context before acting |
| **Prompts** | Pre-defined templates for specific workflows | Optional — used for complex multi-step connector workflows |

---

## 3.2 MCP Host Client

### File: [NEW] `app/connectors/mcp_client.py`

```python
"""
MCP Host Client — connects to MCP servers via JSON-RPC 2.0.
Supports stdio and SSE transport modes.
"""
import asyncio
import json
import logging
import subprocess
from typing import Dict, List, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger("app.connectors.mcp_client")

class MCPTool(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema

class MCPResource(BaseModel):
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None

class MCPServerConfig(BaseModel):
    name: str
    command: str              # e.g., "npx -y @modelcontextprotocol/server-github"
    args: List[str] = []
    env: Dict[str, str] = {}  # Environment variables (API keys, tokens)
    transport: str = "stdio"  # "stdio" | "sse"

class MCPClient:
    """
    Manages a single MCP server connection via stdio transport.
    Handles JSON-RPC 2.0 message framing.
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: Optional[asyncio.subprocess.Process] = None
        self.request_id = 0
        self.tools: List[MCPTool] = []
        self.resources: List[MCPResource] = []

    async def connect(self):
        """Start the MCP server process and initialize the connection."""
        env = {**dict(os.environ), **self.config.env}
        self.process = await asyncio.create_subprocess_exec(
            self.config.command, *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        # Send initialize request
        await self._send_request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}, "resources": {}},
            "clientInfo": {"name": "AgentOchuko", "version": "1.0.0"},
        })
        # Discover available tools
        tools_response = await self._send_request("tools/list", {})
        self.tools = [MCPTool(**t) for t in tools_response.get("tools", [])]
        # Discover available resources
        resources_response = await self._send_request("resources/list", {})
        self.resources = [MCPResource(**r) for r in resources_response.get("resources", [])]

        logger.info(
            f"MCP server '{self.config.name}' connected: "
            f"{len(self.tools)} tools, {len(self.resources)} resources"
        )

    async def call_tool(self, tool_name: str, arguments: Dict) -> str:
        """Execute a tool on the MCP server and return the result."""
        response = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        # Extract text content from response
        content = response.get("content", [])
        return "\n".join(
            item.get("text", "") for item in content
            if item.get("type") == "text"
        )

    async def read_resource(self, uri: str) -> str:
        """Read a resource from the MCP server."""
        response = await self._send_request("resources/read", {"uri": uri})
        contents = response.get("contents", [])
        return "\n".join(c.get("text", "") for c in contents)

    async def _send_request(self, method: str, params: Dict) -> Dict:
        """Send a JSON-RPC 2.0 request and wait for response."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }
        message = json.dumps(request) + "\n"
        self.process.stdin.write(message.encode())
        await self.process.stdin.drain()

        # Read response line
        response_line = await asyncio.wait_for(
            self.process.stdout.readline(), timeout=30
        )
        response = json.loads(response_line.decode())

        if "error" in response:
            raise Exception(f"MCP error: {response['error']}")
        return response.get("result", {})

    async def disconnect(self):
        """Terminate the MCP server process."""
        if self.process:
            self.process.terminate()
            await self.process.wait()

    def get_tool_definitions(self) -> List[Dict]:
        """
        Returns tool definitions in OpenAI function-calling format.
        These are injected into the agent's tool set dynamically.
        """
        definitions = []
        for tool in self.tools:
            definitions.append({
                "type": "function",
                "name": f"mcp_{self.config.name}_{tool.name}",
                "description": f"[{self.config.name}] {tool.description}",
                "parameters": tool.parameters,
            })
        return definitions
```

---

## 3.3 MCP Server Registry

### File: [NEW] `app/connectors/mcp_registry.py`

```python
"""
MCP Server Registry — discovers, manages, and permission-scopes MCP servers per user.
"""
import logging
from typing import Dict, List, Optional
from pydantic import BaseModel

logger = logging.getLogger("app.connectors.mcp_registry")

# Pre-configured MCP servers (built-in)
BUILTIN_MCP_SERVERS = {
    "github": MCPServerConfig(
        name="github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": ""},  # Filled from user_connectors
    ),
    "filesystem": MCPServerConfig(
        name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp/sandbox"],
        env={},
    ),
}

class ConnectorPermission(BaseModel):
    connector_name: str
    scopes: List[str]       # e.g., ["read", "write"] or ["repos:read", "issues:write"]
    is_active: bool = True

class MCPRegistry:
    """Manages active MCP connections per user session."""

    def __init__(self):
        self.active_clients: Dict[str, MCPClient] = {}

    async def get_user_connectors(self, user_id: str) -> List[MCPClient]:
        """
        Returns active MCP clients for a user.
        Loads OAuth tokens from user_connectors table.
        """
        supabase = get_supabase_admin()
        result = await asyncio.to_thread(
            lambda: supabase.table("user_connectors")
                .select("*")
                .eq("user_id", user_id)
                .eq("is_active", True)
                .execute()
        )
        clients = []
        for row in (result.data or []):
            connector_name = row["connector_name"]
            if connector_name in BUILTIN_MCP_SERVERS:
                config = BUILTIN_MCP_SERVERS[connector_name].model_copy()
                # Inject user's OAuth token
                config.env.update(self._decrypt_tokens(row))
                client = MCPClient(config)
                await client.connect()
                clients.append(client)
        return clients

    async def get_all_tool_definitions(self, user_id: str) -> List[Dict]:
        """
        Returns all tool definitions from active connectors.
        These are dynamically injected into the agent's tool set.
        """
        clients = await self.get_user_connectors(user_id)
        tools = []
        for client in clients:
            tools.extend(client.get_tool_definitions())
        return tools

    async def execute_mcp_tool(self, tool_name: str, arguments: Dict) -> str:
        """
        Executes a tool call on the appropriate MCP server.
        Tool name format: mcp_{server_name}_{tool_name}
        """
        parts = tool_name.split("_", 2)
        if len(parts) < 3 or parts[0] != "mcp":
            return f"Invalid MCP tool name: {tool_name}"
        server_name = parts[1]
        actual_tool_name = parts[2]

        client = self.active_clients.get(server_name)
        if not client:
            return f"MCP server '{server_name}' is not connected"

        return await client.call_tool(actual_tool_name, arguments)
```

---

## 3.4 Google API Connectors (Direct)

These use Google OAuth 2.0 directly (extending the existing Google Drive integration).

### File: [NEW] `app/connectors/gmail_connector.py`

```python
"""
Gmail Connector — read inbox, search, send emails, manage drafts.
Uses Google OAuth 2.0 with Gmail API scopes.
"""
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText
from typing import List, Dict, Optional

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
]

class GmailConnector:
    def __init__(self, credentials: Credentials):
        self.service = build("gmail", "v1", credentials=credentials)

    async def search_emails(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search Gmail with query syntax (from:, subject:, after:, etc.)"""
        results = self.service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        messages = []
        for msg_ref in results.get("messages", []):
            msg = self.service.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"]
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
        return messages

    async def read_email(self, message_id: str) -> Dict:
        """Read full email content by ID."""
        msg = self.service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        # Extract body text
        body = self._extract_body(msg.get("payload", {}))
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        return {
            "id": msg["id"],
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body,
        }

    async def send_email(self, to: str, subject: str, body: str) -> Dict:
        """Send an email. THIS IS A HIGH-RISK ACTION — requires HITL approval."""
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = self.service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return {"id": sent["id"], "status": "sent"}

    def get_tool_definitions(self) -> List[Dict]:
        """Returns tool definitions for agent mode."""
        return [
            {
                "type": "function",
                "name": "gmail_search",
                "description": "Search the user's Gmail inbox. Supports Gmail query syntax.",
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
                "description": "Read the full content of a specific email by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {"message_id": {"type": "string"}},
                    "required": ["message_id"],
                },
            },
            {
                "type": "function",
                "name": "gmail_send",
                "description": "Send an email on behalf of the user. HIGH RISK — requires approval.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
        ]
```

### File: [NEW] `app/connectors/google_calendar_connector.py`

```python
"""
Google Calendar Connector — list events, create events, check availability.
"""
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

class GoogleCalendarConnector:
    def __init__(self, credentials):
        self.service = build("calendar", "v3", credentials=credentials)

    async def list_events(self, time_min: str, time_max: str, max_results: int = 20) -> List[Dict]:
        """List calendar events in a date range."""
        ...

    async def create_event(self, summary: str, start: str, end: str,
                          description: str = "", location: str = "") -> Dict:
        """Create a calendar event. HIGH RISK — requires HITL approval."""
        ...

    async def check_availability(self, date: str) -> List[Dict]:
        """Check free/busy status for a date."""
        ...

    def get_tool_definitions(self) -> List[Dict]:
        """Returns tool definitions for agent mode."""
        return [
            {"type": "function", "name": "calendar_list_events", ...},
            {"type": "function", "name": "calendar_create_event", ...},
            {"type": "function", "name": "calendar_check_availability", ...},
        ]
```

---

## 3.5 Dynamic Tool Injection

### File: [MODIFY] `app/api/v1/endpoints/chat.py` (and `agent_task_manager.py`)

When building the tool set for an agent mode turn, dynamically inject connector tools:

```python
# In the agent mode tool construction:
base_tools = [WIDGET_TOOLS, search_tool, code_tool, image_tool, browser_tool]

# Inject MCP connector tools
mcp_registry = MCPRegistry()
connector_tools = await mcp_registry.get_all_tool_definitions(user_id)
all_tools = base_tools + connector_tools

# Inject Google API connector tools
google_connectors = await get_google_connectors(user_id)
for connector in google_connectors:
    all_tools.extend(connector.get_tool_definitions())

# Tool execution routing:
if tool_name.startswith("mcp_"):
    result = await mcp_registry.execute_mcp_tool(tool_name, args)
elif tool_name.startswith("gmail_"):
    result = await gmail_connector.handle_tool_call(tool_name, args)
elif tool_name.startswith("calendar_"):
    result = await calendar_connector.handle_tool_call(tool_name, args)
```

---

## 3.6 Database: `user_connectors` Table

```sql
CREATE TABLE IF NOT EXISTS user_connectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    connector_name TEXT NOT NULL,
    connector_type TEXT NOT NULL DEFAULT 'mcp'
        CHECK (connector_type IN ('mcp', 'google_api', 'oauth2')),
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    token_expiry TIMESTAMPTZ,
    scopes TEXT[] DEFAULT '{}',
    permissions TEXT[] DEFAULT '{"read"}',  -- "read", "write", "delete"
    is_active BOOLEAN DEFAULT true,
    config_json JSONB DEFAULT '{}'::jsonb,  -- MCP-specific config
    connected_at TIMESTAMPTZ DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    UNIQUE(user_id, connector_name)
);

ALTER TABLE user_connectors ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own connectors"
    ON user_connectors FOR ALL
    USING (auth.uid() = user_id);

CREATE INDEX idx_user_connectors_active ON user_connectors(user_id, is_active);
```

---

## 3.7 Connector Management API

### File: [NEW] `app/api/v1/endpoints/connectors.py`

```python
@router.get("/")
async def list_connectors(user=Depends(verify_jwt)):
    """List all available connectors and user's connection status."""

@router.post("/{connector_name}/connect")
async def connect_connector(connector_name: str, user=Depends(verify_jwt)):
    """Initiate OAuth flow for a connector. Returns redirect URL."""

@router.post("/{connector_name}/callback")
async def connector_oauth_callback(connector_name: str, code: str, user=Depends(verify_jwt)):
    """Handle OAuth callback, store encrypted tokens."""

@router.delete("/{connector_name}")
async def disconnect_connector(connector_name: str, user=Depends(verify_jwt)):
    """Revoke access and remove connector."""

@router.put("/{connector_name}/permissions")
async def update_permissions(connector_name: str, permissions: List[str], user=Depends(verify_jwt)):
    """Update permission scopes (read, write, delete)."""
```

---

## 3.8 Frontend: Connector Settings Page

### File: [NEW] `frontend/src/pages/ConnectorSettings.tsx`

A settings page where users manage their connected services:

- **Available Connectors**: Grid of cards (Gmail, Calendar, GitHub, Notion)
- **Connection Status**: Green/gray badge per connector
- **Connect Button**: Initiates OAuth flow in popup window
- **Permission Controls**: Toggles for read/write/delete per connector
- **Disconnect**: Revoke access button

---

## 3.9 Risk Classification for Connector Tools

All connector write operations are classified as HIGH risk:

```python
# In hitl_gates.py:
HIGH_RISK_CONNECTOR_TOOLS = {
    "gmail_send",
    "calendar_create_event",
    "mcp_github_create_issue",
    "mcp_github_create_pull_request",
    "mcp_notion_create_page",
}

# Read operations are LOW risk:
LOW_RISK_CONNECTOR_TOOLS = {
    "gmail_search", "gmail_read",
    "calendar_list_events", "calendar_check_availability",
    "mcp_github_list_repos", "mcp_github_get_file",
}
```

---

## 3.10 File Change Summary

| Action | File | Description |
|---|---|---|
| **NEW** | `app/connectors/__init__.py` | Package init |
| **NEW** | `app/connectors/mcp_client.py` | MCP JSON-RPC client |
| **NEW** | `app/connectors/mcp_registry.py` | MCP server registry + user connection mgmt |
| **NEW** | `app/connectors/gmail_connector.py` | Gmail read/send/search |
| **NEW** | `app/connectors/google_calendar_connector.py` | Calendar events/availability |
| **NEW** | `app/api/v1/endpoints/connectors.py` | Connector management API |
| **NEW** | `frontend/src/pages/ConnectorSettings.tsx` | Connector settings UI |
| **MODIFY** | `app/core/agent_task_manager.py` | Dynamic tool injection from connectors |
| **MODIFY** | `app/core/hitl_gates.py` | Risk classification for connector tools |
| **MODIFY** | `app/main.py` | Register connectors router |
| **NEW** | Supabase migration | `user_connectors` table |

---

## 3.11 Verification Plan

```bash
python -m pytest tests/test_mcp_client.py -v
python -m pytest tests/test_gmail_connector.py -v
python -m pytest tests/test_connector_permissions.py -v
```

### Manual Scenarios

1. **Gmail integration**: Connect Gmail → agent searches inbox → reads email → composes reply (pauses for HITL) → approve → sends
2. **Calendar integration**: Connect Calendar → "Schedule a meeting with John tomorrow at 2pm" → agent checks availability → creates event (pauses for HITL) → approve
3. **MCP GitHub**: Connect GitHub → "Create an issue in repo X for bug Y" → agent creates issue (pauses for HITL) → approve
4. **Permission enforcement**: Disconnect write permissions → verify agent cannot send emails, only read
5. **Token isolation**: Verify connector tool outputs are compressed by sub-agent before reaching orchestrator
