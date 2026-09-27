"""Deterministic recovery planner.

1. Candidates: for every broken/cancelled booking, its replacement options (user-entered
   or catalog alternatives on the booking, else clearly-labelled estimate templates), plus
   "keep it" when the booking still runs, only late.
2. Every combination of one candidate per broken booking is checked for FEASIBILITY
   against the itinerary's dependencies: scheduled services (flights, trains, activity
   slots) run at fixed times and can be missed; on-demand ones (cabs, hotel check-in) can
   start whenever the traveler arrives. A combination that would make the traveler miss
   anything is rejected, with the reason recorded.
3. Each feasible plan gets money (penalties, cash refund, credit, new spend), time (worst
   lateness vs the original schedule), convenience and disruption, and an EXPLAINABLE
   multi-objective score: each objective is normalized across the feasible plans and
   weighted by the traveler's preferences; the per-objective contributions are returned.
4. Plans are organized as Best Balanced / Cheapest / Fastest / further alternatives.

No LLM is involved in any of this, and nothing is booked or paid: plans carry the action
items the traveler performs themselves.
"""
import itertools
from datetime import datetime, timedelta

from app.graph_engine import ItineraryGraph
from app.models import BookingNode, RecoveryOption, RecoveryPlan, TravelerPreferences
from app.money import REFUND_PCT, provider_cancelled, refund_for  # noqa: F401  (REFUND_PCT re-exported for callers)

SCHEDULED_TYPES = {"flight", "train", "activity", "event"}  # fixed departure/slot times
NEW_BOOKING_ACTIONS = {"rebook", "manual_booking", "drop"}
# you physically need the previous leg to arrive (plus its buffer) before these can start;
# "sequential" / "same_day" edges only order the day's plans
HARD_EDGE_TYPES = {"transfer_required", "checkin_dependency"}  # the original booking is cancelled/refunded
MAX_COMBINATIONS = 5000
PRUNE_PER_NODE = 4
MAX_ALTERNATIVES = 3
CATEGORY_LABEL = {
    "balanced": "Best Balanced Plan",
    "cheapest": "Cheapest Plan",
    "fastest": "Fastest Plan",
}


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _is_next_day(candidate: dict) -> bool:
    # explicit flag - matching on the word "next" misfired on same-day options like
    # "Express Cab (next available)" / "Next IndiGo Flight ... Same day"
    return bool(candidate.get("next_day"))


# --- candidates ------------------------------------------------------------------------


def _templates(node: BookingNode, by_provider: bool) -> list[dict]:
    """Generic options when the booking has no alternatives of its own. Prices are
    estimates derived from the traveler's own price and are labelled as such."""
    c = float(node.cost)
    cancelled = by_provider
    est = "estimate"
    if node.type == "flight":
        return [
            {"title": "Next available flight, same airline", "provider": node.provider, "start_offset_minutes": 180,
             "cost": round(0.35 * c), "rating": 75, "price_source": est, "action": "reschedule",
             "notes": "Airline must rebook free when it cancelled; otherwise change fee + fare difference (estimate)"},
            {"title": "Other airline, same day", "provider": "another airline", "start_offset_minutes": 120,
             "cost": round(1.1 * c), "rating": 80, "price_source": est, "notes": "New ticket at today's fare (estimate)"},
            {"title": "Next-day flight", "provider": node.provider, "start_offset_minutes": 1440, "next_day": True,
             "cost": round(0.15 * c), "rating": 55, "price_source": est, "action": "reschedule", "notes": "Loses a travel day"},
        ]
    if node.type == "train":
        return [
            {"title": "Next train on the same route", "provider": node.provider, "start_offset_minutes": 120,
             "cost": round(c), "rating": 70, "price_source": est, "notes": "New ticket, subject to availability"},
            {"title": "Tatkal ticket, next day", "provider": node.provider, "start_offset_minutes": 1440, "next_day": True,
             "cost": round(1.3 * c), "rating": 60, "price_source": est, "notes": "Tatkal premium applies"},
            {"title": "Intercity bus or cab for this leg", "provider": "book yourself", "start_offset_minutes": 60,
             "cost": round(0.8 * c), "rating": 50, "price_source": est, "manual": True, "notes": "Slower, but departs on demand"},
        ]
    if node.type == "hotel":
        out = []
        if not cancelled:
            out.append({"title": "Late check-in, same hotel", "provider": node.provider, "start_offset_minutes": 0,
                        "cost": 0, "rating": 90, "price_source": "user-entered", "action": "keep",
                        "notes": "Call the hotel so the room is held"})
        out.append({"title": "Alternate hotel nearby", "provider": "book yourself", "start_offset_minutes": 0,
                    "cost": round(1.2 * c), "rating": 70, "price_source": est, "manual": True, "notes": "Same-night booking premium (estimate)"})
        return out
    if node.type == "transfer":
        duration = int((_dt(node.end) - _dt(node.start)).total_seconds() // 60)
        # Intercity road legs (Jabalpur→Indore etc.) need corridor options, not airport shuttles.
        if duration >= 90:
            return [
                {"title": "Next available private cab / car", "provider": node.provider if node.provider != "unknown" else "book yourself",
                 "start_offset_minutes": 30, "cost": round(1.15 * c), "rating": 78, "price_source": est, "manual": True,
                 "notes": "Same corridor, next free car - book yourself (estimate)"},
                {"title": "Shared taxi / tempo traveller", "provider": "book yourself", "start_offset_minutes": 60,
                 "cost": round(0.65 * c), "rating": 62, "price_source": est, "manual": True,
                 "notes": "Cheaper shared seat; may wait to fill"},
                {"title": "Intercity bus on this corridor", "provider": "book yourself", "start_offset_minutes": 90,
                 "cost": round(0.45 * c), "rating": 58, "price_source": est, "manual": True,
                 "notes": "Fixed departure; check RedBus / state RTC"},
                {"title": "Rail alternative for this road leg", "provider": "book yourself", "start_offset_minutes": 180,
                 "cost": round(0.7 * c), "rating": 55, "price_source": est, "manual": True,
                 "notes": "Only if a useful train runs between these cities today"},
            ]
        return [
            {"title": "New cab (Uber / Ola / prepaid taxi)", "provider": "book yourself", "start_offset_minutes": 15,
             "cost": round(1.3 * c), "rating": 70, "price_source": est, "manual": True,
             "notes": "No live cab API - book it yourself; fare includes a surge estimate"},
            {"title": "Local shuttle or taxi counter", "provider": "book yourself", "start_offset_minutes": 30,
             "cost": round(0.8 * c), "rating": 55, "price_source": est, "manual": True, "notes": "Cheaper, may wait for others"},
        ]
    # activity / event
    return [
        {"title": "Later slot, same day", "provider": node.provider, "start_offset_minutes": 180, "cost": 0,
         "rating": 70, "price_source": est, "weather_safe": False, "action": "reschedule", "notes": "Ask the operator for a later slot"},
        {"title": "Next-day slot", "provider": node.provider, "start_offset_minutes": 1440, "next_day": True,
         "cost": round(0.1 * c), "rating": 65, "price_source": est, "weather_safe": False, "action": "reschedule",
         "notes": "Small reschedule fee (estimate)"},
        {"title": "Indoor alternative", "provider": "local operator", "start_offset_minutes": 0, "cost": round(0.5 * c),
         "rating": 55, "price_source": est, "weather_safe": True, "manual": True, "notes": "Covered option that runs in any weather"},
    ]


def _normalize(node: BookingNode, raw: dict, by_provider: bool) -> dict:
    duration = int((_dt(node.end) - _dt(node.start)).total_seconds() // 60)
    action = raw.get("action")
    if action is None:
        manual = bool(raw.get("manual")) or node.type == "transfer"  # no cab booking API exists
        action = "manual_booking" if manual else "rebook"
    cost = float(raw.get("cost", 0))
    notes = raw.get("notes", "")
    if action == "reschedule" and by_provider:
        # the provider cancelled: moving the traveler to its own next service is on the provider
        cost, notes = 0.0, (notes + "; free because the provider cancelled").strip("; ")
    return {
        "title": raw["title"],
        "provider": raw.get("provider", node.provider),
        "cost": cost,
        "rating": float(raw.get("rating", 60)),
        "notes": notes,
        "start_offset_minutes": int(raw.get("start_offset_minutes", 0)),
        "duration_minutes": int(raw.get("duration_minutes") or duration),
        "next_day": bool(raw.get("next_day")),
        "weather_safe": raw.get("weather_safe"),
        "price_source": raw.get("price_source", "catalog"),
        "action": action,
    }


def _as_list(disruption) -> list[dict]:
    if not disruption:
        return []
    return [d for d in (disruption if isinstance(disruption, list) else [disruption]) if d]


def _for_node(node_id: str, disruptions: list[dict]) -> dict | None:
    """The latest active disruption that originated at this booking."""
    return next((d for d in reversed(disruptions) if d.get("node_id") == node_id), None)


def candidates_for(node: BookingNode, disruption: dict | None) -> list[dict]:
    by_provider = provider_cancelled(node, disruption)
    raw = node.alternatives or _templates(node, by_provider)
    cands = [_normalize(node, r, by_provider) for r in raw]
    if node.status == "cancelled":
        # a cancelled booking no longer exists: "keep it" options (e.g. late check-in at the
        # same hotel) are impossible, whoever cancelled it
        cands = [c for c in cands if c["action"] != "keep"] or cands
    # the delayed booking itself still runs - staying on it is usually an option
    if (
        disruption
        and disruption.get("kind") == "delay"
        and disruption.get("node_id") == node.id
        and node.status != "cancelled"
    ):
        cands.insert(0, {
            # staying on your own booking needs no rebooking at all - highly convenient
            "title": f"Keep {node.title} (delayed)", "provider": node.provider, "cost": 0.0, "rating": 88.0,
            "notes": f"Still operating, {disruption.get('delay_minutes', 0)} min late", "next_day": False,
            "start_offset_minutes": int(disruption.get("delay_minutes") or 0),
            "duration_minutes": int((_dt(node.end) - _dt(node.start)).total_seconds() // 60),
            "weather_safe": None, "price_source": "user-entered", "action": "keep",
        })
    return cands


def _filtered(cands: list[dict], node: BookingNode, is_weather: bool, prefs: TravelerPreferences) -> list[dict]:
    """Preference filters narrow the candidates but never empty them."""
    if is_weather and node.weather_sensitive:
        cands = [c for c in cands if c.get("weather_safe") or c["action"] == "keep"] or cands
    if prefs.min_rating > 0:
        cands = [c for c in cands if c["rating"] >= prefs.min_rating] or cands
    if prefs.avoid_next_day:
        cands = [c for c in cands if not _is_next_day(c)] or cands
    return cands


def _prune(per_node: list[list[dict]]) -> list[list[dict]]:
    """Keeps the search exhaustive for normal trips; only very large ones get pruned to the
    cheapest, fastest and best-rated few options per booking."""
    size = 1
    for c in per_node:
        size *= len(c)
    if size <= MAX_COMBINATIONS:
        return per_node
    pruned = []
    for cands in per_node:
        keep = {id(min(cands, key=lambda c: c["cost"])), id(min(cands, key=lambda c: c["start_offset_minutes"]))}
        keep |= {id(c) for c in sorted(cands, key=lambda c: -c["rating"])[:PRUNE_PER_NODE]}
        pruned.append([c for c in cands if id(c) in keep])
    return pruned


# --- feasibility -------------------------------------------------------------------------


def _schedule(graph: ItineraryGraph, choice: dict[str, dict], disruption) -> tuple[dict | None, str | None]:
    disruptions = _as_list(disruption)
    """Effective start/end of every booking under this choice, or (None, reason) when it
    would make the traveler miss a scheduled booking."""
    order = _topological(graph)
    eff: dict[str, tuple[datetime, datetime] | None] = {}
    for nid in order:
        node = graph.nodes[nid]
        orig_start, orig_end = _dt(node.start), _dt(node.end)
        duration = orig_end - orig_start
        earliest = None
        for e in graph.predecessors(nid):
            pe = eff.get(e.source)
            if pe is None:
                continue  # dropped predecessor - no constraint
            if e.type in HARD_EDGE_TYPES:
                need = pe[1] + timedelta(minutes=e.buffer_minutes)
            elif pe[1].date() == orig_start.date():
                need = pe[1]  # soft ordering: just don't overlap on the same day
            else:
                continue  # soft ordering across days (e.g. an activity moved to tomorrow)
            earliest = need if earliest is None or need > earliest else earliest

        cand = choice.get(nid)
        if cand is not None:
            if cand["action"] == "drop":
                eff[nid] = None
                continue
            start = orig_start + timedelta(minutes=cand["start_offset_minutes"])
            dur = timedelta(minutes=cand["duration_minutes"]) if cand["duration_minutes"] else duration
            if earliest and earliest > start:
                if node.type in SCHEDULED_TYPES:
                    return None, f"{cand['title']} leaves at {start:%d %b %H:%M}, before you can make it ({earliest:%H:%M})"
                start = earliest  # on-demand: cab / check-in waits for you
            eff[nid] = (start, start + dur)
            continue

        # not being replaced: its lateness comes only from its predecessors under THIS plan,
        # plus its own delay if it is the delayed booking itself
        start = orig_start
        own = _for_node(nid, disruptions)
        if own and own.get("kind") == "delay":
            start += timedelta(minutes=int(own.get("delay_minutes") or 0))
        if earliest and earliest > start:
            if node.type in SCHEDULED_TYPES:
                return None, f"you would miss {node.title} ({node.start[11:16]})"
            start = earliest
        eff[nid] = (start, start + duration)
    return eff, None


def _topological(graph: ItineraryGraph) -> list[str]:
    indeg = {nid: 0 for nid in graph.nodes}
    for e in graph.edges:
        indeg[e.target] += 1
    ready = sorted((n for n, d in indeg.items() if d == 0), key=lambda n: graph.nodes[n].start)
    out = []
    while ready:
        n = ready.pop(0)
        out.append(n)
        for e in graph.successors(n):
            indeg[e.target] -= 1
            if indeg[e.target] == 0:
                ready.append(e.target)
                ready.sort(key=lambda x: graph.nodes[x].start)
    return out


# --- evaluation ----------------------------------------------------------------------------


def _decision_time(graph: ItineraryGraph) -> datetime:
    """When the traveler is making these changes: at the first disrupted booking."""
    hit = [n for n in graph.nodes.values() if n.status != "safe"]
    return min(_dt(n.start) for n in hit) if hit else min(_dt(n.start) for n in graph.nodes.values())


def _evaluate(graph: ItineraryGraph, broken: list[BookingNode], combo: tuple, schedule: dict, disruption=None) -> dict:
    disruptions = _as_list(disruption)
    decided_at = _decision_time(graph)
    money = {"penalty": 0.0, "cash_refund": 0.0, "credit": 0.0, "lost": 0.0, "new_spend": 0.0}
    options, ratings, replaced = [], [], 0
    for node, cand in zip(broken, combo):
        ratings.append(cand["rating"])
        if cand["action"] != "keep":
            replaced += 1
            money["new_spend"] += cand["cost"]
        if cand["action"] in NEW_BOOKING_ACTIONS:
            r = refund_for(node, decided_at, _for_node(node.id, disruptions))
            for k in ("penalty", "cash_refund", "credit", "lost"):
                money[k] += r[k]
        slot = schedule.get(node.id)
        options.append(RecoveryOption(
            node_id=node.id,
            replacement_title=cand["title"],
            provider=cand["provider"],
            cost=cand["cost"],
            start=slot[0].isoformat() if slot else node.start,
            end=slot[1].isoformat() if slot else node.end,
            notes=cand["notes"],
            action=cand["action"],
            requires_manual_booking=cand["action"] == "manual_booking",
            price_source=cand["price_source"],
            original_cost=float(node.cost),
            price_vs_original=round(cand["cost"] - float(node.cost), 2) if cand["action"] in NEW_BOOKING_ACTIONS else 0.0,
            market_price=None,
            market_price_source="unavailable - no live fare API configured",
        ))

    lateness = 0.0
    shifted = 0
    for nid, slot in schedule.items():
        if slot is None:
            continue
        late = (slot[0] - _dt(graph.nodes[nid].start)).total_seconds() / 60
        if late > 0:
            shifted += 1
            lateness = max(lateness, late)
    net_cash = money["new_spend"] - money["cash_refund"]
    return {
        "options": options,
        "money": {**{k: round(v, 2) for k, v in money.items()}, "net_cash": round(net_cash, 2),
                  "net_after_credit": round(net_cash - money["credit"], 2)},
        "time": int(round(lateness)),
        "convenience": round(sum(ratings) / len(ratings), 1),
        "pct_affected": round(100 * max(replaced, shifted) / len(graph.nodes), 1),
        "schedule": schedule,
    }


TIME_SCALE_MINUTES = 720  # losing half a day of the trip = zero time score


def _score(plans: list[dict], prefs: TravelerPreferences, trip_value: float = 0.0) -> None:
    """Explainable multi-objective score, 0-100, weighted by the traveler's preferences.
    Cost and time are measured against real-world scales (the trip's own value, half a day)
    rather than only against each other - otherwise spending INR 10,000 to save an hour
    looks almost as good as spending nothing whenever those are the only two options."""
    weights = {
        "cost": prefs.cost_weight, "time": prefs.time_weight,
        "convenience": prefs.convenience_weight, "disruption": prefs.disruption_weight,
    }
    w_total = sum(weights.values()) or 1.0
    costs = [p["money"]["net_cash"] for p in plans]
    times = [p["time"] for p in plans]

    def inv_norm(v, values, scale):
        lo, hi = min(values), max(values)
        span = max(hi - lo, scale)
        return 1.0 if span <= 0 else max(0.0, 1 - (v - lo) / span)

    cost_scale = max(trip_value, 1.0)

    for p in plans:
        normalized = {
            "cost": inv_norm(p["money"]["net_cash"], costs, cost_scale),
            "time": inv_norm(p["time"], times, TIME_SCALE_MINUTES),
            "convenience": p["convenience"] / 100,
            "disruption": 1 - p["pct_affected"] / 100,
        }
        values = {"cost": p["money"]["net_cash"], "time": p["time"], "convenience": p["convenience"], "disruption": p["pct_affected"]}
        units = {"cost": "INR net cash", "time": "min worst lateness", "convenience": "/100 avg rating", "disruption": "% of trip changed"}
        breakdown = {
            k: {
                "value": values[k], "unit": units[k], "normalized": round(normalized[k], 3),
                "weight": round(weights[k] / w_total, 3),
                "contribution": round(100 * weights[k] / w_total * normalized[k], 1),
            }
            for k in weights
        }
        p["score"] = round(sum(b["contribution"] for b in breakdown.values()), 1)
        p["breakdown"] = breakdown


def _action_items(graph: ItineraryGraph, plan: dict, disruption=None) -> list[str]:
    disruptions = _as_list(disruption)
    items = []
    decided_at = _decision_time(graph)
    for o in plan["options"]:
        node = graph.nodes[o.node_id]
        when = f"{_dt(o.start):%d %b %H:%M}"
        if o.action == "keep":
            items.append(f"Keep {node.title} - now around {when}; tell {node.provider} you will be late.")
            continue
        if o.action == "reschedule":
            fee = f" (~INR {o.cost:.0f} fee)" if o.cost else " (no fee)"
            items.append(f"Ask {node.provider} to move {node.title} to: {o.replacement_title} at {when}{fee}.")
            continue
        if o.action == "drop":
            items.append(f"Cancel {node.title} with {node.provider}.")
        elif o.action == "manual_booking":
            items.append(f"Book yourself: {o.replacement_title} for {when} (~INR {o.cost:.0f}, {o.price_source}).")
        else:
            items.append(f"Rebook with {o.provider}: {o.replacement_title} at {when} (~INR {o.cost:.0f}).")
        r = refund_for(node, decided_at, _for_node(node.id, disruptions))
        if r["cash_refund"]:
            items.append(f"Claim INR {r['cash_refund']:.0f} refund for {node.title} from {node.provider}.")
        if r["credit"]:
            items.append(f"Keep the INR {r['credit']:.0f} {node.provider} credit for {node.title}.")
    items.append("TripRescue does not book or pay - mark each booking as done once you have made it.")
    return items


def recovery_analysis(
    graph: ItineraryGraph,
    disruption_reason: str | None = None,
    preferences: TravelerPreferences | None = None,
    disruption: dict | None = None,
    impact_report: dict | None = None,
) -> dict:
    prefs = preferences or TravelerPreferences()
    broken = sorted((n for n in graph.nodes.values() if n.status in ("broken", "cancelled")), key=lambda n: n.start)
    if not broken:
        return {"plans": [], "combinations_checked": 0, "feasible": 0, "infeasible_examples": []}

    is_weather = bool(disruption_reason) and "weather" in disruption_reason.lower()
    disruptions = _as_list(disruption)
    per_node = _prune([_filtered(candidates_for(n, _for_node(n.id, disruptions)), n, is_weather, prefs) for n in broken])

    feasible, rejected = [], []
    checked = 0
    for combo in itertools.product(*per_node):
        checked += 1
        choice = {n.id: c for n, c in zip(broken, combo)}
        schedule, reason = _schedule(graph, choice, disruptions)
        if schedule is None:
            if len(rejected) < 5 and reason not in rejected:
                rejected.append(reason)
            continue
        feasible.append(_evaluate(graph, broken, combo, schedule, disruptions))

    if not feasible:
        return {"plans": [], "combinations_checked": checked, "feasible": 0, "infeasible_examples": rejected}

    _score(feasible, prefs, sum(float(n.cost) for n in graph.nodes.values()))
    by_score = sorted(feasible, key=lambda p: (-p["score"], p["money"]["net_cash"]))
    picks = {
        "balanced": by_score[0],
        "cheapest": min(feasible, key=lambda p: (p["money"]["net_cash"], -p["score"])),
        "fastest": min(feasible, key=lambda p: (p["time"], -p["score"])),
    }

    def key(p):
        return tuple((o.node_id, o.replacement_title) for o in p["options"])

    ordered: dict[tuple, dict] = {}
    for cat in ("balanced", "cheapest", "fastest"):
        p = picks[cat]
        entry = ordered.setdefault(key(p), {"plan": p, "category": cat, "badges": []})
        entry["badges"].append(cat)
    alt_n = 0
    for p in by_score:
        if alt_n >= MAX_ALTERNATIVES:
            break
        if key(p) not in ordered:
            alt_n += 1
            ordered[key(p)] = {"plan": p, "category": "alternative", "badges": [], "n": alt_n}

    plans = []
    for entry in ordered.values():
        p, cat = entry["plan"], entry["category"]
        pid = f"plan-{cat}" if cat != "alternative" else f"plan-alt-{entry['n']}"
        label = CATEGORY_LABEL.get(cat, f"Alternative {entry.get('n')}")
        plans.append(RecoveryPlan(
            id=pid,
            label=label,
            options=p["options"],
            total_cost_delta=p["money"]["net_cash"],
            total_time_delta_minutes=p["time"],
            convenience_score=p["convenience"],
            pct_itinerary_affected=p["pct_affected"],
            refund_recovered=round(p["money"]["cash_refund"] + p["money"]["credit"], 2),
            score=p["score"],
            category=cat,
            badges=entry["badges"],
            score_breakdown=p["breakdown"],
            money=p["money"],
            action_items=_action_items(graph, p, disruptions),
        ))
    return {"plans": plans, "combinations_checked": checked, "feasible": len(feasible), "infeasible_examples": rejected}


def generate_recovery_plans(
    graph: ItineraryGraph,
    disruption_reason: str | None = None,
    preferences: TravelerPreferences | None = None,
    disruption: dict | None = None,
    impact_report: dict | None = None,
) -> list[RecoveryPlan]:
    return recovery_analysis(graph, disruption_reason, preferences, disruption, impact_report)["plans"]


def apply_plan(graph: ItineraryGraph, plan: RecoveryPlan) -> None:
    """Records the chosen plan on the itinerary. Replacements take the new provider, price
    and times but stay `pending_manual_booking` - the traveler books them; nothing is
    booked or paid here."""
    for option in plan.options:
        node = graph.nodes.get(option.node_id)
        if not node:
            continue
        node.start, node.end = option.start, option.end
        node.status = "safe"
        if option.action == "keep":
            continue
        if option.action == "reschedule":
            node.title = f"{option.replacement_title} (Rescheduled)"
            node.cost = float(node.cost) + option.cost
            node.booking_status = "pending_manual_booking"
            continue
        if option.action == "drop":
            node.booking_status = "dropped"
            continue
        node.title = f"{option.replacement_title} (Recovered)"
        node.provider = option.provider
        node.cost = option.cost
        node.booking_status = "pending_manual_booking"
        node.alternatives = []

    for node in graph.nodes.values():
        if node.status in ("at_risk", "broken", "cancelled"):
            node.status = "safe"
