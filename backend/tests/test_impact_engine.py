from app.impact_engine import propagate_disruption, apply_weather_event, scan_proactive_risks


def test_small_delay_causes_at_risk_not_broken(fresh_state):
    graph = fresh_state.graph
    propagate_disruption(graph, "FL1", "delay", 10)

    assert graph.nodes["FL1"].status == "at_risk"
    assert graph.nodes["TR1"].status == "at_risk"


def test_large_delay_breaks_flight_and_transfer_but_not_the_rest(fresh_state):
    """Regression test for the original scaffold's hotel-modeling bug: a 3h flight
    delay should only threaten same-day connections, not next-day plans, since the
    overnight buffer easily absorbs it."""
    graph = fresh_state.graph
    report = propagate_disruption(graph, "FL1", "delay", 180)

    assert graph.nodes["FL1"].status == "broken"
    assert graph.nodes["TR1"].status == "broken"
    assert graph.nodes["HT1"].status == "at_risk"
    assert graph.nodes["AC1"].status == "safe"
    assert graph.nodes["AC2"].status == "safe"
    assert graph.nodes["TR2"].status == "safe"
    assert graph.nodes["FL2"].status == "safe"

    assert report["HT1"]["overrun_minutes"] == 165


def test_cancellation_cascades_only_through_hard_blockers(fresh_state):
    """Regression test for the cancel-cascade bug: cancelling a transfer should only
    break what it directly, physically blocks (check-in) - not the entire rest of
    the trip, which is reachable only via soft same-day scheduling edges."""
    graph = fresh_state.graph
    propagate_disruption(graph, "TR1", "cancel", 0)

    assert graph.nodes["TR1"].status == "cancelled"
    assert graph.nodes["HT1"].status == "broken"
    assert graph.nodes["AC1"].status == "safe"
    assert graph.nodes["AC2"].status == "safe"
    assert graph.nodes["TR2"].status == "safe"
    assert graph.nodes["FL2"].status == "safe"
    assert graph.nodes["FL1"].status == "safe"


def test_cancelling_an_activity_does_not_cascade_to_the_next_one(fresh_state):
    graph = fresh_state.graph
    propagate_disruption(graph, "AC1", "cancel", 0)

    assert graph.nodes["AC1"].status == "cancelled"
    assert graph.nodes["AC2"].status == "safe"


def test_severe_weather_cancels_only_weather_sensitive_activities(fresh_state):
    graph = fresh_state.graph
    result = apply_weather_event(graph, "2026-10-11", "severe")

    assert {o["node_id"] for o in result["origins"]} == {"AC1", "AC2"}
    assert graph.nodes["AC1"].status == "cancelled"
    assert graph.nodes["AC2"].status == "cancelled"
    assert graph.nodes["TR2"].status == "safe"
    assert graph.nodes["FL2"].status == "safe"


def test_moderate_weather_delays_activities_without_breaking_transfer(fresh_state):
    graph = fresh_state.graph
    apply_weather_event(graph, "2026-10-11", "moderate")

    assert graph.nodes["AC1"].status == "broken"
    assert graph.nodes["AC2"].status == "broken"
    assert graph.nodes["TR2"].status == "safe"
    assert graph.nodes["FL2"].status == "safe"


def test_weather_event_on_a_day_with_no_bookings_finds_nothing(fresh_state):
    graph = fresh_state.graph
    result = apply_weather_event(graph, "2099-01-01", "severe")
    assert result["origins"] == []
    assert result["affected_nodes"] == {}


def test_scan_proactive_risks_flags_only_the_two_genuinely_tight_connections(fresh_state):
    warnings = scan_proactive_risks(fresh_state.graph)
    by_node = {w.node_id: w.severity for w in warnings}

    assert by_node == {"TR1": "medium", "HT1": "high"}
