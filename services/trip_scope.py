"""Resolve whether a user-submitted trip crosses national borders."""

import logging
from typing import Any

from services.providers.nominatim import geocode_place

logger = logging.getLogger(__name__)


def classify_route_scope(request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return domestic/international/unknown using explicit or geocoded countries.

    Geocoding occurs only during an explicit trip-planning request and uses the
    cached, rate-limited Nominatim adapter. Failure stays unknown; it never
    guesses a country from a city name.
    """
    origin_country = str(request.get("origin_country", "")).strip()
    destination_country = str(request.get("destination_country", "")).strip()
    source = "request"

    if not origin_country or not destination_country:
        origin = str(request.get("origin", "")).strip()
        destination = str(request.get("destination", "")).strip()
        if not origin or not destination:
            return "unknown", {"source": "missing route endpoints"}
        try:
            origin_match = geocode_place(origin)
            destination_match = geocode_place(destination)
        except Exception as exc:
            logger.info("Could not resolve route countries; using generic travel allocation: %s", exc)
            return "unknown", {"source": "country lookup unavailable"}
        origin_country = str(origin_match.get("country", "")).strip()
        destination_country = str(destination_match.get("country", "")).strip()
        source = "Nominatim / OpenStreetMap"

    if not origin_country or not destination_country:
        return "unknown", {"source": source, "origin_country": origin_country, "destination_country": destination_country}
    scope = "domestic" if origin_country.casefold() == destination_country.casefold() else "international"
    return scope, {"source": source, "origin_country": origin_country, "destination_country": destination_country}
