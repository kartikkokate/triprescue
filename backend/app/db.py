"""Supabase client wrapper. Every caller must go through is_configured() first -
without SUPABASE_URL and SUPABASE_KEY set, get_client() returns None and callers fall
back to in-memory storage, exactly like the LLM explainer falls back without an
GEMINI_API_KEY. Nothing else in the app should import the `supabase` package directly.
"""
import os

import httpx

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None

_client = None


def is_configured() -> bool:
    return bool(
        create_client is not None
        and os.environ.get("SUPABASE_URL")
        and os.environ.get("SUPABASE_KEY")
    )


def get_client():
    global _client
    if not is_configured():
        return None
    if _client is None:
        _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _client


def reset_client() -> None:
    global _client
    _client = None


def execute(build):
    """Runs `build(client).execute()`, retrying once on a fresh connection when the
    pooled keep-alive socket turns out to be dead (seen on Windows as httpx.ReadError /
    WinError 10035) - otherwise a transient blip surfaces as a 500 to the traveler."""
    for attempt in (1, 2):
        try:
            return build(_client_for_request()).execute()
        except httpx.TransportError:
            reset_client()
            _user_clients.clear()
            if attempt == 2:
                raise


# --- optional per-account access (Supabase Auth) ----------------------------------------
# The frontend may send the signed-in user's access token. We verify it with Supabase
# (never trust a client-sent user id) and run that request's queries with the token, so
# the trips table's row-level security scopes rows to auth.uid().
import contextvars
import time

_request_token: contextvars.ContextVar[str | None] = contextvars.ContextVar("sb_token", default=None)
_verified: dict[str, tuple[str, float]] = {}  # token -> (user_id, cached_until)
_user_clients: dict[str, object] = {}


def user_from_token(token: str | None) -> str | None:
    """Verified user id for an access token, or None (guest / invalid / no Supabase)."""
    if not token or get_client() is None:
        return None
    hit = _verified.get(token)
    if hit and hit[1] > time.time():
        return hit[0]
    try:
        res = get_client().auth.get_user(token)
        uid = res.user.id if res and res.user else None
    except Exception:
        uid = None
    if uid:
        if len(_verified) > 256:
            _verified.clear()
        _verified[token] = (uid, time.time() + 300)
    return uid


def use_token(token: str | None) -> None:
    """Queries in the current request context run as this user (None = anonymous)."""
    _request_token.set(token)


def _client_for_request():
    token = _request_token.get()
    if not token:
        return get_client()
    c = _user_clients.get(token)
    if c is None:
        if len(_user_clients) > 32:
            _user_clients.clear()
        c = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        c.postgrest.auth(token)
        _user_clients[token] = c
    return c
