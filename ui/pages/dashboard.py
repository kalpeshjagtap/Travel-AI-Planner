import streamlit as st
from services.file_service import FileService

def render():
    st.markdown('<div class="hero"><h2>Plan a better trip, with local AI</h2><p>Research, organize and save travel plans in one private workspace.</p></div>', unsafe_allow_html=True)
    trips=FileService().list_trips()
    a,b,c=st.columns(3)
    a.metric("Saved trips",len(trips)); b.metric("AI runtime","Ollama · local"); c.metric("Travel data","Source labeled")
    st.markdown("### Start planning")
    st.write("Create a day-wise itinerary, find free place records, view a weather forecast and keep your documents nearby.")
    if trips:
        st.markdown("#### Recently saved")
        for trip in trips[-5:]: st.code(trip, language=None)
