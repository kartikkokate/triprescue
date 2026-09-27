import asyncio
import os
import threading
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# must run before any app.* import - app.external_apis reads its API keys from the
# environment at import time, so .env has to be loaded first or they'll see nothing
load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.models import (
    DisruptionRequest,
    WeatherDisruptionRequest,
    TravelerPreferences,
    CreateTripRequest,
    TwinScenario,
    TwinObservation,
)
from app.store import state
from app.impact_engine import STATUS_RANK, propagate_disruption, scan_proactive_risks, apply_weather_event
from app.recovery_engine import generate_recovery_plans, recovery_analysis, apply_plan
from app.llm_explainer import explain_impact, explain_plans, explain_rights
from app import nugen_client
from nugen import pipeline_state
from app.live_monitor import manager as risk_feed_manager, monitor_loop
from app import trip_repository, db
from app.external_apis import check_weather, check_flight_status
from app.llm_explainer import explain_twin
from app.twin.service import twin, twin_loop
from app.twin.learner import learner
from app.twin.simulator import plan_success
from app.twin import social
from app.itinerary_builder import ItineraryInput, build_graph
from app.monitor.service import monitor, monitor_scheduler
from datetime import datetime
from fastapi import Header


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(monitor_loop()),
        asyncio.create_task(twin_loop(lambda: state.graph, risk_feed_manager.broadcast)),
        asyncio.create_task(monitor_scheduler(lambda: state.graph, lambda: state.preferences, risk_feed_manager.broadcast)),
    ]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="Travel Disruption Recovery Engine", lifespan=lifespan)

# CORS_ALLOWED_ORIGINS: comma-separated list, e.g. "https://your-app.vercel.app,http://localhost:5173"
_cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5180,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/itinerary")
def get_itinerary():
    return state.graph.to_dict()


@app.post("/api/itinerary")
def set_itinerary(data: ItineraryInput, authorization: str | None = Header(default=None)):
    """Replaces the demo trip with the traveler's own bookings (prices, terms, alternatives).
    Dependencies are inferred from the timeline when not given."""
    try:
        graph = build_graph(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    record = state.set_trip(graph, data.name, user_id=_caller(authorization), update_trip_id=data.update_trip_id)
    twin.snapshot = None  # the twin re-learns the new trip on next read
    _monitor_new_trip()
    return {"itinerary": graph.to_dict(), "trip_name": data.name, "trip_id": record["id"]}


@app.post("/api/reset")
def reset_itinerary():
    """Undo disruptions and applied plans - back to the current trip as booked."""
    state.reset()
    return state.graph.to_dict()


@app.post("/api/demo")
def load_demo_trip():
    state.load_demo()
    twin.snapshot = None
    _monitor_new_trip()
    return state.graph.to_dict()


@app.post("/api/disrupt")
def disrupt(req: DisruptionRequest):
    if req.node_id not in state.graph.nodes:
        raise HTTPException(status_code=404, detail=f"Unknown node {req.node_id}")

    report = propagate_disruption(
        state.graph, req.node_id, req.kind, req.delay_minutes or 0
    )
    state.record_disruption(req.model_dump(), report)
    _learn_from_disruption(req)

    return {
        "itinerary": state.graph.to_dict(),
        "impact_report": report,
        "disruption": state.last_disruption,
    }


@app.post("/api/disrupt-weather")
def disrupt_weather(req: WeatherDisruptionRequest):
    matching = [n for n in state.graph.nodes.values() if n.start.startswith(req.date)]
    if not matching:
        raise HTTPException(status_code=404, detail=f"No bookings scheduled on {req.date}")

    result = apply_weather_event(state.graph, req.date, req.severity)
    state.record_disruption({
        "node_id": None,
        "kind": "weather",
        "date": req.date,
        "severity": req.severity,
        "reason": f"weather ({req.severity}) on {req.date}",
    }, result["affected_nodes"])

    return {
        "itinerary": state.graph.to_dict(),
        "impact_report": result["affected_nodes"],
        "weather_origins": result["origins"],
        "disruption": state.last_disruption,
    }


WEATHER_REASON_WORDS = ("weather", "rain", "storm", "flood", "fog", "cyclone", "heat", "wind")


def _learn_from_disruption(req: DisruptionRequest) -> None:
    """Continuous learning: a real delay the traveler attributes to weather becomes a
    training observation for the twin (paired with the live conditions at that booking)."""
    reason = (req.reason or "").lower()
    if req.kind != "delay" or not any(w in reason for w in WEATHER_REASON_WORDS):
        return
    try:
        twin.observe(state.graph, req.node_id, req.delay_minutes or 0, source=f"disruption:{req.reason}")
    except Exception:
        pass  # a booking type without a weather model (e.g. hotel) or no live data - nothing to learn


def _current_reason() -> str | None:
    return state.last_disruption.get("reason") if state.last_disruption else None


def _current_analysis() -> dict:
    return recovery_analysis(
        state.graph, _current_reason(), state.preferences, state.disruptions or state.last_disruption, state.last_impact_report
    )


def _current_plans():
    return _current_analysis()["plans"]


@app.get("/api/preferences")
def get_preferences():
    return state.preferences.model_dump()


@app.put("/api/preferences")
def set_preferences(prefs: TravelerPreferences):
    state.preferences = prefs
    return state.preferences.model_dump()


@app.get("/api/recovery-plans")
def recovery_plans():
    analysis = _current_analysis()
    return {
        "plans": [p.model_dump() for p in analysis["plans"]],
        "analysis": {k: v for k, v in analysis.items() if k != "plans"},
    }


@app.post("/api/apply-plan/{plan_id}")
def apply_recovery_plan(plan_id: str):
    plans = _current_plans()
    plan = next((p for p in plans if p.id == plan_id), None)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Unknown or stale plan {plan_id}")

    apply_plan(state.graph, plan)
    state.last_impact_report = None
    state.last_disruption = None
    state.disruptions = []

    return {"itinerary": state.graph.to_dict(), "applied_plan": plan.model_dump()}


@app.get("/api/risk-scan")
def risk_scan():
    warnings = scan_proactive_risks(state.graph)
    return {"warnings": [w.model_dump() for w in warnings]}


@app.get("/api/risk-feed")
def risk_feed_history():
    """Recent live-monitor events (buffer erosion forecasts) - fetched once on load,
    then the WebSocket below pushes anything new as it happens."""
    return {"events": state.risk_feed}


@app.websocket("/ws/risk-feed")
async def risk_feed_ws(websocket: WebSocket):
    await risk_feed_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # client sends nothing; just keeps the socket open
    except WebSocketDisconnect:
        risk_feed_manager.disconnect(websocket)


@app.get("/api/explain-impact")
def explain_impact_endpoint():
    if not state.last_disruption or not state.last_impact_report:
        raise HTTPException(status_code=400, detail="No disruption has been triggered yet")
    return explain_impact(state.last_disruption, state.last_impact_report, state.graph)


@app.get("/api/explain-plans")
def explain_plans_endpoint():
    plans = _current_plans()
    if not plans:
        raise HTTPException(status_code=400, detail="No recovery plans available")
    return explain_plans(plans, state.last_disruption, state.graph, state.preferences)


@app.get("/api/traveler-rights")
def traveler_rights_endpoint():
    if not state.last_disruption or state.last_impact_report is None:
        raise HTTPException(status_code=400, detail="No disruption has been triggered yet")
    return explain_rights(state.last_disruption, state.last_impact_report, state.graph)


@app.get("/api/ai-model")
def ai_model_status():
    """Which model is answering, and the provenance of our Nugen domain-aligned model
    (base model -> alignment -> deployed model, with its benchmark evaluation)."""
    return {
        "active_tier": "nugen-aligned" if nugen_client.is_configured() else "gemini-or-rule-based",
        "nugen_model_id": nugen_client.NUGEN_MODEL_ID,
        # deployed but not answering (cold GPU / gateway timeout): answers fall back to Gemini meanwhile
        "nugen_last_error": nugen_client.last_error,
        "nugen_cooling_down": nugen_client.is_cooling_down(),
        "pipeline": pipeline_state.load(),
        "dataset": pipeline_state.dataset_stats(),
    }


# --- multi-trip persistence (Supabase-backed, in-memory fallback - see app.trip_repository) ---


def _monitor_new_trip() -> None:
    """Old provider rows/alerts belong to the previous trip: clear them, then check the new
    trip's bookings right away instead of showing '0 provider checks' until the next tick."""
    monitor.new_trip()
    graph, prefs = state.graph, state.preferences

    def _run():
        try:
            monitor.run(graph, prefs, None, "trip switch")
        except Exception:
            pass

    if os.environ.get("MONITOR_SCHEDULER", "inprocess") != "off":
        threading.Thread(target=_run, daemon=True).start()


def _caller(authorization: str | None) -> str | None:
    """Signed-in account for this request, verified with Supabase Auth from the bearer token.
    No / invalid token = guest: anonymous trips (login is optional for now)."""
    token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    uid = db.user_from_token(token)
    db.use_token(token if uid else None)
    return uid


@app.get("/api/auth-config")
def auth_config():
    """Public Supabase settings for the optional sign-in page. Only a publishable/anon key
    is ever handed out - a secret/service key stays on the server."""
    key = os.environ.get("SUPABASE_KEY", "")
    public = key.startswith("sb_publishable_") or (key.startswith("eyJ") and "service_role" not in key)
    url = os.environ.get("SUPABASE_URL", "")
    return {"enabled": bool(url and public and db.is_configured()), "url": url if public else "", "key": key if public else ""}


@app.get("/api/trip-status")
def trip_status():
    return {
        "trip_id": state.trip_id,
        "trip_name": state.trip_name,
        "is_demo": state.is_demo,
        "disruptions": state.disruptions,
        "persistence_backend": "supabase" if db.is_configured() else "in-memory",
    }


@app.post("/api/trips")
def create_trip(req: CreateTripRequest, authorization: str | None = Header(default=None)):
    try:
        return state.save_as_new_trip(req.name, user_id=_caller(authorization))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/trips")
def list_trips(authorization: str | None = Header(default=None)):
    return {"trips": trip_repository.list_trips(user_id=_caller(authorization))}


@app.post("/api/trips/{trip_id}/save")
def save_trip(trip_id: str, authorization: str | None = Header(default=None)):
    """Saves the CURRENTLY ACTIVE working itinerary+preferences under this trip id,
    making it the active trip going forward. Overwrites whatever was there before."""
    if not trip_repository.is_valid_trip_id(trip_id):
        raise HTTPException(status_code=400, detail="Trip id must be a UUID")
    state.trip_id = trip_id
    try:
        return state.save_current_trip(user_id=_caller(authorization))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/trips/{trip_id}/load")
def load_trip(trip_id: str, authorization: str | None = Header(default=None)):
    _caller(authorization)
    try:
        record = state.load_trip(trip_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown trip {trip_id}")
    twin.snapshot = None
    _monitor_new_trip()

    return {
        "itinerary": state.graph.to_dict(),
        "preferences": state.preferences.model_dump(),
        "trip": {"id": record["id"], "name": record["name"]},
    }


@app.delete("/api/trips/{trip_id}")
def delete_trip(trip_id: str, authorization: str | None = Header(default=None)):
    _caller(authorization)
    trip_repository.delete_trip(trip_id)
    if state.trip_id == trip_id:
        state.trip_id = None
        state.trip_name = "My Trip"
    return {"deleted": trip_id}


# --- real external API checks (weather / flight status) - "check" only; the frontend
# confirms and then calls the existing /api/disrupt or /api/disrupt-weather to act on it ---


@app.get("/api/weather-check")
def weather_check(location: str, date: str):
    return check_weather(location, date)


@app.get("/api/flight-status")
def flight_status(flight_iata: str):
    result = check_flight_status(flight_iata)
    # continuous learning: a real observed delay on one of the trip's flights, paired with
    # the live weather at that booking, updates the twin's flight model
    if result.get("found") and result.get("delay_minutes"):
        code = flight_iata.replace("-", "").replace(" ", "").upper()
        node = next(
            (n for n in state.graph.nodes.values()
             if n.type == "flight" and code in n.title.replace("-", "").replace(" ", "").upper()),
            None,
        )
        if node:
            try:
                result["twin_learned"] = twin.observe(state.graph, node.id, result["delay_minutes"], source="aviationstack")
            except Exception:
                pass
    return result


# --- weather digital twin (HackCelestial midnight task) ---------------------------------


@app.get("/api/twin/state")
def twin_state(refresh: bool = False):
    snap = twin.refresh(state.graph) if refresh else twin.ensure_live(state.graph)
    return {**snap, "history": twin.history, "learner": learner.summary()}


@app.post("/api/twin/simulate")
def twin_simulate(scenario: TwinScenario):
    """What-if / counterfactual run on a copy of the itinerary - the real trip is untouched."""
    return twin.what_if(state.graph, scenario.model_dump())


@app.post("/api/twin/explain")
def twin_explain(scenario: TwinScenario | None = None):
    sc = scenario.model_dump() if scenario else None
    sim = twin.what_if(state.graph, sc) if sc and any(v is not None for v in sc["overrides"].values()) else twin.ensure_live(state.graph)
    return explain_twin(sim, sc)


@app.post("/api/twin/observe")
def twin_observe(obs: TwinObservation):
    if obs.node_id not in state.graph.nodes:
        raise HTTPException(status_code=404, detail=f"Unknown node {obs.node_id}")
    try:
        record = twin.observe(state.graph, obs.node_id, obs.delay_minutes, source="traveler_report")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    snap = twin.refresh(state.graph)
    return {"observation": record, "learner": learner.summary(), "trip": snap["trip"]}


@app.post("/api/twin/promote")
def twin_promote(scenario: TwinScenario):
    """Applies a scenario's most likely outcome to the REAL itinerary, handing off to the
    existing recovery-plan flow."""
    sc = scenario.model_dump()
    sim = twin.what_if(state.graph, sc)
    result = twin.promote(state.graph, sim)
    if not result["origins"]:
        raise HTTPException(status_code=400, detail="This scenario's most likely outcome disrupts nothing")
    state.record_disruption({
        "node_id": None,
        "kind": "weather",
        "date": sc.get("target_date") or "trip",
        "severity": "severe" if sim["trip"]["p_any_disruption"] >= 0.8 else "moderate",
        "reason": "weather (digital twin scenario)",
    }, result["impact_report"])
    for o in result["origins"]:
        state.disruptions.append({**o, "reason": "weather (digital twin scenario)"})
    return {"itinerary": state.graph.to_dict(), **result, "disruption": state.last_disruption}


@app.get("/api/twin/plan-risk")
def twin_plan_risk():
    """Twin-aware recovery: how likely each current recovery plan holds up under the live forecast."""
    plans = _current_plans()
    snap = twin.ensure_live(state.graph)
    return {"plans": plan_success(plans, snap, state.graph)}


@app.get("/api/twin/social")
def twin_social(place: str = "Goa"):
    return social.fetch_signals(place)


# --- proactive monitoring (every 20 min by default) ---------------------------------------

MONITOR_CRON_TOKEN = os.environ.get("MONITOR_CRON_TOKEN")


@app.get("/api/monitor/status")
def monitor_status():
    """Scheduler settings, the last run, open events and per-provider freshness/evidence."""
    return monitor.status()


@app.post("/api/monitor/run")
async def monitor_run(now: str | None = None, x_monitor_token: str | None = Header(default=None)):
    """One monitoring pass - for an external cron, or to test. `now` (ISO) lets you replay
    the checks as if it were a given moment, e.g. the morning of travel."""
    if MONITOR_CRON_TOKEN and x_monitor_token != MONITOR_CRON_TOKEN:
        raise HTTPException(status_code=401, detail="Bad monitor token")
    try:
        at = datetime.fromisoformat(now) if now else None
    except ValueError:
        raise HTTPException(status_code=400, detail="now must be an ISO datetime")
    out = await asyncio.to_thread(monitor.run, state.graph, state.preferences, at, "api")
    for note in out["notifications"]:
        await risk_feed_manager.broadcast({"type": "monitor_alert", **note})
    return out


@app.get("/api/notifications")
def notifications(unread_only: bool = False):
    notes = [n for n in monitor.notifications if not (unread_only and n["read"])]
    return {"notifications": notes[::-1], "unread": sum(not n["read"] for n in monitor.notifications)}


@app.post("/api/notifications/{note_id}/read")
def notification_read(note_id: str):
    if not monitor.mark_read(note_id):
        raise HTTPException(status_code=404, detail="Unknown notification")
    return {"read": note_id}


@app.post("/api/monitor/events/{event_id}/apply")
def monitor_apply(event_id: str):
    """The traveler accepts a detected disruption: it is applied to the real itinerary and
    the recovery flow takes over (still nothing is booked or paid)."""
    event = monitor.event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Unknown event")
    if event["node_id"] not in state.graph.nodes:
        raise HTTPException(status_code=409, detail="That booking is no longer in the itinerary")
    before = {nid: n.status for nid, n in state.graph.nodes.items()}
    report = propagate_disruption(state.graph, event["node_id"], event["kind"], event.get("delay_minutes") or 0)
    for nid, st in before.items():
        if STATUS_RANK[st] > STATUS_RANK[state.graph.nodes[nid].status]:
            state.graph.nodes[nid].status = st
    state.record_disruption({
        "node_id": event["node_id"], "kind": event["kind"], "delay_minutes": event.get("delay_minutes") or 0,
        "reason": f"monitor: {event['reason']}",
    }, report)
    monitor.set_event_status(event_id, "applied")
    analysis = _current_analysis()
    return {
        "itinerary": state.graph.to_dict(),
        "impact_report": report,
        "plans": [p.model_dump() for p in analysis["plans"]],
    }


@app.post("/api/monitor/events/{event_id}/dismiss")
def monitor_dismiss(event_id: str):
    if not monitor.event(event_id):
        raise HTTPException(status_code=404, detail="Unknown event")
    monitor.set_event_status(event_id, "dismissed")
    return {"dismissed": event_id}
