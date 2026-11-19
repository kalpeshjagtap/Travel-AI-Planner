"""LangGraph node factories and failure isolation."""

import logging
import time
from typing import Any, Callable

import httpx

from graph.state import TravelPlanState
from services.mcp_client import MCPToolError

logger = logging.getLogger(__name__)


def make_agent_node(agent: Any, agent_name: str | None = None) -> Callable[[TravelPlanState], dict[str, Any]]:
    """Adapt an agent to a graph node and turn failures into state results."""
    name = agent_name or agent.name

    def node(state: TravelPlanState) -> dict[str, Any]:
        max_attempts = 2 if name in {"flight", "hotel", "weather", "itinerary", "rag", "supervisor"} else 1
        for attempt in range(1, max_attempts + 1):
            try:
                update = agent.run(state)
                return {**update, "agent_status": {name: "completed"}}
            except Exception as exc:
                if attempt < max_attempts and _is_transient(exc):
                    delay = 0.25 * (2 ** (attempt - 1))
                    logger.warning(
                        "Retrying agent %s after transient failure (attempt %d/%d): %s",
                        name,
                        attempt,
                        max_attempts,
                        exc,
                    )
                    time.sleep(delay)
                    continue
                logger.exception("Agent %s failed for trip %s", name, state.get("trip_id", "unknown"))
                message = f"{name.replace('_', ' ').title()} agent failed after {attempt} attempt(s): {exc}"
                return {
                    "agent_results": {name: {"available": False, "error": message}},
                    "agent_status": {name: "error"},
                    "errors": [message],
                }
        raise RuntimeError(f"Agent {name} exhausted its retry policy without a result.")

    return node


def _is_transient(error: Exception) -> bool:
    """Restrict retries to transport and temporary service failures."""
    if isinstance(error, (httpx.TimeoutException, httpx.NetworkError, MCPToolError, TimeoutError, ConnectionError)):
        return True
    message = str(error).casefold()
    return any(term in message for term in ("timed out", "connection refused", "temporarily unavailable", "502", "503", "504"))
