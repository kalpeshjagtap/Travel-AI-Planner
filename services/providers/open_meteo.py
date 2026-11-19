"""Open-Meteo non-commercial free weather forecast adapter."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from config.settings import get_settings
from .cache import DailyRequestBudget, JsonProviderCache
from .nominatim import geocode_place


class WeatherProviderError(RuntimeError):
    pass


def get_weather_forecast(destination: str, start_date: str, end_date: str) -> dict[str, Any]:
    try:
        trip_start, trip_end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except ValueError as exc:
        raise WeatherProviderError("Weather dates must use YYYY-MM-DD format.") from exc
    if trip_end < trip_start:
        raise WeatherProviderError("Trip end date must not be earlier than its start date.")

    settings = get_settings()
    if not settings.non_commercial_mode:
        return {"available": False, "source": "Open-Meteo", "reason": "The no-key Open-Meteo endpoint is restricted to non-commercial use; enable NON_COMMERCIAL_MODE only for eligible use.", "days": []}
    today = datetime.now(UTC).date()
    horizon_end = today + timedelta(days=15)
    forecast_start, forecast_end = max(today, trip_start), min(horizon_end, trip_end)
    if forecast_start > forecast_end:
        return {"available": False, "destination": destination, "source": "Open-Meteo", "attribution": "Weather data by Open-Meteo (CC BY 4.0)", "reason": f"No forecast is available for those dates; this provider currently covers through {horizon_end.isoformat()}.", "days": []}

    location = geocode_place(destination)
    params = {
        "latitude": location["latitude"], "longitude": location["longitude"],
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 16,
    }
    cache = JsonProviderCache(settings.api_cache_directory)
    cache_key = cache.key("open-meteo-forecast", params)
    payload = cache.get(cache_key)
    if payload is None:
        DailyRequestBudget(settings.api_cache_directory).consume("open-meteo", limit=settings.open_meteo_daily_call_cap)
        try:
            response = httpx.get(settings.open_meteo_forecast_url, params=params, timeout=settings.travel_api_timeout)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WeatherProviderError(f"Open-Meteo forecast failed: {exc}") from exc
        cache.set(cache_key, payload, settings.weather_cache_ttl_seconds)
    daily = payload.get("daily", {})
    days = []
    for index, day in enumerate(daily.get("time", [])):
        if forecast_start.isoformat() <= day <= forecast_end.isoformat():
            days.append({
                "date": day,
                "weather_code": _value(daily, "weather_code", index),
                "temperature_max_c": _value(daily, "temperature_2m_max", index),
                "temperature_min_c": _value(daily, "temperature_2m_min", index),
                "precipitation_probability_max_percent": _value(daily, "precipitation_probability_max", index),
            })
    return {
        "available": bool(days), "destination": location, "source": "Open-Meteo",
        "data_type": "forecast", "attribution": "Weather data by Open-Meteo (CC BY 4.0): https://open-meteo.com/",
        "retrieved_at": datetime.now(UTC).isoformat(), "forecast_window_end": horizon_end.isoformat(),
        "requested_start_date": start_date, "requested_end_date": end_date,
        "partial": bool(days) and (trip_start < today or trip_end > horizon_end),
        "reason": None if days else "The provider returned no forecast for those dates.", "days": days,
    }


def _value(data: dict[str, Any], field: str, index: int) -> Any:
    values = data.get(field, [])
    return values[index] if index < len(values) else None
