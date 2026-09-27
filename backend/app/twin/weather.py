"""Live weather input for the digital twin: Open-Meteo hourly forecast (16 days, no API key)
and Open-Meteo's GloFAS river-discharge flood forecast, per booking location.

Results are cached per rounded coordinate for CACHE_SECONDS, so the continuous twin loop
and interactive what-if runs don't hammer the API.
"""
import time
from datetime import datetime

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
HOURLY_VARS = "precipitation,precipitation_probability,temperature_2m,wind_speed_10m,wind_gusts_10m,weather_code"
CURRENT_VARS = "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,weather_code"
CACHE_SECONDS = 600
HEAVY_RAIN_MM_H = 2.5  # hours at or above this count toward storm duration

_cache: dict[tuple, tuple[float, dict | None]] = {}


def _key(kind: str, lat: float, lon: float) -> tuple:
    return (kind, round(lat, 2), round(lon, 2))


def _cached_get(kind: str, lat: float, lon: float, url: str, params: dict) -> dict | None:
    key = _key(kind, lat, lon)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        resp = httpx.get(url, params={"latitude": lat, "longitude": lon, **params}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        data = None
    _cache[key] = (time.time(), data)
    return data


def fetch_forecast(lat: float, lon: float) -> dict | None:
    return _cached_get(
        "forecast", lat, lon, FORECAST_URL,
        {"hourly": HOURLY_VARS, "current": CURRENT_VARS, "forecast_days": 16, "timezone": "Asia/Kolkata"},
    )


def fetch_flood(lat: float, lon: float) -> dict | None:
    return _cached_get(
        "flood", lat, lon, FLOOD_URL,
        {"daily": "river_discharge,river_discharge_median", "forecast_days": 16},
    )


def flood_index(flood: dict | None, date: str) -> float:
    """0..1 - river discharge relative to its long-run median for that day (1 = 3x median or more)."""
    if not flood or "daily" not in flood:
        return 0.0
    daily = flood["daily"]
    try:
        i = daily["time"].index(date)
    except ValueError:
        return 0.0
    q, median = daily["river_discharge"][i], daily["river_discharge_median"][i]
    if not q or not median:
        return 0.0
    return max(0.0, min(1.0, (q / median - 1.0) / 2.0))


def conditions_at(forecast: dict | None, iso_time: str, window_hours: int = 3) -> dict | None:
    """Worst-case hourly conditions in the window starting at `iso_time`, plus how many
    consecutive heavy-rain hours surround it (storm duration)."""
    if not forecast or "hourly" not in forecast:
        return None
    h = forecast["hourly"]
    target = datetime.fromisoformat(iso_time).strftime("%Y-%m-%dT%H:00")
    try:
        i = h["time"].index(target)
    except ValueError:
        return None
    window = range(i, min(i + window_hours, len(h["time"])))
    # the last forecast days can come back as nulls - that's "no data", not 0 degC / 0 km/h
    if all(h["temperature_2m"][j] is None for j in window):
        return None

    def worst(var: str, default: float = 0.0) -> float:
        vals = [h[var][j] for j in window if h[var][j] is not None]
        return max(vals) if vals else default

    # storm duration: contiguous heavy-rain run touching the window
    start, end = i, i
    while start > 0 and (h["precipitation"][start - 1] or 0) >= HEAVY_RAIN_MM_H:
        start -= 1
    while end + 1 < len(h["time"]) and (h["precipitation"][end + 1] or 0) >= HEAVY_RAIN_MM_H:
        end += 1
    storm_hours = (end - start + 1) if (h["precipitation"][i] or 0) >= HEAVY_RAIN_MM_H else 0

    return {
        "time": target,
        "rain_mm_h": worst("precipitation"),
        # no probability given: assume rain happens if any is forecast
        "precip_prob": worst("precipitation_probability", 100.0 if worst("precipitation") > 0 else 0.0) / 100.0,
        "temp_c": worst("temperature_2m"),
        "wind_kmh": worst("wind_speed_10m"),
        "gust_kmh": worst("wind_gusts_10m"),
        "weather_code": int(worst("weather_code")),
        "storm_hours": storm_hours,
    }


def current_conditions(forecast: dict | None) -> dict | None:
    if not forecast or "current" not in forecast:
        return None
    c = forecast["current"]
    return {
        "time": c.get("time"),
        "temp_c": c.get("temperature_2m"),
        "rain_mm_h": c.get("precipitation"),
        "wind_kmh": c.get("wind_speed_10m"),
        "gust_kmh": c.get("wind_gusts_10m"),
        "weather_code": c.get("weather_code"),
    }
