"""Optional OpenTripMap free-plan attraction search; never required to start."""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

import httpx

from config.settings import get_settings
from .cache import DailyRequestBudget, JsonProviderCache
from .nominatim import geocode_place


class OpenTripMapError(RuntimeError):
    pass


def find_attractions(destination: str, *, limit: int = 10) -> dict[str, Any]:
    settings = get_settings()
    fallback = {
        "available": False, "source": "OpenTripMap", "data_type": "discovery link",
        "attribution": "[OpenTripMap](https://opentripmap.com); data may include [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) (ODbL)",
        "attractions": [],
        "search_link": f"https://www.openstreetmap.org/search?query={quote_plus(destination + ' attractions')}",
        "reason": "OpenTripMap is optional: add a key from its $0 non-commercial plan to enable POI results.",
    }
    api_key = settings.opentripmap_api_key.get_secret_value()
    if not settings.non_commercial_mode:
        fallback["reason"] = "OpenTripMap free access is limited to non-commercial use; use the discovery link instead."
        return fallback
    if not api_key or not settings.opentripmap_free_plan_confirmed:
        fallback["reason"] = "OpenTripMap is disabled unless an API key from its $0 non-commercial plan is configured and OPENTRIPMAP_FREE_PLAN_CONFIRMED=true."
        return fallback
    location = geocode_place(destination)
    limit = max(1, min(int(limit), 20))
    params = {
        "radius": 6000, "lon": location["longitude"], "lat": location["latitude"],
        "kinds": "interesting_places", "format": "json", "limit": limit,
        "apikey": api_key,
    }
    cache = JsonProviderCache(settings.api_cache_directory)
    key = cache.key("opentripmap", {k: v for k, v in params.items() if k != "apikey"})
    records = cache.get(key)
    if records is None:
        cache.wait_for_interval("opentripmap", 0.12)  # free plan: max 10 requests/second
        records = cache.get(key)
        if records is None:
            DailyRequestBudget(settings.api_cache_directory).consume("opentripmap", limit=settings.opentripmap_daily_call_cap)
            try:
                response = httpx.get(settings.opentripmap_radius_url, params=params, timeout=settings.travel_api_timeout)
                response.raise_for_status()
                records = response.json()
            except httpx.HTTPStatusError as exc:
                # Avoid echoing the request URL because it contains the private API key.
                raise OpenTripMapError(f"OpenTripMap returned HTTP {exc.response.status_code}.") from exc
            except (httpx.RequestError, ValueError) as exc:
                raise OpenTripMapError(f"OpenTripMap request failed ({type(exc).__name__}).") from exc
            cache.set(key, records, settings.opentripmap_cache_ttl_seconds)
    attractions = []
    for item in records:
        point = item.get("point", {})
        if not item.get("name") or point.get("lat") is None or point.get("lon") is None:
            continue
        attractions.append({
            "name": item["name"], "kinds": item.get("kinds", ""),
            "latitude": point["lat"], "longitude": point["lon"],
            "distance_m": item.get("dist"), "xid": item.get("xid"),
            "source": "OpenTripMap", "data_type": "POI record; not a booking or availability result",
        })
    return {
        "available": True, "source": "OpenTripMap", "data_type": "mapped POI records",
        "attribution": "© [OpenTripMap](https://opentripmap.com); underlying data may include © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) (ODbL)",
        "retrieved_at": datetime.now(UTC).isoformat(), "attractions": attractions,
        "search_link": fallback["search_link"],
        "note": "Attraction records are discovery information, not opening-hours confirmation, prices, or availability.",
    }
