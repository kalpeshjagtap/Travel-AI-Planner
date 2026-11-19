"""Local conversational travel assistant used by the Streamlit chat page."""

import json
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from graph.state import TravelPlanState
from services.ollama_service import OllamaService, get_ollama_service
from .base import BaseAgent


CHAT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Answer concisely using supplied trip facts only. Never invent prices, availability, schedules, or weather. Label suggestions. Ask one brief follow-up if needed."),
    ("human", "Recent turns: {conversation}\nRequest: {request}\nRelevant trip data: {research}"),
])


class ChatAgent(BaseAgent):
    """Answers free-form travel questions using only the local Ollama model."""

    name = "chat"

    def __init__(self, ollama: OllamaService | None = None) -> None:
        self.ollama = ollama or get_ollama_service()

    def run(self, state: TravelPlanState) -> dict[str, Any]:
        messages = state.get("messages", [])[-4:]
        conversation = "\n".join(
            f"{getattr(message, 'type', 'message')}: {str(getattr(message, 'content', message))}"
            for message in messages
        )
        answer = (CHAT_PROMPT | self.ollama.get_chat_model() | StrOutputParser()).invoke({
            "conversation": conversation,
            "request": state.get("user_request", ""),
            "research": json.dumps({key: _compact(value) for key, value in state.get("agent_results", {}).items()}, ensure_ascii=False, default=str),
        }).strip()
        return {"agent_results": {self.name: {"answer": answer, "data_type": "local AI response"}}}


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        keys = ("answer", "plan_text", "days", "destination", "source", "url", "data_type", "listings")
        return {k: _compact(v) for k, v in value.items() if k in keys}
    if isinstance(value, list):
        return [_compact(x) for x in value[:5]]
    if isinstance(value, str):
        return value[:1800]
    return value
