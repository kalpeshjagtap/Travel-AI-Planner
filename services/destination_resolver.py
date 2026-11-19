"""Thin geographic resolver using the existing policy-compliant Nominatim adapter."""
from typing import Any
from services.providers.nominatim import geocode_place

def resolve_destination(query: str) -> dict[str, Any]:
    """Resolve one user-entered city/region/country; user action and cached lookup required."""
    place=geocode_place(query)
    return {**place,"query":query,"resolution_status":"provider match; confirm it is the intended place"}
