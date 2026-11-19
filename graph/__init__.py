"""LangGraph workflow package.

Keep workflow imports lazy: agent modules depend on ``graph.state``, so loading
the whole workflow during package initialization creates an agent/state cycle.
"""

from typing import Any


def build_travel_graph(*args: Any, **kwargs: Any):
    """Build the application graph after state and agent modules are loaded."""
    from .workflow import build_travel_graph as _build_travel_graph

    return _build_travel_graph(*args, **kwargs)


__all__ = ["build_travel_graph"]
