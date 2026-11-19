"""User-permission-aware browser location adapter."""

from typing import Any

from .base import BaseTool


class LocationTool(BaseTool):
    """Validate browser coordinates returned after an explicit user grant."""

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        if not kwargs.get("permission_granted"):
            raise PermissionError("Location access requires explicit user consent.")
        try:
            latitude = float(kwargs["latitude"])
            longitude = float(kwargs["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Permission was granted, but browser coordinates are unavailable.") from exc
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Browser returned invalid latitude/longitude values.")
        return {
            "latitude": latitude,
            "longitude": longitude,
            "accuracy_meters": kwargs.get("accuracy"),
            "source": "browser geolocation (user permission granted)",
        }
