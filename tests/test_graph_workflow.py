"""Offline checks for fan-out, checkpoint persistence, context, and termination."""

from pathlib import Path
from threading import Barrier, BrokenBarrierError, Lock
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import HumanMessage

from graph.checkpointing import JSONFileCheckpointer
from graph.workflow import build_travel_graph


class FakeSupervisor:
    name = "supervisor"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        selected = (
            ["flight", "hotel", "weather", "current_location", "rag", "itinerary", "file", "email"]
            if "complete" in state["user_request"]
            else ["weather"]
        )
        return {"selected_agents": selected, "agent_status": {self.name: "completed"}}


class FakeAgent:
    def __init__(self, name: str, barrier: Barrier | None = None, calls: list[str] | None = None, lock: Any = None):
        self.name = name
        self.barrier = barrier
        self.calls = calls if calls is not None else []
        self.lock = lock or Lock()

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.barrier and "complete" in state["user_request"]:
            try:
                self.barrier.wait(timeout=4)
            except BrokenBarrierError as exc:
                raise AssertionError("Independent research workers did not run concurrently.") from exc
        with self.lock:
            self.calls.append(self.name)
        value = {"agent": self.name, "trip_id": state["trip_id"]}
        if self.name == "itinerary":
            value["plan_text"] = "Day 1: traveler-selected activities."
            return {"itinerary": value, "agent_results": {self.name: value}}
        return {"agent_results": {self.name: value}}


def _graph(directory: str, research: dict[str, FakeAgent], itinerary: FakeAgent, file: FakeAgent, email: FakeAgent):
    return build_travel_graph(
        supervisor=FakeSupervisor(),
        research_agents=research,
        itinerary_agent=itinerary,
        file_agent=file,
        email_agent=email,
        rag_service=SimpleNamespace(vector_store=object()),
        checkpointer=JSONFileCheckpointer(directory),
    )


def _state(text: str, thread_id: str) -> dict[str, Any]:
    return {
        "trip_id": "trip-checkpoint",
        "thread_id": thread_id,
        "request": {"destination": "Reykjavik"},
        "user_request": text,
        "messages": [HumanMessage(content=text)],
        "agent_status": {},
        "agent_results": {},
        "errors": [],
        "notices": [],
    }


def test_parallel_agents_unify_and_checkpoint_thread_context() -> None:
    with TemporaryDirectory(prefix="travel-checkpoint-") as directory:
        barrier = Barrier(5)
        calls: list[str] = []
        lock = Lock()
        research = {
            name: FakeAgent(name, barrier=barrier, calls=calls, lock=lock)
            for name in ("flight", "hotel", "weather", "current_location", "rag")
        }
        itinerary = FakeAgent("itinerary", calls=calls, lock=lock)
        file_agent = FakeAgent("file", calls=calls, lock=lock)
        email_agent = FakeAgent("email", calls=calls, lock=lock)
        graph = _graph(directory, research, itinerary, file_agent, email_agent)
        config = {"configurable": {"thread_id": "conversation-1"}}

        first = graph.invoke(_state("complete trip request", "conversation-1"), config=config)
        assert set(first["agent_results"]) == {
            "flight", "hotel", "weather", "current_location", "rag", "itinerary", "file", "email"
        }
        assert "Day 1" in first["final_response"]["text"]
        assert first["agent_status"]["finalizer"] == "completed"
        assert len(calls) == 8

        second = graph.invoke(_state("follow-up weather request", "conversation-1"), config=config)
        assert set(second["agent_results"]) == {"weather"}
        assert len(second["messages"]) == 4
        assert "itinerary" not in second["agent_status"]

        snapshot = graph.get_state(config)
        assert snapshot.values["final_response"]["text"] == second["final_response"]["text"]
        checkpoint_files = list(Path(directory).rglob("*.json"))
        assert checkpoint_files


def test_agent_failure_is_recorded_and_graph_still_terminates() -> None:
    with TemporaryDirectory(prefix="travel-checkpoint-error-") as directory:
        calls = []

        class FailingHotel:
            name = "hotel"

            def run(self, state: dict[str, Any]) -> dict[str, Any]:
                calls.append("hotel")
                raise ConnectionError("temporary accommodation provider timeout")

        class HotelSupervisor:
            name = "supervisor"

            def run(self, state: dict[str, Any]) -> dict[str, Any]:
                return {"selected_agents": ["hotel"], "agent_status": {self.name: "completed"}}

        graph = build_travel_graph(
            supervisor=HotelSupervisor(),
            research_agents={"hotel": FailingHotel()},
            itinerary_agent=FakeAgent("itinerary"),
            file_agent=FakeAgent("file"),
            email_agent=FakeAgent("email"),
            rag_service=SimpleNamespace(vector_store=object()),
            checkpointer=JSONFileCheckpointer(directory),
        )
        result = graph.invoke(_state("hotel request", "conversation-error"), config={"configurable": {"thread_id": "conversation-error"}})
        assert calls == ["hotel", "hotel"]
        assert result["agent_status"]["hotel"] == "error"
        assert result["final_response"]["errors"]
        assert result["messages"][-1].type == "ai"
