def test_trip_status_starts_with_no_active_trip(client):
    res = client.get("/api/trip-status")
    assert res.status_code == 200
    body = res.json()
    assert body["trip_id"] is None
    assert body["persistence_backend"] == "in-memory"  # no SUPABASE_URL/KEY in this test env


def test_create_list_load_delete_trip(client):
    created = client.post("/api/trips", json={"name": "Goa Getaway"}).json()
    trip_id = created["id"]
    assert created["name"] == "Goa Getaway"

    listed = client.get("/api/trips").json()["trips"]
    assert any(t["id"] == trip_id for t in listed)

    status = client.get("/api/trip-status").json()
    assert status["trip_id"] == trip_id
    assert status["trip_name"] == "Goa Getaway"

    loaded = client.post(f"/api/trips/{trip_id}/load").json()
    assert loaded["trip"]["id"] == trip_id
    assert loaded["itinerary"]["nodes"]

    client.delete(f"/api/trips/{trip_id}")
    assert all(t["id"] != trip_id for t in client.get("/api/trips").json()["trips"])
    # deleting the active trip clears trip-status back to no active trip
    assert client.get("/api/trip-status").json()["trip_id"] is None


def test_save_persists_current_working_disruption(client):
    trip_id = client.post("/api/trips", json={"name": "Working Copy"}).json()["id"]

    client.post(
        "/api/disrupt",
        json={"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"},
    )
    client.post(f"/api/trips/{trip_id}/save")

    client.post("/api/reset")
    assert client.get("/api/itinerary").json()["nodes"][0]["status"] == "safe"

    loaded = client.post(f"/api/trips/{trip_id}/load").json()
    statuses = {n["id"]: n["status"] for n in loaded["itinerary"]["nodes"]}
    assert statuses["FL1"] == "broken"


def test_load_unknown_trip_returns_404(client):
    res = client.post("/api/trips/does-not-exist/load")
    assert res.status_code == 404


def test_save_with_non_uuid_trip_id_is_rejected(client):
    resp = client.post("/api/trips/not-a-uuid/save")
    assert resp.status_code == 400


def test_non_uuid_trip_id_is_404_even_with_supabase(client, monkeypatch):
    """Postgres rejects non-UUID ids on a uuid column (22P02); that used to leak out as a 500."""
    from app import db

    class ExplodingClient:
        def table(self, name):
            raise AssertionError("must not query Supabase with a non-UUID id")

    monkeypatch.setattr(db, "get_client", lambda: ExplodingClient())
    assert client.post("/api/trips/does-not-exist/load").status_code == 404



CUSTOM = {
    "name": "Pune weekend",
    "geocode": False,
    "bookings": [
        {"type": "train", "title": "Deccan Queen CSMT -> PUNE", "start": "2026-11-07T17:10:00", "end": "2026-11-07T20:25:00",
         "cost": 450, "provider": "Indian Railways", "service_code": "12123", "lat": 18.94, "lon": 72.83, "dest_lat": 18.53, "dest_lon": 73.87},
        {"type": "hotel", "title": "Koregaon Park hotel", "start": "2026-11-07T21:00:00", "end": "2026-11-07T21:30:00",
         "cost": 5200, "provider": "Hotel", "cancellation_policy": "free_24h", "lat": 18.54, "lon": 73.89},
    ],
}


def test_built_trip_is_saved_and_reset_keeps_it(client):
    body = client.post("/api/itinerary", json=CUSTOM).json()
    assert body["trip_id"]
    status = client.get("/api/trip-status").json()
    assert status == {**status, "trip_name": "Pune weekend", "is_demo": False, "trip_id": body["trip_id"]}
    assert any(t["id"] == body["trip_id"] for t in client.get("/api/trips").json()["trips"])

    client.post("/api/disrupt", json={"node_id": "B1", "kind": "cancel", "reason": "operator_cancellation"})
    client.post("/api/reset")  # undo the disruption - must NOT fall back to the demo trip
    nodes = client.get("/api/itinerary").json()["nodes"]
    assert {n["title"] for n in nodes} == {"Deccan Queen CSMT -> PUNE", "Koregaon Park hotel"}
    assert all(n["status"] == "safe" for n in nodes)


def test_demo_is_an_explicit_choice(client):
    client.post("/api/itinerary", json=CUSTOM)
    client.post("/api/demo")
    status = client.get("/api/trip-status").json()
    assert status["is_demo"] is True and status["trip_id"] is None
    assert len(client.get("/api/itinerary").json()["nodes"]) == 7


def test_startup_resumes_the_last_saved_trip(client):
    from app.store import AppState

    client.post("/api/itinerary", json=CUSTOM)
    resumed = AppState(restore_last_trip=True)
    assert resumed.trip_name == "Pune weekend" and not resumed.is_demo


def test_a_new_trip_never_overwrites_the_active_saved_trip(client):
    first = client.post("/api/itinerary", json=CUSTOM).json()
    second = client.post("/api/itinerary", json={**CUSTOM, "name": "Pune to Indore"}).json()
    assert second["trip_id"] != first["trip_id"]
    names = {t["id"]: t["name"] for t in client.get("/api/trips").json()["trips"]}
    assert names[first["trip_id"]] == "Pune weekend" and names[second["trip_id"]] == "Pune to Indore"


def test_editing_the_active_trip_updates_its_row(client):
    first = client.post("/api/itinerary", json=CUSTOM).json()
    again = client.post("/api/itinerary", json={**CUSTOM, "name": "Pune long weekend", "update_trip_id": first["trip_id"]}).json()
    assert again["trip_id"] == first["trip_id"]
    trips = client.get("/api/trips").json()["trips"]
    assert [t["name"] for t in trips] == ["Pune long weekend"]


def test_an_unverified_token_is_treated_as_a_guest(client):
    # without Supabase no token can be verified: the caller is a guest and sees guest trips
    body = client.post("/api/itinerary", json=CUSTOM, headers={"Authorization": "Bearer forged"}).json()
    assert any(t["id"] == body["trip_id"] for t in client.get("/api/trips").json()["trips"])


def test_auth_config_never_hands_out_a_secret_key(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "sb_secret_abc")
    cfg = client.get("/api/auth-config").json()
    assert cfg["enabled"] is False and cfg["key"] == ""
