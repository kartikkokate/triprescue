"""Builds the TripRescue domain dataset for Nugen alignment.

Every sample is (prompt the live app would send, expert answer). Prompts come from
app.advisor_prompts; answers come from running the real impact and recovery engines and
app.advisor_knowledge on each scenario, so the targets are correct by construction and
use the same formats the model sees in production.

Outputs (in nugen/data/):
  triprescue_train.jsonl   - alignment training data (one {"question","answer"} per line)
  triprescue_benchmark.json - held-out evaluation set (JSON list), never trained on

Usage:  python -m nugen.build_dataset      (from backend/)
"""
import json
import random
from pathlib import Path

from app.advisor_knowledge import POLICY_QA, impact_answer, plans_answer, rights_answer, twin_answer
from app.advisor_prompts import impact_prompt, plans_prompt, rights_prompt, twin_prompt
from app.impact_engine import apply_weather_event, propagate_disruption
from app.models import TravelerPreferences
from app.recovery_engine import generate_recovery_plans
from app.store import SEED_PATH, _graph_from_raw
from app.twin.learner import WeatherImpactLearner
from app.twin.simulator import apply_scenario, simulate

OUT_DIR = Path(__file__).parent / "data"
TRAIN_PATH = OUT_DIR / "triprescue_train.jsonl"
BENCHMARK_PATH = OUT_DIR / "triprescue_benchmark.json"

DELAYS = [15, 30, 45, 60, 90, 120, 150, 180, 240, 300, 420, 600, 1500]
REASONS = ["unspecified", "operator_cancellation", "technical", "weather", "air traffic congestion", "crew shortage"]
# tighter / looser connection buffers make the same delay break different bookings
BUFFER_SCALES = [0.5, 1.0, 2.0]
PREFERENCE_PROFILES = [
    TravelerPreferences(),
    TravelerPreferences(cost_weight=0.7, time_weight=0.1, convenience_weight=0.1, disruption_weight=0.1),
    TravelerPreferences(cost_weight=0.1, time_weight=0.7, convenience_weight=0.1, disruption_weight=0.1),
    TravelerPreferences(cost_weight=0.1, time_weight=0.1, convenience_weight=0.7, disruption_weight=0.1),
]
TWIN_SCENARIOS = 120
BENCHMARK_FRACTION = 0.15
SEED = 42


def _fresh_graph(buffer_scale: float):
    raw = json.loads(SEED_PATH.read_text())
    for e in raw["edges"]:
        e["buffer_minutes"] = int(e["buffer_minutes"] * buffer_scale)
    return _graph_from_raw(raw)


def _samples_for(disruption: dict, report: dict, graph, prefs: TravelerPreferences) -> list[dict]:
    samples = [
        {"question": impact_prompt(disruption, report, graph), "answer": impact_answer(disruption, report, graph)},
        {"question": rights_prompt(disruption, report, graph), "answer": rights_answer(disruption, report, graph)},
    ]
    plans = generate_recovery_plans(graph, disruption.get("reason"), prefs, disruption, report)
    if plans:
        samples.append({"question": plans_prompt(plans, disruption, graph, prefs), "answer": plans_answer(plans)})
    return samples


def _twin_samples(rng: random.Random) -> list[dict]:
    """Digital-twin briefings over a spread of normal and extreme weather what-ifs, simulated
    offline from the learner's expert priors (no live API calls, reproducible)."""
    learner = WeatherImpactLearner(persist=False)
    out = []
    for i in range(TWIN_SCENARIOS):
        overrides = {
            "rain_mm_h": rng.choice([0, 0, 2, 5, 10, 20, 35, 60, 80]),
            "wind_kmh": rng.choice([8, 15, 30, 50, 80, 110]),
            "temp_c": rng.choice([26, 30, 34, 38, 42, 45]),
            "storm_hours": rng.choice([0, 0, 3, 6, 12, 24]),
            "flood_index": rng.choice([0, 0, 0, 0.3, 0.7, 1.0]),
            "social_index": rng.choice([0, 0, 0.2, 0.5, 1.0]),
        }
        scenario = {
            "overrides": overrides,
            "target_place": rng.choice(["all", "Goa", "Delhi"]),
            "target_date": rng.choice([None, "2026-10-10", "2026-10-11", "2026-10-12"]),
        }
        graph = _fresh_graph(rng.choice(BUFFER_SCALES))
        sim = simulate(graph, apply_scenario(graph, {}, scenario), learner, n=200, seed=i)
        out.append({"question": twin_prompt(sim, scenario), "answer": twin_answer(sim, scenario)})
    return out


def build() -> tuple[list[dict], list[dict]]:
    rng = random.Random(SEED)
    samples: list[dict] = []
    node_ids = [n["id"] for n in json.loads(SEED_PATH.read_text())["nodes"]]

    for scale in BUFFER_SCALES:
        for node_id in node_ids:
            for delay in DELAYS:
                graph = _fresh_graph(scale)
                reason = rng.choice(REASONS)
                report = propagate_disruption(graph, node_id, "delay", delay)
                disruption = {"node_id": node_id, "kind": "delay", "delay_minutes": delay, "reason": reason}
                samples += _samples_for(disruption, report, graph, rng.choice(PREFERENCE_PROFILES))

            graph = _fresh_graph(scale)
            reason = rng.choice(REASONS)
            report = propagate_disruption(graph, node_id, "cancel", 0)
            disruption = {"node_id": node_id, "kind": "cancel", "delay_minutes": 0, "reason": reason}
            samples += _samples_for(disruption, report, graph, rng.choice(PREFERENCE_PROFILES))

        for date in ["2026-10-10", "2026-10-11", "2026-10-12"]:
            for severity in ["moderate", "severe"]:
                graph = _fresh_graph(scale)
                result = apply_weather_event(graph, date, severity)
                disruption = {
                    "node_id": None, "kind": "weather", "date": date, "severity": severity,
                    "reason": f"weather ({severity}) on {date}",
                }
                samples += _samples_for(disruption, result["affected_nodes"], graph, rng.choice(PREFERENCE_PROFILES))

    samples += _twin_samples(rng)

    # identical prompts can recur across buffer scales when buffers don't matter - keep one
    unique = list({s["question"]: s for s in samples}.values())
    rng.shuffle(unique)

    policy = [{"question": q, "answer": a} for q, a in POLICY_QA]
    rng.shuffle(policy)

    n_bench = int(len(unique) * BENCHMARK_FRACTION)
    n_policy_bench = max(3, int(len(policy) * BENCHMARK_FRACTION))
    benchmark = unique[:n_bench] + policy[:n_policy_bench]
    train = unique[n_bench:] + policy[n_policy_bench:]
    rng.shuffle(train)
    return train, benchmark


def main():
    train, benchmark = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with TRAIN_PATH.open("w", encoding="utf-8") as f:
        for s in train:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    BENCHMARK_PATH.write_text(json.dumps(benchmark, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"train: {len(train)} samples -> {TRAIN_PATH}")
    print(f"benchmark: {len(benchmark)} samples -> {BENCHMARK_PATH}")


if __name__ == "__main__":
    main()
