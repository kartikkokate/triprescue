"""These exercise the in-memory fallback path (no SUPABASE_URL/KEY set in this test
environment) - the Supabase-backed path is a thin, structurally-identical wrapper around
the same client calls and isn't independently tested here (needs a live project)."""
from app import trip_repository
from app.impact_engine import propagate_disruption


def test_create_list_load_delete_round_trip(fresh_state):
    itinerary = fresh_state.graph.to_dict()
    prefs = {
        "cost_weight": 0.2, "time_weight": 0.3, "convenience_weight": 0.4,
        "disruption_weight": 0.1, "min_rating": 0, "avoid_next_day": False,
    }

    record = trip_repository.create_trip("Goa Trip", itinerary, prefs)
    assert record["name"] == "Goa Trip"
    trip_id = record["id"]

    summaries = trip_repository.list_trips()
    assert any(t["id"] == trip_id and t["name"] == "Goa Trip" for t in summaries)

    loaded = trip_repository.load_trip(trip_id)
    assert loaded["itinerary"] == itinerary
    assert loaded["preferences"] == prefs

    trip_repository.delete_trip(trip_id)
    assert trip_repository.load_trip(trip_id) is None
    assert all(t["id"] != trip_id for t in trip_repository.list_trips())


def test_load_unknown_trip_returns_none():
    assert trip_repository.load_trip("does-not-exist") is None


def test_save_trip_upserts_and_preserves_name_when_not_given(fresh_state):
    itinerary = fresh_state.graph.to_dict()
    prefs = {"cost_weight": 0.2, "time_weight": 0.3, "convenience_weight": 0.4, "disruption_weight": 0.1, "min_rating": 0, "avoid_next_day": False}
    record = trip_repository.create_trip("Original Name", itinerary, prefs)

    propagate_disruption(fresh_state.graph, "FL1", "delay", 60)
    updated_itinerary = fresh_state.graph.to_dict()
    trip_repository.save_trip(record["id"], None, updated_itinerary, prefs)

    reloaded = trip_repository.load_trip(record["id"])
    assert reloaded["name"] == "Original Name"
    assert reloaded["itinerary"] == updated_itinerary


def test_app_state_save_and_load_trip_round_trip(fresh_state):
    fresh_state.save_as_new_trip("Test Trip")
    trip_id = fresh_state.trip_id
    assert trip_id is not None

    propagate_disruption(fresh_state.graph, "FL1", "delay", 180)
    fresh_state.last_disruption = {"node_id": "FL1", "kind": "delay"}
    fresh_state.save_current_trip()

    fresh_state.reset()  # undo disruptions, stay on the same trip
    assert fresh_state.trip_id == trip_id
    assert fresh_state.graph.nodes["FL1"].status == "safe"

    fresh_state.load_trip(trip_id)
    assert fresh_state.trip_id == trip_id
    assert fresh_state.trip_name == "Test Trip"
    assert fresh_state.graph.nodes["FL1"].status == "broken"
    # loading a trip clears working disruption state - it's a fresh session on that trip
    assert fresh_state.last_disruption is None


def test_supabase_calls_retry_once_on_a_dead_connection(monkeypatch):
    import httpx

    from app import db

    calls = {"n": 0}

    class Req:
        def execute(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ReadError("WinError 10035")
            return type("Res", (), {"data": [{"id": "x", "name": "t", "updated_at": "now"}]})()

        def is_(self, *a):
            return self

    class Client:
        def table(self, name):
            return self

        def select(self, *a):
            return self

        def order(self, *a, **k):
            return Req()

    monkeypatch.setattr(db, "get_client", lambda: Client())
    assert trip_repository.list_trips() == [{"id": "x", "name": "t", "updated_at": "now"}]
    assert calls["n"] == 2
