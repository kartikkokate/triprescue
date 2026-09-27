"""Real external data feeds: live weather forecast (OpenWeatherMap) and live flight
status (AviationStack). Both are "check" endpoints only - they never mutate the
itinerary themselves. They return a suggestion the frontend shows the traveler, who
then confirms via the existing /api/disrupt or /api/disrupt-weather to actually act on
it, same "recommend, then apply" shape as the recovery-plan flow.

Same fallback philosophy as the LLM explainer: with no API key configured, these return
a clear `configured: False` response instead of crashing, so the app runs identically
without either key - the two checks are pure upside once you add them.
"""
import os

import httpx

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
AVIATIONSTACK_API_KEY = os.environ.get("AVIATIONSTACK_API_KEY")

SEVERE_CONDITIONS = {"thunderstorm", "tornado", "squall"}
MODERATE_CONDITIONS = {"rain", "drizzle", "snow"}
SEVERE_WIND_MS = 15.0  # roughly 54 km/h


def _safe_error(e: Exception, provider: str) -> str:
    """Turns a request failure into a message safe to send to the browser. httpx's own
    error text embeds the full request URL - which carries our API key as a query param -
    so we never pass str(e) through; we use the provider's own error message instead."""
    if isinstance(e, httpx.HTTPStatusError):
        try:
            body = e.response.json()
            err = body.get("error") if isinstance(body, dict) else None
            detail = (err.get("message") if isinstance(err, dict) else None) or (
                body.get("message") if isinstance(body, dict) else None
            )
        except Exception:
            detail = None
        return f"{provider} returned HTTP {e.response.status_code}" + (f": {detail}" if detail else "")
    if isinstance(e, httpx.TimeoutException):
        return f"{provider} request timed out"
    return f"{provider} request failed ({type(e).__name__})"


def check_weather(location: str, date: str) -> dict:
    """Live forecast check via OpenWeatherMap's free 5-day/3-hour forecast endpoint.
    `date` is "YYYY-MM-DD"; only useful within ~5 days of today since that's all the
    free tier forecasts. Returns a `severity_suggestion` of None/"moderate"/"severe"
    mirroring the same severities /api/disrupt-weather accepts.
    """
    if not OPENWEATHER_API_KEY:
        return _check_weather_open_meteo(location, date)

    try:
        resp = httpx.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"q": location, "appid": OPENWEATHER_API_KEY, "units": "metric"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"configured": True, "error": _safe_error(e, "OpenWeatherMap")}

    matches = [entry for entry in data.get("list", []) if entry.get("dt_txt", "").startswith(date)]
    if not matches:
        return {
            "configured": True,
            "found": False,
            "message": f"No forecast data for {date} at {location} (free tier only covers ~5 days ahead).",
        }

    conditions = [m["weather"][0]["main"].lower() for m in matches if m.get("weather")]
    max_wind = max((m.get("wind", {}).get("speed", 0) for m in matches), default=0)

    if any(c in SEVERE_CONDITIONS for c in conditions) or max_wind >= SEVERE_WIND_MS:
        suggestion = "severe"
    elif any(c in MODERATE_CONDITIONS for c in conditions):
        suggestion = "moderate"
    else:
        suggestion = None

    return {
        "configured": True,
        "found": True,
        "location": location,
        "date": date,
        "conditions": sorted(set(conditions)),
        "max_wind_speed_ms": round(max_wind, 1),
        "severity_suggestion": suggestion,
    }


# WMO weather codes (Open-Meteo): 95-99 thunderstorm; 51-67 / 80-82 drizzle-rain; 71-77 / 85-86 snow
_SEVERE_CODES = set(range(95, 100))
_MODERATE_CODES = set(range(51, 68)) | set(range(80, 83)) | set(range(71, 78)) | {85, 86}


def _check_weather_open_meteo(location: str, date: str) -> dict:
    """Keyless fallback: Open-Meteo geocoding + 16-day hourly forecast, same response shape
    as the OpenWeatherMap path so the frontend doesn't care which one ran."""
    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "country_code": "IN"}, timeout=10,
        )
        geo.raise_for_status()
        results = geo.json().get("results") or []
        if not results:
            return {"configured": True, "found": False, "message": f"Could not locate '{location}'."}
        lat, lon = results[0]["latitude"], results[0]["longitude"]
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon, "forecast_days": 16, "timezone": "Asia/Kolkata",
                "hourly": "precipitation,wind_speed_10m,weather_code",
            },
            timeout=10,
        )
        resp.raise_for_status()
        hourly = resp.json()["hourly"]
    except Exception as e:
        return {"configured": True, "error": _safe_error(e, "Open-Meteo")}

    idx = [i for i, t in enumerate(hourly["time"]) if t.startswith(date)]
    if not idx:
        return {
            "configured": True,
            "found": False,
            "message": f"No forecast data for {date} at {location} (forecast covers the next 16 days).",
        }
    codes = {hourly["weather_code"][i] for i in idx if hourly["weather_code"][i] is not None}
    max_wind_ms = max((hourly["wind_speed_10m"][i] or 0) for i in idx) / 3.6
    max_rain = max((hourly["precipitation"][i] or 0) for i in idx)

    if codes & _SEVERE_CODES or max_wind_ms >= SEVERE_WIND_MS or max_rain >= 15:
        suggestion = "severe"
    elif codes & _MODERATE_CODES or max_rain >= 2.5:
        suggestion = "moderate"
    else:
        suggestion = None
    return {
        "configured": True,
        "found": True,
        "provider": "Open-Meteo",
        "location": location,
        "date": date,
        "conditions": sorted(f"wmo_{c}" for c in codes),
        "max_rain_mm_h": round(max_rain, 1),
        "max_wind_speed_ms": round(max_wind_ms, 1),
        "severity_suggestion": suggestion,
    }


def check_flight_status(flight_iata: str) -> dict:
    """Live flight status via AviationStack's free tier (note: free tier is HTTP only,
    not HTTPS - that's an AviationStack limitation, not a bug here). Returns a
    `suggested_action` of "delay"/"cancel"/None the frontend can offer to apply via the
    existing /api/disrupt endpoint.
    """
    if not AVIATIONSTACK_API_KEY:
        return {
            "configured": False,
            "message": "Set AVIATIONSTACK_API_KEY to enable real flight status checks.",
        }

    try:
        resp = httpx.get(
            "http://api.aviationstack.com/v1/flights",
            params={"access_key": AVIATIONSTACK_API_KEY, "flight_iata": flight_iata},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"configured": True, "error": _safe_error(e, "AviationStack")}

    flights = data.get("data") or []
    if not flights:
        return {
            "configured": True,
            "found": False,
            "message": f"No live data for flight {flight_iata}.",
        }

    flight = flights[0]
    departure = flight.get("departure") or {}
    delay_minutes = departure.get("delay") or 0
    status = flight.get("flight_status")

    if status == "cancelled":
        suggested_action = "cancel"
    elif delay_minutes and delay_minutes > 0:
        suggested_action = "delay"
    else:
        suggested_action = None

    return {
        "configured": True,
        "found": True,
        "flight_iata": flight_iata,
        "status": status,
        "delay_minutes": delay_minutes,
        "suggested_action": suggested_action,
    }
