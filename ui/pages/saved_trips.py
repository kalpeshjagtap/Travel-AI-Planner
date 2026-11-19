import streamlit as st
from ui.services import run_graph,thread
from ui.components import results

def render():
    st.subheader("Saved trips")
    if st.button("Refresh saved trips"):
        try:
            state=run_graph({"file_action":"list_trips","agent_requests":["file"]},"List my saved trips.","saved_trips_thread_id")
            st.session_state["saved_trip_ids"]=state.get("agent_results",{}).get("file",{}).get("trip_ids",[])
        except Exception as exc: st.error(f"Could not list saved trips: {exc}")
    ids=st.session_state.get("saved_trip_ids",[])
    if not ids: st.info("Select refresh to list local JSON trip records."); return
    selected=st.selectbox("Trip record",ids)
    c1,c2=st.columns(2)
    if c1.button("Load trip"):
        try:
            state=run_graph({"file_action":"load_trip","file_trip_id":selected,"agent_requests":["file"]},f"Load saved trip {selected}.","saved_trips_thread_id")
            trip=state.get("agent_results",{}).get("file",{}).get("trip",{})
            st.session_state["loaded_trip"]=trip
            st.success("Trip loaded.")
            if trip.get("itinerary"): st.markdown(trip["itinerary"].get("plan_text",""))
            results({**state,"request":trip.get("request",{}),"itinerary":trip.get("itinerary",{}),"agent_results":trip.get("agent_results",{})})
        except Exception as exc: st.error(f"Could not load trip: {exc}")
    if c2.button("Delete trip",type="secondary"):
        try:
            state=run_graph({"file_action":"delete_trip","file_trip_id":selected,"agent_requests":["file"]},f"Delete saved trip {selected}.","saved_trips_thread_id")
            st.session_state["saved_trip_ids"]=[item for item in ids if item != selected]
            st.success("Trip record deleted." if state.get("agent_results",{}).get("file",{}).get("deleted") else "Trip record was already missing.")
        except Exception as exc: st.error(f"Could not delete trip: {exc}")
