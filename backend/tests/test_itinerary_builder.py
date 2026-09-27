from app.itinerary_builder import BookingInput, ItineraryInput, build_graph

TRIP = {
    "name": "Mumbai -> Jaipur",
    "geocode": False,
    "bookings": [
        {"type": "flight", "title": "AI 631 BOM -> JAI", "start": "2026-11-02T07:00:00", "end": "2026-11-02T08:45:00",
         "cost": 6200, "provider": "Air India", "cancellation_policy": "partial_50pct", "service_code": "AI631",
         "lat": 19.09, "lon": 72.87, "dest_lat": 26.82, "dest_lon": 75.81},
        {"type": "transfer", "title": "Airport -> hotel cab", "start": "2026-11-02T09:30:00", "end": "2026-11-02T10:15:00",
         "cost": 700, "provider": "local cab", "lat": 26.82, "lon": 75.81},
        {"type": "hotel", "title": "Hotel check-in", "start": "2026-11-02T12:00:00", "end": "2026-11-02T12:30:00",
         "cost": 8000, "provider": "Heritage Haveli", "cancellation_policy": "free_24h", "cancellation_penalty": 2000,
         "lat": 26.92, "lon": 75.82},
        {"type": "activity", "title": "Amber Fort tour", "start": "2026-11-02T15:00:00", "end": "2026-11-02T18:00:00",
         "cost": 1500, "provider": "Jaipur Tours", "weather_sensitive": True, "lat": 26.98, "lon": 75.85},
    ],
}


def test_dependencies_are_inferred_from_the_timeline():
    g = build_graph(ItineraryInput(**TRIP))
    edges = {(e.source, e.target): (e.type, e.buffer_minutes) for e in g.edges}
    assert edges[("B1", "B2")] == ("transfer_required", 30)
    assert edges[("B2", "B3")] == ("checkin_dependency", 15)
    assert edges[("B3", "B4")][0] == "same_day"


def test_buffer_never_exceeds_the_travelers_own_gap():
    trip = {**TRIP, "bookings": [dict(b) for b in TRIP["bookings"]]}
    trip["bookings"][1]["start"] = "2026-11-02T09:00:00"  # only 15 min after landing
    g = build_graph(ItineraryInput(**trip))
    assert next(e for e in g.edges if e.source == "B1").buffer_minutes == 15


def test_rejects_bad_input():
    import pytest

    bad = {**TRIP, "dependencies": [{"source": "B1", "target": "NOPE"}]}
    with pytest.raises(ValueError):
        build_graph(ItineraryInput(**bad))
    with pytest.raises(ValueError):
        BookingInput(type="hotel", title="x", start="2026-11-02T12:00:00", end="2026-11-02T11:00:00", cost=1)


def test_custom_trip_end_to_end_via_api(client):
    body = client.post("/api/itinerary", json=TRIP).json()
    assert len(body["itinerary"]["nodes"]) == 4

    client.post("/api/disrupt", json={"node_id": "B1", "kind": "cancel", "reason": "operator_cancellation"})
    plans = client.get("/api/recovery-plans").json()["plans"]
    assert plans and plans[0]["id"] == "plan-balanced"
    b2 = [o for p in plans for o in p["options"] if o["node_id"] == "B2"]
    assert b2 and all(o["requires_manual_booking"] for o in b2)  # no cab API: always book yourself
    assert any(o["price_source"] == "estimate" for p in plans for o in p["options"])

    twin = client.get("/api/twin/state").json()
    assert set(twin["nodes"]) == {"B1", "B2", "B3", "B4"}
    assert "Mumbai" not in twin["places"] and len(twin["places"]) >= 2  # places come from the trip itself


def test_bad_itinerary_is_a_400(client):
    assert client.post("/api/itinerary", json={**TRIP, "dependencies": [{"source": "B1", "target": "B9"}]}).status_code == 400


def test_destination_is_kept_in_location_for_place_names():
    trip = {"name": "x", "geocode": False, "bookings": [
        {"type": "flight", "title": "AI 631", "start": "2026-11-02T07:00:00", "end": "2026-11-02T08:45:00", "cost": 1,
         "location": "Mumbai", "destination": "Jaipur", "lat": 19.09, "lon": 72.87, "dest_lat": 26.82, "dest_lon": 75.81},
    ]}
    g = build_graph(ItineraryInput(**trip))
    assert g.nodes["B1"].location == "Mumbai to Jaipur"

    from app.twin.simulator import PLACES, register_places

    register_places(g)
    assert set(PLACES) == {"Mumbai", "Jaipur"}


def test_a_tour_during_a_hotel_stay_hangs_off_arrival_not_checkout():
    def b(type_, title, start, end):
        return BookingInput(type=type_, title=title, start=start, end=end, cost=100, lat=31.6, lon=74.9)

    g = build_graph(ItineraryInput(name="stay", geocode=False, bookings=[
        b("flight", "DEL-ATQ", "2026-10-03T14:30:00", "2026-10-03T15:45:00"),
        b("hotel", "Hotel", "2026-10-03T17:00:00", "2026-10-05T11:00:00"),
        b("activity", "Wagah", "2026-10-04T15:30:00", "2026-10-04T18:30:00"),
        b("flight", "ATQ-DEL", "2026-10-05T15:00:00", "2026-10-05T16:15:00"),
    ]))
    links = {(e.source, e.target) for e in g.edges}
    assert ("B2", "B3") not in links          # the tour is not "after checkout"
    assert ("B1", "B3") in links              # it needs the traveler to have arrived
    assert ("B2", "B4") in links              # the chain continues from checkout
