"""Itinerary email drafting and explicitly confirmed Gmail delivery."""

import logging
from typing import Any

from graph.state import TravelPlanState
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from services.ollama_service import OllamaService, get_ollama_service
from services.mcp_client import MCPToolRegistry
from .base import BaseAgent

logger = logging.getLogger(__name__)
EMAIL_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "Write a concise email containing the supplied draft itinerary. Do not add facts, prices, bookings, or availability."),
        ("human", "Destination: {destination}\nItinerary draft:\n{itinerary}"),
    ]
)


class EmailAgent(BaseAgent):
    """Creates Gmail drafts and sends only after explicit user confirmation."""

    name = "email"

    def __init__(self, ollama: OllamaService | None = None, mcp: MCPToolRegistry | None = None) -> None:
        self.ollama = ollama or get_ollama_service()
        self.mcp = mcp or MCPToolRegistry()

    def run(self, state: TravelPlanState) -> dict[str, Any]:
        request = state["request"]
        action = str(request.get("gmail_action", "create_draft")).strip().lower()
        if action == "authorize":
            result = self.mcp.call_tool("gmail", "authorize_gmail", {})
            return {"agent_results": {self.name: {"status": "authorized", **result}}}
        if action == "read_relevant":
            result = self.mcp.call_tool("gmail", "list_relevant_emails", {
                "query": request.get("gmail_query", ""),
                "max_results": int(request.get("gmail_max_results", 10)),
            })
            return {"agent_results": {self.name: {"status": "emails_read", **result}}}
        if action == "send_existing_draft":
            if not request.get("email_confirmation"):
                raise PermissionError("Sending denied: explicit user confirmation is required.")
            draft_id = request.get("gmail_draft_id", "")
            try:
                result = self.mcp.call_tool("gmail", "send_gmail_draft", {
                    "draft_id": draft_id, "user_confirmation": True,
                })
                return {"agent_results": {self.name: {**result, "draft_id": draft_id, "sent": True}}}
            except Exception as exc:
                logger.warning("Sending existing Gmail draft %s was blocked", draft_id, exc_info=True)
                return {"agent_results": {self.name: {
                    "draft_id": draft_id, "sent": False, "status": "send_blocked",
                    "message": _send_failure_message(exc),
                }}}
        if action not in {"create_draft", "send_new_draft"}:
            raise ValueError("gmail_action must be authorize, read_relevant, create_draft, send_new_draft, or send_existing_draft.")
        itinerary = state.get("itinerary") or state.get("agent_results", {}).get("itinerary", {})
        if not itinerary:
            raise ValueError("Create an itinerary before preparing its email.")
        body = (
            EMAIL_PROMPT | self.ollama.get_chat_model() | StrOutputParser()
        ).invoke(
            {
                "destination": itinerary.get("destination", request.get("destination", "your trip")),
                "itinerary": itinerary.get("plan_text", ""),
            }
        ).strip()
        subject = request.get("email_subject") or f"Travel itinerary: {itinerary.get('destination', 'your trip')}"
        recipient = request.get("email_recipient", "").strip()
        confirmation = bool(request.get("email_confirmation")) and action == "send_new_draft"
        result: dict[str, Any] = {
            "subject": subject,
            "body": body,
            "recipient": recipient,
            "sent": False,
            "status": "draft",
        }
        draft = self.mcp.call_tool("gmail", "create_gmail_draft", {
            "recipient": recipient, "subject": subject, "body": body,
        })
        result.update(draft)
        result["status"] = "draft_created"
        result["sent"] = False
        if confirmation:
            if not recipient:
                raise ValueError("A recipient email address is required after confirming send.")
            try:
                sent = self.mcp.call_tool("gmail", "send_gmail_draft", {
                    "draft_id": draft["draft_id"], "user_confirmation": True,
                })
                result.update(sent)
                result.update({"sent": True, "status": "sent"})
                logger.info("Confirmed Gmail draft sent for trip %s", state["trip_id"])
            except Exception as exc:
                logger.warning("New Gmail draft %s could not be sent", draft["draft_id"], exc_info=True)
                result.update({
                    "sent": False, "status": "send_blocked",
                    "message": "The itinerary draft was created in Gmail, but sending was blocked. " + _send_failure_message(exc),
                })
        else:
            result["message"] = "Gmail draft created. No email was sent; explicit user confirmation is required."
        return {"agent_results": {self.name: result}}


def _send_failure_message(exc: Exception) -> str:
    message = str(exc)
    if "local daily safety cap reached" in message.casefold():
        return "The local Gmail daily safety limit has been reached. No send request was sent to Google. Keep this draft and retry it after the local quota resets; do not create another draft."
    return f"The draft was not sent: {message}"
