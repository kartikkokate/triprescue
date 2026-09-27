"""These only exercise the "not configured" fallback path (no OPENWEATHER_API_KEY /
AVIATIONSTACK_API_KEY in this test environment) - a real signup + a live network call
would be required to test the configured path, which is out of scope for an automated
suite. The fallback contract (never crash, always return `configured: False` with a
clear message) is what matters for the rest of the app to depend on safely."""
import app.external_apis as external_apis


def _fake_open_meteo(monkeypatch, rain=20.0, code=95):
    import httpx

    def fake_get(url, params=None, timeout=None):
        req = httpx.Request("GET", url)
        if "geocoding" in url:
            return httpx.Response(200, json={"results": [{"latitude": 15.5, "longitude": 73.8}]}, request=req)
        hours = [f"2026-10-11T{h:02d}:00" for h in range(24)]
        return httpx.Response(200, json={"hourly": {
            "time": hours, "precipitation": [rain] * 24,
            "wind_speed_10m": [20.0] * 24, "weather_code": [code] * 24,
        }}, request=req)

    monkeypatch.setattr(external_apis.httpx, "get", fake_get)


def test_weather_check_without_owm_key_uses_open_meteo(monkeypatch):
    monkeypatch.setattr(external_apis, "OPENWEATHER_API_KEY", None)
    _fake_open_meteo(monkeypatch, rain=20.0, code=95)

    result = external_apis.check_weather("Goa", "2026-10-11")

    assert result["provider"] == "Open-Meteo"
    assert result["found"] is True
    assert result["severity_suggestion"] == "severe"  # thunderstorm code + 20 mm/h


def test_open_meteo_calm_day_suggests_nothing(monkeypatch):
    monkeypatch.setattr(external_apis, "OPENWEATHER_API_KEY", None)
    _fake_open_meteo(monkeypatch, rain=0.0, code=1)
    assert external_apis.check_weather("Goa", "2026-10-11")["severity_suggestion"] is None

def test_flight_status_without_api_key_reports_not_configured(monkeypatch):
    monkeypatch.setattr(external_apis, "AVIATIONSTACK_API_KEY", None)
    result = external_apis.check_flight_status("6E204")
    assert result == {
        "configured": False,
        "message": "Set AVIATIONSTACK_API_KEY to enable real flight status checks.",
    }


def test_weather_check_endpoint_works_without_owm_key(client, monkeypatch):
    monkeypatch.setattr(external_apis, "OPENWEATHER_API_KEY", None)
    _fake_open_meteo(monkeypatch, rain=5.0, code=61)
    res = client.get("/api/weather-check", params={"location": "Goa", "date": "2026-10-11"})
    assert res.status_code == 200
    assert res.json()["severity_suggestion"] == "moderate"

def test_flight_status_endpoint_returns_not_configured(client, monkeypatch):
    monkeypatch.setattr(external_apis, "AVIATIONSTACK_API_KEY", None)
    res = client.get("/api/flight-status", params={"flight_iata": "6E204"})
    assert res.status_code == 200
    assert res.json()["configured"] is False


def test_flight_status_error_never_leaks_api_key(monkeypatch):
    import httpx

    secret = "SECRET-KEY-123"
    monkeypatch.setattr(external_apis, "AVIATIONSTACK_API_KEY", secret)

    def fake_get(url, params=None, timeout=None):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(
            429,
            json={"error": {"code": "usage_limit_reached", "message": "Monthly limit reached."}},
            request=request,
        )

    monkeypatch.setattr(external_apis.httpx, "get", fake_get)
    result = external_apis.check_flight_status("AI101")

    assert secret not in result["error"]
    assert "429" in result["error"]
    assert "Monthly limit reached." in result["error"]
