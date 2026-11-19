import streamlit as st
from ui.services import run_graph,thread,trip_service
from ui.components import results
from services.file_service import FileService

def render():
    st.subheader("Gmail center")
    st.caption("Official Gmail API OAuth. Drafts are safe by default; sending requires your explicit confirmation.")
    if st.button("Connect Gmail with Google OAuth"):
        try:
            state=run_graph({"gmail_action":"authorize","agent_requests":["email"]},"Authorize Gmail access.","gmail_thread_id"); results(state,map_view=False)
        except Exception as exc: st.error(f"Gmail authorization failed: {exc}")
    with st.form("gmail_search"):
        query=st.text_input("Search mail",placeholder="from:airline.example subject:booking")
        read=st.form_submit_button("Read matching email summaries")
    if read:
        try:
            state=run_graph({"gmail_action":"read_relevant","gmail_query":query,"agent_requests":["email"]},f"Read Gmail matching {query}","gmail_thread_id"); results(state,map_view=False)
        except Exception as exc: st.error(f"Could not read Gmail: {exc}")
    plan=st.session_state.get("last_trip_state",{})
    if not plan.get("itinerary"):
        saved_ids=FileService().list_trips()
        if saved_ids:
            st.markdown("#### Choose a saved trip")
            saved_id=st.selectbox("Saved itinerary",saved_ids,key="gmail_saved_trip")
            if st.button("Use saved trip for email"):
                try:
                    saved_trip=FileService().load_trip(saved_id)
                    plan={**saved_trip,"trip_id":saved_id,"thread_id":st.session_state.get("travel_thread_id",saved_id)}
                    st.session_state["gmail_email_plan"]=plan
                except Exception as exc: st.error(f"Could not load saved trip: {exc}")
    if not plan.get("itinerary"):
        plan=st.session_state.get("gmail_email_plan",{})
    if plan.get("itinerary"):
        st.markdown("#### Email a trip itinerary")
        with st.form("itinerary_email"):
            recipient=st.text_input("Recipient"); confirm=st.checkbox("I explicitly confirm sending this itinerary to the recipient above.")
            submit=st.form_submit_button("Create draft" if not confirm else "Send confirmed email")
        if submit:
            try:
                state=trip_service().run_email_action(plan,recipient=recipient,confirmed=confirm)
                st.session_state["last_trip_state"]=state; results(state,map_view=False)
                email=state.get("agent_results",{}).get("email",{})
                if email.get("status")=="send_blocked" and email.get("draft_id"):
                    st.session_state["gmail_pending_draft"]={"draft_id":email["draft_id"],"recipient":email.get("recipient",recipient),"subject":email.get("subject","")}
                elif email.get("sent"):
                    st.session_state.pop("gmail_pending_draft",None)
            except Exception as exc: st.error(f"Could not prepare itinerary email: {exc}")
    pending=st.session_state.get("gmail_pending_draft")
    if pending:
        st.warning("An unsent itinerary draft is saved in Gmail. Retry this same draft later to avoid creating duplicates.")
        st.caption(f"Draft ID: {pending['draft_id']} · Recipient: {pending.get('recipient','not shown')}")
        with st.form("retry_existing_gmail_draft"):
            retry_confirm=st.checkbox("I explicitly confirm sending this existing draft to its saved recipient.")
            retry=st.form_submit_button("Send existing draft")
        if retry:
            if not retry_confirm:
                st.error("Check the confirmation box before sending.")
            else:
                try:
                    state=trip_service().run_email_action(plan,recipient=pending.get("recipient",""),confirmed=True,existing_draft_id=pending["draft_id"])
                    st.session_state["last_trip_state"]=state
                    email=state.get("agent_results",{}).get("email",{})
                    results(state,map_view=False)
                    if email.get("sent"):
                        st.session_state.pop("gmail_pending_draft",None)
                    elif email.get("draft_id"):
                        st.session_state["gmail_pending_draft"]=pending
                except Exception as exc:
                    st.error(f"Could not send the existing draft: {exc}")
    if not plan.get("itinerary"):
        st.info("Create an itinerary in Trip Planner before preparing an itinerary email.")
