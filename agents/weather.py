"""Weather agent backed by Open-Meteo public forecast data."""

import logging
from typing import Any

from graph.state import TravelPlanState
from tools.weather import WeatherForecastTool
from .base import BaseAgent

logger = logging.getLogger(__name__)


class WeatherAgent(BaseAgent):
    """Retrieves only forecast values returned for supported travel dates."""

    name = "weather"

    def __init__(self, tool: WeatherForecastTool | None = None) -> None:
        self.tool = tool or WeatherForecastTool()

    def run(self, state: TravelPlanState) -> dict[str, Any]:
        request = state["request"]
        logger.info("Retrieving forecast for %s", request.get("destination"))
        result = self.tool.invoke(
            destination=request.get("destination", ""),
            start_date=request.get("start_date", ""),
            end_date=request.get("end_date", ""),
        )
        return {"agent_results": {self.name: result}}
