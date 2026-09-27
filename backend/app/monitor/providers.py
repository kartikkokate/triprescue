"""Provider checks for proactive monitoring. Each returns a ProviderResult with freshness
and evidence, and never raises: a failing API becomes status "error", a missing API
"unavailable", an irrelevant booking "skipped".

Signals are decided by fixed rules here - never by an LLM.
"""
from datetime import datetime, timedelta

from app import external_apis
from app.models import BookingNode
from app.twin import weather
from app.twin.learner import learner

FLIGHT_WINDOW_BEFORE_H = 24  # only spend live flight-status quota on flights departing soon
FLIGHT_WINDOW_AFTER_H = 6
WEATHER_HORIZON_DAYS = 16  # Open-Meteo forecast range
FRESH_MINUTES = {"flight": 20, "weather": 60, "road": 60, "rail": 0, "hotel": 0}

THUNDER_CODES = set(range(95, 100))


def _result(provider: str, category: str, node: BookingNode, status: str, now: datetime,
            evidence: dict | None = None, signal: dict | None = None) -> dict:
    return {
        "provider": provider,
        "category": category,
        "node_id": node.id,
        "status": status,  # ok | skipped | unavailable | error
        "checked_at": now.isoformat(timespec="seconds"),
        "fresh_until": (now + timedelta(minutes=FRESH_MINUTES.get(category, 20))).isoformat(timespec="seconds"),
        "evidence": evidence or {},
        "signal": signal,
    }


def check_flight(node: BookingNode, now: datetime) -> dict:
    if not node.service_code:
        return _result("AviationStack", "flight", node, "skipped", now, {"reason": "no flight number on booking"})
    dep = datetime.fromisoformat(node.start)
    if not (now - timedelta(hours=FLIGHT_WINDOW_AFTER_H) <= dep <= now + timedelta(hours=FLIGHT_WINDOW_BEFORE_H)):
        return _result("AviationStack", "flight", node, "skipped", now,
                       {"reason": f"departure outside the {FLIGHT_WINDOW_BEFORE_H} h live-status window"})
    try:
        r = external_apis.check_flight_status(node.service_code)
    except Exception as e:  # never let a provider take the monitor down
        return _result("AviationStack", "flight", node, "error", now, {"error": type(e).__name__})
    if not r.get("configured"):
        return _result("AviationStack", "flight", node, "unavailable", now, {"reason": "AVIATIONSTACK_API_KEY not set"})
    if r.get("error"):
        return _result("AviationStack", "flight", node, "error", now, {"error": r["error"]})
    if not r.get("found"):
        return _result("AviationStack", "flight", node, "ok", now, {"message": r.get("message")})
    evidence = {"flight": node.service_code, "status": r.get("status"), "delay_minutes": r.get("delay_minutes")}
    signal = None
    if r.get("status") == "cancelled":
        signal = {"kind": "cancel", "severity": "high", "reason": f"{node.service_code} cancelled (airline status)"}
    elif (r.get("delay_minutes") or 0) >= 15:
        d = int(r["delay_minutes"])
        signal = {"kind": "delay", "delay_minutes": d, "severity": "high" if d >= 120 else "medium",
                  "reason": f"{node.service_code} departing {d} min late (airline status)"}
    return _result("AviationStack", "flight", node, "ok", now, evidence, signal)


def _severity(c: dict) -> str | None:
    if (c.get("weather_code") in THUNDER_CODES or c.get("rain_mm_h", 0) >= 15
            or c.get("wind_kmh", 0) >= 60 or c.get("flood_index", 0) >= 0.6):
        return "severe"
    if c.get("rain_mm_h", 0) >= 5 or c.get("wind_kmh", 0) >= 40 or c.get("flood_index", 0) >= 0.3 or c.get("temp_c", 0) >= 42:
        return "moderate"
    return None


def check_weather(node: BookingNode, now: datetime) -> list[dict]:
    """Weather at the booking (Open-Meteo), plus the derived road/cab check for transfers -
    there is no live cab or traffic API, so road safety is inferred from weather and flooding."""
    start = datetime.fromisoformat(node.start)
    if start < now - timedelta(hours=2) or start > now + timedelta(days=WEATHER_HORIZON_DAYS):
        return [_result("Open-Meteo", "weather", node, "skipped", now, {"reason": "booking outside forecast horizon"})]
    if node.lat is None:
        return [_result("Open-Meteo", "weather", node, "skipped", now, {"reason": "booking has no coordinates"})]
    try:
        fc = weather.fetch_forecast(node.lat, node.lon)
        c = weather.conditions_at(fc, node.start)
        if fc is None:
            return [_result("Open-Meteo", "weather", node, "error", now, {"error": "forecast request failed"})]
        if c is None:
            return [_result("Open-Meteo", "weather", node, "skipped", now,
                            {"reason": "forecast does not reach this booking yet - will check again next run"})]
        c["flood_index"] = weather.flood_index(weather.fetch_flood(node.lat, node.lon), node.start[:10])
    except Exception as e:
        return [_result("Open-Meteo", "weather", node, "error", now, {"error": type(e).__name__})]

    sev = _severity(c)
    evidence = {k: c.get(k) for k in ("time", "rain_mm_h", "precip_prob", "wind_kmh", "temp_c", "weather_code", "flood_index")}
    results = []
    signal = None
    if sev and node.type == "activity" and node.weather_sensitive:
        signal = ({"kind": "cancel", "severity": "high", "reason": "forecast makes this outdoor booking unsafe"}
                  if sev == "severe" else
                  {"kind": "delay", "delay_minutes": 120, "severity": "medium", "reason": "rain likely - expect a later slot"})
    elif sev == "severe" and node.type == "flight":
        d = int(round(learner.expected_delay("flight", c)))
        if d >= 15:
            signal = {"kind": "delay", "delay_minutes": d, "severity": "medium",
                      "reason": f"severe weather forecast - twin estimates ~{d} min delay"}
    results.append(_result("Open-Meteo", "weather", node, "ok", now, evidence, signal))

    if node.type == "transfer":
        road = None
        if sev == "severe":
            road = {"kind": "cancel", "severity": "high",
                    "reason": "roads unsafe (severe weather / flooding): existing cab likely cancelled - new cab required, book it yourself"}
        elif sev == "moderate":
            road = {"kind": "delay", "delay_minutes": 30, "severity": "medium", "reason": "wet roads - allow ~30 min extra"}
        results.append(_result("Road (derived from weather)", "road", node, "ok", now,
                               {"basis": "no live cab/traffic API - inferred from forecast", **evidence}, road))
    return results


def check_rail(node: BookingNode, now: datetime) -> dict:
    return _result("Indian Railways", "rail", node, "unavailable", now,
                   {"reason": "no free live train-status API is configured; enter delays manually"})


def check_hotel(node: BookingNode, now: datetime) -> dict:
    return _result("Hotel", "hotel", node, "unavailable", now,
                   {"reason": "hotels expose no public status API; changes come from the traveler or the hotel"})


def checks_for(node: BookingNode, now: datetime) -> list[dict]:
    out: list[dict] = []
    if node.type == "flight":
        out.append(check_flight(node, now))
    elif node.type == "train":
        out.append(check_rail(node, now))
    elif node.type == "hotel":
        out.append(check_hotel(node, now))
    out.extend(check_weather(node, now))
    return out
