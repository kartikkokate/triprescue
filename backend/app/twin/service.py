"""The digital twin as a service inside the existing app.

- `refresh()` pulls live weather (Open-Meteo), flood (GloFAS) and social signals for every
  place the trip touches, re-simulates the live itinerary and keeps a rolling history of
  snapshots - run on a timer by `twin_loop()` and pushed over the existing risk-feed websocket.
- `what_if()` runs a counterfactual scenario on a copy of the itinerary.
- `observe()` feeds a real observation into the learner (continuous learning).
- `promote()` turns a scenario's most likely outcome into a real disruption, handing it to
  the existing recovery-plan flow.
"""
import asyncio
import math
from datetime import datetime, timezone

from app.impact_engine import STATUS_RANK, propagate_disruption
from app.twin import social, weather
from app.twin.learner import learner
from app.twin.simulator import PLACES, apply_scenario, node_places, register_places, simulate

REFRESH_SECONDS = 600
HISTORY_LIMIT = 48
SOCIAL_DECAY_DAYS = 1.5  # social reports describe conditions now; their relevance fades with lead time


def social_weight(booking_start: str, now: datetime | None = None) -> float:
    now = now or datetime.now()
    lead_days = max(0.0, (datetime.fromisoformat(booking_start) - now).total_seconds() / 86400)
    return math.exp(-lead_days / SOCIAL_DECAY_DAYS)


class TwinService:
    def __init__(self):
        self.snapshot: dict | None = None
        self.history: list[dict] = []
        self.live_inputs: dict = {}

    # --- live data --------------------------------------------------------------

    def collect_live(self, graph) -> dict:
        """Per-node live conditions + per-place current weather and social signals."""
        register_places(graph)
        places_used = sorted({p for n in graph.nodes.values() for p in node_places(n)})
        place_info = {}
        for place in places_used:
            lat, lon = PLACES[place]
            fc = weather.fetch_forecast(lat, lon)
            place_info[place] = {
                "lat": lat, "lon": lon,
                "current": weather.current_conditions(fc),
                "forecast_live": fc is not None,
                "social": social.fetch_signals(place),
            }

        node_conditions, sources = {}, {"forecast_points": 0, "beyond_horizon": 0}
        for nid, node in graph.nodes.items():
            points = [(node.lat, node.lon, node.start)]
            if node.dest_lat is not None:
                points.append((node.dest_lat, node.dest_lon, node.end))
            merged = None
            for lat, lon, when in points:
                if lat is None:
                    continue
                c = weather.conditions_at(weather.fetch_forecast(lat, lon), when)
                if c is None:
                    sources["beyond_horizon"] += 1
                    continue
                sources["forecast_points"] += 1
                c["flood_index"] = weather.flood_index(weather.fetch_flood(lat, lon), when[:10])
                merged = c if merged is None else {
                    k: max(merged[k], c[k]) if isinstance(c[k], (int, float)) else merged[k] for k in c
                }
            if merged is not None:
                raw = max(
                    (place_info[p]["social"]["social_index"] for p in node_places(node) if p in place_info), default=0.0
                )
                merged["social_index"] = round(raw * social_weight(node.start), 3)
                node_conditions[nid] = merged
        return {"nodes": node_conditions, "places": place_info, "sources": sources}

    @staticmethod
    def signature(graph) -> str:
        """Changes whenever the itinerary does (a disruption, a reset, an applied plan)."""
        nodes = "|".join(f"{n.id}:{n.status}:{n.start}:{n.end}:{n.title}" for n in graph.nodes.values())
        # connections too: re-wiring the same bookings changes every cascade
        edges = "|".join(sorted(f"{e.source}>{e.target}:{e.type}:{e.buffer_minutes}" for e in graph.edges))
        return f"{nodes}#{edges}"

    def _simulate_live(self, graph) -> dict:
        result = simulate(graph, apply_scenario(graph, self.live_inputs["nodes"], {}), learner)
        self.snapshot = {"updated_at": datetime.now(timezone.utc).isoformat(), "scenario": {"mode": "live"}, **result,
                         "places": self.live_inputs["places"], "sources": self.live_inputs["sources"],
                         "_signature": self.signature(graph)}
        return result

    def refresh(self, graph) -> dict:
        self.live_inputs = self.collect_live(graph)
        result = self._simulate_live(graph)
        now = self.snapshot["updated_at"]
        self.history.append({
            "at": now,
            "p_any_disruption": result["trip"]["p_any_disruption"],
            "expected_loss_inr": result["trip"]["expected_loss_inr"],
            "max_rain_mm_h": max((c.get("rain_mm_h", 0) for c in self.live_inputs["nodes"].values()), default=0),
        })
        self.history = self.history[-HISTORY_LIMIT:]
        return self.snapshot

    def ensure_live(self, graph) -> dict:
        """The live twin always mirrors the CURRENT itinerary: if the trip changed since the
        last snapshot, re-simulate on the cached live inputs (no new API calls); if the set
        of bookings changed, re-collect."""
        if self.snapshot is None or set(self.snapshot["nodes"]) != set(graph.nodes):
            return self.refresh(graph)
        if self.snapshot.get("_signature") != self.signature(graph):
            self._simulate_live(graph)
        return self.snapshot

    # --- what-if / counterfactual -------------------------------------------------

    def what_if(self, graph, scenario: dict) -> dict:
        self.ensure_live(graph)
        live = self.live_inputs["nodes"]
        scenario_result = simulate(graph, apply_scenario(graph, live, scenario), learner)
        baseline = self.snapshot
        delta = {
            nid: round((e["p_broken"] + e["p_at_risk"]) - (baseline["nodes"][nid]["p_broken"] + baseline["nodes"][nid]["p_at_risk"]), 3)
            for nid, e in scenario_result["nodes"].items() if nid in baseline["nodes"]
        }
        return {
            "scenario": scenario,
            **scenario_result,
            "baseline_trip": baseline["trip"],
            "delta_vs_live": delta,
            "places": baseline["places"],
        }

    # --- continuous learning --------------------------------------------------------

    def observe(self, graph, node_id: str, delay_minutes: float, source: str, conditions: dict | None = None) -> dict:
        node = graph.nodes[node_id]
        etype = "activity" if node.type == "activity" else node.type
        if etype not in learner.models:
            raise ValueError(f"{node.type} bookings have no weather-delay model")
        if conditions is None:
            self.ensure_live(graph)
            conditions = self.live_inputs["nodes"].get(node_id) or {}
        record = learner.observe(etype, conditions, delay_minutes, source)
        record["node_id"] = node_id
        return record

    # --- twin -> real system ----------------------------------------------------------

    def promote(self, graph, sim: dict) -> dict:
        """Applies the scenario's most likely outcome to the REAL itinerary."""
        report, origins = {}, []
        for nid, e in sim["nodes"].items():
            if not e["weather_exposed"]:
                continue
            if e["p_cancelled"] >= 0.5:
                origins.append((nid, "cancel", 0))
            elif e["delay_p50"] >= 15:
                origins.append((nid, "delay", int(e["delay_p50"])))
        worst = {nid: n.status for nid, n in graph.nodes.items()}
        for nid, kind, delay in sorted(origins, key=lambda o: graph.nodes[o[0]].start):
            for rid, info in propagate_disruption(graph, nid, kind, delay).items():
                report[rid] = info
                if STATUS_RANK[graph.nodes[rid].status] > STATUS_RANK[worst[rid]]:
                    worst[rid] = graph.nodes[rid].status
        for nid, st in worst.items():
            graph.nodes[nid].status = st
        return {"impact_report": report, "origins": [{"node_id": n, "kind": k, "delay_minutes": d} for n, k, d in origins]}


twin = TwinService()


async def twin_loop(get_graph, broadcast):
    """Continuously re-estimates the live twin as new weather/social data arrives."""
    while True:
        try:
            snap = await asyncio.to_thread(twin.refresh, get_graph())
            await broadcast({
                "type": "twin_update",
                "updated_at": snap["updated_at"],
                "trip": snap["trip"],
                "history": twin.history[-12:],
            })
        except Exception:
            pass
        await asyncio.sleep(REFRESH_SECONDS)
