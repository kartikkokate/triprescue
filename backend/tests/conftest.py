import sys
from pathlib import Path

# make `app` importable regardless of how/where pytest is invoked from
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.store import AppState, state as global_state
from app.models import TravelerPreferences
from app import trip_repository


@pytest.fixture(autouse=True)
def _no_real_external_services(monkeypatch):
    """backend/.env holds real keys (Supabase, Gemini, Nugen, ...) that app.main loads on
    import. Tests must never write to the real database or spend API quota, so every
    integration is forced into its offline fallback; tests that exercise an integration
    opt back in by monkeypatching a fake transport."""
    from app import db, external_apis, llm_explainer, nugen_client

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("MONITOR_SCHEDULER", "off")  # no background provider pass on trip switch
    monkeypatch.setattr(db, "_client", None)
    monkeypatch.setattr(llm_explainer, "GEMINI_API_KEY", None)
    monkeypatch.setattr(nugen_client, "NUGEN_API_KEY", None)
    monkeypatch.setattr(nugen_client, "NUGEN_MODEL_ID", None)
    monkeypatch.setattr(external_apis, "OPENWEATHER_API_KEY", None)
    monkeypatch.setattr(external_apis, "AVIATIONSTACK_API_KEY", None)

    # digital twin: no live weather/social fetches, and a fresh in-memory learner per test
    from app.twin import service, social, weather
    from app.twin.learner import learner

    monkeypatch.setattr(weather, "fetch_forecast", lambda lat, lon: None)
    monkeypatch.setattr(weather, "fetch_flood", lambda lat, lon: None)
    monkeypatch.setattr(
        social, "fetch_signals",
        lambda place: {"place": place, "live": False, "window_hours": 72, "social_index": 0.0,
                       "category_counts": {}, "items": []},
    )
    monkeypatch.setattr(learner, "persist", False)
    learner.reset()

    from app.monitor.service import monitor

    monkeypatch.setattr(monitor, "persist", False)
    monitor.reset()
    service.twin.snapshot = None
    service.twin.history = []


@pytest.fixture(autouse=True)
def _isolate_global_state():
    """`app.store.state` (and trip_repository's in-memory fallback store) are
    module-level singletons the whole app shares - reset them before and after every
    test so nothing leaks between tests (a disruption, a preference change, a saved
    trip, a live-monitor tick) regardless of test order or Supabase configuration."""
    global_state.load_demo()
    global_state.preferences = TravelerPreferences()
    trip_repository._memory_trips.clear()
    yield
    global_state.load_demo()
    global_state.preferences = TravelerPreferences()
    trip_repository._memory_trips.clear()


@pytest.fixture
def fresh_state() -> AppState:
    """An isolated AppState for tests that exercise the engine modules directly
    (not through the API), so they don't need to touch the shared singleton at all."""
    return AppState()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    # deliberately NOT using `with TestClient(app) as c:` - that triggers FastAPI's
    # startup event, which spawns the live-monitor background task. None of the
    # HTTP-level tests need it running, and avoiding it keeps tests fast and quiet.
    return TestClient(app)
