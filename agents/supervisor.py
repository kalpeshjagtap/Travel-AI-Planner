"""LLM-assisted, prerequisite-aware agent selection."""

import json
import logging
import re
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from graph.state import TravelPlanState
from services.ollama_service import OllamaService, get_ollama_service
from .base import BaseAgent

logger = logging.getLogger(__name__)
AVAILABLE_AGENTS = ("flight", "hotel", "weather", "current_location", "itinerary", "rag", "file", "email", "chat")
ROUTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Choose specialist agent names as a compact JSON array only: flight, hotel, weather, current_location, itinerary, rag, file, email, chat. "
            "Select only agents the user actually needs. Do not include file unless they ask to save, "
            "load, or list documents/trips. Do not include email unless they ask for an email. "
            "Do not include current_location unless they ask to use their device location.",
        ),
        ("human", "Recent conversation:\n{conversation}\n\nCurrent request: {user_request}\nStructured request: {request_summary}"),
    ]
)


class SupervisorAgent(BaseAgent):
    """Uses local llama3.2:1b to route requests, with deterministic safety gates."""

    name = "supervisor"

    def __init__(self, ollama: OllamaService | None = None) -> None:
        self.ollama = ollama or get_ollama_service()

    def run(self, state: TravelPlanState) -> dict[str, Any]:
        request = state.get("request", {}) or {}
        user_request = str(state.get("user_request", "") or "")
        # Structured form actions already specify the eligible specialists. Avoid spending
        # a generation call on deterministic UI requests and do not send transcript history.
        explicit_requests = set(request.get("agent_requests") or [])
        if explicit_requests or request.get("file_action") or request.get("gmail_action"):
            requested = explicit_requests | self._flag_requests(request)
            if request.get("gmail_action") or request.get("email_requested"):
                requested.add("email")
            return self._select_agents(requested, request, state)
        conversation = ""
        model_selection: set[str] = set()
        if user_request.strip():
            try:
                response = (
                    ROUTER_PROMPT | self.ollama.get_chat_model() | StrOutputParser()
                ).invoke(
                    {
                        "user_request": user_request,
                        "request_summary": json.dumps(request, ensure_ascii=False, default=str),
                        "conversation": conversation,
                    }
                )
                parsed = json.loads(response.strip())
                if isinstance(parsed, dict):
                    parsed = parsed.get("agents", [])
                if isinstance(parsed, list):
                    model_selection = {str(item).strip().lower() for item in parsed}
            except Exception as exc:
                logger.warning("Supervisor model routing failed; using request flags: %s", exc)

        requested = model_selection & explicit_requests if explicit_requests else set(model_selection)
        if user_request.strip() and not model_selection and not explicit_requests:
            requested.update(self._keyword_fallback(user_request))
        requested.update(explicit_requests)
        requested.update(self._flag_requests(request))
        if state.get("itinerary") and request.get("email_requested") and not request.get("create_itinerary"):
            requested.discard("itinerary")
        requested = {name for name in requested if name in AVAILABLE_AGENTS}

        if request.get("email_requested") or request.get("gmail_action"):
            requested.add("email")
            if not state.get("itinerary") and request.get("gmail_action", "create_draft") in {"create_draft", "send_new_draft"}:
                requested.add("itinerary")
        return self._select_agents(requested, request, state)

    def _select_agents(self, requested: set[str], request: dict[str, Any], state: TravelPlanState) -> dict[str, Any]:
        requested = {name for name in requested if name in AVAILABLE_AGENTS}
        eligible: list[str] = []
        notices: list[str] = []
        for name in AVAILABLE_AGENTS:
            if name not in requested:
                continue
            if self._eligible(name, request):
                eligible.append(name)
            else:
                notice = self._missing_requirements(name, request)
                if notice:
                    notices.append(notice)
        if requested and not eligible and not notices:
            notices.append("No agent could run because required trip details or permissions were missing.")
        elif not requested:
            notices.append("No agent was selected. Choose a planning action or ask a travel question.")
        logger.info("Supervisor selected agents: %s", eligible or "none")
        return {
            "selected_agents": eligible,
            "agent_status": {self.name: "completed"},
            "notices": notices,
        }

    @staticmethod
    def _flag_requests(request: dict[str, Any]) -> set[str]:
        flags = set()
        if request.get("create_itinerary"):
            flags.add("itinerary")
        if request.get("use_current_location"):
            flags.add("current_location")
        if request.get("document_question"):
            flags.add("rag")
        if request.get("file_action"):
            flags.add("file")
        if request.get("chat_mode"):
            flags.add("chat")
        return flags

    @staticmethod
    def _conversation_text(messages: list[Any], *, limit: int = 8) -> str:
        """Format a short recent transcript for local supervisor routing."""
        lines = []
        for message in messages[-limit:]:
            role = getattr(message, "type", message.__class__.__name__).replace("_", " ")
            content = getattr(message, "content", str(message))
            if isinstance(content, list):
                content = " ".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)
            lines.append(f"{role}: {content}")
        return "\n".join(lines) or "No prior conversation."

    @staticmethod
    def _keyword_fallback(user_request: str) -> set[str]:
        """Keep basic routing available if local model output is malformed."""
        text = re.sub(r"\s+", " ", user_request.lower())
        selected = set()
        if re.search(r"\b(flight|flights|fly|airfare)\b", text):
            selected.add("flight")
        if re.search(r"\b(hotel|hotels|accommodation|lodging)\b", text):
            selected.add("hotel")
        if re.search(r"\b(weather|forecast)\b", text):
            selected.add("weather")
        if re.search(r"\b(itinerary|plan (a |my )?(trip|vacation)|travel plan)\b", text):
            selected.add("itinerary")
        if re.search(r"\b(current location|my location|device location)\b", text):
            selected.add("current_location")
        if re.search(r"\b(uploaded documents?|travel documents?)\b", text) and "?" in text:
            selected.add("rag")
        if re.search(r"\b(email|email me|send the itinerary)\b", text):
            selected.add("email")
        return selected

    @staticmethod
    def _eligible(name: str, request: dict[str, Any]) -> bool:
        if name == "flight":
            return all(request.get(field) for field in ("origin", "destination", "start_date", "end_date"))
        if name == "hotel":
            return bool(request.get("destination"))
        if name == "weather":
            return all(request.get(field) for field in ("destination", "start_date", "end_date"))
        if name == "current_location":
            return bool(request.get("use_current_location") and request.get("location_consent"))
        if name == "itinerary":
            return all(request.get(field) for field in ("destination", "start_date", "end_date"))
        if name == "rag":
            return bool(request.get("document_question"))
        if name == "file":
            return bool(request.get("file_action"))
        if name == "email":
            action = request.get("gmail_action", "create_draft")
            if action in {"authorize", "read_relevant"}:
                return action == "authorize" or bool(request.get("gmail_query"))
            if action == "send_existing_draft":
                return bool(request.get("gmail_draft_id"))
            return bool(request.get("email_requested")) and bool(request.get("destination") or request.get("email_recipient"))
        if name == "chat":
            return bool(request.get("chat_mode"))
        return False

    @staticmethod
    def _missing_requirements(name: str, request: dict[str, Any]) -> str:
        if name == "flight":
            missing = [field for field in ("origin", "destination", "start_date", "end_date") if not request.get(field)]
            return "Flight search skipped; provide " + ", ".join(missing) + "."
        if name == "weather":
            missing = [field for field in ("destination", "start_date", "end_date") if not request.get(field)]
            return "Weather lookup skipped; provide " + ", ".join(missing) + "."
        if name == "hotel" and not request.get("destination"):
            return "Accommodation search skipped; provide a destination."
        if name == "current_location" and not request.get("location_consent"):
            return "Current location was not accessed because explicit permission was not granted."
        if name == "itinerary" and not request.get("destination"):
            return "Itinerary skipped; provide a destination."
        if name == "itinerary" and not (request.get("start_date") and request.get("end_date")):
            return "Itinerary skipped; provide the trip start and end dates."
        if name == "rag" and not request.get("document_question"):
            return "Document retrieval skipped; provide a question about uploaded documents."
        if name == "email" and not (request.get("destination") or request.get("email_recipient")):
            return "Email draft skipped; provide an itinerary destination or recipient."
        return ""
