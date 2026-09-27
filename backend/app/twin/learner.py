"""The digital twin's learned weather -> delay relationship.

Per booking type (flight / transfer / activity) we keep a Bayesian linear regression

    delay_minutes = phi(weather) . beta + noise,      beta ~ N(mu, Sigma)

starting from expert priors and updated in closed form (conjugate normal update) every
time a real observation arrives: a weather-attributed disruption in the live app, a live
flight-status check, or an explicit report via /api/twin/observe. The posterior mean
drives predictions and the posterior covariance is part of the twin's uncertainty.

Cancellation hazards are logistic curves with expert-set coefficients (a cancellation is
too rare an event to learn from a demo's worth of data).
"""
import json
import math
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

STATE_PATH = Path(__file__).parent / "learner_state.json"

FEATURES = ["bias", "rain_mm_h", "wind_10kmh", "heat_over_35c", "flood_index", "storm_6h", "social_index"]

# Expert priors: minutes of delay per unit of each feature
PRIORS = {
    "flight":   {"mu": [0, 1.5, 4.0, 1.0, 20, 20, 15], "noise_sd": 20},
    "transfer": {"mu": [0, 2.5, 1.0, 1.0, 60, 10, 15], "noise_sd": 12},
    "activity": {"mu": [0, 6.0, 6.0, 8.0, 40, 30, 10], "noise_sd": 25},
}


def features(c: dict) -> np.ndarray:
    return np.array([
        1.0,
        c.get("rain_mm_h", 0.0),
        c.get("wind_kmh", 0.0) / 10.0,
        max(0.0, c.get("temp_c", 28.0) - 35.0),
        c.get("flood_index", 0.0),
        c.get("storm_hours", 0.0) / 6.0,
        c.get("social_index", 0.0),
    ])


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def cancel_probability(entity_type: str, c: dict, outdoor: bool = False) -> float:
    rain, wind = c.get("rain_mm_h", 0.0), c.get("wind_kmh", 0.0)
    heat, flood = max(0.0, c.get("temp_c", 28.0) - 38.0), c.get("flood_index", 0.0)
    storm, social = c.get("storm_hours", 0.0) / 6.0, c.get("social_index", 0.0)
    if entity_type == "flight":
        z = -6.5 + 0.05 * rain + 0.06 * max(0.0, wind - 40) + 2.0 * flood + 0.8 * storm + 0.8 * social
    elif entity_type == "transfer":
        z = -7.0 + 0.03 * rain + 4.0 * flood + 0.3 * storm
    elif entity_type == "activity" and outdoor:
        z = -3.5 + 0.12 * rain + 0.08 * max(0.0, wind - 25) + 0.25 * heat + 2.0 * flood + 0.5 * storm
    else:
        return 0.0
    return _sigmoid(z)


class WeatherImpactLearner:
    def __init__(self, path: Path = STATE_PATH, persist: bool = True):
        self.path, self.persist = path, persist
        self._lock = threading.Lock()
        self.reset()
        if persist:
            self._load()

    def reset(self) -> None:
        self.models = {}
        for etype, p in PRIORS.items():
            mu = np.array(p["mu"], dtype=float)
            sd = 0.5 * np.abs(mu) + 1.0  # prior uncertainty: +/-50% of each expert coefficient
            self.models[etype] = {"mu": mu, "cov": np.diag(sd ** 2), "noise_sd": p["noise_sd"], "n": 0}
        self.history: list[dict] = []

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return
        for etype, m in raw.get("models", {}).items():
            if etype in self.models:
                self.models[etype].update(mu=np.array(m["mu"]), cov=np.array(m["cov"]), n=m["n"])
        self.history = raw.get("history", [])

    def _save(self) -> None:
        if not self.persist:
            return
        raw = {
            "models": {k: {"mu": v["mu"].tolist(), "cov": v["cov"].tolist(), "n": v["n"]} for k, v in self.models.items()},
            "history": self.history[-200:],
        }
        self.path.write_text(json.dumps(raw), encoding="utf-8")

    def observe(self, entity_type: str, conditions: dict, delay_minutes: float, source: str) -> dict:
        """Conjugate Bayesian update with one (weather, observed delay) pair."""
        if entity_type not in self.models:
            raise ValueError(f"No weather model for {entity_type}")
        with self._lock:
            m = self.models[entity_type]
            x = features(conditions)
            before = float(x @ m["mu"])
            prec = np.linalg.inv(m["cov"])
            noise_var = m["noise_sd"] ** 2
            new_cov = np.linalg.inv(prec + np.outer(x, x) / noise_var)
            new_mu = new_cov @ (prec @ m["mu"] + x * delay_minutes / noise_var)
            m.update(mu=new_mu, cov=new_cov, n=m["n"] + 1)
            after = float(x @ new_mu)
            record = {
                "at": datetime.now(timezone.utc).isoformat(),
                "entity_type": entity_type,
                "source": source,
                "observed_delay": round(float(delay_minutes), 1),
                "predicted_before": round(before, 1),
                "predicted_after": round(after, 1),
                "conditions": {k: round(float(v), 2) for k, v in conditions.items() if isinstance(v, (int, float))},
            }
            self.history.append(record)
            self._save()
            return record

    def sample_betas(self, entity_type: str, n: int, rng: np.random.Generator) -> np.ndarray:
        m = self.models[entity_type]
        return rng.multivariate_normal(m["mu"], m["cov"], size=n, method="cholesky")

    def expected_delay(self, entity_type: str, conditions: dict) -> float:
        return max(0.0, float(features(conditions) @ self.models[entity_type]["mu"]))

    def contributions(self, entity_type: str, conditions: dict) -> dict:
        m = self.models[entity_type]
        x = features(conditions)
        return {name: round(float(x[i] * m["mu"][i]), 1) for i, name in enumerate(FEATURES) if name != "bias"}

    def summary(self) -> dict:
        return {
            "features": FEATURES,
            "models": {
                k: {
                    "observations": v["n"],
                    "coefficients": [round(float(x), 2) for x in v["mu"]],
                    "coefficient_sd": [round(float(math.sqrt(max(d, 0))), 2) for d in np.diag(v["cov"])],
                    "noise_sd": v["noise_sd"],
                }
                for k, v in self.models.items()
            },
            "recent_observations": self.history[-8:][::-1],
        }


learner = WeatherImpactLearner()
