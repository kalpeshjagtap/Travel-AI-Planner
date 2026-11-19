from datetime import date,timedelta
import streamlit as st
from ui.components import results
from ui.services import run_graph,thread,trip_service,rag_service
from services.trip_service import TripService
from streamlit_geolocation import streamlit_geolocation
from services.file_service import FileService
from services.cost_planner import allocate_trip_budget
from services.trip_scope import classify_route_scope
from services.visa_information_service import official_entry_information_link
from services.transport_planner import compare_transfer_options

def render():
    st.subheader("Trip planner")
    preferences=FileService().load_preferences()
    consent=st.checkbox("Allow this browser to share its location for this trip",key="planner_location_consent")
    location={}
    if consent:
        result=streamlit_geolocation()
        if isinstance(result,dict) and result.get("latitude") is not None:
            location={"latitude":result["latitude"],"longitude":result["longitude"],"accuracy":result.get("accuracy")}
    with st.form("trip_form"):
        x,y=st.columns(2); origin=x.text_input("Origin city"); destination=y.text_input("Destination country or city",placeholder="Thailand or Kyoto, Japan")
        x,y=st.columns(2); arrival_airport=x.text_input("Preferred arrival airport/city (optional)"); departure_airport=y.text_input("Preferred return airport/city (optional)")
        x,y=st.columns(2); start=x.date_input("Departure",date.today()); end=y.date_input("Return",date.today()+timedelta(days=3))
        travelers=st.number_input("Travelers",1,20,int(preferences.get("travelers",1)))
        preferences_text=st.text_input("Travel preferences",value=", ".join(preferences.get("preferences",[])))
        budget_text=st.text_input("Total budget in INR (optional)",placeholder="Leave empty if undecided")
        regions_text=st.text_input("Preferred regions or cities",placeholder="e.g. North and South Thailand")
        style=st.selectbox("Travel style",["Not specified","Budget","Standard","Comfortable"])
        stay_style=st.selectbox("Accommodation preference",["Not specified","Hostel","Budget hotel","Mid-range hotel","Comfortable hotel"])
        transport_style=st.selectbox("Preferred transportation",["Not specified","Lowest cost","Balanced","Fastest"])
        interests_text=st.text_input("Interests",placeholder="beaches, culture, food, nature")
        x,y,z=st.columns(3); flights=x.checkbox("Flight search link",True); hotels=y.checkbox("Stay discovery",True); weather=z.checkbox("Weather",True)
        itinerary=st.checkbox("Create day-wise itinerary",True)
        question=st.text_input("Optional question about your uploaded documents")
        submitted=st.form_submit_button("Build my travel plan",type="primary")
    if submitted:
        if end<start: st.error("Return date must be on or after departure."); return
        agents=[name for name,enabled in [("flight",flights),("hotel",hotels),("weather",weather)] if enabled]
        if itinerary: agents.append("itinerary")
        if question.strip(): agents.append("rag")
        if consent and location: agents.append("current_location")
        try:
            budget=float(budget_text) if budget_text.strip() else None
        except ValueError:
            st.error("Enter a valid numeric INR budget."); return
        req={"origin":origin.strip(),"destination":destination.strip(),"arrival_airport":arrival_airport.strip(),"departure_airport":departure_airport.strip(),"start_date":start.isoformat(),"end_date":end.isoformat(),"travelers":int(travelers),"budget":budget,"preferred_regions":[p.strip() for p in regions_text.split(",") if p.strip()],"travel_style":style,"accommodation_preference":stay_style,"transport_preference":transport_style,"interests":[p.strip() for p in interests_text.split(",") if p.strip()],"preferences":[p.strip() for p in preferences_text.split(",") if p.strip()],"agent_requests":agents,"create_itinerary":itinerary,"document_question":question.strip(),"use_current_location":bool(consent and location),"location_consent":consent,"current_location":location}
        try:
            FileService().save_preferences({"travelers":int(travelers),"preferences":[p.strip() for p in preferences_text.split(",") if p.strip()],"travel_style":style,"accommodation_preference":stay_style,"transport_preference":transport_style,"interests":[p.strip() for p in interests_text.split(",") if p.strip()]})
            state=run_graph(req,f"Plan a trip from {origin} to {destination} from {start} through {end}.")
            if state.get("trip_id"): st.session_state["active_trip_id"]=state["trip_id"]
            results(state)
            _render_cost(state)
            _render_journey(state)
        except Exception as exc: st.error(f"Travel plan could not be completed: {exc}")
    state=st.session_state.get("last_trip_state")
    if state:
        _render_cost(state)
        _render_journey(state)
    itinerary=state.get("itinerary") if state else None
    if state and itinerary:
        st.divider(); st.markdown("### Edit or refresh itinerary")
        with st.form("edit_itinerary"):
            edited=st.text_area("Itinerary draft",itinerary.get("plan_text",""),height=300)
            save=st.form_submit_button("Save itinerary edits")
        c1,c2=st.columns(2)
        if save:
            try:
                edited_state=trip_service().plan_trip(None,{**state.get("request",{}),"itinerary_override":edited,"create_itinerary":True,"agent_requests":["itinerary"]},user_request="Save my edited itinerary.",thread_id=thread("travel_thread_id"))
                st.session_state["last_trip_state"]=edited_state; st.success("Edits saved."); results(edited_state)
            except Exception as exc: st.error(f"Could not save the edit: {exc}")
        if c1.button("Regenerate itinerary",type="secondary"):
            try:
                req={**state.get("request",{}),"itinerary_override":"","create_itinerary":True,"agent_requests":["itinerary"]}
                updated=trip_service().plan_trip(None,req,user_request="Regenerate the itinerary.",thread_id=thread("travel_thread_id"))
                st.session_state["last_trip_state"]=updated; results(updated)
            except Exception as exc: st.error(f"Could not regenerate itinerary: {exc}")
        if c2.button("Save trip locally",key="planner_save_trip"):
            try:
                snapshot={"trip_id":state.get("trip_id"),"request":state.get("request",{}),"itinerary":state.get("itinerary",{}),"agent_results":state.get("agent_results",{})}
                saved=trip_service().plan_trip(state.get("trip_id"),{**state.get("request",{}),"file_action":"save_plan","file_action_payload":snapshot,"agent_requests":["file"]},user_request="Save this trip.",thread_id=thread("travel_thread_id"))
                st.session_state["last_trip_state"]=saved; st.success("Trip saved as a local JSON record.")
            except Exception as exc: st.error(f"Could not save trip: {exc}")

def _render_cost(state):
    plan=state.get("agent_results",{}).get("budget")
    request=state.get("request",{})
    if not plan or plan.get("mode") != "budget_allocation":
        try:
            route_scope, _route_info = classify_route_scope(request) if request.get("budget") not in (None, "") else ("unknown", {})
            plan=allocate_trip_budget(request.get("budget"),int(request.get("travelers",1)),route_scope=route_scope)
        except Exception: return
    st.markdown("### Suggested trip expense allocation")
    st.caption(plan["notice"])
    if plan.get("mode") != "budget_allocation":
        st.info("Enter a total budget in the trip form to get a suggested expense allocation.")
        return
    rows=[{"Expense category":value.get("label",key.replace("_"," ").title()),"Suggested allocation (group)":f"₹{value['amount_inr_group']:,.0f}","Approx. per traveler":f"₹{value['amount_inr_per_person']:,.0f}","Share":f"{value['allocation_percent']}%"} for key,value in plan["breakdown"].items()]
    st.dataframe(rows,use_container_width=True,hide_index=True)
    st.metric("Allocated trip budget",f"₹{plan['allocated_total_inr_group']:,.0f}")

def _render_journey(state):
    journey=state.get("agent_results",{}).get("journey")
    if not isinstance(journey,dict): return
    st.markdown("### Complete journey and accommodation")
    st.caption(" ".join(str(journey.get(key, "")) for key in ("price_status", "route_comparison", "currency_status") if journey.get(key)))
    raw_days=journey.get("itinerary",[])
    days=raw_days if isinstance(raw_days,list) else []
    if not days:
        st.info("No day-wise journey details are available. Rebuild the trip to generate them.")
    for index,raw_day in enumerate(days, start=1):
        # Older saved trips may contain plain text or partial day objects. Normalize
        # at the UI boundary so one legacy record cannot crash the whole page.
        day=raw_day if isinstance(raw_day,dict) else {"notes":str(raw_day)}
        stay=day.get("accommodation")
        stay=stay if isinstance(stay,dict) else {}
        place=day.get("city_or_region") or day.get("city") or stay.get("area") or "Travel day"
        day_date=day.get("date") or f"Day {index}"
        with st.expander(f"{day_date} · {place}"):
            for label,key in (("Morning","morning"),("Afternoon","afternoon"),("Evening","evening"),("Transfer","transfer")):
                if day.get(key): st.write(f"{label}:",day[key])
            if stay:
                st.write("Overnight:",stay.get("area",place),"· nights:",stay.get("nights",0),"·",stay.get("price_status",stay.get("price","Price unavailable")))
            if day.get("return_journey"): st.write("Return:",day["return_journey"])
            if day.get("notes"): st.write(day["notes"])
    alternatives=journey.get("route_alternatives_unranked",[])
    if isinstance(alternatives,list) and len(alternatives)>1:
        st.write("Candidate stop orders (not ranked; fares and schedules unavailable):",alternatives)
    request=state.get("request",{})
    stops=journey.get("stops",[])
    if isinstance(stops,list) and len(stops)>1:
        st.markdown("#### Transfer modes to check")
        st.dataframe(compare_transfer_options(stops[0],stops[1]),use_container_width=True,hide_index=True)
    st.markdown("#### Entry requirements")
    st.caption("No visa eligibility or entry rule is inferred. Confirm requirements with the destination government's official source.")
    st.link_button("Search official entry information",official_entry_information_link(request.get("destination",""),request.get("traveler_nationality","")))
    for issue in journey.get("validation_issues",[]): st.warning(issue)
