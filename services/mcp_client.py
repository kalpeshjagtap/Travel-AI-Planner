"""Synchronous application gateway to local MCP stdio servers."""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MCPToolError(RuntimeError):
    """Raised when an MCP server or tool call fails."""


class MCPToolRegistry:
    """Launches configured local servers over stdio and calls named tools."""

    def __init__(self, server_config: dict[str, dict[str, Any]] | None = None) -> None:
        self.server_config = server_config or {
            "filesystem": {"module": "mcp_servers.filesystem_server", "timeout": 60.0},
            "gmail": {"module": "mcp_servers.gmail_server", "timeout": 60.0},
            "travel": {"module": "mcp_servers.travel_server", "timeout": 30.0},
        }

    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool through MCP and decode its JSON result."""
        config = self.server_config.get(server_name, {})
        module = config.get("module", f"mcp_servers.{server_name}")
        timeout = float(config.get("timeout", 45.0))
        logger.info("Calling MCP tool %s on %s", tool_name, server_name)
        try:
            return asyncio.run(asyncio.wait_for(self._call(module, tool_name, arguments, timeout), timeout=timeout * 2 + 5))
        except TimeoutError as exc:
            raise MCPToolError(
                f"MCP server {server_name} did not complete {tool_name} within {timeout * 2 + 5:g} seconds."
            ) from exc
        except Exception as exc:
            raise MCPToolError(f"MCP tool {server_name}.{tool_name} failed: {exc}") from exc

    @staticmethod
    async def _call(module: str, tool_name: str, arguments: dict[str, Any], timeout: float) -> dict[str, Any]:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", module],
            cwd=PROJECT_ROOT,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await asyncio.wait_for(session.initialize(), timeout=timeout)
                response = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments),
                    timeout=timeout,
                )
        if getattr(response, "isError", getattr(response, "is_error", False)):
            details = "; ".join(
                block.text for block in response.content if getattr(block, "text", None)
            )
            raise MCPToolError(details or "MCP server returned an error.")
        structured = getattr(response, "structuredContent", None)
        if structured is None:
            structured = getattr(response, "structured_content", None)
        if isinstance(structured, dict):
            return structured
        text_blocks = [block.text for block in response.content if getattr(block, "text", None)]
        if not text_blocks:
            return {"content": []}
        joined = "\n".join(text_blocks)
        try:
            decoded = json.loads(joined)
        except json.JSONDecodeError:
            return {"text": joined}
        return decoded if isinstance(decoded, dict) else {"result": decoded}
