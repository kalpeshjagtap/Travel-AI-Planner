"""Itinerary agent that creates date-indexed drafts with the local LLM."""

import json
import logging
from datetime import date
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from graph.state import TravelPlanState
from services.ollama_service import OllamaService, get_ollama_service
from services.travel_data import find_travel_attractions
from services.cost_planner import allocate_trip_budget
from services.trip_scope import classify_route_scope
from services.journey_planner import build_journey, validate_journey
from .base import BaseAgent

logger = logging.getLogger(__name__)
ITINERARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Create a concise day-wise itinerary for the exact destination in the trip request. "
            "The destination is the only city/region whose activities belong in this itinerary. "
            "Do not use the origin as a destination or mention origin-city sightseeing. "
            "Only name a landmark, attraction, restaurant, beach, or neighborhood if that exact place appears in supplied attraction research. "
            "Otherwise suggest general activity types without inventing names or claiming they are nearby. "
            "Do not invent expenses, fares, hotel rates, visa costs, or currency conversions. Only repeat amounts explicitly supplied by the user or providers. "
            "Use the traveler's stated total budget, category allocation, travel style, interests, traveler count and duration as planning constraints. "
            "The category allocation is a planning split of the user's budget, not market-price evidence; do not repeat it as a provider quote or guarantee that actual costs fit. "
            "When a budget is provided, prioritize low-cost choices and explain practical trade-offs, but do not claim the plan fits the budget unless all major trip costs are supported by verified/user-provided quotes. "
            "Clearly mark activities as suggestions. Never claim bookings, live opening hours, flight schedules, "
            "hotel availability, or prices unless a supplied source explicitly states them. Do not invent weather. "
            "If research is absent, provide general activity ideas and state that details need traveler verification. "
            "Use the exact supplied trip dates and keep each day labeled. The destination field is the city/region to plan for; origin is only the departure point. Never substitute origin for destination.",
        ),
        ("human", "Trip request:\n{request}\n\nAvailable research:\n{research}"),
    ]
)


class ItineraryAgent(BaseAgent):
    """Builds one clearly labeled itinerary draft for the request dates."""

    name = "itinerary"

    def __init__(self, ollama: OllamaService | None = None) -> None:
        self.ollama = ollama or get_ollama_service()

    def run(self, state: TravelPlanState) -> dict[str, Any]:
        request = state["request"]
        destination = request.get("destination", "")
        if not destination:
            raise ValueError("A destination is required to draft an itinerary.")
        if request.get("itinerary_override"):
            itinerary = dict(state.get("itinerary", {}))
            itinerary.update({
                "destination": destination,
                "plan_text": request["itinerary_override"].strip(),
                "status": "edited draft",
            })
            return {"itinerary": itinerary, "agent_results": {self.name: itinerary}}
        start = request.get("start_date")
        end = request.get("end_date")
        dates: list[str] = []
        if start and end:
            start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
            if end_day < start_day:
                raise ValueError("Trip end date must not precede start date.")
            if (end_day - start_day).days > 30:
                raise ValueError("Itinerary drafts are limited to trips of 31 days or fewer.")
            dates = [date.fromordinal(day).isoformat() for day in range(start_day.toordinal(), end_day.toordinal() + 1)]

        research = dict(state.get("agent_results", {}))
        if "itinerary" in research:
            research.pop("itinerary", None)
        attractions = find_travel_attractions(destination, limit=5)
        research["attractions"] = attractions
        route_scope, route_countries = classify_route_scope(request) if request.get("budget") not in (None, "") else ("unknown", {})
        budget = allocate_trip_budget(request.get("budget"), int(request.get("travelers", 1)), route_scope=route_scope)
        if route_countries:
            budget["route_countries"] = route_countries
        if budget.get("mode") == "budget_allocation":
            research["budget_allocation"] = budget
        logger.info("Drafting itinerary for %s across %s days", destination, len(dates) or "unspecified")
        draft = (
            ITINERARY_PROMPT | self.ollama.get_chat_model() | StrOutputParser()
        ).invoke(
            {
                # Deliberately omit origin: small local models otherwise anchor
                # itinerary activities to the departure city instead of destination.
                "request": json.dumps({key: request.get(key) for key in ("origin", "destination", "start_date", "end_date", "travelers", "budget", "currency", "preferences", "preferred_regions", "travel_style", "accommodation_preference", "transport_preference", "interests") if request.get(key) is not None}, ensure_ascii=False),
                "research": json.dumps(_compact_research(research), ensure_ascii=False, default=str),
            }
        )
        itinerary = {
            "destination": destination,
            "start_date": start,
            "end_date": end,
            "dates": dates,
            "day_count": len(dates),
            "plan_text": draft.strip(),
            "status": "draft",
            "disclaimer": "AI-generated suggestions; verify details with the cited sources and local providers.",
            "source_agents": list(research.keys()),
        }
        journey = build_journey(request)
        nights=max(0,(date.fromisoformat(end)-date.fromisoformat(start)).days) if start and end else 0
        journey["validation_issues"]=validate_journey(journey,nights)
        return {"itinerary": itinerary, "agent_results": {self.name: itinerary, "attractions": attractions, "budget": budget, "journey": journey}}


def _compact_research(value: Any) -> Any:
    """Trim provider records before they reach a small local model."""
    if isinstance(value, dict):
        useful = ("available", "source", "data_type", "days", "listings", "attractions", "budget_allocation", "breakdown", "amount_inr_group", "amount_inr_per_person", "allocation_percent", "name", "category", "latitude", "longitude", "note", "reason")
        return {key: _compact_research(item) for key, item in value.items() if key in useful}
    if isinstance(value, list):
        return [_compact_research(item) for item in value[:5]]
    if isinstance(value, str):
        return value[:1200]
    return value
