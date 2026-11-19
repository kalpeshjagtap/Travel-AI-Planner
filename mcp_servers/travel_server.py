"""MCP server exposing the same source-backed travel adapters as the agents."""

from mcp.server.fastmcp import FastMCP
from urllib.parse import quote_plus

from services.travel_data import build_flight_search_link, find_hotel_listings, get_route, get_weather_forecast

mcp = FastMCP("travel-planner")


@mcp.tool()
def search_flights(origin: str, destination: str, start_date: str, end_date: str) -> dict:
    """Return a provider search link; this tool does not report fares or seats."""
    return build_flight_search_link(origin, destination, start_date, end_date)


@mcp.tool()
def search_hotels(destination: str, limit: int = 12) -> dict:
    """Find named OpenStreetMap accommodation records, without prices or availability."""
    return find_hotel_listings(destination, limit=limit)


@mcp.tool()
def get_weather(destination: str, start_date: str, end_date: str) -> dict:
    """Retrieve a supported Open-Meteo forecast for the destination and dates."""
    return get_weather_forecast(destination, start_date, end_date)


@mcp.tool()
def get_driving_route(waypoints: list[dict[str, float]]) -> dict:
    """Request a light-use route estimate from the public OSRM demo."""
    coordinates = [(point["latitude"], point["longitude"]) for point in waypoints]
    try:
        return get_route(coordinates, profile="driving")
    except RuntimeError as exc:
        route_query = " to ".join(f"{lat},{lon}" for lat, lon in coordinates)
        return {
            "available": False,
            "data_type": "directions search link",
            "search_link": f"https://www.google.com/maps/dir/?api=1&origin={quote_plus(route_query.split(' to ')[0])}&destination={quote_plus(route_query.split(' to ')[-1])}",
            "reason": f"Public demo routing is unavailable; use a directions provider link instead. {exc}",
        }


if __name__ == "__main__":
    mcp.run(transport="stdio")
