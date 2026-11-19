"""Hotel agent backed by free OpenStreetMap accommodation records."""

import logging
from typing import Any

from graph.state import TravelPlanState
from tools.hotels import HotelSearchTool
from .base import BaseAgent

logger = logging.getLogger(__name__)


class HotelAgent(BaseAgent):
    """Finds named accommodation records without claiming availability."""

    name = "hotel"

    def __init__(self, tool: HotelSearchTool | None = None) -> None:
        self.tool = tool or HotelSearchTool()

    def run(self, state: TravelPlanState) -> dict[str, Any]:
        destination = state["request"].get("destination", "")
        logger.info("Searching public accommodation records for %s", destination)
        result = self.tool.invoke(destination=destination)
        return {"agent_results": {self.name: result}}
