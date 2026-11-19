from decimal import Decimal

import pytest

from services.cost_planner import CATEGORIES, allocate_trip_budget, calculate_trip_cost


def test_complete_user_quotes_calculate_per_person_group_and_contingency():
    quotes = {category: 1000 for category in CATEGORIES}
    result = calculate_trip_cost(quotes, travelers=2, budget_inr=22000)
    assert result["complete"] is True
    assert result["known_subtotal_inr_per_person"] == 10000
    assert result["contingency_inr_per_person"] == 1000
    assert result["estimated_total_inr_per_person"] == 11000
    assert result["estimated_total_inr_group"] == 22000
    assert result["budget_status"] == "within budget"


def test_missing_prices_are_unavailable_and_do_not_become_zero_or_false_budget_pass():
    result = calculate_trip_cost({"international_return_flights": 18000}, 1, budget_inr=20000)
    assert result["complete"] is False
    assert result["estimated_total_inr_group"] is None
    assert result["breakdown"]["accommodation"]["status"] == "Price unavailable"
    assert result["budget_status"].startswith("cannot determine")


def test_empty_budget_is_not_zero():
    result = calculate_trip_cost({}, travelers=1, budget_inr=None)
    assert result["budget_inr_group"] is None
    assert result["budget_status"] == "budget not provided"


def test_budget_allocation_covers_all_categories_and_exactly_matches_group_budget():
    result = allocate_trip_budget(100001, travelers=3, route_scope="international")
    assert result["mode"] == "budget_allocation"
    assert "international_return_flights" in result["breakdown"]
    assert sum(row["amount_inr_group"] for row in result["breakdown"].values()) == 100001
    assert result["allocated_total_inr_group"] == 100001
    assert all("not a quoted price" in row["status"] for row in result["breakdown"].values())
    assert "visa" not in result["breakdown"]
    assert "insurance" not in result["breakdown"]


def test_domestic_allocation_has_no_international_flight_or_visa_categories():
    result = allocate_trip_budget(40000, travelers=2, route_scope="domestic")
    assert "domestic_return_travel" in result["breakdown"]
    assert "international_return_flights" not in result["breakdown"]
    assert "visa" not in result["breakdown"]
    assert "insurance" not in result["breakdown"]
    assert "excluded" in result["notice"]
    assert result["allocated_total_inr_group"] == 40000


def test_missing_budget_returns_no_fake_allocation():
    result = allocate_trip_budget(None, travelers=1)
    assert result["mode"] == "unavailable"
    assert result["breakdown"] == {}


def test_negative_quotes_are_rejected():
    with pytest.raises(ValueError):
        calculate_trip_cost({"food": -1}, 1)
