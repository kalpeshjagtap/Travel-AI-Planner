"""Public weather forecast tool."""

from typing import Any

from services.mcp_client import MCPToolRegistry
from .base import BaseTool


class WeatherForecastTool(BaseTool):
    """Retrieve destination weather for supported forecast dates."""

    def __init__(self, mcp: MCPToolRegistry | None = None) -> None:
        self.mcp = mcp or MCPToolRegistry()

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        required = ("destination", "start_date", "end_date")
        missing = [key for key in required if not kwargs.get(key)]
        if missing:
            raise ValueError("Weather lookup requires: " + ", ".join(missing))
        return self.mcp.call_tool(
            "travel_server",
            "get_weather",
            {key: str(kwargs[key]) for key in required},
        )
