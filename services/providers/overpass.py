"""Light-use, cached OpenStreetMap Overpass discovery adapter."""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

import httpx

from config.settings import get_settings
from .cache import DailyRequestBudget, JsonProviderCache
from .nominatim import geocode_place


class OverpassError(RuntimeError):
    pass


def find_osm_places(destination: str, *, category: str, limit: int = 12) -> dict[str, Any]:
    settings = get_settings()
    if not settings.non_commercial_mode:
        raise OverpassError("The configured public Overpass integration is restricted to low-volume personal/non-commercial use.")
    location = geocode_place(destination)
    limit = max(1, min(int(limit), 20))
    if category == "accommodation":
        filter_query = '["tourism"~"^(hotel|hostel|guest_house|motel)$"]'
        search_name = "hotel"
    elif category == "attraction":
        filter_query = '["tourism"~"^(attraction|museum|gallery|viewpoint|zoo|theme_park)$"]'
        search_name = "attractions"
    else:
        raise ValueError("category must be accommodation or attraction")
    query = (
        f'[out:json][timeout:15];(nwr(around:6000,{location["latitude"]},{location["longitude"]})'
        f'{filter_query});out center body {limit};'
    )
    cache = JsonProviderCache(settings.api_cache_directory)
    key = cache.key("overpass", {"query": query, "endpoint": settings.overpass_api_url})
    payload = cache.get(key)
    if payload is None:
        # The app is deliberately capped below the public server's published
        # occasional-use range and runs one small, user-triggered query only.
        cache.wait_for_interval("overpass", settings.overpass_min_interval_seconds)
        payload = cache.get(key)
        if payload is None:
            DailyRequestBudget(settings.api_cache_directory).consume("overpass", limit=settings.overpass_daily_query_cap)
            try:
                response = httpx.post(
                    settings.overpass_api_url,
                    data={"data": query},
                    headers={"User-Agent": settings.osm_user_agent},
                    timeout=max(settings.travel_api_timeout, 20.0),
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise OverpassError(f"OpenStreetMap discovery is unavailable: {exc}") from exc
            cache.set(key, payload, settings.osm_data_cache_ttl_seconds)

    items = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        point = element.get("center", element)
        items.append({
            "name": name,
            "category": tags.get("tourism", category),
            "latitude": point.get("lat"), "longitude": point.get("lon"),
            "address": ", ".join(filter(None, (tags.get("addr:street"), tags.get("addr:city")))),
            "website": tags.get("website") or tags.get("contact:website"),
            "source": "OpenStreetMap contributors",
            "source_url": f"https://www.openstreetmap.org/{element.get('type')}/{element.get('id')}",
        })
    return {
        "destination": location, "source": "OpenStreetMap contributors", "data_type": "mapped records",
        "attribution": "© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL",
        "retrieved_at": datetime.now(UTC).isoformat(), "listings": items[:limit],
        "note": "OpenStreetMap records may be incomplete. Prices and availability are not provided.",
        "search_link": f"https://www.openstreetmap.org/search?query={quote_plus(destination + ' ' + search_name)}",
        "booking_search_link": f"https://www.google.com/travel/hotels?q={quote_plus(destination + ' ' + search_name)}",
    }
