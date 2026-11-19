import streamlit as st
from ui.services import run_graph,rag_service
from ui.components import results

def render():
    st.subheader("Travel documents & RAG")
    st.caption("Documents and vectors stay in the local project data directory.")
    files=st.file_uploader("Upload PDF, DOCX, TXT, CSV or Markdown",type=["pdf","docx","txt","csv","md","markdown"],accept_multiple_files=True)
    if st.button("Store and index documents",type="primary",disabled=not files):
        payload=[{"filename":f.name,"content":f.getvalue()} for f in files]
        try:
            state=run_graph({"file_action":"ingest_uploads","uploaded_files":payload,"agent_requests":["file"]},"Index my uploaded travel documents.","documents_thread_id")
            st.session_state["documents_result"]=state
            for item in state.get("agent_results",{}).get("file",{}).get("files",[]):
                if item.get("indexed"): st.success(f"Indexed {item.get('filename')} ({item.get('chunks')} chunks)")
                else: st.error(f"{item.get('filename')}: {item.get('error','indexing failed')}")
        except Exception as exc: st.error(f"Document indexing failed: {exc}")
    try:
        sources=rag_service().vector_store.list_sources()
        st.markdown("#### Indexed sources")
        if sources: st.dataframe(sources,use_container_width=True,hide_index=True)
        else: st.info("No indexed documents yet.")
    except Exception as exc: st.warning(f"Could not load indexed sources: {exc}")
    with st.form("rag_question"):
        question=st.text_input("Ask about your uploaded documents",placeholder="What is the cancellation policy?")
        ask=st.form_submit_button("Ask documents")
    if ask and question.strip():
        try:
            state=run_graph({"document_question":question.strip(),"agent_requests":["rag"]},question,"documents_thread_id")
            results(state,map_view=False)
        except Exception as exc: st.error(f"Document question failed: {exc}")
