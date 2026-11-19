"""Modular Streamlit interface for the AI Travel Planner."""
import logging
import streamlit as st
from config.settings import get_settings
from ui.components import apply_theme
from ui.pages import chat,dashboard,documents,gmail,planner,research,saved_trips

def main():
    settings=get_settings()
    st.set_page_config(page_title=settings.app_name,page_icon="✈️",layout="wide",initial_sidebar_state="expanded")
    logging.basicConfig(level=settings.log_level)
    apply_theme()
    with st.sidebar:
        st.title("✈️ Atlas")
        st.caption("Your private travel workspace")
        page=st.radio("Workspace",["Home","AI chat","Trip planner","Flights, stays & weather","Documents & RAG","Gmail","Saved trips"],label_visibility="collapsed")
        st.divider()
        st.caption("AI runs with local Ollama. Travel information is labeled by source.")
    st.title(settings.app_name)
    st.caption("Plan thoughtfully with local AI and source-backed travel information.")
    if page=="Home": dashboard.render()
    elif page=="AI chat": chat.render()
    elif page=="Trip planner": planner.render()
    elif page=="Flights, stays & weather": research.render()
    elif page=="Documents & RAG": documents.render()
    elif page=="Gmail": gmail.render()
    else: saved_trips.render()

if __name__=="__main__": main()
