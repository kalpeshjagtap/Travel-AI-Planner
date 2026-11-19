"""RAG agent interface to the local Chroma/Ollama document QA pipeline."""

import logging
from dataclasses import asdict
from typing import Any

from graph.state import TravelPlanState
from rag.qa import TravelRAGService
from .base import BaseAgent

logger = logging.getLogger(__name__)


class RAGAgent(BaseAgent):
    """Retrieves and answers from indexed traveler documents."""

    name = "rag"

    def __init__(self, service: TravelRAGService | None = None) -> None:
        self.service = service or TravelRAGService()

    def run(self, state: TravelPlanState) -> dict[str, Any]:
        question = state["request"].get("document_question", "").strip()
        if not question:
            raise ValueError("A document question is required for RAG retrieval.")
        logger.info("Retrieving uploaded-document context for trip %s", state["trip_id"])
        result = self.service.ask(question)
        payload = asdict(result)
        return {"agent_results": {self.name: payload}}
