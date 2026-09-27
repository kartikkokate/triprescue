"""Inference against our Nugen domain-aligned TripRescue Advisor model.

The model itself is produced by nugen/align.py (base model -> Nugen alignment on the
TripRescue dataset -> deployed aligned model); this module only calls it. Configure with
NUGEN_API_KEY and NUGEN_MODEL_ID (the aligned model id align.py prints and writes to .env).
"""
import os
import re
import time

import httpx

NUGEN_API_KEY = os.environ.get("NUGEN_API_KEY") or None
NUGEN_MODEL_ID = os.environ.get("NUGEN_MODEL_ID") or None
NUGEN_BASE_URL = os.environ.get("NUGEN_BASE_URL", "https://api.nugen.in")

# reasoning base models (e.g. *-reasoning) can emit their chain of thought inline
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


# After a failure (e.g. the deployed model is cold or the gateway times out) skip Nugen for a
# while, so the next answers come from the fallback tier at once instead of each waiting out
# the timeout first.
COOLDOWN_SECONDS = 300
_down_until = 0.0
last_error: str | None = None


def is_configured() -> bool:
    return bool(NUGEN_API_KEY and NUGEN_MODEL_ID)


def is_cooling_down() -> bool:
    return time.monotonic() < _down_until


def chat(system_prompt: str, user_prompt: str, max_tokens: int = 400, timeout: float = 20) -> str | None:
    """Returns the aligned model's answer, or None on any failure so callers can fall back."""
    global _down_until, last_error
    if not is_configured() or is_cooling_down():
        return None
    try:
        resp = httpx.post(
            f"{NUGEN_BASE_URL}/api/v3/inference/chat/completions",
            headers={"Authorization": f"Bearer {NUGEN_API_KEY}"},
            json={
                "model": NUGEN_MODEL_ID,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "stream": False,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        choices = resp.json().get("choices") or []
        content = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
        text = _THINK_BLOCK.sub("", content).strip()
        last_error = None if text else "empty answer"
        return text or None
    except Exception as e:
        last_error = type(e).__name__ if not isinstance(e, httpx.HTTPStatusError) else f"HTTP {e.response.status_code}"
        _down_until = time.monotonic() + COOLDOWN_SECONDS
        return None
