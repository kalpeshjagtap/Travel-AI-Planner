"""Optional low-volume OSRM public-demo routing adapter."""

from typing import Any

import httpx

from config.settings import get_settings
from .cache import DailyRequestBudget, JsonProviderCache


class RoutingProviderError(RuntimeError):
    pass


def get_route(coordinates: list[tuple[float, float]], *, profile: str = "driving") -> dict[str, Any]:
    if len(coordinates) < 2 or len(coordinates) > 10:
        raise ValueError("OSRM routes require between two and ten waypoints.")
    if profile != "driving":
        raise ValueError("The configured public OSRM demo supports driving routes only.")
    settings = get_settings()
    if not settings.non_commercial_mode:
        raise RoutingProviderError("The public OSRM demo is for reasonable, non-commercial use only.")
    points = ";".join(f"{float(lon)},{float(lat)}" for lat, lon in coordinates)
    key_data = {"profile": profile, "points": points}
    cache = JsonProviderCache(settings.api_cache_directory)
    key = cache.key("osrm-route", key_data)
    result = cache.get(key)
    if result is None:
        cache.wait_for_interval("osrm", 1.05)
        result = cache.get(key)
        if result is None:
            DailyRequestBudget(settings.api_cache_directory).consume("osrm", limit=settings.osrm_daily_call_cap)
            try:
                response = httpx.get(
                    f"{settings.osrm_demo_url}/route/v1/{profile}/{points}",
                    params={"overview": "full", "geometries": "geojson", "steps": "false"},
                    headers={"User-Agent": settings.osm_user_agent},
                    timeout=settings.travel_api_timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("code") != "Ok" or not payload.get("routes"):
                    raise RoutingProviderError(f"OSRM returned {payload.get('code', 'no route')}.")
                route = payload["routes"][0]
                result = {"distance_m": route["distance"], "duration_s": route["duration"], "geometry": route["geometry"]}
            except (httpx.HTTPError, ValueError) as exc:
                raise RoutingProviderError(f"OSRM demo routing unavailable: {exc}") from exc
            cache.set(key, result, settings.osrm_cache_ttl_seconds)
    return {
        **result, "available": True, "source": "OSRM public demo", "data_type": "routing estimate",
        "attribution": "© OpenStreetMap contributors, ODbL; routing by OSRM",
        "note": "Best-effort, non-commercial demo route. Verify local conditions; no uptime guarantee.",
    }
