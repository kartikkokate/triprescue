"""Turns a traveler's own bookings into an itinerary graph (replacing the demo trip).

Every booking carries the traveler's own price and terms. Dependencies can be given
explicitly; otherwise they are inferred from the timeline: consecutive bookings are
chained, and the edge type (and the minimum buffer it needs) follows from what connects
to what - e.g. a flight feeding a transfer needs time to deplane, anything feeding a
flight needs check-in time. Coordinates are looked up by place name when missing
(best effort; the trip still works without them).
"""
from datetime import datetime

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

from app.graph_engine import ItineraryGraph
from app.models import BookingNode, DependencyEdge, EdgeType, NodeType

# (from_type, to_type) -> (edge type, minimum buffer minutes); "*" matches any type
EDGE_RULES: list[tuple[str, str, str, int]] = [
    ("flight", "transfer", "transfer_required", 30),
    ("train", "transfer", "transfer_required", 15),
    ("transfer", "flight", "transfer_required", 90),
    ("transfer", "train", "transfer_required", 20),
    ("transfer", "hotel", "checkin_dependency", 15),
    ("flight", "hotel", "checkin_dependency", 60),
    ("train", "hotel", "checkin_dependency", 30),
    ("*", "flight", "transfer_required", 120),
    ("*", "train", "transfer_required", 30),
]
SAME_DAY_BUFFER = 30


class BookingInput(BaseModel):
    id: str | None = None
    type: NodeType
    title: str
    start: str
    end: str
    cost: float = Field(ge=0)
    provider: str = "unknown"
    location: str = ""
    cancellation_policy: str = "non_refundable"
    cancellation_penalty: float | None = Field(default=None, ge=0)
    refund_mode: str = "cash"
    service_code: str | None = None
    weather_sensitive: bool = False
    lat: float | None = None
    lon: float | None = None
    dest_lat: float | None = None
    dest_lon: float | None = None
    destination: str | None = None  # place name for transport legs, geocoded if no dest coords
    alternatives: list[dict] = Field(default_factory=list)

    @field_validator("start", "end")
    @classmethod
    def _iso(cls, v: str) -> str:
        datetime.fromisoformat(v)
        return v

    @model_validator(mode="after")
    def _order(self):
        if datetime.fromisoformat(self.end) < datetime.fromisoformat(self.start):
            raise ValueError(f"'{self.title}' ends before it starts")
        return self


class DependencyInput(BaseModel):
    source: str
    target: str
    type: EdgeType | None = None
    buffer_minutes: int | None = Field(default=None, ge=0)


class ItineraryInput(BaseModel):
    name: str = "My Trip"
    bookings: list[BookingInput] = Field(min_length=1)
    dependencies: list[DependencyInput] | None = None  # None = infer from the timeline
    geocode: bool = True
    update_trip_id: str | None = None  # set = overwrite this saved trip; None = save as a new trip


def _edge_rule(src: BookingNode, dst: BookingNode) -> tuple[str, int]:
    for a, b, etype, buf in EDGE_RULES:
        if (a == "*" or a == src.type) and (b == "*" or b == dst.type):
            return etype, buf
    same_day = src.end[:10] == dst.start[:10]
    return ("same_day" if same_day else "sequential"), (SAME_DAY_BUFFER if same_day else 0)


def _fit_buffer(src: BookingNode, dst: BookingNode, wanted: int) -> int:
    """Never demand more buffer than the traveler's own plan leaves - the trip as booked is
    feasible by definition; tight gaps show up as proactive warnings instead."""
    gap = int((datetime.fromisoformat(dst.start) - datetime.fromisoformat(src.end)).total_seconds() // 60)
    return max(0, min(wanted, gap))


_geo_cache: dict[str, tuple[float, float] | None] = {}


def geocode(place: str) -> tuple[float, float] | None:
    key = place.strip().lower()
    if not key:
        return None
    if key in _geo_cache:
        return _geo_cache[key]
    result = None
    try:
        resp = httpx.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": place, "count": 1}, timeout=8)
        resp.raise_for_status()
        hits = resp.json().get("results") or []
        if hits:
            result = (hits[0]["latitude"], hits[0]["longitude"])
    except Exception:
        result = None
    _geo_cache[key] = result
    return result


def build_graph(data: ItineraryInput) -> ItineraryGraph:
    nodes: list[BookingNode] = []
    seen: set[str] = set()
    for i, b in enumerate(sorted(data.bookings, key=lambda x: x.start), start=1):
        nid = b.id or f"B{i}"
        if nid in seen:
            raise ValueError(f"Duplicate booking id {nid}")
        seen.add(nid)
        fields = b.model_dump(exclude={"id", "destination"})
        # transport legs keep "Origin to Destination" so places (twin, map) get real names
        if b.destination and " to " not in (b.location or "") and b.destination.strip() != (b.location or "").strip():
            fields["location"] = f"{b.location} to {b.destination}".strip()
        if data.geocode:
            if fields["lat"] is None and b.location:
                hit = geocode(b.location)
                if hit:
                    fields["lat"], fields["lon"] = hit
            if fields["dest_lat"] is None and b.destination:
                hit = geocode(b.destination)
                if hit:
                    fields["dest_lat"], fields["dest_lon"] = hit
        if fields["refund_mode"] not in ("cash", "credit", "none"):
            raise ValueError(f"refund_mode must be cash, credit or none (got {fields['refund_mode']})")
        nodes.append(BookingNode(id=nid, status="safe", **fields))

    by_id = {n.id: n for n in nodes}
    edges: list[DependencyEdge] = []
    if data.dependencies is None:
        # Bookings are chained in time order. A booking that happens DURING a hotel stay (a tour
        # on day 2 of a 3-night stay) depends on arriving, not on checking out: it hangs off
        # whatever fed the hotel, and the chain continues from the hotel (its checkout).
        feeder: dict[str, BookingNode | None] = {}
        prev: BookingNode | None = None
        for dst in nodes:
            src = prev
            during_stay = src is not None and src.type == "hotel" and dst.start < src.end
            if during_stay:
                src = feeder.get(prev.id)
            if src is not None:
                etype, wanted = _edge_rule(src, dst)
                edges.append(DependencyEdge(source=src.id, target=dst.id, type=etype, buffer_minutes=_fit_buffer(src, dst, wanted)))
            feeder[dst.id] = src
            if not during_stay:
                prev = dst
    else:
        for d in data.dependencies:
            if d.source not in by_id or d.target not in by_id:
                raise ValueError(f"Dependency {d.source}->{d.target} references an unknown booking")
            src, dst = by_id[d.source], by_id[d.target]
            etype, wanted = _edge_rule(src, dst)
            buffer = d.buffer_minutes if d.buffer_minutes is not None else _fit_buffer(src, dst, wanted)
            edges.append(DependencyEdge(source=d.source, target=d.target, type=d.type or etype, buffer_minutes=buffer))

    graph = ItineraryGraph(nodes, edges)
    if len(_order(graph)) != len(nodes):
        raise ValueError("Dependencies contain a cycle")
    return graph


def _order(graph: ItineraryGraph) -> list[str]:
    indeg = {n: 0 for n in graph.nodes}
    for e in graph.edges:
        indeg[e.target] += 1
    ready = [n for n, d in indeg.items() if d == 0]
    out = []
    while ready:
        n = ready.pop()
        out.append(n)
        for e in graph.successors(n):
            indeg[e.target] -= 1
            if indeg[e.target] == 0:
                ready.append(e.target)
    return out
