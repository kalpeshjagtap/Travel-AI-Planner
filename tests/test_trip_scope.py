from services import trip_scope


def test_same_geocoded_country_is_domestic(monkeypatch):
    countries = {"Pune": "India", "Goa": "India"}
    monkeypatch.setattr(trip_scope, "geocode_place", lambda place: {"country": countries[place]})
    scope, details = trip_scope.classify_route_scope({"origin": "Pune", "destination": "Goa"})
    assert scope == "domestic"
    assert details["origin_country"] == details["destination_country"] == "India"


def test_different_geocoded_countries_are_international(monkeypatch):
    countries = {"Pune": "India", "Bangkok": "Thailand"}
    monkeypatch.setattr(trip_scope, "geocode_place", lambda place: {"country": countries[place]})
    scope, _ = trip_scope.classify_route_scope({"origin": "Pune", "destination": "Bangkok"})
    assert scope == "international"


def test_country_lookup_failure_does_not_guess_scope(monkeypatch):
    def fail(_place):
        raise RuntimeError("offline")

    monkeypatch.setattr(trip_scope, "geocode_place", fail)
    scope, details = trip_scope.classify_route_scope({"origin": "Pune", "destination": "Goa"})
    assert scope == "unknown"
    assert details["source"] == "country lookup unavailable"
