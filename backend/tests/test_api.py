def test_get_itinerary_returns_seed_data(client):
    res = client.get("/api/itinerary")
    assert res.status_code == 200
    body = res.json()
    node_ids = {n["id"] for n in body["nodes"]}
    assert node_ids == {"FL1", "TR1", "HT1", "AC1", "AC2", "TR2", "FL2"}
    assert all(n["status"] == "safe" for n in body["nodes"])


def test_disrupt_unknown_node_returns_404(client):
    res = client.post(
        "/api/disrupt",
        json={"node_id": "NOPE", "kind": "delay", "delay_minutes": 10, "reason": "unspecified"},
    )
    assert res.status_code == 404


def test_disrupt_delay_updates_statuses(client):
    res = client.post(
        "/api/disrupt",
        json={"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"},
    )
    assert res.status_code == 200
    body = res.json()
    statuses = {n["id"]: n["status"] for n in body["itinerary"]["nodes"]}
    assert statuses["FL1"] == "broken"
    assert statuses["TR1"] == "broken"
    assert statuses["HT1"] == "at_risk"
    assert statuses["AC1"] == "safe"
    assert "TR1" in body["impact_report"]
    assert body["disruption"]["node_id"] == "FL1"


def test_disrupt_weather_unknown_date_returns_404(client):
    res = client.post("/api/disrupt-weather", json={"date": "2099-01-01", "severity": "severe"})
    assert res.status_code == 404


def test_disrupt_weather_severe_cancels_activities(client):
    res = client.post("/api/disrupt-weather", json={"date": "2026-10-11", "severity": "severe"})
    assert res.status_code == 200
    body = res.json()
    statuses = {n["id"]: n["status"] for n in body["itinerary"]["nodes"]}
    assert statuses["AC1"] == "cancelled"
    assert statuses["AC2"] == "cancelled"
    assert statuses["TR2"] == "safe"
    assert {o["node_id"] for o in body["weather_origins"]} == {"AC1", "AC2"}


def test_recovery_plans_empty_before_any_disruption(client):
    res = client.get("/api/recovery-plans")
    assert res.status_code == 200
    assert res.json()["plans"] == []


def test_recovery_plans_after_disruption_are_ranked(client):
    client.post(
        "/api/disrupt",
        json={"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"},
    )
    res = client.get("/api/recovery-plans")
    body = res.json()
    plans = body["plans"]
    assert len(plans) >= 2
    assert plans[0]["id"] == "plan-balanced"
    assert {"balanced", "cheapest", "fastest"} <= {b for p in plans for b in p["badges"]}
    assert body["analysis"]["feasible"] <= body["analysis"]["combinations_checked"]


def test_apply_unknown_plan_id_returns_404(client):
    client.post(
        "/api/disrupt",
        json={"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"},
    )
    res = client.post("/api/apply-plan/not-a-real-plan")
    assert res.status_code == 404


def test_apply_plan_resolves_the_disruption(client):
    client.post(
        "/api/disrupt",
        json={"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"},
    )
    plan_id = client.get("/api/recovery-plans").json()["plans"][0]["id"]

    res = client.post(f"/api/apply-plan/{plan_id}")
    assert res.status_code == 200
    body = res.json()
    assert all(n["status"] == "safe" for n in body["itinerary"]["nodes"])

    # applying clears the disruption, so recovery-plans and explain-impact reset too
    assert client.get("/api/recovery-plans").json()["plans"] == []
    assert client.get("/api/explain-impact").status_code == 400


def test_risk_scan_flags_the_two_tight_connections(client):
    res = client.get("/api/risk-scan")
    warnings = res.json()["warnings"]
    by_node = {w["node_id"]: w["severity"] for w in warnings}
    assert by_node == {"TR1": "medium", "HT1": "high"}


def test_explain_impact_without_a_disruption_returns_400(client):
    res = client.get("/api/explain-impact")
    assert res.status_code == 400


def test_explain_impact_after_a_disruption_has_a_source_field(client):
    client.post(
        "/api/disrupt",
        json={"node_id": "TR1", "kind": "cancel", "reason": "operator_cancellation"},
    )
    res = client.get("/api/explain-impact")
    assert res.status_code == 200
    assert res.json()["source"] in ("llm", "rule-based")


def test_reset_restores_seed_itinerary(client):
    client.post(
        "/api/disrupt",
        json={"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"},
    )
    res = client.post("/api/reset")
    assert res.status_code == 200
    assert all(n["status"] == "safe" for n in res.json()["nodes"])
    assert client.get("/api/recovery-plans").json()["plans"] == []


def test_preferences_default_and_roundtrip(client):
    default = client.get("/api/preferences").json()
    assert default == {
        "cost_weight": 0.2,
        "time_weight": 0.3,
        "convenience_weight": 0.4,
        "disruption_weight": 0.1,
        "min_rating": 0,
        "avoid_next_day": False,
    }

    updated = {
        "cost_weight": 1,
        "time_weight": 0,
        "convenience_weight": 0,
        "disruption_weight": 0,
        "min_rating": 0,
        "avoid_next_day": False,
    }
    res = client.put("/api/preferences", json=updated)
    assert res.status_code == 200
    assert client.get("/api/preferences").json()["cost_weight"] == 1


def test_preferences_change_which_plan_is_recommended(client):
    client.post(
        "/api/disrupt",
        json={"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"},
    )
    client.put(
        "/api/preferences",
        json={
            "cost_weight": 1,
            "time_weight": 0,
            "convenience_weight": 0,
            "disruption_weight": 0,
            "min_rating": 0,
            "avoid_next_day": False,
        },
    )
    plans = client.get("/api/recovery-plans").json()["plans"]
    assert plans[0]["total_cost_delta"] == min(p["total_cost_delta"] for p in plans)


def test_traveler_rights_requires_a_disruption(client):
    assert client.get("/api/traveler-rights").status_code == 400


def test_traveler_rights_after_a_cancellation(client):
    client.post("/api/disrupt", json={"node_id": "FL1", "kind": "cancel", "reason": "operator_cancellation"})
    body = client.get("/api/traveler-rights").json()

    assert body["model"] == "rule-based"  # conftest disables every real model
    assert "DGCA" in body["explanation"]


def test_ai_model_reports_fallback_tier_without_nugen(client):
    body = client.get("/api/ai-model").json()
    assert body["active_tier"] == "gemini-or-rule-based"
    assert body["nugen_model_id"] is None
    assert isinstance(body["pipeline"], dict)
