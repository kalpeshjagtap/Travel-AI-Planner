from services.journey_planner import build_journey, validate_journey

SCENARIOS=[
    ("Pune, India","Goa, India",["Goa, India"]),
    ("Pune, India","Kashmir, India",["Kashmir, India"]),
    ("Pune, India","Thailand",["Chiang Mai","Phuket"]),
    ("Pune, India","Japan",["Tokyo","Kyoto"]),
    ("Delhi, India","Switzerland",["Zurich","Swiss Alps"]),
    ("London, UK","Paris, France",["Paris, France"]),
    ("New York, USA","Los Angeles, USA",["Los Angeles, USA"]),
    ("Pune, India","Europe multi-country",["Milan, Italy","Paris, France","Zurich, Switzerland"]),
]

def req(origin,destination,stops,days=7):
    return {"origin":origin,"destination":destination,"preferred_regions":stops,
            "start_date":"2026-12-01","end_date":f"2026-12-{days:02d}"}

def test_worldwide_examples_are_treated_as_user_locations_not_country_constants():
    for origin,destination,stops in SCENARIOS:
        journey=build_journey(req(origin,destination,stops))
        assert journey["stops"]==stops
        assert journey["itinerary"][-1]["return_journey"]
        assert all(day["accommodation"]["price_status"].startswith("Price unavailable") for day in journey["itinerary"])

def test_multi_stop_generates_unranked_forward_and_reverse_candidates():
    journey=build_journey(req("Pune","Europe",["Milan","Paris","Zurich"],10))
    assert journey["route_alternatives_unranked"]==[["Milan","Paris","Zurich"],["Zurich","Paris","Milan"]]
    assert "not cost-ranked" in journey["route_comparison"]

def test_south_thailand_text_is_preserved_but_not_mapped_to_hardcoded_cities():
    journey=build_journey(req("Pune","Thailand",["South Thailand"],7))
    assert journey["stops"]==["South Thailand"]

def test_single_way_does_not_claim_return_journey():
    journey=build_journey({**req("London","Paris",["Paris"],2),"journey_type":"one_way"})
    assert journey["itinerary"][-1]["return_journey"] is None
    assert validate_journey(journey,1)==[]

def test_generated_days_use_city_or_region_schema_and_have_safe_accommodation():
    journey=build_journey(req("Pune","Goa",["Goa"],3))
    assert all("city_or_region" in day for day in journey["itinerary"])
    assert all(isinstance(day["accommodation"],dict) for day in journey["itinerary"])

def test_journey_renderer_normalizes_legacy_and_malformed_day_records():
    # The UI must remain renderable if a saved/old graph result contains a
    # string day, missing city fields, or a non-dictionary accommodation.
    from unittest.mock import MagicMock
    from ui.pages import planner

    fake_st=MagicMock()
    fake_st.expander.return_value.__enter__.return_value=None
    original=planner.st
    planner.st=fake_st
    try:
        planner._render_journey({"request":{},"agent_results":{"journey":{
            "itinerary":["old plain-text day", {"date":"2026-12-02","accommodation":None}],
            "stops":[],
        }}})
    finally:
        planner.st=original
