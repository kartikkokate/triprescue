from datetime import datetime

from app import external_apis
from app.monitor import providers
from app.monitor.service import MonitorService, fingerprint
from app.twin import weather

TRAVEL_MORNING = datetime(2026, 10, 10, 7, 0)  # 3 h before FL1 departs


def _flight_status(status="active", delay=0):
    return lambda code: {"configured": True, "found": True, "flight_iata": code, "status": status,
                         "delay_minutes": delay, "suggested_action": None}


def _hourly(rain=0.0, wind=10.0, code=1):
    hours = [f"2026-10-{d:02d}T{h:02d}:00" for d in (10, 11, 12) for h in range(24)]
    n = len(hours)
    return {"hourly": {"time": hours, "precipitation": [rain] * n, "precipitation_probability": [90] * n,
                       "temperature_2m": [29.0] * n, "wind_speed_10m": [wind] * n,
                       "wind_gusts_10m": [wind * 1.5] * n, "weather_code": [code] * n}}


def test_fingerprint_is_stable_and_escalation_changes_it():
    a = fingerprint("FL1", {"kind": "delay", "severity": "medium", "delay_minutes": 40})
    assert a == fingerprint("FL1", {"kind": "delay", "severity": "medium", "delay_minutes": 50})  # same 30-min bucket
    assert a != fingerprint("FL1", {"kind": "delay", "severity": "high", "delay_minutes": 130})


def test_flight_delay_alerts_once_then_suppresses_duplicates(fresh_state, monkeypatch):
    monkeypatch.setattr(external_apis, "check_flight_status", _flight_status("active", 150))
    m = MonitorService(persist=False)

    first = m.run(fresh_state.graph, fresh_state.preferences, TRAVEL_MORNING)
    second = m.run(fresh_state.graph, fresh_state.preferences, TRAVEL_MORNING)

    assert first["new_alerts"] == 1 and second["new_alerts"] == 0
    assert second["suppressed_duplicates"] == 1
    note = first["notifications"][0]
    assert note["node_id"] == "FL1" and note["source"] == "AviationStack"
    assert note["impact"].get("TR1") == "broken"  # impact recalculated...
    assert note["plans_preview"] and note["plans_preview"][0]["id"] == "plan-balanced"  # ...and plan scores
    assert all(n.status == "safe" for n in fresh_state.graph.nodes.values())  # real trip untouched


def test_worse_delay_escalates_with_a_new_alert(fresh_state, monkeypatch):
    m = MonitorService(persist=False)
    monkeypatch.setattr(external_apis, "check_flight_status", _flight_status("active", 40))
    m.run(fresh_state.graph, fresh_state.preferences, TRAVEL_MORNING)
    monkeypatch.setattr(external_apis, "check_flight_status", _flight_status("cancelled", 0))
    out = m.run(fresh_state.graph, fresh_state.preferences, TRAVEL_MORNING)
    assert out["new_alerts"] == 1 and "cancel" in out["notifications"][0]["title"]


def test_flight_status_quota_is_only_spent_near_departure(fresh_state, monkeypatch):
    calls = []
    monkeypatch.setattr(external_apis, "check_flight_status", lambda code: calls.append(code) or _flight_status()(code))
    MonitorService(persist=False).run(fresh_state.graph, fresh_state.preferences, datetime(2026, 9, 27, 12))
    assert calls == []  # trip is two weeks away
    MonitorService(persist=False).run(fresh_state.graph, fresh_state.preferences, TRAVEL_MORNING)
    assert calls == ["6E204"]  # only FL1 departs within 24 h


def test_severe_weather_means_new_cab_required(fresh_state, monkeypatch):
    monkeypatch.setattr(weather, "fetch_forecast", lambda lat, lon: _hourly(rain=30, code=95))
    out = MonitorService(persist=False).run(fresh_state.graph, fresh_state.preferences, TRAVEL_MORNING)
    cab = [n for n in out["notifications"] if n["node_id"] == "TR1"]
    assert cab and "new cab required" in cab[0]["message"]
    assert cab[0]["source"] == "Road (derived from weather)"
    outdoor = {n["node_id"] for n in out["notifications"]} & {"AC1", "AC2"}
    assert outdoor == {"AC1", "AC2"}


def test_failing_providers_never_crash_the_monitor(fresh_state, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(external_apis, "check_flight_status", boom)
    monkeypatch.setattr(weather, "fetch_forecast", boom)
    out = MonitorService(persist=False).run(fresh_state.graph, fresh_state.preferences, TRAVEL_MORNING)
    assert out["by_status"]["error"] >= 2 and out["new_alerts"] == 0


def test_rail_and_hotel_are_reported_as_unavailable_not_faked(fresh_state):
    from app.models import BookingNode

    train = BookingNode(id="T", type="train", title="T", location="x", start="2026-10-10T10:00:00",
                        end="2026-10-10T12:00:00", cost=1, provider="IR", cancellation_policy="x")
    assert providers.check_rail(train, TRAVEL_MORNING)["status"] == "unavailable"


# --- API ------------------------------------------------------------------------------------


def test_monitor_api_alert_then_apply_into_recovery(client, monkeypatch):
    monkeypatch.setattr(external_apis, "check_flight_status", _flight_status("cancelled", 0))
    run = client.post("/api/monitor/run", params={"now": "2026-10-10T07:00:00"}).json()
    assert run["new_alerts"] == 1

    notes = client.get("/api/notifications").json()
    assert notes["unread"] == 1
    note = notes["notifications"][0]
    assert client.post(f"/api/notifications/{note['id']}/read").status_code == 200

    status = client.get("/api/monitor/status").json()
    assert status["interval_minutes"] == 20
    assert any(p["provider"] == "AviationStack" and p["status"] == "ok" for p in status["providers"])
    assert status["open_events"][0]["id"] == note["event_id"]

    applied = client.post(f"/api/monitor/events/{note['event_id']}/apply").json()
    statuses = {n["id"]: n["status"] for n in applied["itinerary"]["nodes"]}
    assert statuses["FL1"] == "cancelled" and applied["plans"]
    assert client.get("/api/monitor/status").json()["open_events"] == []


def test_monitor_run_rejects_bad_time(client):
    assert client.post("/api/monitor/run", params={"now": "tomorrow"}).status_code == 400



def test_switching_trips_clears_old_provider_rows_and_alerts(client, monkeypatch):
    monkeypatch.setattr(external_apis, "check_flight_status", _flight_status("cancelled", 0))
    client.post("/api/monitor/run", params={"now": "2026-10-10T07:00:00"})
    assert client.get("/api/monitor/status").json()["providers"]
    client.post("/api/demo")
    status = client.get("/api/monitor/status").json()
    assert status["providers"] == [] and status["open_events"] == []
    assert client.get("/api/notifications").json()["notifications"] == []
