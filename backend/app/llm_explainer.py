"""Natural-language explanations of disruption impact, recovery plans and traveler rights.

Three tiers, best first:
  1. "nugen-aligned" - our TripRescue Advisor, a Nugen domain-aligned model trained on this
     app's own prompt format and recovery engine outputs (see nugen/ and app.nugen_client)
  2. "gemini"        - general-purpose Gemini Flash-Lite, same prompts
  3. "rule-based"    - app.advisor_knowledge's deterministic expert answers
so the demo never breaks without network/creds. Every tier gets the identical prompt
from app.advisor_prompts.
"""
import os

import httpx

from app import nugen_client
from app.advisor_knowledge import impact_answer, plans_answer, rights_answer, twin_answer
from app.advisor_prompts import SYSTEM_PROMPT, impact_prompt, plans_prompt, rights_prompt, twin_prompt
from app.graph_engine import ItineraryGraph
from app.models import RecoveryPlan, TravelerPreferences

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# Flash-Lite for latency/cost (explanations are 2-4 sentences). The "-latest" aliases track
# Google's current models, so a retired pinned version can't silently knock us onto the
# rule-based fallback. Override via env to pin one.
MODEL_ID = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
# Tried next when the primary model is overloaded (Gemini returns 503/429 or hangs under demand spikes).
BACKUP_MODEL_ID = "gemini-flash-latest"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

def _generate(model: str, system_prompt: str, user_prompt: str, max_tokens: int, timeout: float) -> httpx.Response:
    return httpx.post(
        GEMINI_URL.format(model=model),
        # Key goes in a header, not the URL, so it can't end up in logs or error text.
        headers={"x-goog-api-key": GEMINI_API_KEY},
        json={
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            # Headroom above max_tokens: newer Flash models spend part of the budget thinking.
            "generationConfig": {"maxOutputTokens": max_tokens * 4},
        },
        timeout=timeout,
    )


def _call_gemini(system_prompt: str, user_prompt: str, max_tokens: int = 300) -> str | None:
    if not GEMINI_API_KEY:
        return None
    try:
        # Primary gets a short leash: under load it can hang rather than 503, and a traveler
        # staring at a spinner is worse than a slightly lighter model's answer.
        try:
            resp = _generate(MODEL_ID, system_prompt, user_prompt, max_tokens, timeout=12)
            overloaded = resp.status_code == 429 or resp.status_code >= 500
        except httpx.TransportError:  # timeouts, dropped connections
            overloaded = True
        if overloaded:
            resp = _generate(BACKUP_MODEL_ID, system_prompt, user_prompt, max_tokens, timeout=20)
        resp.raise_for_status()
        candidates = resp.json().get("candidates") or []
        parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        return text or None
    except Exception:
        return None


def _answer(user_prompt: str, fallback: str) -> dict:
    text = nugen_client.chat(SYSTEM_PROMPT, user_prompt)
    if text:
        return {"explanation": text, "source": "llm", "model": "nugen-aligned"}
    text = _call_gemini(SYSTEM_PROMPT, user_prompt)
    if text:
        return {"explanation": text, "source": "llm", "model": "gemini"}
    return {"explanation": fallback, "source": "rule-based", "model": "rule-based"}


def explain_impact(disruption: dict, impact_report: dict, graph: ItineraryGraph) -> dict:
    return _answer(
        impact_prompt(disruption, impact_report, graph),
        impact_answer(disruption, impact_report, graph),
    )


def explain_plans(
    plans: list[RecoveryPlan],
    disruption: dict | None,
    graph: ItineraryGraph | None = None,
    preferences: TravelerPreferences | None = None,
) -> dict:
    return _answer(plans_prompt(plans, disruption, graph, preferences), plans_answer(plans))


def explain_rights(disruption: dict, impact_report: dict, graph: ItineraryGraph) -> dict:
    return _answer(
        rights_prompt(disruption, impact_report, graph),
        rights_answer(disruption, impact_report, graph),
    )


def explain_twin(sim: dict, scenario: dict | None) -> dict:
    return _answer(twin_prompt(sim, scenario), twin_answer(sim, scenario))
