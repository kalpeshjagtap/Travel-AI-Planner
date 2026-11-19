"""Central trip-cost arithmetic. Only user-entered/provider-verified quotes are totaled."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

CATEGORIES = (
    "international_return_flights", "domestic_transport", "accommodation", "food",
    "local_transport", "airport_transfers", "activities", "visa", "insurance", "miscellaneous",
)

# These are planning splits (not market-price estimates). Route-specific lists
# avoid allocating international flights or visa fees to a domestic itinerary.
_ALLOCATION_PROFILES = {
    "domestic": {
        "domestic_return_travel": (35, "Domestic return travel"),
        "intercity_transport": (10, "Intercity transport"),
        "accommodation": (25, "Accommodation"),
        "food": (15, "Food"),
        "local_transport": (8, "Local transport"),
        "terminal_transfers": (2, "Airport/station transfers"),
        "activities": (5, "Activities"),
    },
    "international": {
        "international_return_flights": (30, "International return flights"),
        "domestic_transport": (10, "Domestic/intercity transport"),
        "accommodation": (25, "Accommodation"),
        "food": (15, "Food"),
        "local_transport": (5, "Local transport"),
        "airport_transfers": (3, "Airport transfers"),
        "activities": (7, "Activities"),
        "miscellaneous": (5, "Other expenses"),
    },
    "unknown": {
        "return_transport": (35, "Return travel (mode unconfirmed)"),
        "intercity_transport": (10, "Intercity transport"),
        "accommodation": (25, "Accommodation"),
        "food": (15, "Food"),
        "local_transport": (7, "Local transport"),
        "terminal_transfers": (3, "Airport/station transfers"),
        "activities": (5, "Activities"),
    },
}


def allocate_trip_budget(budget_inr: Any, travelers: int = 1, *, route_scope: str = "unknown") -> dict[str, Any]:
    """Allocate a user budget across categories without claiming actual prices."""
    if travelers < 1:
        raise ValueError("Travelers must be at least one.")
    if budget_inr in (None, ""):
        return {
            "mode": "unavailable", "currency": "INR", "travelers": travelers,
            "budget_inr_group": None, "breakdown": {}, "complete": False,
            "budget_status": "budget not provided",
            "notice": "Enter a budget to see a suggested allocation. Allocations are planning guidance, not live prices or verified costs.",
        }
    try:
        budget = Decimal(str(budget_inr))
    except InvalidOperation as exc:
        raise ValueError("Budget must be a valid INR amount.") from exc
    if budget < 0:
        raise ValueError("Budget cannot be negative.")
    route_scope = route_scope if route_scope in _ALLOCATION_PROFILES else "unknown"
    profile = _ALLOCATION_PROFILES[route_scope]
    if sum(percent for percent, _label in profile.values()) != 100:
        raise ValueError("Budget allocation percentages must sum to 100.")

    # Round to whole rupees and assign rounding remainder to miscellaneous so
    # category allocations always add up exactly to the submitted group budget.
    rounded_budget = budget.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    breakdown: dict[str, dict[str, Any]] = {}
    allocated = Decimal("0")
    profile_items = list(profile.items())
    for category, (percentage, label) in profile_items[:-1]:
        amount = (rounded_budget * Decimal(percentage) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        allocated += amount
        breakdown[category] = {
            "label": label,
            "amount_inr_group": float(amount),
            "amount_inr_per_person": float((amount / travelers).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "allocation_percent": percentage,
            "status": "Suggested allocation, not a quoted price",
        }
    category, (percentage, label) = profile_items[-1]
    remainder = rounded_budget - allocated
    breakdown[category] = {
        "label": label,
        "amount_inr_group": float(remainder),
        "amount_inr_per_person": float((remainder / travelers).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "allocation_percent": percentage,
        "status": "Suggested allocation, not a quoted price",
    }
    return {
        "mode": "budget_allocation", "currency": "INR", "travelers": travelers, "route_scope": route_scope,
        "budget_inr_group": float(rounded_budget), "breakdown": breakdown,
        "allocated_total_inr_group": float(sum(Decimal(str(row["amount_inr_group"])) for row in breakdown.values())),
        "complete": True, "budget_status": "allocation only; actual cost and affordability unverified",
        "notice": _allocation_notice(route_scope),
    }


def _allocation_notice(route_scope: str) -> str:
    base = "Suggested split of your entered budget, not live prices or provider quotes. This does not confirm affordability; verify fares and lodging before booking."
    if route_scope == "domestic":
        return base + " International flights and visa costs are excluded for this domestic route. Travel insurance is optional and excluded."
    if route_scope == "international":
        return base + " Visa/entry fees depend on traveler nationality and are excluded; travel insurance is optional and excluded."
    return base + " Route countries could not be confirmed, so no international-flight or visa category is assumed. Travel insurance is optional and excluded."

def calculate_trip_cost(quotes: dict[str, Any], travelers: int, budget_inr: Any = None,
                        contingency_rate: Any = Decimal("0.10")) -> dict[str, Any]:
    """Calculate per-person and group totals without filling missing prices."""
    if travelers < 1:
        raise ValueError("Travelers must be at least one.")
    rate = Decimal(str(contingency_rate))
    if rate < 0 or rate > 1:
        raise ValueError("Contingency rate must be between 0 and 1.")
    breakdown = {}
    known = Decimal("0")
    missing = []
    for category in CATEGORIES:
        raw = quotes.get(category)
        if raw in (None, ""):
            breakdown[category] = {"amount_inr_per_person": None, "status": "Price unavailable"}
            missing.append(category)
            continue
        try:
            amount = Decimal(str(raw))
        except InvalidOperation as exc:
            raise ValueError(f"Invalid INR quote for {category}.") from exc
        if amount < 0:
            raise ValueError(f"Quote for {category} cannot be negative.")
        breakdown[category] = {"amount_inr_per_person": float(amount), "status": "User-provided quote"}
        known += amount
    contingency = (known * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    per_person = known + contingency
    group_total = per_person * travelers
    budget = Decimal(str(budget_inr)) if budget_inr not in (None, "") else None
    if budget is not None and budget < 0:
        raise ValueError("Budget cannot be negative.")
    complete = not missing
    if budget is None:
        feasibility = "budget not provided"
    elif not complete:
        feasibility = "cannot determine: add quotes for all categories"
    else:
        feasibility = "within budget" if group_total <= budget else "over budget"
    return {
        "currency": "INR", "travelers": travelers, "breakdown": breakdown,
        "known_subtotal_inr_per_person": float(known),
        "contingency_rate": float(rate), "contingency_inr_per_person": float(contingency),
        "estimated_total_inr_per_person": float(per_person) if complete else None,
        "estimated_total_inr_group": float(group_total) if complete else None,
        "known_cost_with_contingency_inr_per_person": float(per_person),
        "missing_categories": missing, "complete": complete,
        "budget_inr_group": float(budget) if budget is not None else None,
        "budget_status": feasibility,
        "notice": "Totals include only user-provided quotes and a 10% contingency; missing prices are not estimated or treated as zero.",
    }
