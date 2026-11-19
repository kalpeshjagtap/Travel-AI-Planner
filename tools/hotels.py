"""Open-data accommodation discovery tool."""

from typing import Any

from services.mcp_client import MCPToolRegistry
from .base import BaseTool


class HotelSearchTool(BaseTool):
    """Find named OpenStreetMap accommodation records, without booking data."""

    def __init__(self, mcp: MCPToolRegistry | None = None) -> None:
        self.mcp = mcp or MCPToolRegistry()

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        destination = str(kwargs.get("destination", "")).strip()
        if not destination:
            raise ValueError("A destination is required for hotel search.")
        return self.mcp.call_tool(
            "travel_server",
            "search_hotels",
            {"destination": destination, "limit": int(kwargs.get("limit", 12))},
        )
