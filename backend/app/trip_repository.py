"""Persists trips (itinerary + preferences) so they survive a server restart and so a
traveler can have more than one trip saved at once. Backed by Supabase when configured
(SUPABASE_URL / SUPABASE_KEY set - see supabase/schema.sql for the table this expects),
otherwise falls back to an in-memory dict so the app works identically without a database,
same fallback philosophy as the LLM explainer without GEMINI_API_KEY.
"""
import uuid
from datetime import datetime, timezone

from app import db

_memory_trips: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_trip(name: str, itinerary: dict, preferences: dict, user_id: str | None = None) -> dict:
    trip_id = str(uuid.uuid4())
    record = {
        "id": trip_id,
        "name": name,
        "itinerary": itinerary,
        "preferences": preferences,
        "user_id": user_id,
        "updated_at": _now_iso(),
    }

    client = db.get_client()
    if client is not None:
        # upsert on our own uuid keeps the retry idempotent: a retried create never duplicates
        row = {"id": trip_id, "name": name, "itinerary": itinerary, "preferences": preferences}
        if user_id:
            row["user_id"] = user_id
        db.execute(lambda c: c.table("trips").upsert(row))
    else:
        _memory_trips[trip_id] = record

    return record


def save_trip(
    trip_id: str, name: str | None, itinerary: dict, preferences: dict, user_id: str | None = None
) -> None:
    """Upsert - creates the row if trip_id doesn't exist yet, otherwise updates it."""
    client = db.get_client()
    if client is not None:
        payload = {"id": trip_id, "itinerary": itinerary, "preferences": preferences}
        if name is not None:
            payload["name"] = name
        if user_id:
            payload["user_id"] = user_id
        db.execute(lambda c: c.table("trips").upsert(payload))
        return

    existing = _memory_trips.get(trip_id, {})
    _memory_trips[trip_id] = {
        "id": trip_id,
        "name": name if name is not None else existing.get("name", "My Trip"),
        "itinerary": itinerary,
        "preferences": preferences,
        "user_id": user_id if user_id is not None else existing.get("user_id"),
        "updated_at": _now_iso(),
    }


def is_valid_trip_id(value: str) -> bool:
    """Trip ids are UUIDs (the Supabase trips.id column is a uuid - Postgres rejects anything
    else with a 22P02 error, which would surface as a 500 rather than a clean 4xx)."""
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def load_trip(trip_id: str) -> dict | None:
    client = db.get_client()
    if client is not None:
        if not is_valid_trip_id(trip_id):
            return None
        res = db.execute(lambda c: c.table("trips").select("*").eq("id", trip_id).limit(1))
        return res.data[0] if res.data else None

    return _memory_trips.get(trip_id)


def list_trips(user_id: str | None = None) -> list[dict]:
    """Returns summaries only (id, name, updated_at) - not the full itinerary payload,
    to keep the trip-picker list lightweight.

    When user_id is set, returns that account's trips. When None (guest / demo mode),
    returns anonymous trips (user_id IS NULL) so the demo list stays shared and useful.
    """
    client = db.get_client()
    if client is not None:
        def _q(c):
            q = c.table("trips").select("id,name,updated_at,user_id").order("updated_at", desc=True)
            if user_id:
                return q.eq("user_id", user_id)
            return q.is_("user_id", "null")
        res = db.execute(_q)
        return res.data

    rows = list(_memory_trips.values())
    if user_id:
        rows = [t for t in rows if t.get("user_id") == user_id]
    else:
        rows = [t for t in rows if not t.get("user_id")]
    return sorted(
        ({"id": t["id"], "name": t["name"], "updated_at": t["updated_at"]} for t in rows),
        key=lambda t: t["updated_at"],
        reverse=True,
    )


def delete_trip(trip_id: str) -> None:
    client = db.get_client()
    if client is not None:
        if not is_valid_trip_id(trip_id):
            return
        db.execute(lambda c: c.table("trips").delete().eq("id", trip_id))
        return

    _memory_trips.pop(trip_id, None)
