"""MCP server exposing location tools."""

from mcp.server.fastmcp import FastMCP
from services.travel_data import geocode_place as lookup_place

mcp = FastMCP("travel-location")


@mcp.tool()
def geocode_place(place: str) -> dict:
    """Resolve a user-entered place name using policy-limited Nominatim."""
    return lookup_place(place)


if __name__ == "__main__":
    mcp.run(transport="stdio")
