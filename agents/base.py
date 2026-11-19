"""Common typed contract for LangGraph travel agents."""

from abc import ABC, abstractmethod
from typing import Any

from graph.state import TravelPlanState


class BaseAgent(ABC):
    """Base class for agents that return partial shared-state updates."""

    name: str

    @abstractmethod
    def run(self, state: TravelPlanState) -> dict[str, Any]:
        """Run this specialist and return a serializable result update."""
