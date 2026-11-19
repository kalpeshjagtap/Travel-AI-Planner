import streamlit as st
from config.settings import get_settings
from ui.services import run_graph, thread

def render():
    st.subheader("AI travel chat")
    provider=get_settings().ai_provider.casefold()
    st.caption(("Answers are generated locally with Ollama." if provider == "ollama" else "Answers use Google Gemini through its API.") + " Live facts appear only when returned by a connected source.")
    context=st.session_state.get("last_trip_state",{})
    request=context.get("request",{})
    with st.expander("Optional trip context", expanded=False):
        destination=st.text_input("Destination context",value=request.get("destination", ""),key="chat_destination")
        start=st.text_input("Start date (YYYY-MM-DD)",value=request.get("start_date", ""),key="chat_start")
        end=st.text_input("End date (YYYY-MM-DD)",value=request.get("end_date", ""),key="chat_end")
    for message in st.session_state.get("chat_history",[]):
        with st.chat_message(message["role"]): st.markdown(message["content"])
    prompt=st.chat_input("Ask for ideas, help or trip organization")
    if prompt:
        st.session_state.setdefault("chat_history",[]).append({"role":"user","content":prompt})
        try:
            state=run_graph({"chat_mode":True,"agent_requests":["chat"],"destination":destination,"start_date":start,"end_date":end},prompt,"chat_thread_id")
            answer=state.get("agent_results",{}).get("chat",{}).get("answer") or ("I could not generate an answer. Check that Ollama is running." if provider == "ollama" else "I could not generate an answer. Check your Gemini API key and quota.")
            st.session_state["chat_history"].append({"role":"assistant","content":answer})
            with st.chat_message("assistant"): st.markdown(answer)
            for e in state.get("errors",[]): st.error(e)
        except Exception as exc: st.error(f"Chat could not complete: {exc}")
