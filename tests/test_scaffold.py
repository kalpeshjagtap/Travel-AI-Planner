"""Smoke checks for the initial project scaffold."""

from graph.workflow import build_travel_graph


def test_graph_can_be_built() -> None:
    """The initial graph compiles before agent integrations are added."""
    assert build_travel_graph() is not None
