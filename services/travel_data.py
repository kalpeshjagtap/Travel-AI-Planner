"""Backward-compatible facade over separately configured free provider adapters."""

from typing import Any
from urllib.parse import quote_plus

from services.providers.nominatim import NominatimError, geocode_place
from services.providers.open_meteo import WeatherProviderError, get_weather_forecast as _get_weather_forecast
from services.providers.opentripmap import OpenTripMapError, find_attractions
from services.providers.overpass import OverpassError, find_osm_places
from services.providers.osrm import RoutingProviderError, get_route


class TravelDataError(RuntimeError):
    """Raised when a public source fails or cannot provide requested data."""


def get_weather_forecast(destination: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Return live forecast values or a clear unavailable response."""
    search_link = f"https://www.google.com/search?q={quote_plus(destination + ' weather forecast ' + start_date + ' to ' + end_date)}"
    try:
        result = _get_weather_forecast(destination, start_date, end_date)
        result["search_link"] = search_link
        return result
    except (RuntimeError, TimeoutError) as exc:
        return {
            "available": False, "destination": destination, "source": "Open-Meteo",
            "attribution": "Weather data by Open-Meteo (CC BY 4.0): https://open-meteo.com/",
            "data_type": "forecast", "days": [], "reason": str(exc), "search_link": search_link,
        }


def build_flight_search_link(origin: str, destination: str, start_date: str, end_date: str) -> dict[str, str]:
    """Build a search link; no API calls, fares, schedules, or availability are implied."""
    query = f"Flights from {origin} to {destination} {start_date} to {end_date}"
    return {
        "provider": "Google Flights search",
        "url": f"https://www.google.com/travel/flights?q={quote_plus(query)}",
        "data_type": "search link",
        "disclaimer": "Search link only; the provider displays its own schedules, prices, and availability.",
    }


def find_hotel_listings(destination: str, *, limit: int = 12) -> dict[str, Any]:
    """Show OSM accommodation records with non-scraped provider search fallbacks."""
    try:
        result = find_osm_places(destination, category="accommodation", limit=limit)
    except (RuntimeError, TimeoutError) as exc:
        result = {
            "destination": destination, "source": "OpenStreetMap contributors", "data_type": "discovery link",
            "attribution": "© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL", "listings": [],
            "search_link": f"https://www.openstreetmap.org/search?query={quote_plus(destination + ' hotel')}",
            "reason": f"Mapped hotel discovery is unavailable; use the search link instead. {exc}",
        }
    result["booking_search_link"] = f"https://www.google.com/travel/hotels?q={quote_plus(destination + ' hotels')}"
    result["search_link"] = f"https://www.google.com/maps/search/{quote_plus('hotels in ' + destination)}"
    result["note"] = (
        "Mapped accommodation records are discovery data only. No room prices, booking status, or availability are supplied. "
        "Use the hotel search link to check current offers with a provider."
    )
    return result


def find_travel_attractions(destination: str, *, limit: int = 10) -> dict[str, Any]:
    """Use the optional free OpenTripMap tier, otherwise return a discovery link."""
    try:
        result = find_attractions(destination, limit=limit)
        if result.get("available") and result.get("attractions"):
            return result
        # OpenStreetMap's small, rate-limited attraction query is a useful
        # no-key fallback when the optional OpenTripMap key is absent.
        try:
            osm = find_osm_places(destination, category="attraction", limit=min(limit, 8))
            attractions = [
                {"name": item["name"], "latitude": item.get("latitude"),
                 "longitude": item.get("longitude"), "source": item.get("source", "OpenStreetMap contributors"),
                 "category": item.get("category"), "source_url": item.get("source_url"),
                 "data_type": "mapped attraction record"}
                for item in osm.get("listings", [])
            ]
            if attractions:
                return {"available": True, "source": "OpenStreetMap contributors", "data_type": "mapped POI records",
                        "attractions": attractions, "attribution": osm.get("attribution"),
                        "search_link": f"https://www.google.com/maps/search/{quote_plus('attractions in ' + destination)}",
                        "note": "Mapped attraction records are incomplete and do not confirm opening hours or current access."}
        except (RuntimeError, TimeoutError):
            pass
        result["search_link"] = f"https://www.google.com/maps/search/{quote_plus('tourist attractions in ' + destination)}"
        return result
    except (RuntimeError, TimeoutError) as exc:
        return {
            "available": False, "source": "OpenTripMap", "data_type": "discovery link",
            "attribution": "© [OpenTripMap](https://opentripmap.com); [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL",
            "attractions": [],
            "search_link": f"https://www.google.com/maps/search/{quote_plus('tourist attractions in ' + destination)}",
            "reason": f"Live POI lookup failed; use the search link instead. {exc}",
        }


__all__ = [
    "TravelDataError", "NominatimError", "WeatherProviderError", "OpenTripMapError", "OverpassError",
    "RoutingProviderError", "build_flight_search_link", "geocode_place", "get_weather_forecast",
    "find_hotel_listings", "find_travel_attractions", "get_route",
]
