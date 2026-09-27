import os
import json
from pathlib import Path
from app.models import BookingNode, DependencyEdge, TravelerPreferences
from app.graph_engine import ItineraryGraph
from app import trip_repository

SEED_PATH = Path(__file__).parent / "data" / "seed_itinerary.json"


def _graph_from_raw(raw: dict) -> ItineraryGraph:
    nodes = [BookingNode(**n) for n in raw["nodes"]]
    edges = [DependencyEdge(**e) for e in raw["edges"]]
    return ItineraryGraph(nodes, edges)


ALTERNATIVES_PATH = Path(__file__).parent / "data" / "alternatives.json"


def _load_seed_graph() -> ItineraryGraph:
    """The demo trip. Its replacement-option catalog is attached to each booking, so the
    demo and user-entered trips flow through the recovery engine the same way."""
    with open(SEED_PATH) as f:
        raw = json.load(f)
    with open(ALTERNATIVES_PATH) as f:
        catalog = json.load(f)
    for node in raw["nodes"]:
        node.setdefault("alternatives", catalog.get(node["id"], []))
    return _graph_from_raw(raw)


DEMO_TRIP_NAME = "Demo trip: Delhi → Goa"


def _seed_raw() -> dict:
    return _load_seed_graph().to_dict()


class AppState:
    """The traveler's working trip. `baseline` is the trip as booked (before any disruption
    or applied plan) - Reset returns to it instead of to the demo. A trip the traveler builds
    is saved automatically, and on startup the most recently saved trip is loaded, so the app
    is never stuck on the demo itinerary."""

    def __init__(self, restore_last_trip: bool = False):
        self.last_impact_report: dict | None = None
        self.last_disruption: dict | None = None
        self.disruptions: list[dict] = []  # every disruption active on the working trip

        # live proactive monitor state (see app.live_monitor) - keyed by "source->target"
        self.live_traffic: dict[str, float] = {}
        self.risk_feed_last_severity: dict[str, str | None] = {}
        self.risk_feed: list[dict] = []

        # traveler-level setting - survives itinerary reset, it's not trip state
        self.preferences: TravelerPreferences = TravelerPreferences()

        self.trip_id: str | None = None
        self.trip_name: str = DEMO_TRIP_NAME
        self.is_demo = True
        self.baseline: dict = _seed_raw()
        self.graph: ItineraryGraph = _graph_from_raw(self.baseline)
        if restore_last_trip:
            self._restore_latest_saved_trip()

    def _restore_latest_saved_trip(self) -> None:
        try:
            trips = trip_repository.list_trips()
            if trips:
                self.load_trip(trips[0]["id"])
        except Exception:
            pass  # no database / network: start on the demo trip

    def _clear_working_disruption_state(self):
        self.last_impact_report = None
        self.last_disruption = None
        self.disruptions = []
        self.live_traffic = {}
        self.risk_feed_last_severity = {}
        self.risk_feed = []

    def record_disruption(self, disruption: dict, impact_report: dict | None) -> None:
        self.last_disruption = disruption
        self.last_impact_report = impact_report
        self.disruptions.append(disruption)

    def reset(self):
        """Undo disruptions and applied plans: back to this trip as booked."""
        self.graph = _graph_from_raw(self.baseline)
        self._clear_working_disruption_state()

    def load_demo(self):
        self.baseline = _seed_raw()
        self.graph = _graph_from_raw(self.baseline)
        self._clear_working_disruption_state()
        self.trip_id = None
        self.trip_name = DEMO_TRIP_NAME
        self.is_demo = True

    def set_trip(self, graph: ItineraryGraph, name: str, user_id: str | None = None,
                 update_trip_id: str | None = None) -> dict:
        """A trip the traveler built: becomes the baseline and is saved straight away.
        Overwrites a saved row only when the traveler is editing that very trip
        (update_trip_id == the active trip); a new trip always gets its own row, so building
        a trip never renames or clobbers whatever trip happened to be active."""
        editing = bool(update_trip_id and update_trip_id == self.trip_id and not self.is_demo)
        self.graph = graph
        self.baseline = graph.to_dict()
        self._clear_working_disruption_state()
        self.trip_name = name
        self.is_demo = False
        if not editing:
            self.trip_id = None
        if self.trip_id:
            trip_repository.save_trip(
                self.trip_id, name, self.graph.to_dict(), self.preferences.model_dump(), user_id=user_id
            )
            return {"id": self.trip_id, "name": name, "updated_at": None}
        return self.save_as_new_trip(name, user_id=user_id)

    def save_as_new_trip(self, name: str, user_id: str | None = None) -> dict:
        name = (name or "").strip()
        if not name or name.lower().startswith("demo trip"):
            raise ValueError("Give the trip its own name, e.g. 'Pune → Indore'.")
        record = trip_repository.create_trip(
            name, self.graph.to_dict(), self.preferences.model_dump(), user_id=user_id
        )
        self.trip_id = record["id"]
        self.trip_name = record["name"]
        self.is_demo = False
        return record

    def save_current_trip(self, user_id: str | None = None) -> dict:
        if not self.trip_id:
            raise ValueError("No active saved trip - use save_as_new_trip first")
        trip_repository.save_trip(
            self.trip_id, self.trip_name, self.graph.to_dict(), self.preferences.model_dump(), user_id=user_id
        )
        return {"id": self.trip_id, "name": self.trip_name}

    def load_trip(self, trip_id: str) -> dict:
        record = trip_repository.load_trip(trip_id)
        if not record:
            raise KeyError(trip_id)

        self.baseline = record["itinerary"]
        self.graph = _graph_from_raw(self.baseline)
        self.preferences = TravelerPreferences(**record["preferences"])
        self.trip_id = record["id"]
        self.trip_name = record["name"]
        self.is_demo = False
        self._clear_working_disruption_state()
        return record


# the running app resumes the traveler's last saved trip; tests build AppState() directly
state = AppState(restore_last_trip=os.environ.get("TRIPRESCUE_RESTORE_LAST_TRIP", "1") == "1")
