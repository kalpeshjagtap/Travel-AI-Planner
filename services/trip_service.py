"""Application service for invoking the LangGraph travel workflow."""

import logging
import uuid
from typing import Any

from langchain_core.messages import HumanMessage

from graph.workflow import build_travel_graph
from rag.qa import TravelRAGService

logger = logging.getLogger(__name__)


class TripService:
    """Runs and resumes travel planning graph requests."""

    def __init__(self, graph: Any | None = None, rag_service: TravelRAGService | None = None) -> None:
        self.graph = graph or build_travel_graph(rag_service=rag_service)

    def plan_trip(
        self,
        trip_id: str | None,
        request: dict[str, Any],
        *,
        user_request: str = "",
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Invoke the graph and continue the selected filesystem-checkpointed thread."""
        conversation_id = thread_id or trip_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": conversation_id}}
        previous_values: dict[str, Any] = {}
        try:
            previous_values = self.graph.get_state(config).values
        except Exception:
            logger.debug("No prior checkpoint found for thread %s", conversation_id, exc_info=True)

        previous_request = previous_values.get("request", {})
        transient_defaults = {
            "agent_requests": [],
            "create_itinerary": False,
            "chat_mode": False,
            "itinerary_override": "",
            "use_current_location": False,
            "location_consent": False,
            "document_question": "",
            "file_action": "",
            "file_action_payload": {},
            "uploaded_files": [],
            "email_requested": False,
            "email_confirmation": False,
            "gmail_action": "",
            "gmail_query": "",
            "gmail_draft_id": "",
        }
        merged_request = {**previous_request, **transient_defaults, **request}
        previous_trip_id = previous_values.get("trip_id")
        previous_destination = previous_request.get("destination")
        current_destination = merged_request.get("destination")
        identifier = trip_id or (
            previous_trip_id
            if previous_trip_id and previous_destination == current_destination
            else str(uuid.uuid4())
        )
        prompt_text = user_request.strip() or "Plan a trip using the structured travel request."
        initial_state = {
            "trip_id": identifier,
            "thread_id": conversation_id,
            "request": merged_request,
            "user_request": prompt_text,
            "messages": [HumanMessage(content=prompt_text)],
            "agent_status": {},
            "agent_results": {},
            "errors": [],
            "notices": [],
        }
        logger.info("Starting travel plan workflow %s on thread %s", identifier, conversation_id)
        try:
            result = self.graph.invoke(initial_state, config=config)
        except Exception as exc:
            # A stale/orphaned checkpoint id can survive an interrupted local run.
            # Start a clean persistent conversation thread once and report its id.
            if "checkpoint" not in str(exc).casefold() or "does not exist" not in str(exc).casefold():
                raise
            logger.warning("Checkpoint thread %s is inconsistent; starting a fresh thread", conversation_id)
            saver = getattr(self.graph, "checkpointer", None)
            if saver is not None and hasattr(saver, "delete_thread"):
                saver.delete_thread(conversation_id)
            conversation_id = str(uuid.uuid4())
            config = {"configurable": {"thread_id": conversation_id}}
            initial_state["thread_id"] = conversation_id
            result = self.graph.invoke(initial_state, config=config)
        result["thread_id"] = conversation_id
        logger.info("Travel plan workflow %s finished with agents %s", identifier, result.get("agent_status", {}))
        return result

    def run_email_action(
        self,
        previous_state: dict[str, Any],
        *,
        recipient: str,
        confirmed: bool,
        existing_draft_id: str = "",
    ) -> dict[str, Any]:
        """Create a draft or send only after an explicit confirmation value."""
        state = dict(previous_state)
        request = dict(state.get("request", {}))
        request.update(
            {
                "email_requested": True,
                "email_recipient": recipient,
                "email_confirmation": bool(confirmed),
                "gmail_action": ("send_existing_draft" if existing_draft_id else "send_new_draft") if confirmed else "create_draft",
                "gmail_draft_id": existing_draft_id,
                "agent_requests": ["email"],
                "create_itinerary": False,
            }
        )
        state.update(
            {
                "request": request,
                "user_request": "Prepare the itinerary email. Send only if the user explicitly confirmed.",
                "messages": [HumanMessage(content="Prepare the itinerary email. Send only if I confirmed it.")],
                "agent_status": {},
                "errors": [],
                "notices": [],
                "selected_agents": [],
            }
        )
        thread_id = str(state.get("thread_id") or state.get("trip_id"))
        config = {"configurable": {"thread_id": thread_id}}
        logger.info("Running itinerary email action for trip %s (confirmed=%s)", state.get("trip_id"), confirmed)
        return self.graph.invoke(state, config=config)
