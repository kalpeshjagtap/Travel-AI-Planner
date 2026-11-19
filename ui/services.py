"""Cached application services shared by Streamlit pages."""
import uuid
import streamlit as st
from rag import TravelRAGService
from services.trip_service import TripService
from services.ollama_service import get_ollama_service

@st.cache_resource
def rag_service() -> TravelRAGService:
    return TravelRAGService()

@st.cache_resource
def trip_service() -> TripService:
    return TripService(rag_service=rag_service())

@st.cache_resource
def ollama_service():
    return get_ollama_service()

def thread(key: str) -> str:
    if key not in st.session_state:
        st.session_state[key] = str(uuid.uuid4())
    return st.session_state[key]

def run_graph(request: dict, prompt: str, key: str = "travel_thread_id") -> dict:
    with st.spinner("Your local travel agents are working…"):
        state = trip_service().plan_trip(None, request, user_request=prompt, thread_id=thread(key))
    st.session_state["last_trip_state"] = state
    return state
