"""Supervisor-routed, parallel LangGraph travel workflow."""

from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Overwrite, Send

from agents.current_location import CurrentLocationAgent
from agents.chat import ChatAgent
from agents.email import EmailAgent
from agents.file import FileAgent
from agents.flight import FlightAgent
from agents.hotel import HotelAgent
from agents.itinerary import ItineraryAgent
from agents.rag import RAGAgent
from agents.supervisor import SupervisorAgent
from agents.weather import WeatherAgent
from graph.nodes import make_agent_node
from graph.state import TravelPlanState
from graph.checkpointing import JSONFileCheckpointer, create_checkpointer
from rag.qa import TravelRAGService
from rag.vector_store import TravelVectorStore


def _send_state(node: str, state: TravelPlanState, agent_name: str | None = None) -> Send:
    """Copy state for a dynamically scheduled agent task."""
    payload: dict[str, Any] = dict(state)
    if agent_name:
        payload["current_agent"] = agent_name
    return Send(node, payload)


def _initial_routes(state: TravelPlanState) -> list[Send] | str:
    selected = set(state.get("selected_agents", []))
    parallel_research = selected - {"itinerary", "file", "email", "chat"}
    if parallel_research:
        return [_send_state("research_worker", state, name) for name in sorted(parallel_research)]
    if "itinerary" in selected:
        return [_send_state("itinerary_worker", state)]
    if "chat" in selected:
        return [_send_state("chat_worker", state)]
    post_agents = selected & {"file", "email"}
    if post_agents:
        return [_send_state("post_worker", state, name) for name in sorted(post_agents)]
    return "finalize"


def _routes_after_research(state: TravelPlanState) -> list[Send] | str:
    selected = set(state.get("selected_agents", []))
    if "itinerary" in selected:
        return [_send_state("itinerary_worker", state)]
    if "chat" in selected:
        return [_send_state("chat_worker", state)]
    post_agents = selected & {"file", "email"}
    if post_agents:
        return [_send_state("post_worker", state, name) for name in sorted(post_agents)]
    return "finalize"


def _routes_after_itinerary(state: TravelPlanState) -> list[Send] | str:
    if "chat" in set(state.get("selected_agents", [])):
        return [_send_state("chat_worker", state)]
    post_agents = set(state.get("selected_agents", [])) & {"file", "email"}
    if not post_agents:
        return "finalize"
    return [_send_state("post_worker", state, name) for name in sorted(post_agents)]


def _routes_after_chat(state: TravelPlanState) -> list[Send] | str:
    post_agents = set(state.get("selected_agents", [])) & {"file", "email"}
    if post_agents:
        return [_send_state("post_worker", state, name) for name in sorted(post_agents)]
    return "finalize"


def build_travel_graph(
    *,
    supervisor: SupervisorAgent | None = None,
    research_agents: dict[str, Any] | None = None,
    itinerary_agent: ItineraryAgent | None = None,
    file_agent: FileAgent | None = None,
    email_agent: EmailAgent | None = None,
    rag_service: TravelRAGService | None = None,
    checkpointer: JSONFileCheckpointer | None = None,
):
    """Compile the multi-agent workflow.

    Independent research agents are dynamically fanned out with LangGraph
    ``Send`` and merged through typed-state reducers. Itinerary generation
    waits for those workers; persistence and email run afterward when selected.
    """
    supervisor_agent = supervisor or SupervisorAgent()
    shared_rag = rag_service or TravelRAGService()
    shared_store = shared_rag.vector_store
    research = research_agents or {
        "flight": FlightAgent(),
        "hotel": HotelAgent(),
        "weather": WeatherAgent(),
        "current_location": CurrentLocationAgent(),
        "rag": RAGAgent(service=shared_rag),
    }
    plan_agent = itinerary_agent or ItineraryAgent()
    persistence_agent = file_agent or FileAgent(vector_store=shared_store)
    mail_agent = email_agent or EmailAgent()
    chat_agent = ChatAgent()

    graph = StateGraph(TravelPlanState)

    def begin_run(state: TravelPlanState) -> dict[str, Any]:
        """Clear per-run results while retaining checkpointer conversation messages."""
        action = state.get("request", {})
        preserve = bool(state.get("itinerary") and (action.get("email_requested") or action.get("file_action") in {"save_plan", "save_trip", "update_trip"} or action.get("itinerary_override")))
        preserved_itinerary = state.get("itinerary", {}) if preserve else {}
        return {
            "agent_status": Overwrite({}),
            "agent_results": Overwrite({"itinerary": preserved_itinerary} if preserved_itinerary else {}),
            "errors": Overwrite([]),
            "notices": Overwrite([]),
            "selected_agents": [],
            "current_agent": "",
            "itinerary": preserved_itinerary,
            "final_response": {},
        }

    graph.add_node("begin_run", begin_run)
    graph.add_node("supervisor", make_agent_node(supervisor_agent))

    def research_dispatch(state: TravelPlanState) -> dict[str, Any]:
        name = state.get("current_agent", "")
        agent = research.get(name)
        if agent is None:
            return {
                "agent_results": {name: {"available": False, "error": f"Unknown research agent: {name}"}},
                "agent_status": {name: "error"},
                "errors": [f"Unknown research agent: {name}"],
            }
        return make_agent_node(agent, name)(state)

    graph.add_node("research_worker", research_dispatch)
    graph.add_node("itinerary_worker", make_agent_node(plan_agent, "itinerary"))
    graph.add_node("chat_worker", make_agent_node(chat_agent, "chat"))

    def post_dispatch(state: TravelPlanState) -> dict[str, Any]:
        name = state.get("current_agent", "")
        agent = {"file": persistence_agent, "email": mail_agent}.get(name)
        if agent is None:
            return {
                "agent_results": {name: {"available": False, "error": f"Unknown post-processing agent: {name}"}},
                "agent_status": {name: "error"},
                "errors": [f"Unknown post-processing agent: {name}"],
            }
        return make_agent_node(agent, name)(state)

    graph.add_node("post_worker", post_dispatch)
    graph.add_node("after_research", lambda _state: {})
    graph.add_node("after_itinerary", lambda _state: {})
    graph.add_node("after_chat", lambda _state: {})

    def finalize(state: TravelPlanState) -> dict[str, Any]:
        """Assemble all successful results and errors into one assistant response."""
        results = state.get("agent_results", {})
        sections: list[str] = []
        itinerary = state.get("itinerary") or results.get("itinerary", {})
        if itinerary.get("plan_text"):
            sections.append("Itinerary draft\n" + itinerary["plan_text"])
        flight = results.get("flight", {})
        if flight.get("url"):
            sections.append(f"Flight search: {flight['url']} (search link only; confirm prices and availability with the provider).")
        hotel = results.get("hotel", {})
        if hotel:
            hotel_names = [item.get("name") for item in hotel.get("listings", []) if item.get("name")]
            if hotel_names:
                sections.append("Accommodation records: " + ", ".join(hotel_names))
            sections.append(hotel.get("note", "Accommodation prices and availability are not confirmed."))
            if hotel.get("booking_search_link"):
                sections.append("Hotel search: " + hotel["booking_search_link"])
        attractions = results.get("attractions", {})
        if attractions:
            names = [item.get("name") for item in attractions.get("attractions", []) if item.get("name")]
            if names:
                sections.append("Attraction records: " + ", ".join(names))
            if attractions.get("search_link"):
                sections.append("Attraction discovery: " + attractions["search_link"])
            if attractions.get("note"):
                sections.append(attractions["note"])
        weather = results.get("weather", {})
        if weather:
            if weather.get("available"):
                sections.append(
                    f"Weather: {len(weather.get('days', []))} forecast day(s) from {weather.get('source', 'the forecast provider')}."
                )
            else:
                sections.append("Weather: " + weather.get("reason", "No forecast was returned."))
        rag = results.get("rag", {})
        if rag.get("answer"):
            sections.append("Uploaded documents\n" + rag["answer"])
        file_result = results.get("file", {})
        if file_result:
            sections.append("File operation: " + str(file_result.get("action", "completed")))
        email = results.get("email", {})
        if email:
            sections.append("Itinerary email: " + str(email.get("status", "draft")))
        sections.extend(state.get("notices", []))
        sections.extend(state.get("errors", []))
        response_text = "\n\n".join(sections) or "No travel agents were run for this request."
        response = {
            "text": response_text,
            "agent_results": results,
            "agent_status": state.get("agent_status", {}),
            "errors": state.get("errors", []),
            "notices": state.get("notices", []),
        }
        return {
            "final_response": response,
            "messages": [AIMessage(content=response_text)],
            "agent_status": {"finalizer": "completed"},
        }

    graph.add_node("finalize", finalize)

    graph.add_edge(START, "begin_run")
    graph.add_edge("begin_run", "supervisor")
    graph.add_conditional_edges("supervisor", _initial_routes)
    graph.add_edge("research_worker", "after_research")
    graph.add_conditional_edges("after_research", _routes_after_research)
    graph.add_edge("itinerary_worker", "after_itinerary")
    graph.add_conditional_edges("after_itinerary", _routes_after_itinerary)
    graph.add_edge("post_worker", "finalize")
    graph.add_edge("chat_worker", "after_chat")
    graph.add_conditional_edges("after_chat", _routes_after_chat)
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer or create_checkpointer())
