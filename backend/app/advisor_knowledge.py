"""TripRescue domain knowledge: the reference ("expert") answers for the three advisor
tasks, built deterministically from the impact/recovery engines plus Indian travel rules.

Used twice:
  - as the training/benchmark targets in the Nugen alignment dataset (nugen/build_dataset.py)
  - as the rule-based fallback when no aligned model or LLM is reachable
so the fallback and the aligned model agree on the facts.

Airline rules follow DGCA Civil Aviation Requirement Section 3 Series M Part IV
("Facilities to be provided to passengers by airlines due to denied boarding,
cancellation of flights and delays in flights"). Railway rules follow Indian Railways'
refund rules for confirmed e-tickets.
"""
from datetime import datetime

from app.graph_engine import ItineraryGraph
from app.models import RecoveryPlan
from app.money import TRAVELER_REASONS
from app.recovery_engine import REFUND_PCT

# DGCA: no cancellation compensation is owed when the cause is beyond the airline's control
EXTRAORDINARY_KEYWORDS = (
    "weather", "storm", "cyclone", "fog", "flood", "strike", "riot", "security",
    "political", "natural", "government", "curfew", "war",
)

POLICY_TEXT = {
    "free_24h": "free cancellation up to 24 hours before start, so a timely cancellation is refunded in full",
    "partial_50pct": "a 50% refund on cancellation",
    "non_refundable": "no refund if you cancel yourself",
}


def _block_minutes(node) -> int:
    fmt = datetime.fromisoformat
    return int((fmt(node.end) - fmt(node.start)).total_seconds() // 60)


def _is_extraordinary(reason: str | None) -> bool:
    r = (reason or "").lower()
    return any(k in r for k in EXTRAORDINARY_KEYWORDS)


def dgca_cancellation_compensation(block_minutes: int) -> int:
    if block_minutes <= 60:
        return 5000
    if block_minutes <= 120:
        return 7500
    return 10000


def dgca_meal_threshold_minutes(block_minutes: int) -> int:
    if block_minutes <= 150:
        return 120
    if block_minutes <= 300:
        return 180
    return 240


def fmt_minutes(minutes: int) -> str:
    if minutes < 120:
        return f"{minutes} minutes"
    hours = minutes / 60
    return f"{minutes} minutes (about {hours:.0f} hours)" if hours < 48 else f"{minutes} minutes (about {hours / 24:.0f} days)"


def _fmt_time(iso: str | None) -> str:
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso)
    return dt.strftime("%d %b %H:%M")


# --- EXPLAIN_IMPACT ---------------------------------------------------------------


def impact_answer(disruption: dict, impact_report: dict, graph: ItineraryGraph) -> str:
    origin_id = disruption.get("node_id")
    kind = disruption.get("kind")

    if kind == "weather":
        headline = (
            f"A {disruption.get('severity', 'moderate')} weather event on {disruption.get('date')} "
            "hits your outdoor plans and road travel that day."
        )
    else:
        origin = graph.nodes.get(origin_id)
        title = origin.title if origin else origin_id
        if kind == "cancel":
            headline = f"{title} was cancelled."
        else:
            new_end = (impact_report.get(origin_id) or {}).get("new_end")
            when = f", now finishing around {_fmt_time(new_end)}" if new_end else ""
            headline = f"{title} is delayed by {fmt_minutes(disruption.get('delay_minutes', 0))}{when}."

    broken, at_risk, safe = [], [], []
    for nid, node in graph.nodes.items():
        if nid == origin_id:
            continue
        if node.status in ("broken", "cancelled"):
            broken.append(node)
        elif node.status == "at_risk":
            at_risk.append(node)
        elif nid not in impact_report or not (impact_report[nid] or {}).get("overrun_minutes"):
            safe.append(node)

    parts = [headline]
    if broken:
        names = ", ".join(n.title for n in broken)
        verb = "needs" if len(broken) == 1 else "need"
        parts.append(
            f"Because each booking depends on the one before it, {names} can no longer go ahead as booked "
            f"and {verb} a recovery plan."
        )
    if at_risk:
        descr = []
        for n in at_risk:
            shift = (impact_report.get(n.id) or {}).get("overrun_minutes")
            descr.append(f"{n.title} (pushed about {fmt_minutes(shift)})" if shift else n.title)
        verb = "is" if len(at_risk) == 1 else "are"
        parts.append(f"{', '.join(descr)} {verb} at risk but still recoverable, so keep an eye on it.")
    if not broken and not at_risk:
        parts.append("Your downstream connections still fit within their buffers, so the rest of the trip stays unaffected.")
    elif safe:
        parts.append(f"{', '.join(n.title for n in safe[:3])} and later plans are unaffected.")
    return " ".join(parts)


# --- RECOMMEND_PLAN ---------------------------------------------------------------


def plans_answer(plans: list[RecoveryPlan]) -> str:
    if not plans:
        return "Nothing in your itinerary needs recovering right now, so no change is required."
    top = plans[0]
    picks = ", ".join(f"{o.replacement_title} from {o.provider}" for o in top.options)
    parts = [
        f"I recommend '{top.label}': it uses {picks}, costs a net INR {top.total_cost_delta:+.0f} after "
        f"INR {top.refund_recovered:.0f} in refunds, adds about {top.total_time_delta_minutes} minutes and "
        f"scores {top.convenience_score:.0f}/100 on convenience while touching {top.pct_itinerary_affected:.0f}% of your trip."
    ]
    for alt in plans[1:3]:
        cheaper = alt.total_cost_delta < top.total_cost_delta
        faster = alt.total_time_delta_minutes < top.total_time_delta_minutes
        trade = (
            "is cheaper" if cheaper and not faster
            else "is faster" if faster and not cheaper
            else "is cheaper and faster" if cheaper and faster
            else "costs more and takes longer"
        )
        parts.append(
            f"'{alt.label}' {trade} (net INR {alt.total_cost_delta:+.0f}, +{alt.total_time_delta_minutes} min) "
            f"but rates {alt.convenience_score:.0f}/100 on convenience."
        )
    return " ".join(parts)


# --- TRAVELER_RIGHTS --------------------------------------------------------------


def _flight_rights(node, disruption: dict, is_origin: bool) -> str:
    block = _block_minutes(node)
    reason = disruption.get("reason")
    if is_origin and disruption.get("kind") == "cancel" and str(reason or "").lower() in TRAVELER_REASONS:
        return (
            f"You cancelled {node.title} yourself, so DGCA passenger-charter refunds and compensation do not apply; "
            f"the fare rules ({POLICY_TEXT.get(node.cancellation_policy, node.cancellation_policy)}) decide what comes back."
        )
    if is_origin and disruption.get("kind") == "cancel":
        comp = dgca_cancellation_compensation(block)
        text = (
            f"For the cancelled {node.title}, DGCA rules entitle you to a full refund or an alternate flight; "
            "if you were told less than 24 hours before departure the airline must also pay compensation of "
            f"INR {comp} or your one-way basic fare plus fuel charge, whichever is lower"
        )
        if _is_extraordinary(reason):
            text += ", although that compensation is not owed when the cause is beyond the airline's control such as weather"
        return text + "."
    if is_origin and disruption.get("kind") == "delay":
        delay = disruption.get("delay_minutes", 0)
        meal = dgca_meal_threshold_minutes(block)
        bits = [f"For the delayed {node.title}, DGCA rules give you free meals and refreshments once the delay reaches {meal // 60} hours"]
        if delay > 360:
            bits.append("and because it exceeds 6 hours you may choose an alternate flight within 6 hours or a full refund")
        if delay > 1440:
            bits.append("plus free hotel accommodation since it is beyond 24 hours")
        return " ".join(bits) + "; there is no cash compensation for delays alone."
    return f"{node.title} was not disrupted by the airline itself, so standard fare rules ({POLICY_TEXT.get(node.cancellation_policy, node.cancellation_policy)}) apply if you change it."


def _train_rights(node, disruption: dict, is_origin: bool) -> str:
    if is_origin and disruption.get("kind") == "cancel":
        return f"For the cancelled {node.title}, Indian Railways refunds the full fare; e-ticket refunds are processed automatically."
    if is_origin and disruption.get("delay_minutes", 0) > 180:
        return (
            f"Since {node.title} is running more than 3 hours late, you can get a full fare refund if you do not travel, "
            "by cancelling or filing a TDR before the train actually departs."
        )
    return f"{node.title} follows normal railway cancellation charges if you change it yourself."


def _booking_rights(node, disruption: dict, is_origin: bool) -> str:
    if node.type == "flight":
        return _flight_rights(node, disruption, is_origin)
    if node.type == "train":
        return _train_rights(node, disruption, is_origin)
    refund = node.cost * REFUND_PCT.get(node.cancellation_policy, 0.0)
    policy = POLICY_TEXT.get(node.cancellation_policy, node.cancellation_policy)
    if node.type == "hotel":
        return (
            f"{node.title} has {policy} (about INR {refund:.0f} back); call the hotel now to flag a late arrival "
            "so the room is not released as a no-show."
        )
    if is_origin and disruption.get("kind") == "cancel":
        return (
            f"{node.provider} cancelled {node.title}, and a provider-side cancellation normally entitles you to a "
            "reschedule or refund even on a non-refundable booking, so ask them for it in writing."
        )
    if node.cancellation_policy == "non_refundable":
        return (
            f"{node.title} is non-refundable, so contact {node.provider} to reschedule rather than cancel, "
            "and keep proof of the upstream disruption."
        )
    return f"{node.title} has {policy}, worth about INR {refund:.0f} if you cancel."


def rights_answer(disruption: dict, impact_report: dict, graph: ItineraryGraph) -> str:
    origin_id = disruption.get("node_id")
    affected = [
        n for n in graph.nodes.values()
        if n.status in ("broken", "cancelled", "at_risk") or n.id == origin_id
    ]
    if not affected:
        return "No booking is affected, so there is nothing to claim; your itinerary stands as booked."
    parts = [_booking_rights(n, disruption, n.id == origin_id) for n in affected[:4]]
    if any(n.type == "flight" for n in affected):
        parts.append(
            "Keep screenshots of every delay or cancellation notice and claim refunds to the original payment "
            "method, which DGCA requires within 7 days for card payments."
        )
    else:
        parts.append("Keep screenshots of every delay or cancellation notice and the receipts for anything you pay extra.")
    return " ".join(parts)


# --- General policy knowledge (training data + benchmark) ---------------------------

POLICY_QA: list[tuple[str, str]] = [
    ("What compensation does DGCA require when a domestic flight with a block time under 1 hour is cancelled at short notice?",
     "If you are informed less than 24 hours before departure, the airline must pay INR 5,000 or your one-way basic fare plus fuel charge, whichever is lower, in addition to a refund or alternate flight."),
    ("What compensation does DGCA require when a flight with a block time between 1 and 2 hours is cancelled at short notice?",
     "INR 7,500 or the one-way basic fare plus fuel charge, whichever is lower, on top of a full refund or alternate flight."),
    ("What compensation does DGCA require when a flight with a block time over 2 hours is cancelled at short notice?",
     "INR 10,000 or the one-way basic fare plus fuel charge, whichever is lower, on top of a full refund or alternate flight."),
    ("Is compensation owed if an Indian airline cancels because of bad weather?",
     "No. DGCA exempts cancellations caused by extraordinary circumstances beyond the airline's control, such as weather, natural disasters, strikes or security risks, from compensation, but you still get a refund or alternate flight."),
    ("What must an airline offer if it cancels a flight and informs the passenger at least two weeks before departure?",
     "An alternate flight or a full refund, whichever the passenger prefers; no extra compensation is owed with that much notice."),
    ("What must an airline offer if it cancels a flight less than two weeks but more than 24 hours before departure?",
     "An alternate flight departing within two hours of the original time, or a full refund if that alternative is not acceptable."),
    ("When do Indian airlines have to give free meals during a delay?",
     "Free meals and refreshments are due once the delay reaches 2 hours for flights with block time up to 2.5 hours, 3 hours for block time of 2.5 to 5 hours, and 4 hours for longer flights."),
    ("What are my options if my domestic flight is delayed by more than 6 hours?",
     "If the airline informed you 24 hours in advance of a delay beyond 6 hours, it must offer an alternate flight within 6 hours of the original departure or a full refund."),
    ("When must an airline provide a hotel during a flight delay in India?",
     "When the delay exceeds 24 hours, or 6 hours for flights scheduled between 20:00 and 03:00, the airline must provide free hotel accommodation including transfers."),
    ("Do Indian airlines pay cash compensation for flight delays?",
     "No. DGCA rules give meals, refund or rebooking, and hotel accommodation for long delays, but no cash compensation for a delay alone."),
    ("What compensation is due for denied boarding if the airline rebooks me within 24 hours?",
     "200% of your one-way basic fare plus fuel charge, capped at INR 10,000; no compensation is due if the alternate flight departs within 1 hour."),
    ("What compensation is due for denied boarding if the alternate flight is more than 24 hours later?",
     "400% of your one-way basic fare plus fuel charge, capped at INR 20,000."),
    ("How quickly must an Indian airline refund a cancelled ticket?",
     "Within 7 days for credit card payments, immediately for cash payments at the airline office, and within 30 days when booked through a travel agent, who is responsible for passing it on."),
    ("I missed my connecting flight because the first flight was late. Who has to fix it?",
     "If both flights are on the same PNR, the airline must rebook you at no cost; if they were separate tickets, the second airline has no obligation and you bear the change cost, which is why separate tickets need bigger buffers."),
    ("What refund do I get from Indian Railways if my train is cancelled?",
     "A full fare refund; for e-tickets it is processed automatically to the original payment method."),
    ("My train is running more than 3 hours late. Can I get a refund?",
     "Yes. If you choose not to travel, you get a full fare refund by cancelling or filing a TDR before the train's actual departure."),
    ("What does a free_24h cancellation policy mean?",
     "You get a full refund if you cancel more than 24 hours before the booking starts; later cancellations usually lose some or all of the charge."),
    ("What does a partial_50pct cancellation policy mean?",
     "You recover 50% of the booking cost when you cancel, so a replacement costs you the new price minus half of the original."),
    ("What does a non_refundable policy mean when the provider cancels?",
     "Non-refundable only covers your own cancellation; when the provider cancels, you are normally entitled to a reschedule or refund, so ask for it in writing."),
    ("My flight is delayed and I will reach the hotel late. What should I do?",
     "Call the hotel right away to flag a late arrival so the room is held and not released as a no-show, which on many bookings also cancels the remaining nights."),
    ("My flight is delayed and I have a pre-booked airport transfer. What should I do?",
     "Message the transfer operator with the new arrival time; most will reschedule for free if told early, whereas a no-show on a non-refundable transfer is usually lost."),
    ("An outdoor tour is cancelled because of heavy rain. What should I ask for?",
     "Because the operator cancelled, ask for a later slot or a full refund; if the weather is severe all day, prefer indoor alternatives so the day is not lost."),
    ("How much buffer should I keep between a flight landing and a pre-booked transfer?",
     "At least 30 to 60 minutes for domestic arrivals with cabin bags, and more if you check bags or the transfer is non-refundable."),
    ("Why does one delayed flight break several bookings in my itinerary?",
     "Bookings form a dependency chain: the transfer needs the flight to land, and hotel check-in needs the transfer, so when a delay eats the buffer between two linked bookings the next one can no longer start on time and the break cascades."),
    ("What is the difference between a broken booking and an at-risk booking?",
     "A broken booking can no longer happen as booked and needs a replacement; an at-risk booking has been pushed later but can still be kept, for example a hotel that will hold a room for a late check-in."),
    ("How should I choose between recovery plans?",
     "Compare the net cost after refunds, the added time, the convenience score and how much of the trip changes, then weight them by what matters to you; the cheapest plan often costs the most time."),
    ("Should I cancel my non-refundable activity when my flight is delayed?",
     "No, not first; rescheduling with the operator keeps your money, whereas cancelling a non-refundable booking forfeits it."),
    ("What documents should I keep after a travel disruption?",
     "Keep the airline or operator's delay or cancellation notice, boarding passes, receipts for meals, taxis or hotels you paid for, and screenshots of any rebooking offers, since refunds and insurance claims need them."),
    ("Can travel insurance cover costs after a flight cancellation in India?",
     "Many travel policies reimburse extra hotel, transport or rebooking costs caused by a covered disruption, so file with the carrier's written notice and your receipts."),
    ("A severe weather warning covers tomorrow. What should I change?",
     "Move weather-sensitive outdoor activities to another day or swap them for indoor options, add buffer to road transfers, and check whether your flights have a free rebooking waiver."),
]


# --- WEATHER_TWIN -----------------------------------------------------------------

DRIVER_TEXT = {
    "rain_mm_h": "rain intensity", "wind_10kmh": "wind", "heat_over_35c": "heat",
    "flood_index": "flooding", "storm_6h": "storm duration", "social_index": "on-the-ground reports",
}


def twin_answer(sim: dict, scenario: dict | None) -> str:
    trip = sim["trip"]
    nodes = sorted(sim["nodes"].values(), key=lambda e: e["p_broken"] + e["p_at_risk"], reverse=True)
    hit = [e for e in nodes if e["p_broken"] + e["p_at_risk"] >= 0.3]
    if not hit:
        return (
            f"Under these conditions your trip runs as planned: there is only a {trip['p_any_disruption']:.0%} chance "
            "of any booking breaking, so no action is needed beyond keeping an eye on the forecast."
        )
    top = hit[0]
    driver = DRIVER_TEXT.get(top.get("top_driver") or "", "the weather")
    p_top = top["p_broken"] + top["p_at_risk"]
    cancel = f", including a {top['p_cancelled']:.0%} chance of outright cancellation" if top["p_cancelled"] >= 0.1 else ""
    parts = [
        f"{top['title']} is the weak point: {driver} makes it {p_top:.0%} likely to be disrupted{cancel}, "
        f"with delays of about {top['delay_p50']:.0f} minutes and up to {top['delay_p90']:.0f} in a bad case."
    ]
    also = [f"{e['title']} ({e['p_broken'] + e['p_at_risk']:.0%})" for e in hit[1:4]]
    if also:
        parts.append(f"Also likely affected, directly or through connected bookings: {', '.join(also)}.")
    for place, eco in sim["ecosystem"].items():
        if eco["cab_availability"]["mean"] <= 0.8 or eco["hotel_occupancy"]["mean"] >= 0.8:
            parts.append(
                f"Around {place}, cabs drop to {eco['cab_availability']['mean']:.0%} availability and hotels reach "
                f"{eco['hotel_occupancy']['mean']:.0%} occupancy, so recovery options get scarcer and pricier the longer you wait."
            )
            break
    if top["type"] == "activity":
        action = f"move {top['title']} to an indoor or later slot while rescheduling is still free"
    elif top["type"] == "flight":
        action = f"check {top['title']}'s rebooking options early and flag a late arrival to your hotel"
    else:
        action = f"pre-book a reliable alternative to {top['title']} and add buffer before the next booking"
    parts.append(
        f"Overall there is a {trip['p_any_disruption']:.0%} chance of disruption with about INR "
        f"{trip['expected_loss_inr']:.0f} at stake; the best move now is to {action}."
    )
    return " ".join(parts)
