"""What the traveler gets back (or loses) when a booking has to be replaced.

Who cancelled matters:
  - provider cancelled (status "cancelled"): the traveler is owed a full refund - the
    DGCA rule for flights, and standard practice for hotels, rail and operators
  - traveler walks away from a booking that still runs (it "broke" because something
    upstream moved): the booking's own terms apply - a fixed user-entered
    `cancellation_penalty` if given, else the `cancellation_policy` percentage
Refunds come back as cash or as provider credit depending on `refund_mode`; credit is
tracked separately because it isn't money in hand.
"""
from datetime import datetime

from app.models import BookingNode

FREE_CANCEL_WINDOW_HOURS = 24
# a "cancelled" booking whose cancellation the TRAVELER asked for is not a provider cancellation
TRAVELER_REASONS = {"traveler_request", "traveller_request", "traveler_change", "personal"}


def provider_cancelled(node: BookingNode, disruption: dict | None = None) -> bool:
    if node.status != "cancelled":
        return False
    if disruption and disruption.get("node_id") == node.id and str(disruption.get("reason", "")).lower() in TRAVELER_REASONS:
        return False
    return True

REFUND_PCT = {
    "free_24h": 1.0,
    "partial_50pct": 0.5,
    "non_refundable": 0.0,
}


def refund_for(node: BookingNode, decided_at: datetime | None = None, disruption: dict | None = None) -> dict:
    """`decided_at` is when the traveler cancels; a free-cancellation policy only applies
    if that is still outside its window (24 h before the booking starts)."""
    cost = float(node.cost)
    pct = REFUND_PCT.get(node.cancellation_policy, 0.0)
    if node.cancellation_policy == "free_24h" and decided_at is not None:
        hours_before = (datetime.fromisoformat(node.start) - decided_at).total_seconds() / 3600
        if hours_before < FREE_CANCEL_WINDOW_HOURS:
            pct = 0.0  # past the free window; enter cancellation_penalty for the exact late fee
    by_provider = provider_cancelled(node, disruption)
    if by_provider:
        refundable, penalty = cost, 0.0
    elif node.cancellation_penalty is not None:
        penalty = min(cost, float(node.cancellation_penalty))
        refundable = cost - penalty
    else:
        refundable = cost * pct
        penalty = cost - refundable

    cash = refundable if node.refund_mode == "cash" else 0.0
    credit = refundable if node.refund_mode == "credit" else 0.0
    lost = cost - cash - credit
    return {
        "original_cost": round(cost, 2),
        "penalty": round(penalty, 2),
        "cash_refund": round(cash, 2),
        "credit": round(credit, 2),
        "lost": round(lost, 2),
        "provider_cancelled": by_provider,
    }
