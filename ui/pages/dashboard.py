import streamlit as st
from config.settings import get_settings
from services.file_service import FileService

def render():
    provider=get_settings().ai_provider.casefold()
    runtime="local Ollama" if provider == "ollama" else "Google Gemini API"
    st.markdown(f'<div class="hero"><h2>Plan a better trip with AI</h2><p>Research, organize and save travel plans in one workspace · {runtime}.</p></div>', unsafe_allow_html=True)
    trips=FileService().list_trips()
    a,b,c=st.columns(3)
    a.metric("Saved trips",len(trips)); b.metric("AI runtime","Ollama · local" if provider == "ollama" else "Gemini · API"); c.metric("Travel data","Source labeled")
    st.markdown("### Start planning")
    st.write("Create a day-wise itinerary, find free place records, view a weather forecast and keep your documents nearby.")
    if trips:
        st.markdown("#### Recently saved")
        for trip in trips[-5:]: st.code(trip, language=None)
