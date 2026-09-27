"""Background proactive monitor: simulates live traffic conditions ticking in for
same-day transfers and pushes new risk warnings over WebSocket the moment a booking's
buffer looks like it's getting eaten into - without anyone triggering a disruption.

This is a forecast signal, not a committed disruption: it never mutates node.status
itself. It's meant to nudge the traveler (or the system) to act before something
actually breaks - the frontend offers a one-click "simulate this delay now" that
feeds the estimate into the real disrupt/recovery flow.
"""
import asyncio
import random
import time

from fastapi import WebSocket

from app.store import state

TICK_SECONDS = 8
DRIFT_MIN, DRIFT_MAX = -5.0, 20.0  # slight upward drift so demo runs actually cross thresholds
CLEAR_CHANCE = 0.15  # chance each tick that "traffic clears" and estimate drops
MEDIUM_RATIO = 0.5  # live estimate / buffer_minutes
HIGH_RATIO = 0.8


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, payload: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


def _edge_key(source: str, target: str) -> str:
    return f"{source}->{target}"


def _severity_for_ratio(ratio: float) -> str | None:
    if ratio >= HIGH_RATIO:
        return "high"
    if ratio >= MEDIUM_RATIO:
        return "medium"
    return None


async def _tick():
    graph = state.graph
    for edge in graph.edges:
        if edge.type != "transfer_required":
            continue

        key = _edge_key(edge.source, edge.target)
        current = state.live_traffic.get(key, 0.0)

        if random.random() < CLEAR_CHANCE:
            current = max(0.0, current - random.uniform(10, 25))
        else:
            current = current + random.uniform(DRIFT_MIN, DRIFT_MAX)
        current = max(0.0, min(90.0, current))
        state.live_traffic[key] = current

        target = graph.nodes.get(edge.target)
        if not target or target.status != "safe":
            # already actually disrupted (or recovered/replaced) - the live estimate keeps
            # ticking in the background but stops surfacing noise on top of a real event
            continue

        ratio = current / edge.buffer_minutes if edge.buffer_minutes > 0 else 0
        severity = _severity_for_ratio(ratio)
        last_severity = state.risk_feed_last_severity.get(key)

        if severity == last_severity:
            continue
        state.risk_feed_last_severity[key] = severity

        if severity is None:
            continue  # dropped back below threshold - no need for a "never mind" event

        event = {
            "id": f"{key}-{int(time.time() * 1000)}",
            "timestamp": time.time(),
            "node_id": edge.target,
            "node_title": target.title,
            "source_title": graph.nodes[edge.source].title,
            "severity": severity,
            "live_delay_minutes": round(current),
            "buffer_minutes": edge.buffer_minutes,
            "message": (
                f"Live traffic conditions estimate ~{round(current)} min of delay risk for "
                f"'{target.title}', against a {edge.buffer_minutes} min buffer — "
                f"{'critical, buffer nearly gone' if severity == 'high' else 'worth watching'}."
            ),
        }
        state.risk_feed.append(event)
        state.risk_feed = state.risk_feed[-50:]
        await manager.broadcast(event)


async def monitor_loop():
    while True:
        try:
            await _tick()
        except Exception:
            pass
        await asyncio.sleep(TICK_SECONDS)
