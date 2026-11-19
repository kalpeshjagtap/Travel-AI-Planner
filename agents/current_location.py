"""Current location agent that requires an explicit browser permission grant."""

import logging
from typing import Any

from graph.state import TravelPlanState
from tools.location import LocationTool
from .base import BaseAgent

logger = logging.getLogger(__name__)


class CurrentLocationAgent(BaseAgent):
    """Accepts browser coordinates only after consent and browser approval."""

    name = "current_location"

    def __init__(self, tool: LocationTool | None = None) -> None:
        self.tool = tool or LocationTool()

    def run(self, state: TravelPlanState) -> dict[str, Any]:
        request = state["request"]
        if not request.get("location_consent"):
            raise PermissionError("Current location was not accessed without explicit user consent.")
        browser_location = request.get("current_location", {})
        if not browser_location:
            return {
                "agent_results": {
                    self.name: {
                        "available": False,
                        "message": "Select the browser location button and allow the browser permission prompt.",
                    }
                }
            }
        result = self.tool.invoke(
            permission_granted=True,
            latitude=browser_location.get("latitude"),
            longitude=browser_location.get("longitude"),
            accuracy=browser_location.get("accuracy"),
        )
        logger.info("Accepted permitted browser location for trip %s", state["trip_id"])
        return {"agent_results": {self.name: {"available": True, **result}}}
