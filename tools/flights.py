"""Flight search-link tool. Does not scrape or invent fares."""

from typing import Any

from services.mcp_client import MCPToolRegistry
from .base import BaseTool


class FlightSearchTool(BaseTool):
    """Create a date- and route-specific flight search link."""

    def __init__(self, mcp: MCPToolRegistry | None = None) -> None:
        self.mcp = mcp or MCPToolRegistry()

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        required = ("origin", "destination", "start_date", "end_date")
        missing = [key for key in required if not kwargs.get(key)]
        if missing:
            raise ValueError("Flight search requires: " + ", ".join(missing))
        return self.mcp.call_tool(
            "travel_server",
            "search_flights",
            {key: str(kwargs[key]) for key in required},
        )
