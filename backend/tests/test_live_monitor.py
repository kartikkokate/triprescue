import asyncio

import app.live_monitor as live_monitor
from app.store import state


def test_tick_escalates_severity_as_the_simulated_delay_grows(monkeypatch):
    """Forces a deterministic upward-only drift (no randomness, no traffic-clears) so
    the medium -> high escalation on a real transfer edge is reproducible."""
    monkeypatch.setattr(live_monitor, "CLEAR_CHANCE", 0.0)
    monkeypatch.setattr(live_monitor, "DRIFT_MIN", 10.0)
    monkeypatch.setattr(live_monitor, "DRIFT_MAX", 10.0)

    async def run_ticks():
        for _ in range(6):
            await live_monitor._tick()

    asyncio.run(run_ticks())

    assert state.live_traffic["FL1->TR1"] > 0
    severities = [e["severity"] for e in state.risk_feed if e["node_id"] == "TR1"]
    assert severities == ["medium", "high"]  # each transition logged exactly once, no repeats


def test_tick_stays_silent_once_a_node_is_already_disrupted(monkeypatch):
    """The live monitor is a forecast layer - once a booking is actually broken/cancelled
    via a real disruption, it should stop adding noise on top of that (for that booking
    specifically - the other watched transfer is untouched and may still fire)."""
    monkeypatch.setattr(live_monitor, "CLEAR_CHANCE", 0.0)
    monkeypatch.setattr(live_monitor, "DRIFT_MIN", 50.0)
    monkeypatch.setattr(live_monitor, "DRIFT_MAX", 50.0)

    state.graph.nodes["TR1"].status = "broken"
    state.graph.nodes["FL2"].status = "broken"  # silence the other watched edge too

    asyncio.run(live_monitor._tick())

    assert state.risk_feed == []


def test_tick_only_watches_transfer_required_edges(monkeypatch):
    monkeypatch.setattr(live_monitor, "CLEAR_CHANCE", 0.0)
    monkeypatch.setattr(live_monitor, "DRIFT_MIN", 50.0)
    monkeypatch.setattr(live_monitor, "DRIFT_MAX", 50.0)

    asyncio.run(live_monitor._tick())

    watched_edge_keys = set(state.live_traffic.keys())
    assert watched_edge_keys == {"FL1->TR1", "TR2->FL2"}
