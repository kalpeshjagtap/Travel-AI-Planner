"""Destination-agnostic journey skeleton and completeness validation.

This module never invents airports, schedules, routes, fares, accommodation,
currency conversions, or country-specific rules. It sequences only locations
the traveler actually supplied.
"""
from datetime import date, timedelta
from typing import Any


def _requested_stops(request: dict[str, Any]) -> list[str]:
    raw = request.get("preferred_regions") or request.get("stops") or []
    stops = [str(value).strip() for value in raw if str(value).strip()]
    if not stops:
        dest = str(request.get("destination", "")).strip()
        stops = [dest] if dest else []
    # Preserve order and remove exact duplicates without country assumptions.
    return list(dict.fromkeys(stops))


def build_journey(request: dict[str, Any]) -> dict[str, Any]:
    """Create a conservative itinerary skeleton for any user-entered locations."""
    if not request.get("start_date") or not request.get("end_date"):
        raise ValueError("Start and end dates are required to build a journey.")
    start = date.fromisoformat(request["start_date"])
    end = date.fromisoformat(request["end_date"])
    if end < start:
        raise ValueError("End date must not be earlier than start date.")
    days = (end - start).days + 1
    stops = _requested_stops(request)
    if not stops:
        raise ValueError("Enter a destination or at least one preferred stop.")
    days_out = []
    for index in range(days):
        stop_index = min(len(stops) - 1, (index * len(stops)) // days)
        place = stops[stop_index]
        first, last = index == 0, index == days - 1
        arrival = str(request.get("arrival_airport", "")).strip() or "arrival airport (unconfirmed)"
        departure = str(request.get("departure_airport", "")).strip() or "departure airport (unconfirmed)"
        origin = str(request.get("origin", "origin city (unconfirmed)")).strip()
        previous = stops[stop_index - 1] if stop_index > 0 else ""
        if first:
            transfer = f"{arrival} → accommodation in {place}; transfer mode, time and cost unverified"
            morning = f"Outbound journey from {origin}; flight/train schedule and arrival time require confirmation"
            afternoon = "Arrival formalities, airport/station transfer, accommodation check-in and rest"
        elif previous and previous != place:
            transfer = f"{previous} → {place}; compare available flight, rail, bus, ferry or road options"
            morning = f"Check out and transfer from {previous} toward {place}; departure time unverified"
            afternoon = f"Arrive in {place}, check in and allow time for the transfer"
        else:
            transfer = f"Local transport in {place}; routes and fares require confirmation"
            morning = f"Traveler-selected activities in {place}; verify locations and opening times"
            afternoon = f"Continue activities in {place}; transport details need confirmation"
        one_way = str(request.get("journey_type", "round_trip")).casefold() == "one_way"
        days_out.append({
            "date": (start + timedelta(days=index)).isoformat(),
            "city_or_region": place,
            "morning": morning,
            "afternoon": afternoon,
            "evening": f"Flexible evening near accommodation in {place}; verify venue details",
            "transfer": transfer,
            "accommodation": {
                "area": place,
                "nights": 0 if last else 1,
                "price_status": "Price unavailable until a verified/user-provided quote is added",
                "booking_search": f"https://www.google.com/maps/search/{place.replace(' ', '+')}+accommodation",
            },
            "return_journey": (None if one_way else
                f"Accommodation checkout, transfer to {departure}, return journey to {origin}; schedule, border/entry rules and price unverified"
                if last else None),
        })
    alternatives = [stops, list(reversed(stops))] if len(stops) > 1 else [stops]
    return {
        "stops": stops,
        "itinerary": days_out,
        "route_alternatives_unranked": alternatives,
        "route_comparison": "Alternatives are not cost-ranked. Verified transport schedules, fares and lodging prices are unavailable.",
        "airport_status": "Arrival/departure airports and open-jaw options require user selection or verified provider data.",
        "price_status": "No live prices or availability are asserted; missing costs remain unavailable.",
        "currency_status": "Local currency and conversion are not inferred. Enter verified quotes in the selected display currency (INR by default).",
    }


def validate_journey(journey: dict[str, Any], nights: int) -> list[str]:
    """Check homebound leg, hotel-night count, and explicit transfer fields."""
    issues = []
    days = journey.get("itinerary", [])
    if not days:
        return ["Itinerary has no days."]
    if any(day.get("return_journey") is not None for day in days) and "return journey" not in str(days[-1].get("return_journey", "")).casefold():
        issues.append("Last day is missing the return journey to origin.")
    if sum(int(day.get("accommodation", {}).get("nights", 0)) for day in days) != nights:
        issues.append("Accommodation night count does not match trip duration.")
    for day in days[:-1]:
        if int(day.get("accommodation", {}).get("nights", 0)) < 1:
            issues.append(f"Missing overnight accommodation on {day.get('date')}.")
    for day in days:
        if not day.get("transfer"):
            issues.append(f"Missing transfer details on {day.get('date')}.")
    return issues
