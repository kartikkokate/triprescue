from app.impact_engine import propagate_disruption, apply_weather_event
from app.recovery_engine import generate_recovery_plans, apply_plan
from app.models import TravelerPreferences
import pytest


def _delayed_flight_state(fresh_state):
    propagate_disruption(fresh_state.graph, "FL1", "delay", 180)
    return fresh_state


def test_no_plans_when_nothing_is_broken(fresh_state):
    assert generate_recovery_plans(fresh_state.graph) == []


DELAY = {"node_id": "FL1", "kind": "delay", "delay_minutes": 180, "reason": "unspecified"}


def test_plans_are_organized_into_balanced_cheapest_fastest_and_alternatives(fresh_state):
    state = _delayed_flight_state(fresh_state)
    plans = generate_recovery_plans(state.graph, disruption=DELAY)

    assert plans[0].id == "plan-balanced" and "balanced" in plans[0].badges
    badges = {b for p in plans for b in p.badges}
    assert {"balanced", "cheapest", "fastest"} <= badges
    cheapest = next(p for p in plans if "cheapest" in p.badges)
    fastest = next(p for p in plans if "fastest" in p.badges)
    assert cheapest.total_cost_delta == min(p.total_cost_delta for p in plans)
    assert fastest.total_time_delta_minutes == min(p.total_time_delta_minutes for p in plans)
    assert any(p.category == "alternative" for p in plans)


def test_score_is_explainable(fresh_state):
    state = _delayed_flight_state(fresh_state)
    for p in generate_recovery_plans(state.graph, disruption=DELAY):
        parts = p.score_breakdown
        assert set(parts) == {"cost", "time", "convenience", "disruption"}
        assert sum(v["contribution"] for v in parts.values()) == pytest.approx(p.score, abs=0.2)
        assert sum(v["weight"] for v in parts.values()) == pytest.approx(1.0, abs=0.01)


def test_cost_only_preference_makes_cheapest_the_balanced_pick(fresh_state):
    state = _delayed_flight_state(fresh_state)
    prefs = TravelerPreferences(cost_weight=1, time_weight=0, convenience_weight=0, disruption_weight=0)
    plans = generate_recovery_plans(state.graph, preferences=prefs, disruption=DELAY)

    assert plans[0].total_cost_delta == min(p.total_cost_delta for p in plans)
    assert "cheapest" in plans[0].badges


def test_keeping_the_delayed_booking_is_an_option_with_no_refund(fresh_state):
    state = _delayed_flight_state(fresh_state)
    plans = generate_recovery_plans(state.graph, disruption=DELAY)
    keep = [p for p in plans if any(o.node_id == "FL1" and o.action == "keep" for o in p.options)]

    assert keep, "staying on the delayed flight should be offered"
    assert all(p.money["cash_refund"] == 0 for p in keep)


def test_provider_cancellation_makes_same_airline_reschedule_free_and_refunds_in_full(fresh_state):
    propagate_disruption(fresh_state.graph, "FL1", "cancel", 0)
    plans = generate_recovery_plans(fresh_state.graph)
    reschedules = [o for p in plans for o in p.options if o.node_id == "FL1" and o.action == "reschedule"]
    rebooks = [p for p in plans if any(o.node_id == "FL1" and o.action == "rebook" for o in p.options)]

    assert reschedules and all(o.cost == 0 for o in reschedules)
    assert all(p.money["cash_refund"] >= 4500 for p in rebooks)  # full IndiGo fare back


def test_late_checkin_keeps_the_hotel_without_a_fake_refund(fresh_state):
    propagate_disruption(fresh_state.graph, "FL1", "cancel", 0)
    plans = generate_recovery_plans(fresh_state.graph)
    for p in plans:
        ht1 = next(o for o in p.options if o.node_id == "HT1")
        if ht1.action == "keep":
            assert p.money["cash_refund"] <= 4500  # only the airline refund, never the hotel's


def test_free_cancellation_does_not_apply_inside_24_hours():
    from datetime import datetime

    from app.models import BookingNode
    from app.money import refund_for

    hotel = BookingNode(id="H", type="hotel", title="H", location="x", start="2026-10-10T14:00:00",
                        end="2026-10-10T14:30:00", cost=9000, provider="p", cancellation_policy="free_24h", status="broken")
    assert refund_for(hotel, datetime(2026, 10, 8, 12))["cash_refund"] == 9000  # 50 h before
    assert refund_for(hotel, datetime(2026, 10, 10, 10))["cash_refund"] == 0  # 4 h before


def test_user_entered_penalty_and_credit_refunds():
    from app.models import BookingNode
    from app.money import refund_for

    flight = BookingNode(id="F", type="flight", title="F", location="x", start="2026-10-10T10:00:00",
                         end="2026-10-10T12:00:00", cost=6000, provider="p", cancellation_policy="non_refundable",
                         cancellation_penalty=1500, refund_mode="credit", status="broken")
    r = refund_for(flight)
    assert (r["penalty"], r["credit"], r["cash_refund"]) == (1500, 4500, 0)


def test_infeasible_combinations_are_rejected_with_a_reason(fresh_state):
    from app.recovery_engine import recovery_analysis

    propagate_disruption(fresh_state.graph, "AC1", "cancel", 0)
    analysis = recovery_analysis(fresh_state.graph, "operator_cancellation")
    assert analysis["feasible"] < analysis["combinations_checked"]
    assert any("miss Water Sports Session" in r for r in analysis["infeasible_examples"])


def test_convenience_only_preference_ranks_most_convenient_first(fresh_state):
    state = _delayed_flight_state(fresh_state)
    prefs = TravelerPreferences(cost_weight=0, time_weight=0, convenience_weight=1, disruption_weight=0)
    plans = generate_recovery_plans(state.graph, preferences=prefs)

    assert plans[0].convenience_score == max(p.convenience_score for p in plans)


def test_min_rating_filter_excludes_low_rated_alternatives(fresh_state):
    state = _delayed_flight_state(fresh_state)
    prefs = TravelerPreferences(min_rating=85)
    plans = generate_recovery_plans(state.graph, preferences=prefs)

    tr1_choices = {o.replacement_title for p in plans for o in p.options if o.node_id == "TR1"}
    # of TR1's alternatives (78, 55, 90 rated), only the 90-rated one clears the bar
    assert tr1_choices == {"Hotel Pickup Service"}


NEXT_DAY_TITLES = {"Next-Day Beach Tour", "Water Sports (next day)", "Next-Day IndiGo Flight"}


def test_same_day_options_named_next_are_not_treated_as_next_day():
    from app.recovery_engine import _is_next_day

    assert not _is_next_day({"title": "Express Cab (next available)", "notes": "Pickup within 20 min"})
    assert not _is_next_day({"title": "Next IndiGo Flight GOI -> DEL", "notes": "Same day, 3 hours later"})
    assert _is_next_day({"title": "Next-Day IndiGo Flight", "notes": "loses a travel day", "next_day": True})


def test_avoid_next_day_filter_excludes_next_day_pushes(fresh_state):
    state = fresh_state
    propagate_disruption(state.graph, "TR2", "cancel", 0)
    propagate_disruption(state.graph, "FL2", "cancel", 0)
    prefs = TravelerPreferences(avoid_next_day=True)
    plans = generate_recovery_plans(state.graph, preferences=prefs)

    for p in plans:
        for o in p.options:
            if o.node_id == "FL2":
                assert o.replacement_title not in NEXT_DAY_TITLES


def test_weather_reason_forces_indoor_alternatives_and_dedupes_identical_plans(fresh_state):
    state = fresh_state
    apply_weather_event(state.graph, "2026-10-11", "severe")
    plans = generate_recovery_plans(state.graph, disruption_reason="weather (severe) on 2026-10-11")

    # every strategy is forced into the same single weather-safe candidate per node,
    # so all four canned strategies collapse into one deduped plan
    assert len(plans) == 1
    options_by_node = {o.node_id: o.replacement_title for o in plans[0].options}
    assert options_by_node == {
        "AC1": "Indoor Spice Plantation & Museum Tour",
        "AC2": "Indoor Water Park (covered)",
    }


def test_non_weather_reason_does_not_force_indoor_alternatives(fresh_state):
    state = fresh_state
    propagate_disruption(state.graph, "AC1", "cancel", 0)
    plans = generate_recovery_plans(state.graph, disruption_reason="operator_cancellation")

    ac1_choices = {o.replacement_title for p in plans for o in p.options if o.node_id == "AC1"}
    # outdoor options stay on the table (the afternoon slot is rejected only because it
    # clashes with the 15:00 water sports session, not because of weather)
    assert "Next-Day Beach Tour" in ac1_choices


def test_apply_plan_records_replacements_but_never_books(fresh_state):
    state = _delayed_flight_state(fresh_state)
    plans = generate_recovery_plans(state.graph, disruption=DELAY)
    plan = next(p for p in plans if any(o.action == "rebook" for o in p.options))
    apply_plan(state.graph, plan)

    assert all(n.status == "safe" for n in state.graph.nodes.values())
    fl1 = state.graph.nodes["FL1"]
    assert "(Recovered)" in fl1.title
    assert fl1.booking_status == "pending_manual_booking"
    assert any("does not book or pay" in a for a in plan.action_items)


def test_cab_replacements_always_need_manual_booking(fresh_state):
    state = _delayed_flight_state(fresh_state)
    for p in generate_recovery_plans(state.graph, disruption=DELAY):
        tr1 = next(o for o in p.options if o.node_id == "TR1")
        assert tr1.requires_manual_booking and tr1.action == "manual_booking"


def test_booking_without_alternatives_gets_labelled_estimate_templates(fresh_state):
    for n in fresh_state.graph.nodes.values():
        n.alternatives = []
    propagate_disruption(fresh_state.graph, "FL1", "cancel", 0)
    plans = generate_recovery_plans(fresh_state.graph)

    assert plans
    sources = {o.price_source for p in plans for o in p.options}
    assert "estimate" in sources
    assert all(o.market_price is None and "unavailable" in o.market_price_source for p in plans for o in p.options)


def test_hotel_cancelled_by_hotel_is_never_kept(fresh_state):
    propagate_disruption(fresh_state.graph, "HT1", "cancel", 0)
    plans = generate_recovery_plans(fresh_state.graph, disruption={"node_id": "HT1", "kind": "cancel", "reason": "overbooked"})
    assert plans
    assert all(o.action != "keep" for p in plans for o in p.options if o.node_id == "HT1")


def test_traveler_initiated_cancel_follows_fare_rules_not_provider_rules(fresh_state):
    propagate_disruption(fresh_state.graph, "FL2", "cancel", 0)
    mine = {"node_id": "FL2", "kind": "cancel", "reason": "traveler_request"}
    airline = {"node_id": "FL2", "kind": "cancel", "reason": "operator_cancellation"}

    own = generate_recovery_plans(fresh_state.graph, disruption=mine)
    theirs = generate_recovery_plans(fresh_state.graph, disruption=airline)

    own_resched = [o for p in own for o in p.options if o.action == "reschedule" and "Next IndiGo" in o.replacement_title]
    their_resched = [o for p in theirs for o in p.options if o.action == "reschedule" and "Next IndiGo" in o.replacement_title]
    assert own_resched and own_resched[0].cost > 0  # change fee is on the traveler
    assert their_resched and their_resched[0].cost == 0  # airline must re-accommodate free
    own_rebook = next(p for p in own if any(o.action == "rebook" for o in p.options))
    assert own_rebook.money["cash_refund"] == 2400  # 50% fare rule, not a full refund


def test_traveler_rights_for_own_cancellation_have_no_dgca_claim(fresh_state):
    from app.advisor_knowledge import rights_answer

    propagate_disruption(fresh_state.graph, "FL2", "cancel", 0)
    text = rights_answer({"node_id": "FL2", "kind": "cancel", "reason": "traveler_request"}, {}, fresh_state.graph)
    assert "do not apply" in text and "compensation of INR" not in text


USER_TRIP = {
    "name": "Pune to Indore",
    "geocode": False,
    "bookings": [
        {"type": "flight", "title": "PUNE TO NAGPUR", "start": "2027-02-15T20:00:00", "end": "2027-02-15T23:00:00", "cost": 5000,
         "location": "PUNE", "destination": "NAGPUR", "lat": 18.52, "lon": 73.85, "dest_lat": 21.15, "dest_lon": 79.09},
        {"type": "train", "title": "NAGPUR TO JABALPUR", "start": "2027-02-16T20:00:00", "end": "2027-02-17T04:00:00", "cost": 2000,
         "location": "NAGPUR", "destination": "JABALPUR", "lat": 21.15, "lon": 79.09, "dest_lat": 23.18, "dest_lon": 79.99},
        {"type": "transfer", "title": "JABALPUR TO INDORE", "start": "2027-02-17T06:00:00", "end": "2027-02-17T23:00:00", "cost": 1000,
         "location": "JABALPUR", "destination": "INDORE", "lat": 23.18, "lon": 79.99, "dest_lat": 22.72, "dest_lon": 75.86},
        {"type": "hotel", "title": "ARAB", "start": "2027-02-18T04:00:00", "end": "2027-02-19T06:00:00", "cost": 2000,
         "cancellation_policy": "free_24h", "location": "INDORE", "lat": 22.72, "lon": 75.86},
        {"type": "activity", "title": "CITY TOUR", "start": "2027-02-19T20:00:00", "end": "2027-02-20T02:00:00", "cost": 500,
         "location": "INDORE", "lat": 22.72, "lon": 75.86},
    ],
}


def test_every_delayed_booking_keeps_its_keep_option_when_disruptions_stack(client):
    client.post("/api/itinerary", json=USER_TRIP)
    client.post("/api/disrupt", json={"node_id": "B1", "kind": "delay", "delay_minutes": 180, "reason": "air traffic"})
    client.post("/api/disrupt", json={"node_id": "B3", "kind": "delay", "delay_minutes": 45, "reason": "traffic"})
    plans = client.get("/api/recovery-plans").json()["plans"]
    assert plans
    kept = {o["node_id"] for p in plans for o in p["options"] if o["action"] == "keep"}
    assert {"B1", "B3"} <= kept  # the earlier flight delay is not forgotten
    best = plans[0]
    b1 = next((o for o in best["options"] if o["node_id"] == "B1"), None)
    # a 3 h flight delay that breaks nothing downstream: just stay on it, don't buy a new flight
    assert b1 is None or b1["action"] == "keep"


def test_undo_clears_all_stacked_disruptions(client):
    client.post("/api/itinerary", json=USER_TRIP)
    client.post("/api/disrupt", json={"node_id": "B1", "kind": "delay", "delay_minutes": 180, "reason": "x"})
    client.post("/api/disrupt", json={"node_id": "B3", "kind": "delay", "delay_minutes": 45, "reason": "x"})
    client.post("/api/reset")
    assert all(n["status"] == "safe" for n in client.get("/api/itinerary").json()["nodes"])
    assert client.get("/api/recovery-plans").json()["plans"] == []
