"""Flight agent: provide a real provider search URL, never fabricated fares."""

import logging
from typing import Any

from graph.state import TravelPlanState
from tools.flights import FlightSearchTool
from .base import BaseAgent

logger = logging.getLogger(__name__)


class FlightAgent(BaseAgent):
    """Creates a flight search link for the requested route and dates."""

    name = "flight"

    def __init__(self, tool: FlightSearchTool | None = None) -> None:
        self.tool = tool or FlightSearchTool()

    def run(self, state: TravelPlanState) -> dict[str, Any]:
        request = state["request"]
        logger.info("Creating flight search link for trip %s", state["trip_id"])
        result = self.tool.invoke(
            origin=request.get("origin", ""),
            destination=request.get("destination", ""),
            start_date=request.get("start_date", ""),
            end_date=request.get("end_date", ""),
        )
        return {"agent_results": {self.name: result}}
