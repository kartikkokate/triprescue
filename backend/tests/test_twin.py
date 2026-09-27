import pytest

from app.twin.learner import WeatherImpactLearner
from app.twin.simulator import apply_scenario, simulate
from app.twin.social import classify, is_relevant

CYCLONE = {"overrides": {"rain_mm_h": 70, "wind_kmh": 90, "storm_hours": 24, "flood_index": 0.8}, "target_place": "Goa"}
GOA_MONSOON_DAY2 = {"overrides": {"rain_mm_h": 35, "storm_hours": 10}, "target_place": "Goa", "target_date": "2026-10-11"}


def _run(graph, scenario, n=200):
    return simulate(graph, apply_scenario(graph, {}, scenario), WeatherImpactLearner(persist=False), n=n, seed=1)


def test_extreme_weather_is_far_more_disruptive_than_calm(fresh_state):
    calm = _run(fresh_state.graph, {})
    cyclone = _run(fresh_state.graph, CYCLONE)

    assert calm["trip"]["p_any_disruption"] < 0.2
    assert cyclone["trip"]["p_any_disruption"] > 0.95
    assert cyclone["trip"]["expected_loss_inr"] > 5 * calm["trip"]["expected_loss_inr"]
    assert cyclone["ecosystem"]["Goa"]["cab_availability"]["mean"] < 0.3


def test_outcome_probabilities_are_a_distribution(fresh_state):
    sim = _run(fresh_state.graph, GOA_MONSOON_DAY2)
    for e in sim["nodes"].values():
        assert e["p_safe"] + e["p_at_risk"] + e["p_broken"] == pytest.approx(1.0)
        assert e["delay_p10"] <= e["delay_p50"] <= e["delay_p90"]


def test_scenario_targets_only_its_place_and_day(fresh_state):
    sim = _run(fresh_state.graph, GOA_MONSOON_DAY2)
    assert sim["nodes"]["AC1"]["p_broken"] > 0.9  # outdoor tour on 11 Oct in Goa
    assert sim["nodes"]["FL1"]["p_broken"] < 0.2  # 10 Oct flight - outside the scenario


def test_simulation_never_touches_the_real_itinerary(fresh_state):
    before = fresh_state.graph.to_dict()
    _run(fresh_state.graph, CYCLONE)
    assert fresh_state.graph.to_dict() == before


def test_effect_chain_has_higher_order_effects_in_a_cyclone(fresh_state):
    orders = {c["order"] for c in _run(fresh_state.graph, CYCLONE)["effect_chain"]}
    assert orders == {1, 2, 3}


def test_learner_moves_toward_observations_and_gets_more_certain():
    learner = WeatherImpactLearner(persist=False)
    heavy = {"rain_mm_h": 30.0, "wind_kmh": 20.0, "temp_c": 29.0}
    before = learner.expected_delay("transfer", heavy)
    sd_before = learner.summary()["models"]["transfer"]["coefficient_sd"][1]

    for _ in range(5):
        learner.observe("transfer", heavy, 180.0, source="test")

    after = learner.expected_delay("transfer", heavy)
    assert before < after < 180
    assert learner.summary()["models"]["transfer"]["coefficient_sd"][1] < sd_before
    assert learner.summary()["models"]["transfer"]["observations"] == 5


def test_social_classification_and_relevance():
    assert "flooding" in classify("Waterlogging near Panaji after heavy rain")
    assert is_relevant("Heavy rain lashes Goa, IMD issues orange alert", "Goa")
    assert not is_relevant("SIR storm intensifies in Goa politics", "Goa")  # political "storm"
    assert not is_relevant("Heavy rain in Mumbai", "Goa")


# --- API -----------------------------------------------------------------------------


def test_twin_state_works_offline(client):
    body = client.get("/api/twin/state").json()
    assert set(body["nodes"]) == {"FL1", "TR1", "HT1", "AC1", "AC2", "TR2", "FL2"}
    assert body["places"]["Goa"]["forecast_live"] is False  # conftest blocks the network
    assert "learner" in body and "history" in body


def test_what_if_endpoint_reports_delta_vs_live(client):
    body = client.post("/api/twin/simulate", json=CYCLONE).json()
    assert body["trip"]["p_any_disruption"] > body["baseline_trip"]["p_any_disruption"]
    assert body["delta_vs_live"]["TR1"] > 0.5
    # and the real itinerary is untouched
    statuses = {n["id"]: n["status"] for n in client.get("/api/itinerary").json()["nodes"]}
    assert set(statuses.values()) == {"safe"}


def test_observe_updates_learner_and_rejects_hotels(client):
    body = client.post("/api/twin/observe", json={"node_id": "TR1", "delay_minutes": 90}).json()
    assert body["learner"]["models"]["transfer"]["observations"] == 1
    assert client.post("/api/twin/observe", json={"node_id": "HT1", "delay_minutes": 30}).status_code == 400


def test_weather_attributed_disruption_teaches_the_twin(client):
    client.post("/api/disrupt", json={"node_id": "TR1", "kind": "delay", "delay_minutes": 60, "reason": "heavy rain"})
    client.post("/api/disrupt", json={"node_id": "TR1", "kind": "delay", "delay_minutes": 60, "reason": "driver late"})
    learner = client.get("/api/twin/state").json()["learner"]
    assert learner["models"]["transfer"]["observations"] == 1  # only the weather one counts


def test_promote_hands_scenario_to_recovery_flow(client):
    body = client.post("/api/twin/promote", json=CYCLONE).json()
    statuses = {n["id"]: n["status"] for n in body["itinerary"]["nodes"]}
    assert "cancelled" in statuses.values() or "broken" in statuses.values()
    assert client.get("/api/recovery-plans").json()["plans"], "promoted scenario should produce recovery plans"
    assert client.get("/api/twin/plan-risk").json()["plans"]


def test_promote_a_calm_scenario_is_rejected(client):
    assert client.post("/api/twin/promote", json={"overrides": {"rain_mm_h": 0}}).status_code == 400


def test_twin_briefing_falls_back_to_rule_based(client):
    body = client.post("/api/twin/explain", json=CYCLONE).json()
    assert body["model"] == "rule-based"
    assert "weak point" in body["explanation"]


def test_social_signals_fade_with_booking_lead_time():
    from datetime import datetime

    from app.twin.service import social_weight

    now = datetime(2026, 10, 9, 12, 0)
    assert social_weight("2026-10-09T15:00:00", now) > 0.9  # same day: today's reports matter
    assert social_weight("2026-10-23T15:00:00", now) < 0.01  # two weeks out: they don't


def test_forecast_nulls_are_no_data_not_zero():
    from app.twin.weather import conditions_at

    fc = {"hourly": {
        "time": ["2026-10-12T20:00", "2026-10-12T21:00"],
        "precipitation": [None, None], "precipitation_probability": [None, None],
        "temperature_2m": [None, None], "wind_speed_10m": [None, None],
        "wind_gusts_10m": [None, None], "weather_code": [None, None],
    }}
    assert conditions_at(fc, "2026-10-12T20:00:00") is None


def test_live_twin_follows_the_real_itinerary(client):
    calm = client.get("/api/twin/state").json()["trip"]["p_any_disruption"]
    client.post("/api/disrupt", json={"node_id": "FL1", "kind": "cancel", "reason": "operator_cancellation"})
    assert client.get("/api/twin/state").json()["trip"]["p_any_disruption"] == 1.0
    client.post("/api/reset")
    assert client.get("/api/twin/state").json()["trip"]["p_any_disruption"] == calm


def test_rewiring_the_same_bookings_invalidates_the_live_snapshot(fresh_state):
    from app.twin.service import TwinService

    before = TwinService.signature(fresh_state.graph)
    edge = fresh_state.graph.edges[0]
    fresh_state.graph.edges[0] = edge.model_copy(update={"buffer_minutes": edge.buffer_minutes + 30})
    assert TwinService.signature(fresh_state.graph) != before
