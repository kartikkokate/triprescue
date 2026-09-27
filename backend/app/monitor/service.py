"""Proactive monitoring: every MONITOR_INTERVAL_MINUTES (20 by default) check every
upcoming booking against the relevant providers, and turn real signals into alerts.

- Idempotent: each signal gets a fingerprint (booking + kind + severity + delay bucket).
  A fingerprint already alerted on is suppressed; if things get worse, the fingerprint
  changes and the traveler hears about it again.
- On a new event the impact and every recovery plan's score are recomputed on a COPY of
  the itinerary and attached to the notification. The real trip changes only when the
  traveler applies the event (nothing is ever booked or paid).
- Provider health / freshness is kept per provider for display.
- Runs on a light in-process timer (MONITOR_SCHEDULER=inprocess) or from an external cron
  hitting POST /api/monitor/run (MONITOR_SCHEDULER=off + MONITOR_CRON_TOKEN).
"""
import asyncio
import copy
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from app.graph_engine import ItineraryGraph
from app.impact_engine import STATUS_RANK, propagate_disruption
from app.monitor.providers import checks_for
from app.recovery_engine import recovery_analysis

STATE_PATH = Path(__file__).parent / "monitor_state.json"
INTERVAL_MINUTES = int(os.environ.get("MONITOR_INTERVAL_MINUTES", "20"))
SCHEDULER = os.environ.get("MONITOR_SCHEDULER", "inprocess")
MAX_NOTIFICATIONS = 100


def fingerprint(node_id: str, signal: dict) -> str:
    bucket = int(signal.get("delay_minutes") or 0) // 30 if signal["kind"] == "delay" else 0
    raw = f"{node_id}|{signal['kind']}|{signal['severity']}|{bucket}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


class MonitorService:
    def __init__(self, path: Path = STATE_PATH, persist: bool = True):
        self.path, self.persist = path, persist
        self._lock = threading.Lock()
        self.reset()
        if persist:
            self._load()

    def reset(self) -> None:
        self.events: dict[str, dict] = {}  # fingerprint -> event
        self.notifications: list[dict] = []
        self.providers: dict[str, dict] = {}  # "provider|node" -> latest result
        self.last_run: dict | None = None

    def new_trip(self) -> None:
        """Provider results, events and alerts belong to one trip - start clean on a switch."""
        with self._lock:
            self.reset()
            self._save()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return
        self.events = raw.get("events", {})
        self.notifications = raw.get("notifications", [])
        self.providers = raw.get("providers", {})
        self.last_run = raw.get("last_run")

    def _save(self) -> None:
        if not self.persist:
            return
        self.path.write_text(json.dumps({
            "events": self.events, "notifications": self.notifications[-MAX_NOTIFICATIONS:],
            "providers": self.providers, "last_run": self.last_run,
        }), encoding="utf-8")

    # --- one monitoring pass -------------------------------------------------------------

    def run(self, graph: ItineraryGraph, preferences, now: datetime | None = None, trigger: str = "scheduler") -> dict:
        now = now or datetime.now()
        with self._lock:
            results: list[dict] = []
            for node in graph.nodes.values():
                if node.booking_status == "dropped":
                    continue
                if datetime.fromisoformat(node.end) < now - timedelta(hours=2):
                    continue  # already over
                results.extend(checks_for(node, now))

            new_notes, suppressed = [], 0
            for r in results:
                self.providers[f"{r['provider']}|{r['node_id']}"] = {k: v for k, v in r.items() if k != "signal"}
                sig = r.get("signal")
                if not sig:
                    continue
                fp = fingerprint(r["node_id"], sig)
                if fp in self.events:
                    suppressed += 1
                    self.events[fp]["last_seen"] = now.isoformat(timespec="seconds")
                    continue
                event = {
                    "id": fp, "node_id": r["node_id"], "provider": r["provider"], "category": r["category"],
                    **sig, "evidence": r["evidence"], "detected_at": now.isoformat(timespec="seconds"),
                    "last_seen": now.isoformat(timespec="seconds"), "status": "open",
                }
                self.events[fp] = event
                new_notes.append(self._notify(graph, event, preferences))

            self.last_run = {
                "at": now.isoformat(timespec="seconds"), "trigger": trigger,
                "checks": len(results),
                "by_status": {s: sum(r["status"] == s for r in results) for s in ("ok", "skipped", "unavailable", "error")},
                "new_alerts": len(new_notes), "suppressed_duplicates": suppressed,
                "next_run": (now + timedelta(minutes=INTERVAL_MINUTES)).isoformat(timespec="seconds") if SCHEDULER == "inprocess" else None,
            }
            self._save()
            return {**self.last_run, "notifications": new_notes, "results": results}

    def _notify(self, graph: ItineraryGraph, event: dict, preferences) -> dict:
        """Impact + recovery score recalculation on a copy of the itinerary."""
        preview = copy.deepcopy(graph)
        before = {nid: n.status for nid, n in preview.nodes.items()}
        disruption = {"node_id": event["node_id"], "kind": event["kind"],
                      "delay_minutes": event.get("delay_minutes", 0), "reason": f"monitor: {event['reason']}"}
        report = propagate_disruption(preview, event["node_id"], event["kind"], event.get("delay_minutes", 0) or 0)
        for nid, st in before.items():  # never report something as better than it already is
            if STATUS_RANK[st] > STATUS_RANK[preview.nodes[nid].status]:
                preview.nodes[nid].status = st
        analysis = recovery_analysis(preview, disruption["reason"], preferences, disruption, report)
        node = graph.nodes[event["node_id"]]
        impact = {nid: n.status for nid, n in preview.nodes.items() if n.status != before[nid]}
        what = "cancellation" if event["kind"] == "cancel" else f"~{event.get('delay_minutes')} min delay"
        note = {
            "id": uuid.uuid4().hex[:12],
            "event_id": event["id"],
            "created_at": event["detected_at"],
            "severity": event["severity"],
            "node_id": node.id,
            "title": f"{node.title}: {what}",
            "message": event["reason"],
            "source": event["provider"],
            "evidence": event["evidence"],
            "impact": impact,
            "plans_preview": [
                {"id": p.id, "label": p.label, "badges": p.badges, "score": p.score,
                 "net_cash": p.total_cost_delta, "lateness_minutes": p.total_time_delta_minutes}
                for p in analysis["plans"][:4]
            ],
            "read": False,
        }
        self.notifications.append(note)
        self.notifications = self.notifications[-MAX_NOTIFICATIONS:]
        return note

    # --- traveler actions ----------------------------------------------------------------

    def event(self, event_id: str) -> dict | None:
        return self.events.get(event_id)

    def set_event_status(self, event_id: str, status: str) -> None:
        with self._lock:
            self.events[event_id]["status"] = status
            self._save()

    def mark_read(self, note_id: str) -> bool:
        with self._lock:
            for n in self.notifications:
                if n["id"] == note_id:
                    n["read"] = True
                    self._save()
                    return True
            return False

    def status(self) -> dict:
        providers = list(self.providers.values())
        now = datetime.now()
        for p in providers:
            p["fresh"] = p["status"] == "ok" and datetime.fromisoformat(p["fresh_until"]) >= now
        return {
            "interval_minutes": INTERVAL_MINUTES,
            "scheduler": SCHEDULER,
            "last_run": self.last_run,
            "open_events": [e for e in self.events.values() if e["status"] == "open"],
            "unread": sum(not n["read"] for n in self.notifications),
            "providers": providers,
        }


monitor = MonitorService()


async def monitor_scheduler(get_graph, get_prefs, broadcast):
    """Light in-process timer: sleeps between passes, the pass itself runs in a worker thread."""
    if SCHEDULER != "inprocess":
        return
    await asyncio.sleep(15)  # let the app finish starting
    while True:
        try:
            out = await asyncio.to_thread(monitor.run, get_graph(), get_prefs(), None, "scheduler")
            for note in out["notifications"]:
                await broadcast({"type": "monitor_alert", **note})
        except Exception:
            pass
        await asyncio.sleep(INTERVAL_MINUTES * 60)
