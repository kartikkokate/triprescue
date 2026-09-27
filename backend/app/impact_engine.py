"""Impact propagation: given a disruption on one node, walk the dependency graph
downstream and figure out which bookings are still safe, at risk, or broken.

Heuristic (kept simple and explainable for a hackathon demo):
- Each node has a "flex" tolerance based on its type. Fixed-slot bookings
  (flight/train/transfer/activity/event) have near-zero flex: once their
  effective start time overruns the original slot, they're at risk/broken.
  Hotels are flexible: late arrival just shifts check-in, rarely "breaks".
- We compute an "overrun" at each node = how many minutes late it would
  effectively start, given the delay pushed by its predecessor(s) minus the
  buffer already built into that edge.
- Status thresholds turn overrun into safe / at_risk / broken.
"""
from datetime import datetime, timedelta
from app.models import BookingNode, RiskWarning
from app.graph_engine import ItineraryGraph

FIXED_SLOT_TYPES = {"flight", "train", "transfer", "activity", "event"}

# edge types that represent a hard logistics blocker (you physically cannot proceed
# without it) - a cancellation cascades "broken" through these. "sequential"/"same_day"
# edges are soft scheduling buffers between otherwise-independent bookings (e.g. two
# same-day activities): cancelling one doesn't cascade through those - it just frees up time.
BLOCKING_EDGE_TYPES = {"transfer_required", "checkin_dependency"}

# minutes of overrun before a fixed-slot booking flips at_risk -> broken
FIXED_AT_RISK_THRESHOLD = 0
FIXED_BROKEN_THRESHOLD = 30

# hotels are flexible: only escalate for very large overruns (missed whole day)
HOTEL_AT_RISK_THRESHOLD = 0
HOTEL_BROKEN_THRESHOLD = 12 * 60


def _parse(dt: str) -> datetime:
    return datetime.fromisoformat(dt)


def _status_for_overrun(node_type: str, overrun_minutes: int) -> str:
    if node_type == "hotel":
        if overrun_minutes <= HOTEL_AT_RISK_THRESHOLD:
            return "safe"
        if overrun_minutes <= HOTEL_BROKEN_THRESHOLD:
            return "at_risk"
        return "broken"
    # fixed-slot types
    if overrun_minutes <= FIXED_AT_RISK_THRESHOLD:
        return "safe"
    if overrun_minutes <= FIXED_BROKEN_THRESHOLD:
        return "at_risk"
    return "broken"


def propagate_disruption(
    graph: ItineraryGraph,
    node_id: str,
    kind: str,
    delay_minutes: int = 0,
) -> dict[str, dict]:
    """Mutates node.status in place and returns a report of {node_id: {overrun, new_start, new_end}}."""
    report: dict[str, dict] = {}

    origin = graph.nodes[node_id]

    if kind == "cancel":
        origin.status = "cancelled"
        report[node_id] = {"overrun_minutes": None, "new_start": None, "new_end": None}
        # cascade "broken" only through hard blockers - successors reachable solely via
        # soft scheduling edges (sequential/same_day) simply proceed as originally planned
        frontier = [e.target for e in graph.successors(node_id) if e.type in BLOCKING_EDGE_TYPES]
        visited = {node_id}
        while frontier:
            next_frontier = []
            for target_id in frontier:
                if target_id in visited:
                    continue
                visited.add(target_id)
                target = graph.nodes[target_id]
                target.status = "broken"
                report[target_id] = {"overrun_minutes": None, "new_start": None, "new_end": None}
                for e in graph.successors(target_id):
                    if e.type in BLOCKING_EDGE_TYPES:
                        next_frontier.append(e.target)
            frontier = next_frontier
        return report

    # delay case: compute effective new_end for the origin, then walk downstream
    new_start = _parse(origin.start) + timedelta(minutes=delay_minutes)
    new_end = _parse(origin.end) + timedelta(minutes=delay_minutes)
    origin.status = "safe" if delay_minutes <= 0 else _status_for_overrun(origin.type, delay_minutes)
    report[node_id] = {
        "overrun_minutes": delay_minutes,
        "new_start": new_start.isoformat(),
        "new_end": new_end.isoformat(),
    }

    effective_end = {node_id: new_end}
    order = graph.topological_order_from(node_id)

    for current_id in order:
        for edge in graph.successors(current_id):
            target = graph.nodes[edge.target]
            pred_end = effective_end.get(current_id)
            if pred_end is None:
                continue
            required_start = pred_end + timedelta(minutes=edge.buffer_minutes)
            original_start = _parse(target.start)
            overrun = max(0, int((required_start - original_start).total_seconds() // 60))

            # combine with any overrun already computed for this node via another path
            prior = report.get(edge.target)
            if prior and prior.get("overrun_minutes") is not None:
                overrun = max(overrun, prior["overrun_minutes"])

            status = _status_for_overrun(target.type, overrun)
            target.status = status

            target_new_start = original_start + timedelta(minutes=overrun)
            duration = _parse(target.end) - _parse(target.start)
            target_new_end = target_new_start + duration

            report[edge.target] = {
                "overrun_minutes": overrun,
                "new_start": target_new_start.isoformat(),
                "new_end": target_new_end.isoformat(),
            }
            effective_end[edge.target] = target_new_end

    return report


STATUS_RANK = {"safe": 0, "at_risk": 1, "broken": 2, "cancelled": 3}

# how much a weather event delays a same-day transfer (wet roads, traffic) even
# when the transfer itself isn't outdoor/weather_sensitive
TRANSFER_WEATHER_DELAY_MINUTES = {"moderate": 30, "severe": 60}
ACTIVITY_MODERATE_WEATHER_DELAY_MINUTES = 180  # pushed later same day, hoping it clears


def apply_weather_event(graph: ItineraryGraph, date: str, severity: str) -> dict:
    """A weather event isn't anchored to one booking - it can hit several bookings on
    the same day at once (outdoor activities, same-day transfers). Runs each affected
    booking's disruption through the normal propagation, then reconciles so that the
    worst status any origin caused for a shared downstream node "wins" regardless of
    call order.
    """
    origins: list[tuple[str, str, int]] = []
    for node in graph.nodes.values():
        if not node.start.startswith(date):
            continue
        if node.type == "activity" and node.weather_sensitive:
            if severity == "severe":
                origins.append((node.id, "cancel", 0))
            else:
                origins.append((node.id, "delay", ACTIVITY_MODERATE_WEATHER_DELAY_MINUTES))
        elif node.type == "transfer":
            origins.append((node.id, "delay", TRANSFER_WEATHER_DELAY_MINUTES[severity]))

    merged_report: dict[str, dict] = {}
    worst_status: dict[str, str] = {}

    for node_id, kind, delay in origins:
        report = propagate_disruption(graph, node_id, kind, delay)
        for nid, info in report.items():
            merged_report[nid] = info
            current_status = graph.nodes[nid].status
            if nid not in worst_status or STATUS_RANK[current_status] > STATUS_RANK[worst_status[nid]]:
                worst_status[nid] = current_status

    # a later origin's call may have "improved" a node's status from an earlier
    # origin's worse outcome - restore whichever was worst across all origins
    for nid, status in worst_status.items():
        graph.nodes[nid].status = status

    return {
        "affected_nodes": merged_report,
        "origins": [{"node_id": n, "kind": k, "delay_minutes": d} for n, k, d in origins],
    }


def scan_proactive_risks(graph: ItineraryGraph, tight_buffer_threshold_minutes: int = 45) -> list[RiskWarning]:
    """Flag connections whose buffer is naturally thin, independent of any live disruption —
    these are the ones most likely to break if even a small delay hits upstream."""
    warnings: list[RiskWarning] = []
    for edge in graph.edges:
        if edge.buffer_minutes <= tight_buffer_threshold_minutes and edge.type in (
            "transfer_required",
            "checkin_dependency",
            "same_day",
        ):
            target = graph.nodes[edge.target]
            source = graph.nodes[edge.source]
            severity = "high" if edge.buffer_minutes <= 15 else "medium"
            warnings.append(
                RiskWarning(
                    node_id=target.id,
                    title=target.title,
                    message=(
                        f"Only {edge.buffer_minutes} min buffer between '{source.title}' and "
                        f"'{target.title}' — a small delay upstream could cause a miss."
                    ),
                    severity=severity,
                )
            )
    return warnings
