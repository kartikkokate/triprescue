"""Monte Carlo weather digital twin of the traveler's itinerary and its surrounding
hospitality ecosystem.

For each of N samples:
  1. draw weather at every booking from the (live or what-if) forecast, including forecast
     uncertainty (rain may not happen; intensity, wind and temperature vary)
  2. draw the learned weather -> delay coefficients from the learner's posterior, plus
     cancellation events from the hazard curves
  3. push those delays/cancellations through a COPY of the real itinerary graph using the
     app's own impact engine, so cascades follow the same dependency rules as live
  4. derive ecosystem state per place (road travel time, cab availability, hotel occupancy,
     outdoor/indoor demand, dine-in demand, workforce availability)
The live itinerary is never mutated. Aggregating the samples gives per-booking outcome
probabilities, delay ranges (p10/p50/p90), ecosystem metrics with 80% intervals, and a
first/second/third-order effect chain.
"""
import math

import numpy as np

from app.graph_engine import ItineraryGraph
from app.impact_engine import STATUS_RANK, propagate_disruption
from app.recovery_engine import REFUND_PCT
from app.twin.learner import WeatherImpactLearner, cancel_probability, features

# known city centres; any other trip location becomes its own place (see register_places)
KNOWN_PLACES = {"Goa": (15.4989, 73.8278), "Delhi": (28.6139, 77.2090)}
PLACES: dict[str, tuple[float, float]] = dict(KNOWN_PLACES)
PLACE_RADIUS_KM = 60
WEATHER_TYPES = {"flight", "transfer", "activity"}
MIN_ORIGIN_DELAY = 15  # shorter weather delays are absorbed by normal slack
DEFAULT_SAMPLES = 400
CALM = {"rain_mm_h": 0.0, "precip_prob": 0.0, "temp_c": 28.0, "wind_kmh": 8.0, "gust_kmh": 15.0,
        "storm_hours": 0, "flood_index": 0.0, "social_index": 0.0, "weather_code": 0}
BASE_HOTEL_OCCUPANCY = 0.68  # prior: Goa shoulder-season occupancy in October


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat = math.radians((a[0] + b[0]) / 2)
    return 111.0 * math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(lat))


def register_places(graph: ItineraryGraph) -> None:
    """Groups the trip's coordinates into places (~60 km), reusing known city names, so
    live weather, social signals and the ecosystem are per place for ANY trip."""
    PLACES.clear()
    points = []
    for n in graph.nodes.values():
        loc = n.location or n.title
        if n.lat is not None:
            points.append(((n.lat, n.lon), loc.split(" to ")[0].strip()))
        if n.dest_lat is not None:
            points.append(((n.dest_lat, n.dest_lon), loc.split(" to ")[-1].strip() if " to " in loc else f"{n.title} (arrival)"))
    for coord, label in points:
        if any(_km(coord, c) <= PLACE_RADIUS_KM for c in PLACES.values()):
            continue
        known = next((name for name, c in KNOWN_PLACES.items() if _km(coord, c) <= PLACE_RADIUS_KM), None)
        name = known or label
        while name in PLACES:
            name += "*"
        PLACES[name] = KNOWN_PLACES.get(known, coord) if known else coord


def place_of(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None or not PLACES:
        return None
    return min(PLACES, key=lambda p: _km(PLACES[p], (lat, lon)))


def node_places(node) -> list[str]:
    places = [place_of(node.lat, node.lon), place_of(node.dest_lat, node.dest_lon)]
    return list(dict.fromkeys(p for p in places if p))


def _is_outdoor(node) -> bool:
    return node.type == "activity" and node.weather_sensitive


def _is_weather_node(node) -> bool:
    return node.type in {"flight", "transfer"} or _is_outdoor(node)


def apply_scenario(graph: ItineraryGraph, live: dict[str, dict], scenario: dict) -> dict[str, dict]:
    """Returns per-node conditions after applying the what-if overrides to the targeted
    place/date. Nodes outside the target keep their live forecast."""
    register_places(graph)
    overrides = {k: v for k, v in (scenario.get("overrides") or {}).items() if v is not None}
    place = scenario.get("target_place") or "all"
    date = scenario.get("target_date")
    out = {}
    for nid, node in graph.nodes.items():
        cond = {**CALM, **(live.get(nid) or {})}
        hit_place = place == "all" or place in node_places(node)
        hit_date = not date or node.start.startswith(date) or node.end.startswith(date)
        if overrides and hit_place and hit_date:
            cond.update(overrides)
            if "rain_mm_h" in overrides:
                cond["precip_prob"] = 1.0 if overrides["rain_mm_h"] > 0 else 0.0
        out[nid] = cond
    return out


def _sample_conditions(c: dict, rng: np.random.Generator) -> dict:
    rains = rng.random() < max(c["precip_prob"], 0.05 if c["rain_mm_h"] > 0 else 0.0)
    rain = c["rain_mm_h"] * float(rng.lognormal(0.0, 0.3)) if rains else c["rain_mm_h"] * 0.1
    return {
        **c,
        "rain_mm_h": rain,
        "wind_kmh": max(0.0, c["wind_kmh"] * float(rng.normal(1.0, 0.15))),
        "temp_c": c["temp_c"] + float(rng.normal(0.0, 1.0)),
        "storm_hours": c["storm_hours"] if rains else 0,
    }


def _clone(graph: ItineraryGraph) -> ItineraryGraph:
    return ItineraryGraph([n.model_copy() for n in graph.nodes.values()], list(graph.edges))


def _ecosystem(conds: list[dict], flight_cancel_p: float, rng: np.random.Generator) -> dict:
    """One sample of place-level hospitality state from the worst conditions in that place."""
    rain = max(c["rain_mm_h"] for c in conds)
    flood = max(c["flood_index"] for c in conds)
    wind = max(c["wind_kmh"] for c in conds)
    temp = max(c["temp_c"] for c in conds)
    storm = max(c["storm_hours"] for c in conds) / 6.0
    e = lambda: float(rng.normal(1.0, 0.2))  # elasticity uncertainty
    heat = max(0.0, temp - 36)
    return {
        "road_travel_time_x": 1 + e() * (0.015 * rain + 0.8 * flood + 0.05 * storm),
        "cab_availability": min(1.0, max(0.1, 1 - e() * (0.008 * rain + 0.45 * flood + 0.004 * max(0.0, wind - 30)))),
        "hotel_occupancy": min(1.0, BASE_HOTEL_OCCUPANCY + e() * (0.25 * flight_cancel_p + 0.002 * rain)),
        "outdoor_attraction_demand": max(0.0, math.exp(-0.035 * e() * rain) * (1 - 0.04 * heat) * (1 - 0.5 * flood)),
        "indoor_venue_demand": min(1.8, 1 + e() * (0.012 * rain + 0.03 * heat)),
        "dine_in_restaurant_demand": max(0.2, 1 - e() * (0.006 * rain + 0.3 * flood)),
        "workforce_availability": min(1.0, max(0.3, 1 - e() * (0.35 * flood + 0.003 * rain + 0.01 * max(0.0, temp - 40)))),
    }


def simulate(
    graph: ItineraryGraph,
    conditions: dict[str, dict],
    learner: WeatherImpactLearner,
    n: int = DEFAULT_SAMPLES,
    seed: int | None = 7,
) -> dict:
    register_places(graph)
    rng = np.random.default_rng(seed)
    ids = list(graph.nodes)
    weather_ids = [nid for nid in ids if _is_weather_node(graph.nodes[nid])]
    betas = {t: learner.sample_betas(t, n, rng) for t in WEATHER_TYPES}
    noise = {t: learner.models[t]["noise_sd"] for t in WEATHER_TYPES}

    status_counts = {nid: {"safe": 0, "at_risk": 0, "broken": 0, "cancelled": 0} for nid in ids}
    overruns = {nid: np.zeros(n) for nid in ids}
    origin_delay = {nid: np.zeros(n) for nid in weather_ids}
    cancel_p = {nid: np.zeros(n) for nid in weather_ids}
    any_broken = np.zeros(n, dtype=bool)
    eco_samples: dict[str, list[dict]] = {}

    for s in range(n):
        g = _clone(graph)
        worst = {nid: g.nodes[nid].status for nid in ids}  # the real current state is the floor
        sampled = {}
        origins = []
        for nid in weather_ids:
            node = g.nodes[nid]
            c = _sample_conditions(conditions[nid], rng)
            sampled[nid] = c
            etype = "activity" if node.type == "activity" else node.type
            p = cancel_probability(etype, c, outdoor=_is_outdoor(node))
            cancel_p[nid][s] = p
            if rng.random() < p:
                origins.append((nid, "cancel", 0))
                origin_delay[nid][s] = float("nan")
                continue
            mean = float(features(c) @ betas[etype][s])
            # residual spread grows with how much weather there is to blame - a calm day
            # shouldn't randomly break connections
            spread = noise[etype] * (0.15 + 0.85 * min(1.0, max(0.0, mean) / 30.0))
            d = max(0.0, mean + float(rng.normal(0, spread)))
            origin_delay[nid][s] = d
            if d >= MIN_ORIGIN_DELAY:
                origins.append((nid, "delay", int(round(d))))

        overrun = {nid: 0 for nid in ids}
        for nid, kind, delay in sorted(origins, key=lambda o: g.nodes[o[0]].start):
            report = propagate_disruption(g, nid, kind, delay)
            for rid, info in report.items():
                st = g.nodes[rid].status
                if STATUS_RANK[st] > STATUS_RANK[worst[rid]]:
                    worst[rid] = st
                ov = info.get("overrun_minutes")
                if ov:
                    overrun[rid] = max(overrun[rid], ov)
        for nid in ids:
            status_counts[nid][worst[nid]] += 1
            overruns[nid][s] = overrun[nid]
        any_broken[s] = any(worst[nid] in ("broken", "cancelled") for nid in ids)

        for place in PLACES:
            in_place = [sampled[nid] for nid in weather_ids if place in node_places(graph.nodes[nid])]
            if not in_place:
                continue
            flights = [cancel_p[nid][s] for nid in weather_ids
                       if graph.nodes[nid].type == "flight" and place in node_places(graph.nodes[nid])]
            eco_samples.setdefault(place, []).append(_ecosystem(in_place, float(np.mean(flights)) if flights else 0.0, rng))

    nodes_out = {}
    for nid in ids:
        node = graph.nodes[nid]
        counts = status_counts[nid]
        ov = overruns[nid]
        entry = {
            "id": nid,
            "title": node.title,
            "type": node.type,
            "places": node_places(node),
            "lat": node.lat, "lon": node.lon, "dest_lat": node.dest_lat, "dest_lon": node.dest_lon,
            "current_status": node.status,
            "p_safe": counts["safe"] / n,
            "p_at_risk": counts["at_risk"] / n,
            "p_broken": (counts["broken"] + counts["cancelled"]) / n,
            "p_cancelled": counts["cancelled"] / n,
            "delay_p10": float(np.percentile(ov, 10)),
            "delay_p50": float(np.percentile(ov, 50)),
            "delay_p90": float(np.percentile(ov, 90)),
            "most_likely": max(counts, key=counts.get),
            "weather": {k: round(float(v), 2) for k, v in conditions[nid].items() if isinstance(v, (int, float))},
            "weather_exposed": nid in weather_ids,
        }
        if nid in weather_ids:
            etype = "activity" if node.type == "activity" else node.type
            contrib = learner.contributions(etype, conditions[nid])
            top = max(contrib, key=contrib.get)
            entry["p_weather_cancel"] = float(np.mean(cancel_p[nid]))
            entry["top_driver"] = top if contrib[top] >= 5 else None
        nodes_out[nid] = entry

    ecosystem = {}
    for place, samples in eco_samples.items():
        ecosystem[place] = {
            k: {
                "mean": round(float(np.mean([x[k] for x in samples])), 3),
                "p10": round(float(np.percentile([x[k] for x in samples], 10)), 3),
                "p90": round(float(np.percentile([x[k] for x in samples], 90)), 3),
            }
            for k in samples[0]
        }

    expected_loss = sum(
        e["p_broken"] * graph.nodes[nid].cost * (1 - REFUND_PCT.get(graph.nodes[nid].cancellation_policy, 0.0))
        for nid, e in nodes_out.items()
    )
    return {
        "samples": n,
        "nodes": nodes_out,
        "ecosystem": ecosystem,
        "trip": {
            "p_any_disruption": round(float(np.mean(any_broken)), 3),
            "expected_loss_inr": round(float(expected_loss), 0),
            "expected_extra_minutes": round(float(np.mean([max(overruns[nid][s] for nid in ids) for s in range(n)])), 1),
        },
        "effect_chain": effect_chain(graph, nodes_out, ecosystem),
    }


def effect_chain(graph: ItineraryGraph, nodes: dict, ecosystem: dict, threshold: float = 0.1) -> list[dict]:
    """First-order (weather -> booking), second-order (booking -> dependent booking via the
    itinerary graph) and third-order (ecosystem -> recovery options) effects."""
    chain = []
    affected = lambda nid: nodes[nid]["p_broken"] + nodes[nid]["p_at_risk"]
    already = {nid for nid, e in nodes.items() if e["current_status"] in ("broken", "cancelled")}
    for nid in already:
        # broken by a real (non-weather) disruption: say so instead of blaming the weather
        e = nodes[nid]
        chain.append({
            "order": 0, "from": "active disruption", "to": nid,
            "effect": f"{e['title']}: already {e['current_status']} by the disruption you applied - recover it in the Recovery Console",
            "probability": 1.0,
            "driver": None,
        })
    for nid, e in nodes.items():
        if nid not in already and e["weather_exposed"] and affected(nid) >= threshold:
            chain.append({
                "order": 1, "from": "weather@" + "/".join(e["places"]), "to": nid,
                "effect": (f"{e['title']}: p50 +{e['delay_p50']:.0f} min (p90 +{e['delay_p90']:.0f})"
                           + (f", {e['p_weather_cancel']:.0%} cancel risk" if e.get("p_weather_cancel", 0) >= 0.05 else "")),
                "probability": round(affected(nid), 3),
                "driver": e.get("top_driver"),
            })
    for edge in graph.edges:
        if edge.target in already:
            continue
        if affected(edge.source) >= threshold and affected(edge.target) >= threshold and not (
            nodes[edge.target]["weather_exposed"] and affected(edge.target) <= affected(edge.source) * 0.5
        ):
            chain.append({
                "order": 2, "from": edge.source, "to": edge.target,
                "effect": f"{nodes[edge.target]['title']} {edge.type.replace('_', ' ')} squeezed "
                          f"({edge.buffer_minutes} min buffer) - most likely {nodes[edge.target]['most_likely'].replace('_', ' ')}",
                "probability": round(min(affected(edge.source), affected(edge.target)), 3),
            })
    for place, eco in ecosystem.items():
        if eco["hotel_occupancy"]["mean"] >= BASE_HOTEL_OCCUPANCY + 0.03:
            chain.append({"order": 3, "from": f"flights@{place}", "to": f"hotels@{place}",
                          "effect": f"stranded travelers push hotel occupancy to {eco['hotel_occupancy']['mean']:.0%} - fewer alternate rooms, higher rebooking cost",
                          "probability": round(min(1.0, (eco['hotel_occupancy']['mean'] - BASE_HOTEL_OCCUPANCY) * 5), 3)})
        if eco["cab_availability"]["mean"] <= 0.85:
            chain.append({"order": 3, "from": f"roads@{place}", "to": f"transfers@{place}",
                          "effect": f"cab availability down to {eco['cab_availability']['mean']:.0%}, road time x{eco['road_travel_time_x']['mean']:.2f} - transfer recovery options slower and pricier",
                          "probability": round(1 - eco["cab_availability"]["mean"], 3)})
        if eco["outdoor_attraction_demand"]["mean"] <= 0.8:
            chain.append({"order": 3, "from": f"attractions@{place}", "to": f"indoor@{place}",
                          "effect": f"outdoor demand at {eco['outdoor_attraction_demand']['mean']:.0%}, indoor venues at {eco['indoor_venue_demand']['mean']:.0%} - indoor alternatives fill up",
                          "probability": round(1 - eco["outdoor_attraction_demand"]["mean"], 3)})
        if eco["workforce_availability"]["mean"] <= 0.85:
            chain.append({"order": 3, "from": f"workforce@{place}", "to": f"operations@{place}",
                          "effect": f"staff availability {eco['workforce_availability']['mean']:.0%} - slower check-ins and service",
                          "probability": round(1 - eco["workforce_availability"]["mean"], 3)})
    return sorted(chain, key=lambda c: (c["order"], -c["probability"]))


def plan_success(plans: list, sim: dict, graph: ItineraryGraph) -> dict[str, dict]:
    """Twin-aware recovery: probability each recovery plan's replacement options hold up
    under the simulated conditions (improves the existing recovery ranking)."""
    out = {}
    for plan in plans:
        p_ok, risks = 1.0, []
        for opt in plan.options:
            node = graph.nodes.get(opt.node_id)
            if node is None:
                continue
            eco = next((sim["ecosystem"][p] for p in node_places(node) if p in sim["ecosystem"]), None)
            title = opt.replacement_title.lower()
            fail = 0.0
            if node.type == "transfer" and eco:
                fail = 1 - eco["cab_availability"]["mean"] if ("cab" in title or "shuttle" in title) else (1 - eco["cab_availability"]["mean"]) * 0.4
            elif node.type == "hotel" and eco and "alternate" in title:
                fail = max(0.0, (eco["hotel_occupancy"]["mean"] - 0.75) * 3)
            elif node.type in ("flight", "activity"):
                fail = sim["nodes"][node.id].get("p_weather_cancel", 0.0) * (0.3 if "indoor" in title else 1.0)
            fail = min(0.95, fail)
            if fail >= 0.05:
                risks.append(f"{opt.replacement_title}: {fail:.0%} risk")
            p_ok *= 1 - fail
        out[plan.id] = {"p_success": round(p_ok, 3), "risks": risks}
    return out

