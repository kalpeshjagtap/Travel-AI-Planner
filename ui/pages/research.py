"""Focused view of flight, accommodation, and weather research results."""
import streamlit as st
from ui.components import results
from services.file_service import FileService


def render() -> None:
    st.subheader("Flights, stays & weather")
    st.caption("Source-backed travel research from your most recent trip plan.")
    state = st.session_state.get("last_trip_state", {})
    agent_results = state.get("agent_results", {}) if state else {}
    if not any(key in agent_results for key in ("flight", "hotel", "weather", "attractions")):
        files = FileService()
        saved_ids = files.list_trips()
        if not saved_ids:
            st.info("No research results are available yet. Build a plan in Trip planner and choose Save trip locally to keep results here.")
            return
        chosen = st.selectbox("Load research from a saved trip", saved_ids, key="research_saved_trip")
        if st.button("Load saved research"):
            try:
                state = files.load_trip(chosen)
                st.session_state["last_trip_state"] = state
                agent_results = state.get("agent_results", {})
            except Exception as exc:
                st.error(f"Could not load saved trip research: {exc}")
                return
        else:
            return
    request = state.get("request", {})
    destination = request.get("destination", "your destination")
    origin = request.get("origin", "")
    st.markdown(f"#### {origin + ' → ' if origin else ''}{destination}")
    st.caption(f"{request.get('start_date', '')} to {request.get('end_date', '')}")
    # Reuse the common source-aware renderers while omitting itinerary/RAG/chat panels.
    display_state = {
        **state,
        "itinerary": {},
        "agent_results": {key: value for key, value in agent_results.items() if key in {"flight", "hotel", "weather", "attractions", "current_location"}},
    }
    results(display_state)
