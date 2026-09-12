# app/connectors/mcp_registry.py
"""
MCP Registry — central registry for Model Context Protocol servers and tool dispatch.
"""
import os
import logging
from typing import Any, Dict, Optional
from app.connectors.workstation_mcp import WorkstationMCP

logger = logging.getLogger("app.connectors.mcp_registry")


class MCPRegistry:
    """Registry that manages external MCP tools and routes execution calls."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MCPRegistry, cls).__new__(cls)
        return cls._instance

    def __init__(self, workspace_root: Optional[str] = None):
        if not hasattr(self, "_initialized"):
            self.workstation = WorkstationMCP(workspace_root=workspace_root)
            self._initialized = True

    async def execute_mcp_tool(
        self,
        user_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        conversation_id: Optional[str] = None,
    ) -> str:
        """Executes an MCP tool call."""
        logger.info(f"Executing MCP tool '{tool_name}' for user '{user_id}' with args: {list(arguments.keys())}")
        
        # 1. Workstation Computer Access Tools
        if "workstation" in tool_name or tool_name.startswith("mcp_workstation_"):
            target_path = str(
                arguments.get("path")
                or arguments.get("file_path")
                or arguments.get("target_path")
                or ""
            ).strip()

            is_host_path = (
                (len(target_path) > 2 and target_path[1] == ":" and target_path[2] in ("\\", "/"))
                or target_path.startswith("~")
                or target_path.lower() in ("downloads", "download", "desktop", "documents", "home")
            )

            # Check if target file exists in conversation sandbox first
            if conversation_id:
                conv_dir = f"/tmp/sandbox_{conversation_id}"
                if os.path.exists(conv_dir):
                    # If target is a simple filename or relative path, check if it's already in the sandbox
                    base_name = os.path.basename(target_path) if target_path else ""
                    sandbox_candidate = os.path.join(conv_dir, base_name) if base_name else conv_dir
                    if os.path.exists(sandbox_candidate):
                        arguments["path"] = sandbox_candidate
                    elif not is_host_path:
                        self.workstation.workspace_root = conv_dir

            return await self.workstation.handle_tool_call(tool_name, arguments)

        # 2. Local Filesystem fallback
        elif tool_name.startswith("mcp_filesystem_"):
            return await self.workstation.handle_tool_call(tool_name.replace("mcp_filesystem_", "workstation_"), arguments)

        return f"Error: MCP tool '{tool_name}' is not supported or server is unavailable."
