"""Policy-compliant, user-triggered Nominatim geocoding adapter."""

from typing import Any

import httpx

from config.settings import get_settings
from .cache import JsonProviderCache


class NominatimError(RuntimeError):
    pass


def geocode_place(place: str) -> dict[str, Any]:
    query = " ".join(place.split())
    if not query:
        raise ValueError("Enter a destination to look up.")
    # Disambiguate India's state from the many global matches for bare "Goa".
    if query.casefold() in {"goa", "goa india"}:
        query = "Goa, India"
    settings = get_settings()
    cache = JsonProviderCache(settings.api_cache_directory)
    key = cache.key("nominatim", query.casefold())
    cached = cache.get(key)
    if cached:
        return cached
    # Nominatim requires a deliberate, end-user-triggered query and max 1 req/s
    # across the application. No autocomplete or batch geocoding is implemented.
    cache.wait_for_interval("nominatim", 1.05)
    cached = cache.get(key)
    if cached:
        return cached
    try:
        response = httpx.get(
            settings.nominatim_url,
            params={"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 1},
            headers={"User-Agent": settings.nominatim_user_agent, "Accept-Language": "en"},
            timeout=settings.travel_api_timeout,
        )
        response.raise_for_status()
        results = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise NominatimError(f"Nominatim lookup failed for {query!r}: {exc}") from exc
    if not results:
        raise NominatimError(f"No location match was found for {query!r}.")
    item = results[0]
    address = item.get("address", {})
    value = {
        "name": item.get("name") or item.get("display_name", query).split(",")[0],
        "display_name": item.get("display_name", query),
        "country": address.get("country", ""),
        "admin1": address.get("state", address.get("region", "")),
        "latitude": float(item["lat"]),
        "longitude": float(item["lon"]),
        "timezone": "auto",
        "source": "Nominatim / OpenStreetMap",
        "attribution": "© OpenStreetMap contributors, ODbL",
        "source_url": item.get("osm_id") and f"https://www.openstreetmap.org/{item.get('osm_type','node').lower()}/{item['osm_id']}",
    }
    cache.set(key, value, settings.nominatim_cache_ttl_seconds)
    return value
