"""Prompt formats for the TripRescue Advisor model.

These builders are the single source of truth for what the model sees: the Nugen
alignment dataset (nugen/build_dataset.py) is generated with exactly these functions,
and the live app calls them again at inference time. Training on the same compact
format the model is served with is what makes the aligned model domain-specific
rather than a generic chatbot we happen to prompt.
"""
from app.graph_engine import ItineraryGraph
from app.models import RecoveryPlan, TravelerPreferences

SYSTEM_PROMPT = (
    "You are TripRescue Advisor, a travel disruption recovery specialist for trips in India. "
    "You read a structured itinerary disruption and answer calmly, concisely and accurately "
    "for a stressed traveler. Plain sentences only - no markdown, no bullet points, no preamble."
)

TASK_IMPACT = "EXPLAIN_IMPACT"
TASK_PLANS = "RECOMMEND_PLAN"
TASK_RIGHTS = "TRAVELER_RIGHTS"
TASK_TWIN = "WEATHER_TWIN"


def _disruption_line(disruption: dict, graph: ItineraryGraph | None) -> str:
    kind = disruption.get("kind")
    reason = disruption.get("reason") or "unspecified"
    if kind == "weather":
        return f"weather event, severity={disruption.get('severity')}, date={disruption.get('date')}, reason={reason}"
    node = graph.nodes.get(disruption.get("node_id")) if graph else None
    title = node.title if node else disruption.get("node_id")
    if kind == "cancel":
        return f"{disruption.get('node_id')} ({title}) cancelled, reason={reason}"
    return f"{disruption.get('node_id')} ({title}) delayed {disruption.get('delay_minutes', 0)} min, reason={reason}"


def _booking_lines(graph: ItineraryGraph, impact_report: dict) -> list[str]:
    lines = []
    for node in graph.nodes.values():
        info = impact_report.get(node.id) or {}
        overrun = info.get("overrun_minutes")
        shift = f", pushed {overrun} min" if overrun else ""
        lines.append(
            f"- {node.id} | {node.type} | {node.title} | {node.start} | status={node.status}{shift} "
            f"| policy={node.cancellation_policy} | cost=INR {node.cost:.0f}"
        )
    return lines


def impact_prompt(disruption: dict, impact_report: dict, graph: ItineraryGraph) -> str:
    return "\n".join(
        [
            f"TASK: {TASK_IMPACT}",
            f"DISRUPTION: {_disruption_line(disruption, graph)}",
            "BOOKINGS:",
            *_booking_lines(graph, impact_report),
            "Explain in 2-3 sentences what happened, which bookings are affected and why, "
            "and which remain safe.",
        ]
    )


def plans_prompt(
    plans: list[RecoveryPlan],
    disruption: dict | None,
    graph: ItineraryGraph | None,
    preferences: TravelerPreferences | None = None,
) -> str:
    prefs = preferences or TravelerPreferences()
    lines = [
        f"TASK: {TASK_PLANS}",
        f"DISRUPTION: {_disruption_line(disruption, graph) if disruption else 'unspecified'}",
        (
            f"PREFERENCES: cost={prefs.cost_weight} time={prefs.time_weight} "
            f"convenience={prefs.convenience_weight} disruption={prefs.disruption_weight}"
        ),
        "PLANS (ranked best first):",
    ]
    for i, p in enumerate(plans, 1):
        picks = "; ".join(f"{o.node_id}->{o.replacement_title} ({o.provider}, INR {o.cost:.0f})" for o in p.options)
        lines.append(
            f"{i}. {p.label} | net cost INR {p.total_cost_delta:+.0f} | +{p.total_time_delta_minutes} min "
            f"| convenience {p.convenience_score}/100 | {p.pct_itinerary_affected}% of trip "
            f"| refund INR {p.refund_recovered:.0f} | {picks}"
        )
    lines.append("Recommend the first plan in 2-4 sentences and contrast it with the alternatives.")
    return "\n".join(lines)


def rights_prompt(disruption: dict, impact_report: dict, graph: ItineraryGraph) -> str:
    return "\n".join(
        [
            f"TASK: {TASK_RIGHTS}",
            f"DISRUPTION: {_disruption_line(disruption, graph)}",
            "BOOKINGS:",
            *_booking_lines(graph, impact_report),
            "State the traveler's refund and compensation entitlements for the affected bookings "
            "and the concrete next steps, in 3-5 sentences.",
        ]
    )


def _scenario_line(scenario: dict | None) -> str:
    if not scenario or not scenario.get("overrides"):
        return "live forecast (no what-if overrides)"
    o = {k: v for k, v in scenario["overrides"].items() if v is not None}
    where = scenario.get("target_place") or "all"
    when = scenario.get("target_date") or "whole trip"
    return f"what-if {o} at {where} on {when}"


def twin_prompt(sim: dict, scenario: dict | None) -> str:
    lines = [
        f"TASK: {TASK_TWIN}",
        f"SCENARIO: {_scenario_line(scenario)}",
        (
            f"TRIP: P(any disruption)={sim['trip']['p_any_disruption']:.0%}, "
            f"expected loss INR {sim['trip']['expected_loss_inr']:.0f}, "
            f"expected extra delay {sim['trip']['expected_extra_minutes']:.0f} min"
        ),
        "BOOKINGS:",
    ]
    for e in sim["nodes"].values():
        w = e["weather"]
        lines.append(
            f"- {e['id']} | {e['type']} | {e['title']} | P(broken)={e['p_broken']:.0%} P(at_risk)={e['p_at_risk']:.0%} "
            f"| delay p50/p90={e['delay_p50']:.0f}/{e['delay_p90']:.0f} min | rain {w.get('rain_mm_h', 0):.1f} mm/h, "
            f"wind {w.get('wind_kmh', 0):.0f} km/h, {w.get('temp_c', 0):.0f}C | driver={e.get('top_driver') or 'none'}"
        )
    lines.append("ECOSYSTEM:")
    for place, eco in sim["ecosystem"].items():
        lines.append(
            f"- {place}: cabs {eco['cab_availability']['mean']:.0%}, road time x{eco['road_travel_time_x']['mean']:.2f}, "
            f"hotel occupancy {eco['hotel_occupancy']['mean']:.0%}, outdoor demand {eco['outdoor_attraction_demand']['mean']:.0%}, "
            f"workforce {eco['workforce_availability']['mean']:.0%}"
        )
    lines.append(
        "Brief the traveler in 3-5 sentences: the most likely impact with its probability, what "
        "cascades from it, and the single most useful action to take now."
    )
    return "\n".join(lines)
