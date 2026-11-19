"""Reusable Streamlit display components."""
from typing import Any
import streamlit as st
from streamlit_folium import st_folium
from config.settings import get_settings
from services.map_service import create_trip_map

def apply_theme() -> None:
    st.markdown("""<style>
    .block-container{padding-top:1.5rem;max-width:1280px}
    [data-testid="stMetric"]{background:#f4f8f6;padding:14px;border-radius:14px;border:1px solid #e1eee8}
    div.stButton>button[kind="primary"]{background:#087f5b;border-color:#087f5b}
    .hero{padding:1.3rem 1.6rem;border-radius:18px;background:linear-gradient(120deg,#e5f5ec,#edf4ff);margin-bottom:1rem}
    </style>""", unsafe_allow_html=True)

def errors(state: dict[str, Any]) -> None:
    for item in state.get("notices", []): st.info(item)
    for item in state.get("errors", []): st.error(item)

def results(state: dict[str, Any], *, map_view: bool = True) -> None:
    errors(state)
    data = state.get("agent_results", {})
    statuses = state.get("agent_status", {})
    if statuses:
        with st.expander("Agent activity"): st.json(statuses)
    flight = data.get("flight")
    if flight:
        st.subheader("Flight search")
        if flight.get("url"): st.link_button("Open flight search", flight["url"])
        st.caption(flight.get("disclaimer", "Search link only. Confirm prices and availability with the provider."))
        if flight.get("source"): st.caption("Source: " + str(flight["source"]))
    hotel = data.get("hotel")
    if hotel:
        st.subheader("Stay discovery")
        for item in hotel.get("listings", []):
            link = item.get("website") or item.get("source_url")
            st.markdown(f"- [{item.get('name','Place')}]({link}) · {item.get('category','accommodation')}" if link else f"- {item.get('name','Place')} · {item.get('category','accommodation')}")
        if hotel.get("search_link"): st.link_button("Explore places on map", hotel["search_link"])
        if hotel.get("booking_search_link"): st.link_button("Search booking options", hotel["booking_search_link"])
        st.caption(hotel.get("note", "Discovery records only; no room prices or availability are provided."))
        if hotel.get("attribution"): st.caption(hotel["attribution"])
    attractions = data.get("attractions")
    if attractions:
        st.subheader("Attractions")
        for item in attractions.get("attractions", []):
            st.write(f"• {item.get('name','Attraction')} · {item.get('source', attractions.get('source','POI source'))}")
        if attractions.get("search_link"): st.link_button("Explore attractions", attractions["search_link"])
        if attractions.get("attribution"): st.caption(attractions["attribution"])
        if attractions.get("reason"): st.caption(attractions["reason"])
    weather = data.get("weather")
    if weather:
        st.subheader("Weather")
        if weather.get("available"):
            st.dataframe(weather.get("days", []), use_container_width=True, hide_index=True)
            st.caption(f"Live forecast · {weather.get('source','Open-Meteo')} · {weather.get('retrieved_at','')}")
        else: st.info(weather.get("reason", "Forecast unavailable."))
    itinerary = state.get("itinerary") or data.get("itinerary")
    if itinerary:
        st.subheader("Day-wise itinerary")
        st.markdown(itinerary.get("plan_text", ""))
        st.caption(itinerary.get("disclaimer", "AI-generated suggestions; verify details."))
    rag = data.get("rag")
    if rag:
        st.subheader("Document answer")
        st.markdown(rag.get("answer", ""))
        if rag.get("sources"): st.caption("Sources: " + ", ".join(x.get("document_name", "document") for x in rag["sources"]))
    loc = data.get("current_location", {})
    map_points=[]
    for key in ("hotel", "attractions"):
        group=data.get(key,{})
        for x in group.get("listings",group.get("attractions",[])):
            if x.get("latitude") is not None and x.get("longitude") is not None: map_points.append(x)
    if weather:
        dest=weather.get("destination",{})
        if isinstance(dest,dict) and dest.get("latitude") is not None: map_points.append({**dest,"name":dest.get("name","Destination")})
    if loc.get("latitude") is not None: map_points.append({**loc,"name":"Current location"})
    if map_view and map_points:
        st.subheader("Map")
        st_folium(create_trip_map(map_points), width=None, height=430, returned_objects=[])
        if get_settings().non_commercial_mode: st.caption("© OpenStreetMap contributors · map tiles follow the OpenStreetMap tile policy.")
    if data.get("chat",{}).get("answer"): st.markdown(data["chat"]["answer"])
    email=data.get("email")
    if email:
        st.subheader("Gmail action")
        st.info(email.get("message",email.get("status","Completed")))
        if email.get("recipient"): st.caption(f"To: {email['recipient']} · Subject: {email.get('subject','')}")
        if email.get("body"): st.text(email["body"])
        if email.get("messages"): st.dataframe(email["messages"],use_container_width=True,hide_index=True)
