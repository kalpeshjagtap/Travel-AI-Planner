"""Typed, reducer-aware shared state for the travel-planning graph."""

from operator import add
from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


def merge_dicts(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    """Merge independent parallel worker updates by key."""
    return {**(left or {}), **(right or {})}


class TripRequest(TypedDict, total=False):
    """Normalized trip request and explicit user action flags."""

    origin: str
    destination: str
    start_date: str
    end_date: str
    travelers: int
    budget: float
    cost_quotes: dict[str, Any]
    preferred_regions: list[str]
    travel_style: str
    accommodation_preference: str
    transport_preference: str
    interests: list[str]
    currency: str
    preferences: list[str]
    agent_requests: list[str]
    create_itinerary: bool
    chat_mode: bool
    itinerary_override: str
    use_current_location: bool
    current_location: dict[str, Any]
    location_consent: bool
    document_question: str
    file_action: str
    file_action_payload: dict[str, Any]
    file_trip_id: str
    file_source_id: str
    filename: str
    file_content: str
    overwrite_file: bool
    document_search: str
    uploaded_files: list[dict[str, Any]]
    email_requested: bool
    gmail_action: str
    gmail_query: str
    gmail_draft_id: str
    email_recipient: str
    email_confirmation: bool
    email_subject: str


class TravelPlanState(TypedDict):
    """State passed between supervisor and specialist agent nodes."""

    trip_id: str
    request: TripRequest
    user_request: str
    messages: Annotated[list[AnyMessage], add_messages]
    agent_status: Annotated[dict[str, str], merge_dicts]
    agent_results: Annotated[dict[str, dict[str, Any]], merge_dicts]
    errors: Annotated[list[str], add]
    notices: Annotated[list[str], add]
    selected_agents: NotRequired[list[str]]
    current_agent: NotRequired[str]
    itinerary: NotRequired[dict[str, Any]]
    final_response: NotRequired[dict[str, Any]]
    thread_id: NotRequired[str]
    user_approved: NotRequired[bool]
